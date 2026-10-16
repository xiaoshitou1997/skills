#!/usr/bin/env bash
# Deploy prebuilt immutable images and manage promotion/rollback (delivery side of the pipeline).
# Windows 团队规范:容器部署一律经 WSL,没有 WSL 就失败,禁止本机直接启动应用(见 scripts/wsl-bridge.sh)。
# 镜像由 mv-local-debug 在宿主出包后构建;本脚本只做预检、传输、启动、健康验证、收据与回滚。
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
WSL_DISTRO=''
WSL_HOME=''

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

# SSH reconstructs remote commands through a shell; reject metacharacters in pass-through values.
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
SSH_DEST=""
SSH_KEY=""
if [[ "$ENV" == prod ]]; then
  SSH_DEST=${FF_PROD_SSH:-}
  SSH_KEY=${FF_PROD_SSH_KEY:-}
  [[ -n "$SSH_DEST" ]] || { echo 'FF_PROD_SSH must be set' >&2; exit 3; }
else
  SSH_DEST=${FF_DEV_SSH:-}
  SSH_KEY=${FF_DEV_SSH_KEY:-}
fi

# Explicitly constrain identity syntax; SSH will validate host keys with user's configured known_hosts.
if [[ "$ENV" == prod && -n "${FF_DEV_SSH:-}" && "$SSH_DEST" == "${FF_DEV_SSH}" ]]; then
  echo "Dev and prod cannot use the same SSH target and app directory" >&2; exit 3
fi
if [[ -n "$SSH_DEST" && ! "$SSH_DEST" =~ ^[a-zA-Z0-9_.-]+@[a-zA-Z0-9_.-]+$ ]]; then
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

init_runtime() {
  # Windows 无 WSL 时 bridge distro 直接失败,给出安装指引;FF_WSL_BRIDGE=0 仅供测试/CI。
  WSL_DISTRO=$("$HERE/wsl-bridge.sh" distro)
  WSL_HOME=''
  if [[ -n "$WSL_DISTRO" ]]; then
    bash "$HERE/wsl-bridge.sh" require >/dev/null
    WSL_HOME=$(bash "$HERE/wsl-bridge.sh" home)
  else
    command -v docker >/dev/null 2>&1 || { echo 'Docker not installed' >&2; exit 3; }
  fi
}

# 统一 docker 入口:桥接模式下在 WSL 内执行,并关闭 MSYS 路径转换,防止 /mnt、镜像、路径参数被改写。
docker_cli() {
  if [[ -n "$WSL_DISTRO" ]]; then
    MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' wsl.exe -d "$WSL_DISTRO" -- docker "$@"
  else
    docker "$@"
  fi
}

# 在 WSL 内执行任意命令(桥接模式专用);调用方保证 WSL_DISTRO 非空。
wsl_bash() {
  MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' wsl.exe -d "$WSL_DISTRO" -- "$@"
}

