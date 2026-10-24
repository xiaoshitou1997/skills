#!/usr/bin/env bash
# Deploy prebuilt immutable images and manage promotion/rollback (delivery side of the pipeline).
# 所有部署目标一律经 SSH 访问;宿主不安装 Docker,不直接操作容器。
# 镜像由 mv-image-build 在构建点产出;本脚本只做预检、分发、启动、健康验证、收据与回滚。
# 目标机不执行构建,只加载并运行不可变镜像;镜像常驻,任何流程不得 rmi/prune/清理镜像。
set -euo pipefail
umask 077

HERE=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SKILL_ROOT=$(dirname "$HERE")
ACTION=${1:-}
ENV=${2:-}
APP=${3:-}
IMAGE=${4:-}
APPROVAL=${5:-}

usage() {
  echo 'Usage: deploy.sh deploy dev|prod APP IMAGE [--approve-prod]' >&2
  echo '       deploy.sh status dev|prod APP' >&2
  echo '       deploy.sh rollback dev|prod APP [--approve-prod]' >&2
  exit 2
}

[[ "$ACTION" =~ ^(deploy|status|rollback)$ ]] || usage
[[ "$ENV" =~ ^(dev|prod)$ ]] || usage
[[ "$APP" =~ ^[a-z][a-z0-9_-]{0,62}$ ]] || { echo 'APP must be lowercase letters/digits/hyphens/underscores' >&2; exit 2; }
if [[ "$ACTION" == deploy ]]; then
  [[ "$IMAGE" =~ ^[a-zA-Z0-9][a-zA-Z0-9._:/@-]{0,199}$ ]] || { echo 'Unsafe or empty image ref' >&2; exit 2; }
fi
if [[ "$ENV" == prod && "$ACTION" != status ]]; then
  if [[ "$ACTION" == rollback ]]; then APPROVAL=${4:-}; fi
  [[ "$APPROVAL" == --approve-prod ]] || { echo 'Production mutation requires --approve-prod after explicit user authorization' >&2; exit 3; }
fi

