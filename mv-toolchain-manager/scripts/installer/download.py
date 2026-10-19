"""Download + extract portable archives from official sources. Stdlib only.

Hard constraint: only .zip / .tar.gz / .tgz archives are allowed.
Installer artifacts (.msi/.exe/.pkg/.dmg/.bat/.deb/.rpm) are rejected before
any network request. No version manager, no installer, no admin rights.
"""
from __future__ import annotations
import hashlib
import os
import platform
import shutil
import ssl
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from email.message import Message
from pathlib import Path

ALLOWED_EXTS = ('.zip', '.tar.gz', '.tgz')
BLOCKED_EXTS = ('.msi', '.exe', '.pkg', '.dmg', '.bat', '.deb', '.rpm', '.ps1')
TIMEOUT = 180  # seconds; JDK/Node archives can be large on slow links
CHUNK = 64 * 1024


class ChecksumMismatch(RuntimeError):
    """Downloaded archive does not match the publisher's checksum. Fail closed."""


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


def _validate_archive_name(name):
    # URL filenames are untrusted, including Content-Disposition on signed URLs.
    # Reject path components instead of silently taking basename (also on Windows).
    if (not name or any(c in name for c in '/\\:')
            or any(ord(c) < 32 or ord(c) == 127 for c in name)):
        raise ValueError(f'Unsafe archive filename: {name!r}')
    low = name.lower()
    for bad in BLOCKED_EXTS:
        if low.endswith(bad):
            raise ValueError(f'Refusing installer artifact ({bad}): {name}')
    if not low.endswith(ALLOWED_EXTS):
        raise ValueError(
            f'Unsupported archive extension for {name!r}; must be one of {ALLOWED_EXTS}.')
    return name


def archive_filename(url, content_disposition=None):
    """Safe portable filename from a release path or signed asset disposition.

    GitHub signed URLs have an opaque path and response-content-disposition in
    the query. Parse quoting and filename* with the standard MIME parser. The
    same filename is used for validation, extraction and checksum matching.
    """
    parts = urllib.parse.urlsplit(url)
    path_name = urllib.parse.unquote(parts.path.rsplit('/', 1)[-1])
    # A query must never disguise an explicitly blocked installer path.
    if path_name.lower().endswith(BLOCKED_EXTS):
        _validate_archive_name(path_name)
    dispositions = urllib.parse.parse_qs(parts.query).get(
        'response-content-disposition', [])
    if content_disposition:
        dispositions.append(content_disposition)
    names = []
    for disposition in dispositions:
        message = Message()
        message['Content-Disposition'] = disposition
        name = message.get_filename()
        if name is not None:
            names.append(_validate_archive_name(name))
    if names:
        if any(name != names[0] for name in names):
            raise ValueError('Conflicting archive filenames in Content-Disposition')
        return names[0]
    return _validate_archive_name(path_name)


def display_url(url):
    """Diagnostic URL without signed query credentials or fragments."""
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((
        parts.scheme, parts.netloc, parts.path,
        '<redacted>' if parts.query else '', ''))


def validate_archive_url(url):
    """Raise ValueError unless the URL identifies a safe portable archive."""
    archive_filename(url)
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
            archive_filename(resp.geturl(), resp.headers.get('Content-Disposition'))
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
        raise RuntimeError(f"HTTP {e.code} downloading {display_url(url)}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"URL error downloading {display_url(url)}: {e.reason}") from e
    return dest


# --------------------------------------------------------------------------
# Checksum verification (publisher checksum files or immutable npm SRI metadata)
def _checksum_candidates(url):
    """Locations where the publisher typically publishes a checksum for url."""
    cands = [url + '.sha256', url + '.sha512']
    parts = urllib.parse.urlsplit(url)
    if 'nodejs.org' in parts.netloc:
        cands.append(url.rsplit('/', 1)[0] + '/SHASUMS256.txt')
    # go-containerregistry releases publish one checksums.txt per release.
    if parts.netloc == 'github.com' and '/google/go-containerregistry/releases/download/' in parts.path:
        cands.append(url.rsplit('/', 1)[0] + '/checksums.txt')
    # python-build-standalone releases publish one SHA256SUMS per release.
    if (parts.netloc == 'github.com'
            and '/astral-sh/python-build-standalone/releases/download/' in parts.path):
        cands.append(url.rsplit('/', 1)[0] + '/SHA256SUMS')
    # Astral uv releases publish one sha256sum.txt per release.
    if (parts.netloc == 'github.com'
            and '/astral-sh/uv/releases/download/' in parts.path):
        cands.append(url.rsplit('/', 1)[0] + '/sha256sum.txt')
    return cands


def _fetch_checksum_text(url):
    req = urllib.request.Request(
        url, headers={'User-Agent': 'build-toolchain-installer/1.0'})
    with urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context()) as r:
        return r.read().decode('utf-8', 'replace')


