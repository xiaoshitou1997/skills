#!/usr/bin/env bash
# Install a portable CPython from python-build-standalone WITHOUT requiring Python.
#
# This is the first-Python bootstrap for hosts where mv-toolchain-manager's
# runtime_cli.py cannot run yet. It downloads only the official release archive,
# verifies it against the release's SHA256SUMS, extracts it under
# ~/.mv/toolchain-manager/python/<version>, and prints one session-activation
# line on stdout. Diagnostics go to stderr.
#
# Usage: bootstrap-python.sh [latest|X.Y|X.Y.Z]
#   eval "$(bootstrap-python.sh 3.12)"
#
# Full constraint support and other tools remain in runtime_cli.py.
set -euo pipefail

TAG_URL='https://github.com/astral-sh/python-build-standalone/releases/latest'
DIST='https://github.com/astral-sh/python-build-standalone/releases/download'
CONSTRAINT=${1:-latest}
ROOT=${MV_TOOLCHAIN_MANAGER_HOME:-$HOME/.mv/toolchain-manager}

die() { echo "bootstrap-python: $*" >&2; exit 3; }
log() { echo "  $*" >&2; }

# Git Bash needs /c/Users/... in PATH; a C:/... entry is silently ignored.
to_msys() {
  case "$1" in
    [A-Za-z]:[\\/]*)
      local drive=${1:0:1}
      local rest=${1:2}
      rest=${rest//\\//}
      printf '/%s%s\n' "$(printf '%s' "$drive" | tr 'A-Z' 'a-z')" "$rest"
      ;;
    *) printf '%s\n' "$1" ;;
  esac
}

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) OS=windows ;;
  Darwin) OS=mac ;;
  Linux) OS=linux ;;
  *) die "unsupported OS: $(uname -s)" ;;
esac
case "$(uname -m)" in
  x86_64|amd64) ARCH=x64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) die "unsupported architecture: $(uname -m)" ;;
esac
case "$OS/$ARCH" in
  windows/x64)    TRIPLE=x86_64-pc-windows-msvc ;;
  windows/arm64)  TRIPLE=aarch64-pc-windows-msvc ;;
  linux/x64)      TRIPLE=x86_64-unknown-linux-gnu ;;
  linux/arm64)    TRIPLE=aarch64-unknown-linux-gnu ;;
  mac/x64)        TRIPLE=x86_64-apple-darwin ;;
  mac/arm64)      TRIPLE=aarch64-apple-darwin ;;
  *) die "unsupported platform: $OS/$ARCH" ;;
esac

command -v curl >/dev/null 2>&1 \
  || die 'curl is required to resolve and download the release archive'
command -v tar >/dev/null 2>&1 || die 'tar is required to extract the archive'

fetch() { # fetch URL DEST
  curl -fsSL --retry 2 -o "$2" "$1"
}

TAG=$(curl -fsSL -o /dev/null -w '%{url_effective}' "$TAG_URL" \
  | sed -n 's#.*/tag/\([0-9][0-9]*\)$#\1#p')
[ -n "$TAG" ] || die "cannot resolve the latest release from $TAG_URL"

TMP=$(mktemp -d "${TMPDIR:-/tmp}/pybootstrap.XXXXXX")
trap 'rm -rf "$TMP" 2>/dev/null || true' EXIT

log "release $TAG ($TRIPLE)"
fetch "$DIST/$TAG/SHA256SUMS" "$TMP/SHA256SUMS"

# Stable versions only: asset names embed <ver>+<tag>; pre-releases such as
# 3.16.0a1 do not match the strict X.Y.Z capture.
awk -v t="$TRIPLE" -v tag="$TAG" '
  {
    n = $2
    sub(/^\*/, "", n)
    prefix = "cpython-"
    if (index(n, prefix) != 1) next
    rest = substr(n, length(prefix) + 1)
    split(rest, a, "+")
    ver = a[1]
    if (a[2] != tag "-" t "-install_only.tar.gz") next
    if (ver !~ /^[0-9]+\.[0-9]+\.[0-9]+$/) next
    print ver
  }' "$TMP/SHA256SUMS" | sort -t. -k1,1n -k2,2n -k3,3n > "$TMP/versions"
