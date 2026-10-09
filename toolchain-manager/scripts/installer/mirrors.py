"""Mirror registry. Mirrors are tried before the official source when active.

Activation:
  - env var `BTC_MIRROR=<key>` (e.g. `BTC_MIRROR=cn`)
  - CLI flag `--mirror <key>` on `runtime_cli.py` (sets the env var in-process)

When a mirror is active, each tool's URL builder returns the mirror URL first
and the official URL as fallback. If the mirror fails (HTTP error, network),
download.install_portable falls through to the next candidate. Mirrors are
opt-in: default is no mirror (official only).

Mirror templates use the same placeholders as the official builders:
  - Node:   {ver} {plat} {arch} {ext}
  - JDK:    {feat} {arch} {os} {filename}
  - Maven:  {ver} {ext}
  - Gradle: {ver}
"""
from __future__ import annotations
import os


# mirror region key -> tool -> URL template
MIRRORS = {
    'cn': {
        'node':   'https://cdn.npmmirror.com/binaries/node/v{ver}/node-v{ver}-{plat}-{arch}.{ext}',
        'jdk':    'https://mirrors.tuna.tsinghua.edu.cn/Adoptium/{feat}/jdk/{arch}/{os}/{filename}',
        'maven':  'https://mirrors.tuna.tsinghua.edu.cn/apache/maven/maven-3/{ver}/binaries/apache-maven-{ver}-bin.{ext}',
        'gradle': 'https://mirrors.cloud.tencent.com/gradle/gradle-{ver}-bin.zip',
    },
}


def active_mirror():
    """Return the active mirror key (from BTC_MIRROR env), or None for official only."""
    val = (os.environ.get('BTC_MIRROR') or '').strip().lower()
    if val and val in MIRRORS:
        return val
    return None


def template_for(tool):
    """Return the URL template for the active mirror + tool, or None if mirror disabled."""
    key = active_mirror()
    if not key:
        return None
    return MIRRORS.get(key, {}).get(tool)


def describe():
    """Human description of the current mirror setting (for logging)."""
    key = active_mirror()
    if not key:
        return 'official only (no mirror)'
    return f'mirror={key}'
