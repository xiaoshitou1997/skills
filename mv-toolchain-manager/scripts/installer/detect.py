"""Detect required tool versions from project files.

Precedence (highest first) per tool. Returns dicts of the form
{'source': <file>, 'constraint': <version-string-or-range>}.
"""
from __future__ import annotations
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path


def detect_all(project):
    project = Path(project)
    return {
        'node': detect_node(project),
        'jdk': detect_jdk(project),
        'maven': detect_maven(project),
        'gradle': detect_gradle(project),
        'python': detect_python(project),
        'uv': detect_uv(project),
        'package_manager': detect_package_manager(project),
    }


# --------------------------------------------------------------------------
# Node.js
def detect_node(project):
    project = Path(project)
    for name in ('.nvmrc', '.node-version'):
        p = project / name
        if p.exists():
            text = p.read_text(encoding='utf-8', errors='ignore').strip()
            if text:
                tok = text.split()[0].lstrip('vV')
                if tok:
                    return {'source': name, 'constraint': tok}
    pkg = project / 'package.json'
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding='utf-8'))
            engines = data.get('engines') or {}
            node = engines.get('node')
            if node:
                return {'source': 'package.json#engines.node', 'constraint': node}
        except Exception:
            pass
    tv = _tool_versions(project)
    if tv and 'nodejs' in tv:
        return {'source': '.tool-versions', 'constraint': tv['nodejs'].lstrip('vV')}
    mise = _mise_tools(project)
    if 'node' in mise:
        return {'source': '.mise.toml', 'constraint': mise['node'].lstrip('vV')}
    return None


# --------------------------------------------------------------------------
# JDK
def detect_jdk(project):
    project = Path(project)
    jv = project / '.java-version'
    if jv.exists():
        text = jv.read_text(encoding='utf-8', errors='ignore').strip()
        if text:  # 空文件守卫,与 detect_node 同口径
            return {'source': '.java-version', 'constraint': _major(text.split()[0])}
    sdk = project / '.sdkmanrc'
    if sdk.exists():
        for line in sdk.read_text(encoding='utf-8', errors='ignore').splitlines():
            line = line.strip()
            if line.lower().startswith('java='):
                val = line.split('=', 1)[1].strip()
                m = re.match(r'(\d+)', val)
                if m:
                    return {'source': '.sdkmanrc', 'constraint': m.group(1)}
    pom = project / 'pom.xml'
    if pom.exists():
        v = _parse_pom_java(pom)
        if v:
            return {'source': 'pom.xml', 'constraint': v}
    for name in ('build.gradle', 'build.gradle.kts'):
        g = project / name
        if g.exists():
            v = _parse_gradle_java(g)
            if v:
                return {'source': name, 'constraint': v}
    tv = _tool_versions(project)
    if tv and 'java' in tv:
        m = re.search(r'(\d+)', tv['java'])
        if m:
            return {'source': '.tool-versions', 'constraint': m.group(1)}
    mise = _mise_tools(project)
    if 'java' in mise:
        m = re.search(r'(\d+)', mise['java'])
        if m:
            return {'source': '.mise.toml', 'constraint': m.group(1)}
    return None


# --------------------------------------------------------------------------
# Maven
def detect_maven(project):
    project = Path(project)
    wrap = project / '.mvn' / 'wrapper' / 'maven-wrapper.properties'
    if wrap.exists():
        for line in wrap.read_text(encoding='utf-8', errors='ignore').splitlines():
            m = re.search(r'apache-maven-([\d.]+)', line)
            if m:
                return {
                    'source': 'maven-wrapper.properties',
                    'constraint': m.group(1),
                    'project_managed': True,
                }
    pom = project / 'pom.xml'
    if pom.exists():
        v = _parse_pom_maven(pom)
        if v:
            return {'source': 'pom.xml#prerequisites', 'constraint': v}
    return None


# --------------------------------------------------------------------------
# Gradle
def detect_gradle(project):
    project = Path(project)
    wrap = project / 'gradle' / 'wrapper' / 'gradle-wrapper.properties'
    if wrap.exists():
        for line in wrap.read_text(encoding='utf-8', errors='ignore').splitlines():
            m = re.search(r'gradle-([\d.]+)-bin', line)
            if m:
                return {
                    'source': 'gradle-wrapper.properties',
                    'constraint': m.group(1),
                    'project_managed': True,
                }
    return None