[ -s "$TMP/versions" ] || die "no stable portable CPython for $TRIPLE in release $TAG"

if [ -z "$CONSTRAINT" ] || [ "$CONSTRAINT" = latest ]; then
  VER=$(tail -n 1 "$TMP/versions")
elif printf '%s' "$CONSTRAINT" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'; then
  VER=$(grep -x "$CONSTRAINT" "$TMP/versions" || true)
elif printf '%s' "$CONSTRAINT" | grep -Eq '^[0-9]+\.[0-9]+$'; then
  VER=$(grep -E "^$(printf '%s' "$CONSTRAINT" | sed 's/\./\\./g')\." "$TMP/versions" \
    | tail -n 1)
else
  die "bootstrap supports latest, X.Y, or X.Y.Z; use runtime_cli.py for full constraints"
fi
[ -n "$VER" ] || die "no CPython matches $CONSTRAINT in release $TAG"

TARGET="$ROOT/python/v$VER"

emit_activation() {
  if [ "$OS" = windows ]; then
    BIN_DIR=$(to_msys "$TARGET")
    PY=$TARGET/python.exe
  else
    BIN_DIR=$TARGET/bin
    PY=$BIN_DIR/python3
  fi
  [ -x "$PY" ] || die "installed tree has no executable interpreter: $PY"
  "$PY" --version >&2
  printf 'export PATH="%s:$PATH"\n' "$BIN_DIR"
}

if [ -d "$TARGET" ] && [ -n "$(ls -A "$TARGET" 2>/dev/null)" ]; then
  log "already installed: $TARGET"
  emit_activation
  exit 0
fi

ASSET="cpython-$VER+$TAG-$TRIPLE-install_only.tar.gz"
EXPECTED=$(awk -v n="$ASSET" '$2 == n {print tolower($1)}' "$TMP/SHA256SUMS")
[ -n "$EXPECTED" ] || die "checksum for $ASSET is missing in SHA256SUMS"

log "downloading CPython $VER"
fetch "$DIST/$TAG/$ASSET" "$TMP/$ASSET"

if command -v sha256sum >/dev/null 2>&1; then
  ACTUAL=$(sha256sum "$TMP/$ASSET" | awk '{print tolower($1)}')
elif command -v shasum >/dev/null 2>&1; then
  ACTUAL=$(shasum -a 256 "$TMP/$ASSET" | awk '{print tolower($1)}')
elif command -v openssl >/dev/null 2>&1; then
  ACTUAL=$(openssl dgst -sha256 "$TMP/$ASSET" | awk '{print tolower($NF)}')
else
  die 'need sha256sum, shasum, or openssl to verify the archive'
fi
[ "$ACTUAL" = "$EXPECTED" ] \
  || die "checksum mismatch for $ASSET: expected $EXPECTED, got $ACTUAL"
log 'checksum OK (sha256)'

# Refuse absolute or parent-escaping members before extraction.
if tar -tzf "$TMP/$ASSET" | grep -Eq '^(/|.*(^|/)\.\.(/|$))'; then
  die "archive $ASSET contains unsafe paths"
fi
mkdir -p "$TMP/unpack"
tar -xzf "$TMP/$ASSET" -C "$TMP/unpack"
[ -d "$TMP/unpack/python" ] || die 'unexpected archive layout: missing python/'

mkdir -p "$ROOT/python"
rm -rf "$TARGET"
mv "$TMP/unpack/python" "$TARGET"
log "installed -> $TARGET"

# stdout is evaluated by the caller: eval "$(bootstrap-python.sh ...)"
emit_activation
