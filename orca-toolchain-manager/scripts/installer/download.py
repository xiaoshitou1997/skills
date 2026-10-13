"""Download + extract portable archives from official sources. Stdlib only.

Hard constraint: only .zip / .tar.gz / .tgz archives are allowed.
Installer artifacts (.msi/.exe/.pkg/.dmg/.bat/.deb/.rpm) are rejected before
any network request. No version manager, no installer, no admin rights.
"""
from __future__ import annotations
import os
import platform
import shutil
import ssl
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ALLOWED_EXTS = ('.zip', '.tar.gz', '.tgz')
BLOCKED_EXTS = ('.msi', '.exe', '.pkg', '.dmg', '.bat', '.deb', '.rpm', '.ps1')
TIMEOUT = 180  # seconds; JDK/Node archives can be large on slow links
CHUNK = 64 * 1024


def os_name():
    if sys.platform.startswith('win'):
        return 'windows'
    if sys.platform == 'darwin':
        return 'mac'
    return 'linux'


def arch():
    m = platform.machine().lower()
    if m in ('x86_64', 'amd64'):
        return 'x64'
    if m in ('aarch64', 'arm64'):
        return 'arm64'
    return m


def validate_archive_url(url):
    """Raise ValueError if the URL is not a whitelisted portable archive."""
    low = url.lower().split('#')[0].split('?')[0]
    for bad in BLOCKED_EXTS:
        if low.endswith(bad):
            raise ValueError(f"Refusing installer artifact ({bad}): {url}")
    if not any(low.endswith(ext) for ext in ALLOWED_EXTS):
        raise ValueError(
            f"Unsupported archive extension for {url!r}; "
            f"must be one of {ALLOWED_EXTS}."
        )
    return True


def download(url, dest, show_progress=True):
    """Stream a validated archive URL to dest. Returns dest Path."""
    validate_archive_url(url)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url, headers={'User-Agent': 'build-toolchain-installer/1.0'}
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
            total = resp.headers.get('Content-Length')
            total = int(total) if total else None
            done = 0
            tmp = dest.with_name(dest.name + '.part')
            with open(tmp, 'wb') as f:
                while True:
                    chunk = resp.read(CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if show_progress and total:
                        pct = done * 100 // total
                        sys.stderr.write(
                            f"\r  {done // (1024 * 1024)}MB / "
                            f"{total // (1024 * 1024)}MB ({pct}%)"
                        )
                        sys.stderr.flush()
            if show_progress:
                sys.stderr.write('\n')
            tmp.replace(dest)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} downloading {url}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"URL error downloading {url}: {e.reason}") from e
    return dest


def probe_url(url):
    """Verify a URL is actually downloadable without fetching the body.

    Returns Content-Length (int) or None if the server does not report it.
    Raises RuntimeError on any non-200 outcome or network failure.

    HEAD is tried first; servers that reject HEAD (405) are probed via a
    1-byte ranged GET instead. This pre-validation guarantees that
    `install_portable` never GETs a URL that would 404 — fallback only
    happens between URLs that have already been confirmed downloadable.
    """
    validate_archive_url(url)
    ctx = ssl.create_default_context()
    headers = {'User-Agent': 'build-toolchain-installer/1.0'}
    # 1) HEAD
    try:
        req = urllib.request.Request(url, method='HEAD', headers=headers)
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            if r.status != 200:
                raise RuntimeError(f'HTTP {r.status}')
            cl = r.headers.get('Content-Length')
            return int(cl) if cl else None
    except urllib.error.HTTPError as e:
        if e.code == 405:
            pass  # HEAD not allowed -> fall through to ranged GET
        elif e.code in (401, 403, 404):
            raise RuntimeError(f'HTTP {e.code}')
        else:
            raise RuntimeError(f'HTTP {e.code}')
    except urllib.error.URLError as e:
        raise RuntimeError(f'network: {e.reason}')
    # 2) ranged GET fallback
    try:
        req = urllib.request.Request(
            url, headers={**headers, 'Range': 'bytes=0-0'}
        )
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            if r.status not in (200, 206):
                raise RuntimeError(f'HTTP {r.status}')
            cr = r.headers.get('Content-Range')
            if cr and '/' in cr:
                total = cr.rsplit('/', 1)[-1]
                if total.isdigit():
                    return int(total)
            return None
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'HTTP {e.code}')
    except urllib.error.URLError as e:
        raise RuntimeError(f'network: {e.reason}')


def extract(archive, dest):
    """Extract a zip/tar.gz into dest (created if missing)."""
    archive = Path(archive)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    low = archive.name.lower()
    if low.endswith('.zip'):
        with zipfile.ZipFile(archive) as z:
            z.extractall(dest)
    elif low.endswith(('.tar.gz', '.tgz')):
        # Windows tar handles gz; fall back to Python tarfile
        with tarfile.open(archive, 'r:gz') as t:
            try:
                t.extractall(dest, filter='data')
            except TypeError:
                # Python < 3.12 has no filter argument
                t.extractall(dest)
    else:
        raise ValueError(f"Cannot extract {archive}: unsupported archive type")