# --------------------------------------------------------------------------
# Python / uv
def detect_python(project):
    project = Path(project)
    p = project / '.python-version'
    if p.exists():
        text = p.read_text(encoding='utf-8', errors='ignore').strip()
        if text:
            return {'source': '.python-version', 'constraint': text.split()[0].lstrip('vV')}
    tv = _tool_versions(project)
    if tv and 'python' in tv:
        return {'source': '.tool-versions', 'constraint': tv['python'].lstrip('vV')}
    mise = _mise_tools(project)
    if 'python' in mise:
        return {'source': '.mise.toml', 'constraint': mise['python'].lstrip('vV')}
    required = _pyproject_value(project / 'pyproject.toml', 'requires-python')
    if required:
        return {'source': 'pyproject.toml#project.requires-python', 'constraint': required}
    return None


def detect_uv(project):
    project = Path(project)
    tv = _tool_versions(project)
    if tv and 'uv' in tv:
        return {'source': '.tool-versions', 'constraint': tv['uv'].lstrip('vV')}
    mise = _mise_tools(project)
    if 'uv' in mise:
        return {'source': '.mise.toml', 'constraint': mise['uv'].lstrip('vV')}
    pyproject = project / 'pyproject.toml'
    if pyproject.exists() and re.search(
            r'^\s*\[tool\.uv\]',
            pyproject.read_text(encoding='utf-8', errors='ignore'), re.M):
        return {'source': 'pyproject.toml#tool.uv', 'constraint': 'latest'}
    if (project / 'uv.lock').exists():
        return {'source': 'uv.lock', 'constraint': 'latest'}
    return None


# --------------------------------------------------------------------------
# Node package manager
def detect_package_manager(project):
    project = Path(project)
    # A checked-in Yarn distribution is executable project state. It wins over
    # packageManager so that `ensure --project` never replaces a repository's
    # selected Yarn release with a cache-managed copy.
    yarn_path = _project_yarn_path(project)
    if yarn_path:
        return {
            'source': '.yarnrc.yml/yarnPath',
            'tool': 'yarn',
            'constraint': '',
            'project_managed': True,
            'path': str(yarn_path),
        }

    package = project / 'package.json'
    if package.exists():
        try:
            value = (json.loads(package.read_text(encoding='utf-8'))
                     .get('packageManager'))
        except Exception:
            value = None
        parsed = _parse_package_manager(value)
        if parsed:
            parsed['source'] = 'package.json#packageManager'
            return parsed

    if (project / 'pnpm-lock.yaml').exists():
        return {'source': 'pnpm-lock.yaml', 'tool': 'pnpm', 'constraint': 'latest'}
    if (project / 'package-lock.json').exists():
        return {'source': 'package-lock.json', 'tool': 'npm', 'constraint': ''}
    if (project / 'yarn.lock').exists():
        return {
            'source': 'yarn.lock',
            'tool': 'yarn',
            'constraint': '',
            'error': 'yarn.lock alone does not identify Yarn Classic or modern Yarn; add packageManager or commit yarnPath',
        }
    return None


# --------------------------------------------------------------------------
# helpers
def _tool_versions(project):
    p = Path(project) / '.tool-versions'
    out = {}
    if p.exists():
        for line in p.read_text(encoding='utf-8', errors='ignore').splitlines():
            parts = line.split()
            if len(parts) >= 2:
                out[parts[0]] = parts[1]
    return out