def verify_integrity(archive, integrity):
    """Verify an npm registry SRI value against an already-downloaded archive.

    The npm registry signs tarball metadata with `dist.integrity`. It is the
    authoritative immutable digest for the exact package version and is checked
    before any archive is extracted.
    """
    if not integrity or '-' not in integrity:
        raise ValueError('invalid npm SRI integrity value')
    algorithm, encoded = integrity.split('-', 1)
    algorithm = algorithm.lower()
    if algorithm not in hashlib.algorithms_available:
        raise ValueError(f'unsupported npm integrity algorithm: {algorithm}')
    import base64
    try:
        expected = base64.b64decode(encoded, validate=True)
    except Exception as e:
        raise ValueError('invalid base64 in npm SRI integrity value') from e
    h = hashlib.new(algorithm)
    with open(archive, 'rb') as f:
        for chunk in iter(lambda: f.read(CHUNK), b''):
            h.update(chunk)
    if h.digest() != expected:
        raise ChecksumMismatch(
            f'npm integrity mismatch for {Path(archive).name}: expected {integrity}')
    sys.stderr.write(f'  integrity OK ({algorithm})\n')


def verify_download(url, archive):
    """Verify archive against the publisher's checksum when one is published.

    Checks <url>.sha256 / <url>.sha512, (nodejs.org) SHASUMS256.txt and
    (go-containerregistry releases) checksums.txt and
    (python-build-standalone releases) SHA256SUMS.
    Hex mismatch raises ChecksumMismatch (fail closed — the caller must not
    fall through to the next candidate URL). Sources publishing no checksum
    only get a warning; the limitation stays honest instead of silent.
    """
    archive = Path(archive)
    name = archive.name
    for cand in _checksum_candidates(url):
        try:
            text = _fetch_checksum_text(cand)
        except Exception:
            continue
        if not text:
            continue
        for line in text.splitlines():
            toks = line.split()
            if not toks:
                continue
            hexdigest = toks[0].lower()
            if len(hexdigest) == 64:
                algo = 'sha256'
            elif len(hexdigest) == 128:
                algo = 'sha512'
            else:
                continue
            if any(c not in '0123456789abcdef' for c in hexdigest):
                continue
            # SHASUMS256.txt 行尾带文件名;单文件 .sha256/.sha512 只有一段 hex
            if len(toks) >= 2 and not toks[-1].lstrip('*').endswith(name):
                continue
            h = hashlib.new(algo)
            with open(archive, 'rb') as f:
                for chunk in iter(lambda: f.read(CHUNK), b''):
                    h.update(chunk)
            actual = h.hexdigest()
            if actual != hexdigest:
                raise ChecksumMismatch(
                    f'checksum mismatch for {name} from {display_url(url)}: '
                    f'expected {hexdigest} ({algo}), got {actual}')
            sys.stderr.write(f'  checksum OK ({algo})\n')
            return
    sys.stderr.write(
        '  WARNING: no published checksum found; archive integrity not verified\n')


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
            archive_filename(r.geturl(), r.headers.get('Content-Disposition'))
            cl = r.headers.get('Content-Length')
            return int(cl) if cl else None
    except urllib.error.HTTPError as e:
        # 任何非 200 的 HEAD 结果(含 401/403/404)都直接判失败,交由下一候选
        if e.code != 405:
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
            archive_filename(r.geturl(), r.headers.get('Content-Disposition'))
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


