"""Official source URL builders + latest-version resolvers. Stdlib only.

Sources (official only):
  - Node.js: nodejs.org/dist
  - JDK (Temurin): api.adoptium.net
  - Maven: dlcdn.apache.org  (older -> archive.apache.org)
  - Gradle: services.gradle.org/distributions  (+ /versions/current JSON)

When `BTC_MIRROR` (or `--mirror`) is active, mirror URLs are prepended to the
candidate list returned by the plural URL builders (node_urls / jdk_urls /
maven_urls / gradle_urls). download.install_portable tries each in order.
"""
from __future__ import annotations
import json
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

import download
import mirrors
import versions

NODE_INDEX = 'https://nodejs.org/dist/index.json'
NODE_DIST = 'https://nodejs.org/dist/v{ver}/node-v{ver}-{plat}-{arch}.{ext}'
ADOPTIUM_LATEST = (
    'https://api.adoptium.net/v3/binary/latest/{feat}/ga/{os}/{arch}/'
    'jdk/hotspot/normal/eclipse'
)
MAVEN_PRIMARY = (
    'https://dlcdn.apache.org/maven/maven-3/{ver}/binaries/'
    'apache-maven-{ver}-bin.{ext}'
)
MAVEN_ARCHIVE = (
    'https://archive.apache.org/dist/maven/maven-3/{ver}/binaries/'
    'apache-maven-{ver}-bin.{ext}'
)
MAVEN_DIR = 'https://dlcdn.apache.org/maven/maven-3/'
GRADLE_DIST = 'https://services.gradle.org/distributions/gradle-{ver}-bin.zip'
GRADLE_CURRENT = 'https://services.gradle.org/versions/current'
GRADLE_DISTRIBUTIONS = 'https://services.gradle.org/distributions/'

_TIMEOUT = 60
_CTX = ssl.create_default_context()


def _get(url):
    req = urllib.request.Request(
        url, headers={'User-Agent': 'build-toolchain-installer/1.0', 'Accept': '*/*'}
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT, context=_CTX) as resp:
        return resp.read()


def _get_json(url):
    return json.loads(_get(url).decode('utf-8'))


def _get_text(url):
    return _get(url).decode('utf-8', errors='replace')


# --------------------------------------------------------------------------
# Node.js
def resolve_node(constraint):
    """Latest Node version matching the constraint (LTS preferred). Returns str or None."""
    try:
        data = _get_json(NODE_INDEX)
    except Exception as e:
        raise RuntimeError(f"cannot fetch Node index {NODE_INDEX}: {e}")
    c = versions.parse_constraint(constraint)
    candidates = []
    for item in data:
        ver = (item.get('version') or '').lstrip('vV')
        if not ver or not c.matches(ver):
            continue
        lts = bool(item.get('lts'))
        candidates.append((ver, lts))
    if not candidates:
        return None
    # prefer LTS, then highest version
    candidates.sort(
        key=lambda x: (x[1], versions.parse_version(x[0]) or (0, 0, 0)),
        reverse=True,
    )
    return candidates[0][0]


def node_url(ver):
    """Official Node.js archive URL (back-compat shim). See node_urls() for mirror-aware list."""
    os_ = download.os_name()
    arch = download.arch()
    plat = {'windows': 'win', 'mac': 'darwin', 'linux': 'linux'}[os_]
    ext = 'zip' if os_ == 'windows' else 'tar.gz'
    return NODE_DIST.format(ver=ver, plat=plat, arch=arch, ext=ext)


def node_urls(ver):
    """Ordered candidate URLs for Node.js: mirror first (if active), then official."""
    os_ = download.os_name()
    arch = download.arch()
    plat = {'windows': 'win', 'mac': 'darwin', 'linux': 'linux'}[os_]
    ext = 'zip' if os_ == 'windows' else 'tar.gz'
    out = []
    mt = mirrors.template_for('node')
    if mt:
        out.append(mt.format(ver=ver, plat=plat, arch=arch, ext=ext))
    out.append(NODE_DIST.format(ver=ver, plat=plat, arch=arch, ext=ext))
    return out


# --------------------------------------------------------------------------
# JDK (Temurin via Adoptium API)
def jdk_url(feature):
    """Official Temurin latest-GA binary URL for the given feature version.

    This is the API endpoint that 302-redirects to a signed GitHub release asset.
    """
    os_ = download.os_name()
    arch = download.arch()
    o = {'windows': 'windows', 'mac': 'mac', 'linux': 'linux'}[os_]
    if os_ == 'mac':
        a = {'x64': 'x64', 'arm64': 'arm64'}[arch]
    else:
        a = {'x64': 'x64', 'arm64': 'aarch64'}[arch]
    return ADOPTIUM_LATEST.format(feat=feature, os=o, arch=a)


