#!/usr/bin/env bash
# Optional integrations, fail closed if FF_REQUIRE_SECURITY_SCAN=1.
# gitleaks 的 dir 子命令要求 gitleaks >= 8.19(旧版只有 detect,会以 unknown command 失败);
# dir 模式只扫工作区文件,不扫 git 历史(历史泄漏需另行全量扫描)。
set -euo pipefail
MODE=${1:-source}
TARGET=${2:-.}
[[ "$MODE" == source || "$MODE" == image || "$MODE" == image-tar ]] || { echo 'Usage: security-scan.sh source [path] | image IMAGE | image-tar TAR' >&2; exit 2; }
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
    # image: 扫描本地 Docker 内的镜像引用;image-tar: 扫描镜像 tar(trivy --input,无需守护进程)。
    if [[ "$MODE" == image-tar ]]; then
      trivy image --input "$TARGET" --exit-code 1 --severity HIGH,CRITICAL --no-progress
    else
      trivy image --exit-code 1 --severity HIGH,CRITICAL --no-progress "$TARGET"
    fi
  elif [[ "$REQUIRED" == 1 ]]; then
    echo 'Trivy unavailable; image security gate not satisfied' >&2; exit 3
  else
    echo 'SKIP: Trivy not installed (not a security pass)'
  fi
fi
