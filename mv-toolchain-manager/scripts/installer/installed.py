"""Detect installed tool versions under $HOME/.mv/toolchain-manager and on PATH."""
from __future__ import annotations
import os
import re
import shutil
import subprocess
from pathlib import Path

import versions
from download import install_root


def list_installed():
    """Return cache entries for every manager-owned portable tool."""
    root = install_root()
    out = {
        'node': [], 'jdk': [], 'maven': [], 'gradle': [], 'crane': [],
        'python': [], 'uv': [], 'pnpm': [], 'yarn': [],
    }

    node_dir = root / 'node'
    if node_dir.exists():
        for p in sorted(node_dir.iterdir()):
            if p.is_dir():
                out['node'].append({'version': p.name.lstrip('vV'), 'path': str(p)})

    jdk_dir = root / 'jdk'
    if jdk_dir.exists():
        for p in sorted(jdk_dir.iterdir()):
            if p.is_dir():
                feat = _extract_feature(p.name)
                entry = {'version': p.name, 'path': str(p)}
                if feat:
                    entry['feature'] = feat
                out['jdk'].append(entry)

    maven_dir = root / 'maven'
    if maven_dir.exists():
        for p in sorted(maven_dir.iterdir()):
            if p.is_dir():
                v = p.name.replace('apache-maven-', '')
                out['maven'].append({'version': v, 'path': str(p)})

    gradle_dir = root / 'gradle'
    if gradle_dir.exists():
        for p in sorted(gradle_dir.iterdir()):
            if p.is_dir():
                v = p.name.replace('gradle-', '')
                out['gradle'].append({'version': v, 'path': str(p)})

    crane_dir = root / 'crane'
    if crane_dir.exists():
        for p in sorted(crane_dir.iterdir()):
            if p.is_dir():
                out['crane'].append({'version': p.name.lstrip('vV'), 'path': str(p)})

    python_dir = root / 'python'
    if python_dir.exists():
        for p in sorted(python_dir.iterdir()):
            if p.is_dir():
                out['python'].append({'version': p.name.lstrip('vV'), 'path': str(p)})

    for tool in ('uv', 'pnpm', 'yarn'):
        tool_dir = root / tool
        if not tool_dir.exists():
            continue
        for p in sorted(tool_dir.iterdir()):
            if p.is_dir():
                out[tool].append({'version': p.name.lstrip('vV'), 'path': str(p)})

    return out


def _extract_feature(name):
    """temurin-17 / temurin17 / jdk-17.0.9 -> '17'."""
    m = re.search(r'(\d+)', name)
    return m.group(1) if m else None


def find_matching(tool, requirement, installed=None):
    """Find an installed entry satisfying a requirement.

    requirement: dict {'constraint': ...} or a raw string.
    Node -> npm constraint match; JDK -> feature major match;
    maven/gradle/crane/python -> exact or compatible.
    """
    installed = installed if installed is not None else list_installed()
    constraint = _constraint_of(requirement)

    if tool == 'node':
        c = versions.parse_constraint(constraint)
        for entry in installed['node']:
            if c.matches(entry['version']):
                return entry
        return None

    if tool == 'jdk':
        feat = _major(constraint)
        if not feat:
            return None
        for entry in installed['jdk']:
            if entry.get('feature') == feat:
                return entry
        return None

    # maven / gradle / crane / python / uv / pnpm / yarn: exact or compatible
    for entry in installed[tool]:
        if entry['version'] == constraint:
            return entry
    # fall back to major-line match (e.g. requirement 3.9, installed 3.9.6)
    if constraint and re.match(r'^\d+\.\d+$', constraint):
        for entry in installed[tool]:
            if entry['version'].startswith(constraint + '.'):
                return entry
    return None


def system_version(tool):
    """Probe a tool already on PATH. Returns version string or None."""
    if tool == 'python':
        # Python 3 may be exposed as python3, python, or the Windows launcher.
        for cmd in (['python3', '--version'], ['python', '--version'],
                    ['py', '-3', '--version']):
            if not shutil.which(cmd[0]):
                continue
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=15, shell=False)
            except Exception:
                continue
            v = _parse_python_version((proc.stdout or '') + (proc.stderr or ''))
            if v:
                return v
        return None
    cmds = {
        'node': (['node', '--version'], lambda s: s.strip().lstrip('vV')),
        'jdk': (['java', '-version'], _parse_java_version),
        'maven': (['mvn', '--version'], _parse_mvn_version),
        'gradle': (['gradle', '--version'], _parse_gradle_version),
        'crane': (['crane', 'version'], _parse_crane_version),
        'npm': (['npm', '--version'], _parse_plain_version),
        'pnpm': (['pnpm', '--version'], _parse_plain_version),
        'yarn': (['yarn', '--version'], _parse_plain_version),
        'uv': (['uv', '--version'], _parse_uv_version),
    }
    if tool not in cmds:
        return None
    exe = shutil.which(cmds[tool][0][0])
    if not exe:
        return None
    try:
        proc = subprocess.run(
            cmds[tool][0],
            capture_output=True,
            text=True,
            timeout=15,
            shell=False,
        )
        out = (proc.stderr or '') + (proc.stdout or '')
        return cmds[tool][1](out)
    except Exception:
        return None


def _constraint_of(requirement):
    if isinstance(requirement, dict):
        return str(requirement.get('constraint', '') or '')
    return str(requirement or '')


def _major(v):
    m = re.search(r'(\d+)', str(v))
    return m.group(1) if m else None


def _parse_java_version(text):
    # 'openjdk version "17.0.9" 2023-10-17'  /  'version "1.8.0_382"'
    m = re.search(r'version\s+"([^"]+)"', text)
    if not m:
        return None
    v = m.group(1)
    # normalize 1.8 -> 8
    if v.startswith('1.'):
        parts = v.split('.')
        return parts[1] if len(parts) > 1 else v
    return v.split('_')[0]


def _parse_mvn_version(text):
    # 'Apache Maven 3.9.6 (bc78a8f158aa...)' -> 3.9.6
    m = re.search(r'Apache Maven\s+([\d.]+)', text)
    return m.group(1) if m else None


def _parse_gradle_version(text):
    # 'Gradle 8.5' -> 8.5
    m = re.search(r'Gradle\s+([\d.]+)', text)
    return m.group(1) if m else None


def _parse_crane_version(text):
    # '0.22.1' -> 0.22.1
    m = re.search(r'(\d+\.\d+\.\d+)', text)
    return m.group(1) if m else None


def _parse_python_version(text):
    # 'Python 3.12.15' -> 3.12.15
    m = re.search(r'Python\s+(\d+\.\d+\.\d+)', text)
    return m.group(1) if m else None


def _parse_plain_version(text):
    m = re.search(r'\b(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)\b', text)
    return m.group(1) if m else None


def _parse_uv_version(text):
    # 'uv 0.5.12 (abcdef)' -> 0.5.12
    m = re.search(r'\buv\s+(\d+\.\d+\.\d+)\b', text, re.I)
    return m.group(1) if m else _parse_plain_version(text)