def _mise_tools(project):
    """Read simple `[tools] name = "version"` declarations without tomllib."""
    p = Path(project) / '.mise.toml'
    if not p.exists():
        return {}
    section = False
    out = {}
    for raw in p.read_text(encoding='utf-8', errors='ignore').splitlines():
        line = raw.split('#', 1)[0].strip()
        if line.startswith('[') and line.endswith(']'):
            section = line == '[tools]'
            continue
        if not section:
            continue
        m = re.match(r'([A-Za-z0-9_.-]+)\s*=\s*["\']([^"\']+)["\']', line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def _pyproject_value(path, key):
    """Read a quoted `[project]` scalar without requiring Python 3.11 tomllib."""
    if not path.exists():
        return None
    in_project = False
    for raw in path.read_text(encoding='utf-8', errors='ignore').splitlines():
        line = raw.split('#', 1)[0].strip()
        if line.startswith('[') and line.endswith(']'):
            in_project = line == '[project]'
            continue
        if in_project:
            m = re.match(rf'{re.escape(key)}\s*=\s*["\']([^"\']+)["\']', line)
            if m:
                return m.group(1)
    return None


def _parse_package_manager(value):
    if not isinstance(value, str):
        return None
    m = re.fullmatch(r'\s*(npm|pnpm|yarn)@([^\s]+)\s*', value)
    if not m:
        return None
    return {'tool': m.group(1), 'constraint': m.group(2).lstrip('vV')}


def _project_yarn_path(project):
    config = Path(project) / '.yarnrc.yml'
    if config.exists():
        for raw in config.read_text(encoding='utf-8', errors='ignore').splitlines():
            m = re.match(r'\s*yarnPath\s*:\s*["\']?([^"\'#\s]+)', raw)
            if not m:
                continue
            path = (Path(project) / m.group(1)).resolve()
            root = Path(project).resolve()
            if root == path or root in path.parents:
                return path
    releases = Path(project) / '.yarn' / 'releases'
    if releases.is_dir():
        candidates = sorted(releases.glob('yarn-*.cjs'))
        if len(candidates) == 1:
            return candidates[0]
    return None


def _major(v):
    m = re.search(r'(\d+)', str(v))
    return m.group(1) if m else str(v)


def _parse_pom_java(pom):
    try:
        tree = ET.parse(pom)
        root = tree.getroot()
        ns = ''
        if root.tag.startswith('{'):
            ns = root.tag[1:].split('}')[0]

        def find(tag):
            if ns:
                el = root.find(f'.//{{{ns}}}{tag}')
            else:
                el = root.find(f'.//{tag}')
            return el.text.strip() if (el is not None and el.text) else None

        for tag in (
            'maven.compiler.release',
            'maven.compiler.source',
            'maven.compiler.target',
            'java.version',
        ):
            v = find(tag)
            if v:
                parsed = _normalize_java(v)
                if parsed:
                    return parsed
    except Exception:
        pass
    return None


def _parse_pom_maven(pom):
    try:
        tree = ET.parse(pom)
        root = tree.getroot()
        ns = ''
        if root.tag.startswith('{'):
            ns = root.tag[1:].split('}')[0]
        path = f'.//{{{ns}}}prerequisites/{{{ns}}}maven' if ns else './/prerequisites/maven'
        el = root.find(path)
        if el is not None and el.text:
            return el.text.strip()
    except Exception:
        pass
    return None


def _parse_gradle_java(g):
    try:
        text = g.read_text(encoding='utf-8', errors='ignore')
        patterns = (
            r'languageVersion\s*=\s*JavaLanguageVersion\.of\(\s*(\d+)\s*\)',
            r'sourceCompatibility\s*=\s*[\'\"]?(?:JavaVersion\.VERSION_)?(\d+(?:[._]\d+)?)',
            r'targetCompatibility\s*=\s*[\'\"]?(?:JavaVersion\.VERSION_)?(\d+(?:[._]\d+)?)',
        )
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                parsed = _normalize_java(m.group(1))
                if parsed:
                    return parsed
    except Exception:
        pass
    return None


def _normalize_java(v):
    """Normalize Java version strings to a feature major version.

    Handles: '17' -> '17', '1.8' -> '8', '1_8' -> '8', '11' -> '11'.
    Returns the major version string or None if no digit found.
    """
    if v is None:
        return None
    s = str(v).strip().replace('_', '.')
    m = re.match(r'(\d+)(?:\.(\d+))?', s)
    if not m:
        return None
    major = m.group(1)
    minor = m.group(2)
    if major == '1' and minor:
        return minor  # legacy 1.x -> x
    return major
