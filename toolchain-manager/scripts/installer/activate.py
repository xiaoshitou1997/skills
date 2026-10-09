"""Session-scoped activation snippet generator for sh / PowerShell / cmd.

Hard rule: this module only EMITS commands meant for the current shell session.
It NEVER writes ~/.bashrc, ~/.zshrc, $PROFILE, Windows registry, AutoRun keys,
and NEVER uses `setx` (which persists to the registry). The only file it writes
is an `activate.cmd` artifact, because cmd.exe cannot eval stdout — that file is
invoked via `call` in the current session and is never auto-loaded at startup.
"""
from __future__ import annotations
import json
import os
import re
import sys
from pathlib import Path

from download import os_name, sdks_root


def selection_path():
    return sdks_root() / 'selection.json'


def load_selection():
    p = selection_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}


def save_selection(sel, merge=True):
    p = selection_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    if merge:
        cur = load_selection()
        cur.update(sel)
        payload = cur
    else:
        payload = sel
    p.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    return payload


def detect_shell():
    """Best-effort detection of the parent shell we are emitting for.

    opencode's bash tool is always bash-family even on Windows (Git Bash), so
    the default is 'sh'. 'ps1'/'cmd' are only returned when clearly indicated
    by the environment.
    """
    shell = (os.environ.get('SHELL') or '').lower()
    if 'bash' in shell or 'zsh' in shell:
        return 'sh'
    if sys.platform.startswith('win'):
        # PowerShell injects PSModulePath and (usually) a PSModulePath env var
        if os.environ.get('PSModulePath') and not os.environ.get('MSYSTEM'):
            return 'ps1'
        return 'sh'  # default opencode behavior is Git Bash on Windows
    return 'sh'


# --------------------------------------------------------------------------
# Path normalization per shell
def _to_win(p):
    return str(p).replace('/', '\\')


def _to_msys(p):
    """C:\\Users\\x -> /c/Users/x (for Git Bash on Windows)."""
    s = str(p)
    m = re.match(r'^([A-Za-z]):[\\/](.*)$', s)
    if m:
        return f"/{m.group(1).lower()}/{m.group(2).replace(chr(92), '/')}"
    return s.replace('\\', '/')


def _bin_for(tool, entry):
    """Bin directory to prepend to PATH for the tool."""
    if tool == 'node' and os_name() == 'windows':
        # node.exe lives at the archive root on Windows
        return entry['path']
    return os.path.join(entry['path'], 'bin')


# --------------------------------------------------------------------------
# Emitters
def emit_sh(sel):
    win = os_name() == 'windows'
    lines = ['# build-toolchain-installer: session activation (bash/zsh)']
    parts = []
    if 'jdk' in sel:
        p = _to_msys(sel['jdk']['path']) if win else sel['jdk']['path']
        parts.append(f'export JAVA_HOME="{p}"')
        parts.append('export PATH="$JAVA_HOME/bin:$PATH"')
    if 'maven' in sel:
        p = _to_msys(sel['maven']['path']) if win else sel['maven']['path']
        parts.append(f'export M2_HOME="{p}"')
        parts.append('export PATH="$M2_HOME/bin:$PATH"')
    if 'gradle' in sel:
        p = _to_msys(sel['gradle']['path']) if win else sel['gradle']['path']
        parts.append(f'export GRADLE_HOME="{p}"')
        parts.append('export PATH="$GRADLE_HOME/bin:$PATH"')
    if 'node' in sel:
        bd = _bin_for('node', sel['node'])
        bd = _to_msys(bd) if win else bd
        parts.append(f'export PATH="{bd}:$PATH"')
    lines.extend(parts)
    return '\n'.join(lines) + '\n'


def emit_ps1(sel):
    lines = ['# build-toolchain-installer: session activation (PowerShell)']
    parts = []
    if 'jdk' in sel:
        p = _to_win(sel['jdk']['path'])
        parts.append(f'$env:JAVA_HOME = "{p}"')
        parts.append(f'$env:PATH = "$env:JAVA_HOME\\bin;$env:PATH"')
    if 'maven' in sel:
        p = _to_win(sel['maven']['path'])
        parts.append(f'$env:M2_HOME = "{p}"')
        parts.append(f'$env:PATH = "$env:M2_HOME\\bin;$env:PATH"')
    if 'gradle' in sel:
        p = _to_win(sel['gradle']['path'])
        parts.append(f'$env:GRADLE_HOME = "{p}"')
        parts.append(f'$env:PATH = "$env:GRADLE_HOME\\bin;$env:PATH"')
    if 'node' in sel:
        p = _to_win(_bin_for('node', sel['node']))
        parts.append(f'$env:PATH = "{p};$env:PATH"')
    lines.extend(parts)
    return '\n'.join(lines) + '\n'


def emit_cmd(sel):
    lines = ['@echo off', 'REM build-toolchain-installer: session activation (cmd)']
    parts = []
    if 'jdk' in sel:
        p = _to_win(sel['jdk']['path'])
        parts.append(f'set "JAVA_HOME={p}"')
        parts.append('set "PATH=%JAVA_HOME%\\bin;%PATH%"')
    if 'maven' in sel:
        p = _to_win(sel['maven']['path'])
        parts.append(f'set "M2_HOME={p}"')
        parts.append('set "PATH=%M2_HOME%\\bin;%PATH%"')
    if 'gradle' in sel:
        p = _to_win(sel['gradle']['path'])
        parts.append(f'set "GRADLE_HOME={p}"')
        parts.append('set "PATH=%GRADLE_HOME%\\bin;%PATH%"')
    if 'node' in sel:
        p = _to_win(_bin_for('node', sel['node']))
        parts.append(f'set "PATH={p};%PATH%"')
    lines.extend(parts)
    lines.append('')  # trailing newline
    return '\n'.join(lines) + '\n'


def emit(sel, fmt):
    fmt = (fmt or 'sh').lower()
    if fmt in ('sh', 'bash', 'zsh'):
        return emit_sh(sel)
    if fmt in ('ps1', 'powershell', 'pwsh'):
        return emit_ps1(sel)
    if fmt in ('cmd', 'cmd.exe', 'bat'):
        return emit_cmd(sel)
    raise ValueError(f"unknown shell format: {fmt}")


def write_cmd_file(sel):
    """Materialize activate.cmd so the user can `call` it in cmd.exe."""
    out = emit_cmd(sel)
    p = sdks_root() / 'activate.cmd'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(out, encoding='utf-8')
    return p
