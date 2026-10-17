"""Official source URL builders + latest-version resolvers. Stdlib only.

Sources (official only):
  - Node.js: nodejs.org/dist
  - JDK (Temurin): api.adoptium.net
  - Maven: dlcdn.apache.org  (older -> archive.apache.org)
  - Gradle: services.gradle.org/distributions  (+ /versions/current JSON)

When `FF_MIRROR` (or `--mirror`) is active, mirror URLs are prepended to the
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
ADOPTIUM_LATEST = 'https://api.adoptium.net/v3/assets/latest/{feat}/hotspot'
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
    """Resolve the latest GA portable package through the official assets API.

    Return the release archive link, not the extensionless binary endpoint.
    Keeping the stable release link also keeps its published checksum sidecars
    discoverable before GitHub redirects the transfer to an expiring signed URL.
    """
    os_ = download.os_name()
    architecture = {'x64': 'x64', 'arm64': 'aarch64'}[download.arch()]
    api = ADOPTIUM_LATEST.format(feat=feature) + '?' + urllib.parse.urlencode({
        'architecture': architecture, 'image_type': 'jdk',
        'os': os_, 'vendor': 'eclipse',
    })
    try:
        assets = _get_json(api)
        package = assets[0]['binary']['package']
        url = package['link']
        filename = download.archive_filename(url)
        expected_ext = '.zip' if os_ == 'windows' else '.tar.gz'
        if filename != package['name'] or not filename.lower().endswith(expected_ext):
            raise ValueError('JDK package name or archive type does not match its link')
        return url
    except Exception as e:
        raise RuntimeError(f'cannot resolve Temurin JDK {feature} from {api}: {e}') from e


def _jdk_filename(feature):
    """Exact portable filename from official metadata; None on resolution failure."""
    try:
        return download.archive_filename(jdk_url(feature))
    except Exception as e:
        sys.stderr.write(f'  warning: cannot resolve JDK filename via API: {e}\n')
        return None


def jdk_urls(feature):
    """Mirror (only when opted in), then the official resolved release archive."""
    official = jdk_url(feature)
    out = []
    mt = mirrors.template_for('jdk')
    if mt:
        out.append(mt.format(
            feat=feature, arch=download.arch(), os=download.os_name(),
            filename=download.archive_filename(official)))
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
    avail = _list_maven_versions()
    if not constraint or constraint in ('*', 'latest'):
        if avail:
            return avail[0]
    else:
        c = versions.parse_constraint(constraint)
        for v in avail:
            if c.matches(v):
                return v
    raise RuntimeError(f'no Maven version matches {constraint!r}')


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
    """Exact X.Y / X.Y.Z passes through; ranges must resolve to a match."""
    if constraint and re.fullmatch(r'\d+\.\d+(?:\.\d+)?', constraint):
        return constraint
    try:
        data = _get_json(GRADLE_CURRENT)
        latest = data.get('version')
    except Exception:
        latest = None
    if not constraint or constraint in ('*', 'latest'):
        if latest:
            return latest
        raise RuntimeError('cannot resolve latest Gradle version')
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
    except Exception as e:
        raise RuntimeError(f'cannot resolve Gradle constraint {constraint!r}: {e}') from e
    raise RuntimeError(f'no Gradle version matches {constraint!r}')


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
