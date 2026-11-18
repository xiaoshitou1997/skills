#!/usr/bin/env bash
# Render a self-contained HTML diagram to PNG via a locally installed
# Chrome/Edge in headless mode. Explicit invocation; no downloads, no installs.
set -euo pipefail

usage() {
  echo 'Usage: render_diagram.sh <input.html> <output.png> --width N --height N [--scale N]' >&2
  echo '  --width/--height  canvas size in CSS px, must match the diagram canvas' >&2
  echo '  --scale           device scale factor, decimal allowed (default 2)' >&2
  echo '  BROWSER_BIN       optional path override for the browser binary' >&2
}

die() { echo "render_diagram.sh: $1" >&2; exit 3; }

if [[ $# -eq 1 && ( "$1" == --help || "$1" == -h ) ]]; then usage; exit 0; fi
[[ $# -ge 2 ]] || { usage; exit 2; }
IN=$1
OUT=$2
shift 2
W='' H='' SCALE=2
while [[ $# -gt 0 ]]; do
  case "$1" in
    --width)  [[ $# -ge 2 ]] || die "--width needs a value";  W=$2;  shift 2 ;;
    --height) [[ $# -ge 2 ]] || die "--height needs a value"; H=$2; shift 2 ;;
    --scale)  [[ $# -ge 2 ]] || die "--scale needs a value";  SCALE=$2; shift 2 ;;
    *) usage; exit 2 ;;
  esac
done
[[ "$W" =~ ^[1-9][0-9]*$ && "$H" =~ ^[1-9][0-9]*$ ]] || die '--width and --height must be positive integers (canvas px)'
[[ "$SCALE" =~ ^[0-9]+([.][0-9]+)?$ ]] || die '--scale must be a number'
[[ -f "$IN" ]] || die "input not found: $IN"

# Discover a local browser: BROWSER_BIN override, then PATH, then per-OS locations.
find_browser() {
  local c base
  for c in google-chrome google-chrome-stable chromium chromium-browser msedge; do
    command -v "$c" >/dev/null 2>&1 && { command -v "$c"; return 0; }
  done
  local win_paths=(
    '/c/Program Files/Google/Chrome/Application/chrome.exe'
    '/c/Program Files (x86)/Google/Chrome/Application/chrome.exe'
    "${LOCALAPPDATA:-}/Google/Chrome/Application/chrome.exe"
    '/c/Program Files/Microsoft/Edge/Application/msedge.exe'
    '/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
  )
  for base in "${win_paths[@]}"; do
    [[ -n "$base" && -f "$base" ]] && { echo "$base"; return 0; }
  done
  local mac_paths=(
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'
    '/Applications/Chromium.app/Contents/MacOS/Chromium'
  )
  for base in "${mac_paths[@]}"; do
    [[ -f "$base" ]] && { echo "$base"; return 0; }
  done
  return 1
}

if [[ -n "${BROWSER_BIN:-}" ]]; then
  [[ -f "$BROWSER_BIN" ]] || die "BROWSER_BIN set but not found: $BROWSER_BIN"
  BROWSER=$BROWSER_BIN
else
  BROWSER=$(find_browser) || die 'no local Chrome/Edge found; install one or set BROWSER_BIN'
fi

# Absolute paths; MSYS/Git Bash needs Windows-style mixed paths for the browser.
mkdir -p "$(dirname "$OUT")"
OUT=$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    URL="file:///$(cygpath -m "$(cd "$(dirname "$IN")" && pwd)/$(basename "$IN")")"
    SCREENSHOT_ARG=$(cygpath -m "$OUT")
    PROFILE_ARG=$(cygpath -m "$(mktemp -d)")
    ;;
  *)
    URL="file://$(cd "$(dirname "$IN")" && pwd)/$(basename "$IN")"
    SCREENSHOT_ARG=$OUT
    PROFILE_ARG=$(mktemp -d)
    ;;
esac

# Disposable profile so the render never touches a real browser profile.
# 浏览器进程异步退出且可能晚于启动器释放句柄,清理失败不报错、不刷屏。
trap 'rm -rf "$PROFILE_ARG" 2>/dev/null || true' EXIT

ERRLOG=$(mktemp)
if ! "$BROWSER" --headless=new --no-first-run --disable-gpu --hide-scrollbars \
    --user-data-dir="$PROFILE_ARG" \
    --force-device-scale-factor="$SCALE" \
    --window-size="$W,$H" \
    --default-background-color=FFFFFFFF \
    --screenshot="$SCREENSHOT_ARG" "$URL" >"$ERRLOG" 2>&1; then
  tail -n 5 "$ERRLOG" >&2 || true
  die "browser render failed: $BROWSER"
fi
rm -f "$ERRLOG" 2>/dev/null || true

# 部分浏览器由启动器先返回,截图文件随后落盘:最多等 10 秒。
for _ in 1 2 3 4 5 6 7 8 9 10; do
  [[ -s "$OUT" ]] && break
  sleep 1
done
[[ -s "$OUT" ]] || die "browser produced no output at $OUT"
echo "render_diagram.sh: wrote $OUT ($(wc -c < "$OUT" | tr -d '[:space:]') bytes)"
