#!/usr/bin/env bash
# Optional integrations, fail closed if FF_REQUIRE_SECURITY_SCAN=1.
set -euo pipefail
MODE=${1:-source}
TARGET=${2:-.}
[[ "$MODE" == source || "$MODE" == image ]] || { echo 'Usage: security-scan.sh source [path] | image IMAGE' >&2; exit 2; }
REQUIRED=${FF_REQUIRE_SECURITY_SCAN:-0}
if [[ "$MODE" == source ]]; then
  if command -v gitleaks >/dev/null 2>&1; then
    gitleaks dir "$TARGET" --redact --exit-code 1
  elif [[ "$REQUIRED" == 1 ]]; then
    echo 'Gitleaks unavailable; security gate not satisfied' >&2; exit 3
  else
    echo 'SKIP: Gitleaks not installed (not a security pass)'
  fi
else
  if command -v trivy >/dev/null 2>&1; then
    trivy image --exit-code 1 --severity HIGH,CRITICAL --no-progress "$TARGET"
  elif [[ "$REQUIRED" == 1 ]]; then
    echo 'Trivy unavailable; image security gate not satisfied' >&2; exit 3
  else
    echo 'SKIP: Trivy not installed (not a security pass)'
  fi
fi
