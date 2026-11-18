#!/usr/bin/env bash
# Read-only checks for release targets, intentionally never prints secret env values.
# 预检在宿主侧只做静态配置检查;Docker/Compose 一律经 SSH 到目标机校验,宿主不安装 Docker。
set -euo pipefail
ENV=${1:-}
APP=${2:-}
[[ "$ENV" =~ ^(dev|prod)$ && "$APP" =~ ^[a-z][a-z0-9_-]{0,62}$ ]] || { echo 'Usage: deploy-preflight.sh dev|prod APP' >&2; exit 2; }
if [[ "$ENV" == prod ]]; then
  DEST=${FF_PROD_SSH:-}
  KEY=${FF_PROD_SSH_KEY:-}
  [[ -n "$DEST" ]] || { echo 'FF_PROD_SSH is required' >&2; exit 3; }
else
  DEST=${FF_DEV_SSH:-}
  KEY=${FF_DEV_SSH_KEY:-}
  [[ -n "$DEST" ]] || { echo 'FF_DEV_SSH is required' >&2; exit 3; }
fi
[[ "$DEST" =~ ^[a-zA-Z0-9_.-]+@[a-zA-Z0-9_.-]+$ ]] || { echo 'SSH destination must look like user@host (use ~/.ssh/config for custom ports)' >&2; exit 2; }
SSH_OPTS=(-o BatchMode=yes)
if [[ -n "$KEY" ]]; then SSH_OPTS+=(-i "$KEY"); fi
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
ssh "${SSH_OPTS[@]}" "$DEST" 'docker compose version' >/dev/null 2>&1 || { echo "Docker Compose v2 unavailable on $DEST" >&2; exit 3; }
printf 'Preflight OK: env=%s app=%s target=%s (configuration content withheld)\n' "$ENV" "$APP" "$DEST"