def _jdk_filename(feature):
    """Resolve the exact filename of the latest GA Temurin archive for a feature.

    e.g. 'OpenJDK21U-jdk_x64_windows_hotspot_21.0.11_10.zip'.
    Returns None if the API cannot be reached (caller falls back to official URL).
    """
    api = jdk_url(feature)
    try:
        req = urllib.request.Request(
            api, method='HEAD',
            headers={'User-Agent': 'build-toolchain-installer/1.0', 'Accept': '*/*'},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT, context=_CTX) as r:
            final = r.geturl()
    except Exception as e:
        sys.stderr.write(f'  warning: cannot resolve JDK filename via API: {e}\n')
        return None
    # The signed release-assets URL carries the filename in the
    # `response-content-disposition` query parameter.
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(final).query)
    rcd = urllib.parse.unquote(qs.get('response-content-disposition', [''])[0])
    m = re.search(r'filename=([^;]+\.zip)', rcd)
    if m:
        return m.group(1)
    path = urllib.parse.urlparse(final).path
    if path.lower().endswith('.zip'):
        return path.rsplit('/', 1)[-1]
    return None


def jdk_urls(feature):
    """Ordered candidate URLs for JDK: mirror first (if active), then official API."""
    official = jdk_url(feature)
    out = []
    mt = mirrors.template_for('jdk')
    if mt:
        os_ = download.os_name()
        arch = download.arch()
        filename = _jdk_filename(feature)
        if filename:
            out.append(mt.format(feat=feature, arch=arch, os=os_, filename=filename))
        else:
            sys.stderr.write(
                '  warning: JDK filename unknown; skipping mirror, using official API\n'
            )
    out.append(official)
    return out


# --------------------------------------------------------------------------
# Maven
def _list_maven_versions():
    try:
        html = _get_text(MAVEN_DIR)
    except Exception as e:
        raise RuntimeError(f"cannot list Maven versions at {MAVEN_DIR}: {e}")
    found = re.findall(r'href="(\d+\.\d+\.\d+)/"', html)
    seen = set()
    out = []
    for v in found:
        if v not in seen:
            seen.add(v)
            out.append(v)
    out.sort(key=versions.parse_version, reverse=True)
    return out


def resolve_maven(constraint):
    """Resolve a Maven distribution version. Exact X.Y.Z passes through without network."""
    if constraint and versions.is_exact(constraint):
        return constraint
    try:
        avail = _list_maven_versions()
    except Exception:
        if constraint:
            # cannot list versions, trust the supplied constraint as-is
            return constraint
        raise
    if not constraint or constraint in ('*', 'latest'):
        return avail[0] if avail else constraint
    c = versions.parse_constraint(constraint)
    for v in avail:
        if c.matches(v):
            return v
    return constraint


def maven_urls(ver):
    """Ordered candidate URLs for the given Maven version: mirror first, then
    official primary, then official archive."""
    os_ = download.os_name()
    ext = 'zip' if os_ == 'windows' else 'tar.gz'
    out = []
    mt = mirrors.template_for('maven')
    if mt:
        out.append(mt.format(ver=ver, ext=ext))
    out.append(MAVEN_PRIMARY.format(ver=ver, ext=ext))
    out.append(MAVEN_ARCHIVE.format(ver=ver, ext=ext))
    return out


# --------------------------------------------------------------------------
# Gradle
def resolve_gradle(constraint):
    """Resolve a Gradle distribution version. Exact X.Y.Z passes through."""
    if constraint and versions.is_exact(constraint):
        return constraint
    try:
        data = _get_json(GRADLE_CURRENT)
        latest = data.get('version')
    except Exception:
        latest = None
    if not constraint or constraint in ('*', 'latest'):
        return latest or constraint
    if latest and versions.parse_constraint(constraint).matches(latest):
        return latest
    # fall back to scraping the distributions page for older versions
    try:
        html = _get_text(GRADLE_DISTRIBUTIONS)
        found = re.findall(r'gradle-(\d+\.\d+(?:\.\d+)?)-bin\.zip', html)
        found.sort(key=versions.parse_version, reverse=True)
        c = versions.parse_constraint(constraint)
        for v in found:
            if c.matches(v):
                return v
    except Exception:
        pass
    return latest or constraint


def gradle_url(ver):
    """Official Gradle distribution URL (back-compat shim). See gradle_urls()."""
    return GRADLE_DIST.format(ver=ver)


def gradle_urls(ver):
    """Ordered candidate URLs for Gradle: mirror first (if active), then official."""
    out = []
    mt = mirrors.template_for('gradle')
    if mt:
        out.append(mt.format(ver=ver))
    out.append(GRADLE_DIST.format(ver=ver))
    return out