# Health URL/timeout follow the target runner input contract.
if [[ -n "${FF_HEALTH_URL:-}" && ! "${FF_HEALTH_URL}" =~ ^https?://[a-zA-Z0-9._:/-]+$ ]]; then
  echo 'FF_HEALTH_URL contains unsupported characters; use a simple http(s) health URL without query/credentials' >&2
  exit 2
fi
if [[ -n "${FF_READY_TIMEOUT:-}" && ! "${FF_READY_TIMEOUT}" =~ ^[0-9]+$ ]]; then
  echo 'FF_READY_TIMEOUT must be a positive integer (seconds)' >&2
  exit 2
fi
if [[ "$ACTION" == deploy && "$ENV" == prod && "$IMAGE" == *-dirty* ]]; then
  echo 'Refusing to deploy an image tagged from an uncommitted working tree to prod' >&2
  exit 3
fi

# 部署目标一律经 SSH:dev 与 prod 各自必填,无本机缺省目标,不设宿主侧容器通道。
if [[ "$ENV" == prod ]]; then
  SSH_DEST=${FF_PROD_SSH:-}
  SSH_KEY=${FF_PROD_SSH_KEY:-}
  [[ -n "$SSH_DEST" ]] || { echo 'FF_PROD_SSH must be set' >&2; exit 3; }
  if [[ "$SSH_DEST" == "${FF_DEV_SSH:-}" ]]; then
    echo 'Dev and prod cannot use the same SSH target and app directory' >&2; exit 3
  fi
else
  SSH_DEST=${FF_DEV_SSH:-}
  SSH_KEY=${FF_DEV_SSH_KEY:-}
  [[ -n "$SSH_DEST" ]] || { echo 'FF_DEV_SSH must be set' >&2; exit 3; }
fi
# Explicitly constrain identity syntax; SSH will validate host keys with user's configured known_hosts.
if [[ ! "$SSH_DEST" =~ ^[a-zA-Z0-9_.-]+@[a-zA-Z0-9_.-]+$ ]]; then
  echo 'SSH destination must look like user@host (use ~/.ssh/config for custom ports)' >&2
  exit 2
fi
SSH_OPTS=(-o BatchMode=yes)
SCP_OPTS=(-o BatchMode=yes)
if [[ -n "$SSH_KEY" ]]; then SSH_OPTS+=(-i "$SSH_KEY"); SCP_OPTS+=(-i "$SSH_KEY"); fi

project_checks() {
  [[ -f .dockerignore ]] || { echo 'Missing .dockerignore; refuse sending unsanitized Docker build context' >&2; exit 3; }
  # This is a minimum guard; negative patterns and other secrets still need human review.
  grep -Eq '^\.env\*([[:space:]]|$)' .dockerignore || { echo '.dockerignore must contain .env*' >&2; exit 3; }
  grep -Eq '^\.git([[:space:]]|$)' .dockerignore || { echo '.dockerignore must contain .git' >&2; exit 3; }
  if grep -Eq '^![[:space:]]*\.env' .dockerignore; then
    echo 'Dangerous negated env ignore rule' >&2; exit 3
  fi
}

env_checks() {
  local path=".env.$ENV"
  [[ -f "$path" ]] || { echo "Missing $path" >&2; exit 3; }
  if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    if git ls-files --error-unmatch "$path" >/dev/null 2>&1; then echo "$path is tracked by git; refuse deploy" >&2; exit 3; fi
  fi
  if ! grep -Eq "^APP_ENV=$ENV\r?$" "$path"; then echo "$path must set APP_ENV=$ENV" >&2; exit 3; fi
}

# SSH 把 argv 重新拼成远端 shell 命令;逐参数 POSIX 单引号编码,保留空参数。
# 不用 printf %q:远端登录 shell 不保证是 Bash。
ssh_cli() {
  local remote_command='' arg
  for arg in "$@"; do
    arg=${arg//\'/\'\\\'\'}
    remote_command+=" '$arg'"
  done
  ssh "${SSH_OPTS[@]}" "$SSH_DEST" "$remote_command"
}

case "$ACTION" in
  deploy)
    project_checks
    env_checks
    bash "$SKILL_ROOT/scripts/deploy-preflight.sh" "$ENV" "$APP"
    # 镜像分发不经宿主:目标机已有该镜像直接使用,缺失时经镜像仓库拉取;不构建,不从宿主直传镜像数据。
    if ! ssh_cli docker image inspect "$IMAGE" >/dev/null 2>&1; then
      echo "Image absent on target; pulling from registry: $IMAGE" >&2
      ssh_cli docker pull "$IMAGE" >/dev/null
    fi
    TARGET_ID=$(ssh_cli docker image inspect --format '{{.Id}}' "$IMAGE") || { echo "Image unavailable on target: $IMAGE" >&2; exit 3; }
    [[ "$TARGET_ID" =~ ^sha256:[0-9a-f]{64}$ ]] || { echo 'Target returned unexpected image ID' >&2; exit 3; }
    if [[ "$ENV" == prod && "${FF_REQUIRE_DEV_PROOF:-1}" == 1 ]]; then
      # 晋级门禁在本机核对:dev 收据记录本机执行的验证,按目标机 Image ID 关联。
      RECEIPT_FILE="$HOME/.mv/container-deploy/receipts/$APP/${TARGET_ID//:/-}"
      [[ -f "$RECEIPT_FILE" ]] || { echo 'Image has no verified dev deployment receipt; deploy to dev first (or explicitly set FF_REQUIRE_DEV_PROOF=0 after risk review)' >&2; exit 3; }
    fi
    COMPOSE=${FF_COMPOSE_FILE:-}
    if [[ -z "$COMPOSE" ]]; then
      if [[ -f compose.delivery.yml ]]; then COMPOSE=compose.delivery.yml; else COMPOSE="$SKILL_ROOT/templates/compose.delivery.yml"; fi
    fi
    [[ -f "$COMPOSE" ]] || { echo "Missing Compose file: $COMPOSE" >&2; exit 3; }
    ssh "${SSH_OPTS[@]}" "$SSH_DEST" "mkdir -p '.mv/container-deploy/$APP' && chmod 700 '.mv/container-deploy/$APP'"
    scp "${SCP_OPTS[@]}" "$COMPOSE" "$SSH_DEST:.mv/container-deploy/$APP/compose.yml" >/dev/null
    scp "${SCP_OPTS[@]}" ".env.$ENV" "$SSH_DEST:.mv/container-deploy/$APP/.env.$ENV" >/dev/null
    # scp 落盘到 target-runner 收紧权限之间有窗口,立即按 600 收口。
    ssh "${SSH_OPTS[@]}" "$SSH_DEST" "chmod 600 '.mv/container-deploy/$APP/.env.$ENV'"
    OUTPUT=$(ssh_cli bash -s -- deploy "$ENV" "$APP" "$IMAGE" "${FF_HEALTH_URL:-}" "${FF_READY_TIMEOUT:-}" < "$HERE/target-runner.sh")
    printf '%s\n' "$OUTPUT"
    if [[ "$ENV" == dev && "$OUTPUT" == *"VERIFIED_HEALTH=strong"* ]]; then
      # 文件名不沿用 Image ID 原文:sha256:xxx 的冒号在 Windows 是 NTFS 备用数据流语义,统一替换为连字符。
      RECEIPT_DIR="$HOME/.mv/container-deploy/receipts/$APP"
      RECEIPT_FILE="$RECEIPT_DIR/${TARGET_ID//:/-}"
      mkdir -p "$RECEIPT_DIR"
      chmod 700 "$RECEIPT_DIR"
      printf '%s\n' "$IMAGE" > "$RECEIPT_FILE"
      chmod 600 "$RECEIPT_FILE"
      echo "DEV_RECEIPT=$TARGET_ID"
    elif [[ "$ENV" == dev ]]; then
      echo 'No promotable dev receipt: set FF_HEALTH_URL to the readiness endpoint and redeploy' >&2
    fi
    ;;
  status|rollback)
    ssh_cli bash -s -- "$ACTION" "$ENV" "$APP" '' "${FF_HEALTH_URL:-}" "${FF_READY_TIMEOUT:-}" < "$HERE/target-runner.sh"
    ;;
esac
