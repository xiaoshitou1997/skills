#!/usr/bin/env bash
# Read-only checks for release targets, intentionally never prints secret env values.
# Windows 团队规范:容器一律经 WSL 运行;FF_WSL_BRIDGE=0 仅供测试/CI 绕过。
set -euo pipefail
ENV=${1:-}
APP=${2:-}
[[ "$ENV" =~ ^(dev|prod)$ && "$APP" =~ ^[a-z][a-z0-9_-]{0,62}$ ]] || { echo 'Usage: deploy-preflight.sh dev|prod APP' >&2; exit 2; }
HERE=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

docker_cli() {
  local wsl_distro
  wsl_distro=$(bash "$HERE/wsl-bridge.sh" distro)
  if [[ -n "$wsl_distro" ]]; then
    MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' wsl.exe -d "$wsl_distro" -- docker "$@"
  else
    docker "$@"
  fi
}

docker_cli compose version >/dev/null 2>&1 || { echo 'Docker Compose v2 unavailable' >&2; exit 3; }
[[ -f .dockerignore ]] || { echo 'Missing .dockerignore' >&2; exit 3; }
grep -Eq '^\.env\*([[:space:]]|$)' .dockerignore || { echo '.dockerignore must exclude .env*' >&2; exit 3; }
grep -Eq '^\.git([[:space:]]|$)' .dockerignore || { echo '.dockerignore must exclude .git' >&2; exit 3; }
[[ -f ".env.$ENV" ]] || { echo "Missing .env.$ENV" >&2; exit 3; }
grep -Eq "^APP_ENV=$ENV\r?$" ".env.$ENV" || { echo "Wrong APP_ENV in .env.$ENV" >&2; exit 3; }
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if git ls-files --error-unmatch ".env.$ENV" >/dev/null 2>&1; then
    echo 'Env file is tracked by Git' >&2; exit 3
  fi
fi
if [[ "$ENV" == prod ]]; then
  [[ -n "${FF_PROD_SSH:-}" ]] || { echo 'FF_PROD_SSH is required' >&2; exit 3; }
fi
printf 'Preflight OK: env=%s app=%s (configuration content withheld)\n' "$ENV" "$APP"
