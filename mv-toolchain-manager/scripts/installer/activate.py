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

# 直接执行本模块(而非经 runtime_cli)时,同目录兄弟模块不可导入;补上脚本目录。
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from download import install_root, os_name


def selection_path():
    return install_root() / 'selection.json'


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
    if tool == 'uv':
        # uv ships as a bare executable at the archive root.
        return entry['path']
    if tool in ('pnpm', 'yarn'):
        # Archive paths can be emitted for a shell other than the current host
        # (e.g. Git Bash on Windows), so keep this intermediate path POSIX-like.
        return str(entry['path']).rstrip('/\\') + '/bin'
    if tool in ('node', 'python') and os_name() == 'windows':
        # node.exe / python.exe live at the archive root on Windows
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
    if 'python' in sel:
        bd = _bin_for('python', sel['python'])
        bd = _to_msys(bd) if win else bd
        parts.append(f'export PATH="{bd}:$PATH"')
    for tool in ('uv', 'pnpm', 'yarn'):
        if tool in sel:
            bd = _bin_for(tool, sel[tool])
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
    if 'python' in sel:
        p = _to_win(_bin_for('python', sel['python']))
        parts.append(f'$env:PATH = "{p};$env:PATH"')
    for tool in ('uv', 'pnpm', 'yarn'):
        if tool in sel:
            p = _to_win(_bin_for(tool, sel[tool]))
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
    if 'python' in sel:
        p = _to_win(_bin_for('python', sel['python']))
        parts.append(f'set "PATH={p};%PATH%"')
    for tool in ('uv', 'pnpm', 'yarn'):
        if tool in sel:
            p = _to_win(_bin_for(tool, sel[tool]))
            parts.append(f'set "PATH={p};%PATH%"')
    lines.extend(parts)
    lines.append('')  # trailing newline
    return '\n'.join(lines) + '\n'


# 双引号内会被 shell 展开或截断的字符;路径含这些字符时宁可拒绝也不生成错误片段。
_UNSAFE_IN_SNIPPET = re.compile(r'["`$]')


def _guard_paths(sel, is_cmd=False):
    for tool, entry in sel.items():
        p = str(entry.get('path', '')) if isinstance(entry, dict) else str(entry)
        if _UNSAFE_IN_SNIPPET.search(p) or (is_cmd and '%' in p):
            raise ValueError(
                f'{tool} path contains characters unsafe for activation snippets: {p!r}')


def emit(sel, fmt):
    fmt = (fmt or 'sh').lower()
    if fmt in ('sh', 'bash', 'zsh'):
        _guard_paths(sel)
        return emit_sh(sel)
    if fmt in ('ps1', 'powershell', 'pwsh'):
        _guard_paths(sel)
        return emit_ps1(sel)
    if fmt in ('cmd', 'cmd.exe', 'bat'):
        _guard_paths(sel, is_cmd=True)
        return emit_cmd(sel)
    raise ValueError(f"unknown shell format: {fmt}")


def write_cmd_file(sel):
    """Materialize activate.cmd so the user can `call` it in cmd.exe."""
    out = emit_cmd(sel)
    p = install_root() / 'activate.cmd'
    p.parent.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt':
        # cmd.exe 按 ANSI 代码页解析批处理;UTF-8 写出的非 ASCII 路径(如中文用户名)会乱码。
        p.write_bytes(out.encode('mbcs', errors='strict'))
    else:
        p.write_text(out, encoding='utf-8')
    return p