case "$ACTION" in
  deploy)
    project_checks
    env_checks
    init_runtime
    bash "$SKILL_ROOT/scripts/deploy-preflight.sh" "$ENV" "$APP"
    docker_cli image inspect "$IMAGE" >/dev/null 2>&1 || { echo "Image missing locally: $IMAGE (build first)" >&2; exit 3; }
    LOCAL_ID=$(docker_cli image inspect --format '{{.Id}}' "$IMAGE")
    # 收据/发布历史与运行状态同侧保存:桥接模式在 WSL 的用户目录,否则在本机用户目录。
    RECEIPT_ROOT=${WSL_HOME:-$HOME}
    RECEIPT_DIR="$RECEIPT_ROOT/.mv/container-deploy/receipts/$APP"
    # 文件名不能沿用 Image ID 原文:native 回退路径下 sha256:xxx 的冒号是 NTFS 备用数据流语义,
    # 统一冒号替换为连字符(WSL/远端 Linux 与 Windows 三侧一致)。
    RECEIPT_FILE="$RECEIPT_DIR/${LOCAL_ID//:/-}"
    if [[ "$ENV" == prod && "${FF_REQUIRE_DEV_PROOF:-1}" == 1 ]]; then
      if [[ -n "$WSL_DISTRO" ]]; then
        wsl_bash bash -c 'test -f "$1"' _ "$RECEIPT_FILE" || { echo 'Image has no verified dev deployment receipt; deploy to dev first (or explicitly set FF_REQUIRE_DEV_PROOF=0 after risk review)' >&2; exit 3; }
      else
        [[ -f "$RECEIPT_FILE" ]] || { echo 'Image has no verified dev deployment receipt; deploy to dev first (or explicitly set FF_REQUIRE_DEV_PROOF=0 after risk review)' >&2; exit 3; }
      fi
    fi
    COMPOSE=${FF_COMPOSE_FILE:-}
    if [[ -z "$COMPOSE" ]]; then
      if [[ -f compose.delivery.yml ]]; then COMPOSE=compose.delivery.yml; else COMPOSE="$SKILL_ROOT/templates/compose.delivery.yml"; fi
    fi
    [[ -f "$COMPOSE" ]] || { echo "Missing Compose file: $COMPOSE" >&2; exit 3; }
    if [[ -n "$SSH_DEST" ]]; then
      ssh "${SSH_OPTS[@]}" "$SSH_DEST" "mkdir -p '.mv/container-deploy/$APP' && chmod 700 '.mv/container-deploy/$APP'"
      # Stream immutable image data; no registry and no remote source compilation.
      docker_cli save "$IMAGE" | ssh "${SSH_OPTS[@]}" "$SSH_DEST" docker load >/dev/null
      REMOTE_ID=$(ssh "${SSH_OPTS[@]}" "$SSH_DEST" docker image inspect --format '{{.Id}}' "$IMAGE")
      [[ "$LOCAL_ID" == "$REMOTE_ID" ]] || { echo 'Transferred image ID mismatch' >&2; exit 3; }
      scp "${SCP_OPTS[@]}" "$COMPOSE" "$SSH_DEST:.mv/container-deploy/$APP/compose.yml" >/dev/null
      scp "${SCP_OPTS[@]}" ".env.$ENV" "$SSH_DEST:.mv/container-deploy/$APP/.env.$ENV" >/dev/null
      # scp 落盘到 target-runner 收紧权限之间有窗口,立即按 600 收口。
      ssh "${SSH_OPTS[@]}" "$SSH_DEST" "chmod 600 '.mv/container-deploy/$APP/.env.$ENV'"
      OUTPUT=$(ssh "${SSH_OPTS[@]}" "$SSH_DEST" bash -s -- deploy "$ENV" "$APP" "$IMAGE" "${FF_HEALTH_URL:-}" "${FF_READY_TIMEOUT:-}" < "$HERE/target-runner.sh")
      printf '%s\n' "$OUTPUT"
    else
      if [[ -n "$WSL_DISTRO" ]]; then
        APPDIR="$WSL_HOME/.mv/container-deploy/$APP"
        bash "$HERE/wsl-bridge.sh" push "$COMPOSE" "$APPDIR/compose.yml"
        bash "$HERE/wsl-bridge.sh" push ".env.$ENV" "$APPDIR/.env.$ENV"
        bash "$HERE/wsl-bridge.sh" plain "$HERE/target-runner.sh"
        OUTPUT=$(wsl_bash bash -s -- deploy "$ENV" "$APP" "$IMAGE" "${FF_HEALTH_URL:-}" "${FF_READY_TIMEOUT:-}" < "$HERE/target-runner.sh")
      else
        DIR="$HOME/.mv/container-deploy/$APP"
        mkdir -p "$DIR"
        chmod 700 "$DIR"
        cp -- "$COMPOSE" "$DIR/compose.yml"
        cp -- ".env.$ENV" "$DIR/.env.$ENV"
        OUTPUT=$(bash "$HERE/target-runner.sh" deploy "$ENV" "$APP" "$IMAGE" "${FF_HEALTH_URL:-}" "${FF_READY_TIMEOUT:-}")
      fi
      printf '%s\n' "$OUTPUT"
    fi
    if [[ "$ENV" == dev && "$OUTPUT" == *"VERIFIED_HEALTH=strong"* ]]; then
      if [[ -n "$WSL_DISTRO" ]]; then
        printf '%s\n' "$IMAGE" | wsl_bash bash -c 'mkdir -p "$1" && chmod 700 "$1" && cat > "$2" && chmod 600 "$2"' _ "$RECEIPT_DIR" "$RECEIPT_FILE"
      else
        mkdir -p "$RECEIPT_DIR"
        chmod 700 "$RECEIPT_DIR"
        printf '%s\n' "$IMAGE" > "$RECEIPT_FILE"
        chmod 600 "$RECEIPT_FILE"
      fi
      echo "DEV_RECEIPT=$LOCAL_ID"
    elif [[ "$ENV" == dev ]]; then
      echo 'No promotable dev receipt: configure Docker HEALTHCHECK or FF_HEALTH_URL and redeploy' >&2
    fi
    ;;
  status|rollback)
    if [[ -n "$SSH_DEST" ]]; then
      ssh "${SSH_OPTS[@]}" "$SSH_DEST" bash -s -- "$ACTION" "$ENV" "$APP" '' "${FF_HEALTH_URL:-}" "${FF_READY_TIMEOUT:-}" < "$HERE/target-runner.sh"
    else
      init_runtime
      if [[ -n "$WSL_DISTRO" ]]; then
        bash "$HERE/wsl-bridge.sh" plain "$HERE/target-runner.sh"
        wsl_bash bash -s -- "$ACTION" "$ENV" "$APP" '' "${FF_HEALTH_URL:-}" "${FF_READY_TIMEOUT:-}" < "$HERE/target-runner.sh"
      else
        bash "$HERE/target-runner.sh" "$ACTION" "$ENV" "$APP" '' "${FF_HEALTH_URL:-}" "${FF_READY_TIMEOUT:-}"
      fi
    fi
    ;;
esac