def install_portable(urls, target, label):
    """Download a portable archive and normalize its single top-level dir to `target`.

    `urls` may be a single URL string or an iterable of candidate URLs.

    Two-phase strategy — NO silent 404 retries:

      Phase 1 (probe): Every candidate URL is HEAD-probed (or ranged-GET-probed
        if HEAD is rejected). Only URLs that respond 200 are kept. This is the
        gate that guarantees we never attempt to GET a URL that would 404.

      Phase 2 (fetch): The first probe-passing URL is GET-fetched and extracted.
        If a mid-stream network error aborts the transfer, the next
        probe-passing URL is tried. Mid-stream retries are NOT 404 retries —
        the URL was already confirmed downloadable; only the transfer failed.

    If no URL passes the probe, a RuntimeError is raised listing every
    candidate and its probe outcome (URL + HTTP status / network error),
    so the user can see exactly why each was rejected.

    Returns (target_path, status) where status is 'cached' | 'installed'.
    Idempotent: if `target` already exists and is non-empty, returns immediately
    without downloading.
    """
    if isinstance(urls, str):
        urls = [urls]
    urls = list(urls)
    target = Path(target)
    if target.exists() and any(target.iterdir()):
        return target, 'cached'

    # Phase 1: probe every candidate up-front.
    sys.stderr.write(f'  probing {len(urls)} candidate URL(s) for {label}\n')
    validated = []          # list of (url, content_length)
    rejected = []           # list of (url, reason)
    for url in urls:
        try:
            validate_archive_url(url)
        except ValueError as e:
            rejected.append((url, f'blocked: {e}'))
            sys.stderr.write(f'    [block] {url} -> {e}\n')
            continue
        try:
            length = probe_url(url)
            validated.append((url, length))
            size_str = f'{length} bytes' if length else 'size unknown'
            sys.stderr.write(f'    [ok]    {url} ({size_str})\n')
        except Exception as e:
            rejected.append((url, str(e)))
            sys.stderr.write(f'    [skip]  {url} -> {e}\n')

    if not validated:
        raise RuntimeError(
            f'no downloadable URL for {label}. '
            f'All candidates rejected: '
            + '; '.join(f'{u} -> {r}' for u, r in rejected)
        )

    # Phase 2: GET + extract. Mid-stream failures may fall through to the
    # next pre-validated candidate.
    target.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='btc-installer-'))
    fetch_errors = []
    try:
        for url, _length in validated:
            archive_name = url.split('/')[-1].split('?')[0]
            archive = work / archive_name
            sys.stderr.write(f"  downloading {label}\n    {url}\n")
            try:
                download(url, archive)
                sys.stderr.write('  extracting...\n')
                extract(archive, work / 'extracted')
            except Exception as e:
                sys.stderr.write(f"  download failed: {e}\n")
                fetch_errors.append((url, str(e)))
                extracted = work / 'extracted'
                if extracted.exists():
                    shutil.rmtree(extracted, ignore_errors=True)
                continue
            extracted = work / 'extracted'
            entries = [p for p in extracted.iterdir() if not p.name.startswith('.')]
            if len(entries) == 1 and entries[0].is_dir():
                single = entries[0]
                if target.exists():
                    shutil.rmtree(target)
                shutil.move(str(single), str(target))
            else:
                if target.exists():
                    shutil.rmtree(target)
                shutil.move(str(extracted), str(target))
            sys.stderr.write(f"  installed -> {target}\n")
            return target, 'installed'
        raise RuntimeError(
            f'all probed-OK URLs failed during transfer for {label}: '
            + '; '.join(f'{u} -> {e}' for u, e in fetch_errors)
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)


def sdks_root():
    """Resolve the install root ($HOME/.local/sdks by default)."""
    override = os.environ.get('BTC_SDKS_DIR')
    if override:
        return Path(override)
    return Path.home() / '.local' / 'sdks'


if __name__ == '__main__':
    # quick self-test on the URL validator
    bad = [
        'https://example.com/node.msi',
        'https://example.com/jdk-installer.exe',
        'https://example.com/pkg.dmg',
    ]
    good = [
        'https://nodejs.org/dist/v20.11.0/node-v20.11.0-win-x64.zip',
        'https://nodejs.org/dist/v20.11.0/node-v20.11.0-linux-x64.tar.gz',
        'https://services.gradle.org/distributions/gradle-8.5-bin.zip',
    ]
    ok = True
    for u in bad:
        try:
            validate_archive_url(u)
            print(f'  [FAIL] should have rejected: {u}')
            ok = False
        except ValueError as e:
            print(f'  [OK] rejected: {e}')
    for u in good:
        try:
            validate_archive_url(u)
            print(f'  [OK] accepted: {u}')
        except ValueError as e:
            print(f'  [FAIL] should have accepted: {e}')
            ok = False
    print('all-pass' if ok else 'FAILURES')