def _member_target(dest, name):
    """Resolve an archive member name; raise ValueError if it escapes dest."""
    if name.startswith(('/', '\\')) or (len(name) > 1 and name[1] == ':'):
        raise ValueError(f'unsafe absolute path in archive: {name}')
    dest_r = dest.resolve()
    target = (dest_r / name).resolve()
    if dest_r != target and dest_r not in target.parents:
        raise ValueError(f'unsafe path in archive (escapes destination): {name}')
    return target


def extract(archive, dest):
    """Extract a zip/tar.gz into dest (created if missing).

    Paths are checked before extraction (zip-slip / tar-slip): absolute member
    names and names resolving outside dest are rejected outright.
    """
    archive = Path(archive)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    low = archive.name.lower()
    if low.endswith('.zip'):
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                _member_target(dest, info.filename)
            z.extractall(dest)
    elif low.endswith(('.tar.gz', '.tgz')):
        # Windows tar handles gz; fall back to Python tarfile
        with tarfile.open(archive, 'r:gz') as t:
            try:
                t.extractall(dest, filter='data')
            except TypeError:
                # Python without filter= support: apply manual member checks
                # (absolute/'..' paths and link targets escaping dest).
                for m in t.getmembers():
                    _member_target(dest, m.name)
                    if m.issym() or m.islnk():
                        link = os.path.normpath(
                            os.path.join(os.path.dirname(m.name), m.linkname))
                        if m.linkname.startswith(('/', '\\')) or link.startswith('..'):
                            raise ValueError(
                                f'unsafe link target in archive: {m.name} -> {m.linkname}')
                t.extractall(dest)
    else:
        raise ValueError(f"Cannot extract {archive}: unsupported archive type")


def install_portable(urls, target, label, integrity=None):
    """Download a portable archive and normalize its single top-level dir to `target`.

    Pass `integrity` only for an exact npm-registry package. In that case the
    registry's SRI digest is mandatory and checked before extraction.

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
            sys.stderr.write(f'    [block] {display_url(url)} -> {e}\n')
            continue
        try:
            length = probe_url(url)
            validated.append((url, length))
            size_str = f'{length} bytes' if length else 'size unknown'
            sys.stderr.write(f'    [ok]    {display_url(url)} ({size_str})\n')
        except Exception as e:
            rejected.append((url, str(e)))
            sys.stderr.write(f'    [skip]  {display_url(url)} -> {e}\n')

    if not validated:
        raise RuntimeError(
            f'no downloadable URL for {label}. '
            f'All candidates rejected: '
            + '; '.join(f'{display_url(u)} -> {r}' for u, r in rejected)
        )

    # Phase 2: GET + extract. Mid-stream failures may fall through to the
    # next pre-validated candidate.
    target.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='btc-installer-'))
    fetch_errors = []
    try:
        for index, (url, _length) in enumerate(validated):
            archive_dir = work / f'archive-{index}'
            archive_dir.mkdir()
            archive = archive_dir / archive_filename(url)
            extracted = work / f'extracted-{index}'
            sys.stderr.write(f"  downloading {label}\n    {display_url(url)}\n")
            try:
                download(url, archive)
                if integrity:
                    verify_integrity(archive, integrity)
                else:
                    verify_download(url, archive)
                sys.stderr.write('  extracting...\n')
                extract(archive, extracted)
            except ChecksumMismatch:
                # 校验和不匹配是安全事件,直接失败,不换下一个候选 URL 继续试
                raise
            except Exception as e:
                sys.stderr.write(f"  download failed: {e}\n")
                fetch_errors.append((url, str(e)))
                continue
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
            + '; '.join(f'{display_url(u)} -> {e}' for u, e in fetch_errors)
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)


def install_root():
    """Resolve the install root ($HOME/.mv/toolchain-manager by default)."""
    override = os.environ.get('MV_TOOLCHAIN_MANAGER_HOME')
    if override:
        return Path(override)
    return Path.home() / '.mv' / 'toolchain-manager'


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
