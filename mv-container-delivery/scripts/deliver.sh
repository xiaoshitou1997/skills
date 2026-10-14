#!/usr/bin/env bash
# Package prebuilt artifacts into thin runtime images and deploy. Requires bash, Docker/Compose, SSH for remote targets.
# Windows 团队规范:镜像构建与容器一律经 WSL,没有 WSL 就失败,禁止本机直接启动应用(见 scripts/wsl-bridge.sh)。
# 编译出包在宿主完成(工具链见 mv-toolchain-manager);本脚本只检测产物、打瘦镜像、部署。
# 镜像常驻:构建与部署只新增镜像/替换容器,任何流程不得 rmi/prune/清理镜像。
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
  echo 'Usage: deliver.sh build dev|prod APP' >&2
  echo '       deliver.sh deploy dev|prod APP IMAGE [--approve-prod]' >&2
  echo '       deliver.sh status dev|prod APP' >&2
  echo '       deliver.sh rollback dev|prod APP [--approve-prod]' >&2
  exit 2
}

[[ "$ACTION" =~ ^(build|deploy|status|rollback)$ ]] || usage
[[ "$ENV" =~ ^(dev|prod)$ ]] || usage
[[ "$APP" =~ ^[a-z][a-z0-9_-]{0,62}$ ]] || { echo 'APP must be lowercase letters/digits/hyphens/underscores' >&2; exit 2; }
if [[ "$ACTION" == deploy ]]; then
  [[ "$IMAGE" =~ ^[a-zA-Z0-9][a-zA-Z0-9._:/@-]{0,199}$ ]] || { echo 'Unsafe or empty image ref' >&2; exit 2; }
fi
if [[ "$ENV" == prod && "$ACTION" != status ]]; then
  if [[ "$ACTION" == rollback ]]; then APPROVAL=${4:-}; fi
  [[ "$APPROVAL" == --approve-prod || "$ACTION" == build ]] || { echo 'Production mutation requires --approve-prod after explicit user authorization' >&2; exit 3; }
fi

# SSH reconstructs remote commands through a shell; reject metacharacters in pass-through values.
if [[ -n "${FF_HEALTH_URL:-}" && ! "${FF_HEALTH_URL}" =~ ^https?://[a-zA-Z0-9._:/-]+$ ]]; then
  echo 'FF_HEALTH_URL contains unsupported characters; use a simple http(s) health URL without query/credentials' >&2
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
  [[ -n "$SSH_DEST" || "$ACTION" == build ]] || { echo 'FF_PROD_SSH must be set' >&2; exit 3; }
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

# 产物检测:编译出包由项目在宿主完成,这里只按栈约定定位产物,不做任何编译。
# Gradle 取 build/libs 唯一 boot jar(排除 -plain/-sources);Maven 取 target 唯一 jar
# (排除 -sources/-javadoc/original-*);Node 取 dist/ 或 build/。FF_ARTIFACT 显式指定
# 时优先(文件→app.jar,目录→app/),供多模块或自定义布局使用。
find_artifact() {
  if [[ -n "${FF_ARTIFACT:-}" ]]; then
    [[ -e "$FF_ARTIFACT" ]] || { echo "FF_ARTIFACT 不存在: $FF_ARTIFACT" >&2; exit 3; }
    if [[ -d "$FF_ARTIFACT" ]]; then ARTIFACT_DIR=$FF_ARTIFACT; else ARTIFACT=$FF_ARTIFACT; fi
    return 0
  fi
  if [[ -f pom.xml ]]; then
    ARTIFACT=$(ls -1t target/*.jar 2>/dev/null | grep -vE -- '-(sources|javadoc)\.jar$' | grep -v '/original-' | head -n 1 || true)
    [[ -n "$ARTIFACT" ]] || { echo '未在 target/ 找到可交付 jar;先在宿主出包(如 mvn -B package,工具链准备见 mv-toolchain-manager),或用 FF_ARTIFACT 指定产物' >&2; exit 3; }
  elif [[ -f build.gradle || -f build.gradle.kts ]]; then
    ARTIFACT=$(ls -1t build/libs/*.jar 2>/dev/null | grep -vE -- '-(plain|sources)\.jar$' | head -n 1 || true)
    [[ -n "$ARTIFACT" ]] || { echo '未在 build/libs/ 找到可交付 boot jar;先在宿主出包(如 ./gradlew bootJar),或用 FF_ARTIFACT 指定产物' >&2; exit 3; }
  elif [[ -f package.json ]]; then
    if [[ -d dist ]]; then ARTIFACT_DIR=dist; elif [[ -d build ]]; then ARTIFACT_DIR=build; fi
    [[ -n "$ARTIFACT_DIR" ]] || { echo '未找到 dist/ 或 build/ 静态产物;先在宿主出包(如 npm run build),或用 FF_ARTIFACT 指定产物目录' >&2; exit 3; }
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
  build)
    project_checks
    # 栈检测决定瘦模板;产物必须在宿主已构建完成。
    if [[ -f Dockerfile.delivery ]]; then
      TEMPLATE=Dockerfile.delivery
    elif [[ -f pom.xml || -f build.gradle || -f build.gradle.kts ]]; then
      TEMPLATE="$SKILL_ROOT/templates/Dockerfile.jar"
    elif [[ -f package.json ]]; then
      TEMPLATE="$SKILL_ROOT/templates/Dockerfile.web"
    else
      echo 'Unsupported project: build the artifact on the host and provide a thin Dockerfile.delivery' >&2; exit 3
    fi
    find_artifact
    init_runtime
    REPO=${FF_IMAGE_REPO:-$APP}
    [[ "$REPO" =~ ^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,140}$ ]] || { echo 'Unsafe image repo' >&2; exit 2; }
    SHA=$(git rev-parse --short=12 HEAD 2>/dev/null || echo unversioned)
    DIRTY=''
    if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      if [[ -n "$(git status --porcelain)" ]]; then DIRTY='-dirty'; fi
    else
      DIRTY='-dirty'
    fi
    TAG="${SHA}${DIRTY}-$(date -u +%Y%m%d%H%M%S)"
    IMAGE="$REPO:$TAG"
    # 瘦上下文:只含产物与 Dockerfile。桥接模式经 push 管道直灌 WSL ext4(产物不落
    # Windows 盘中间态,push 自带密文校验,读到密文即报错);native 模式用本地临时目录。
    ARGS=()
    [[ -z "${FF_RUNTIME_IMAGE:-}" ]] || ARGS+=(--build-arg "RUNTIME_IMAGE=$FF_RUNTIME_IMAGE")
    if [[ -n "$WSL_DISTRO" ]]; then
      BUILD_DIR="$WSL_HOME/.local/share/skills/build/$APP"
      wsl_bash bash -c 'rm -rf "$1" && mkdir -p "$1"' _ "$BUILD_DIR"
      # 传输只经透读者(git/bash)通道:透明加密机器上 MSYS coreutils 读到密文,
      # 不能作为传输通道,也不用 grep 预检(会把健康产物误判为密文)。
      if [[ -n "$ARTIFACT" ]]; then
        if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
          BLOB=$(git hash-object -w -- "$ARTIFACT")
          git cat-file blob "$BLOB" | wsl_bash bash -c 'cat > "$1"' _ "$BUILD_DIR/app.jar"
        else
          wsl_bash bash -c 'cat > "$1"' _ "$BUILD_DIR/app.jar" < "$ARTIFACT"
        fi
        echo "ARTIFACT=$ARTIFACT"
      else
        if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
          TMPIDX=$(mktemp "${TMPDIR:-/tmp}/deliver-idx.XXXXXX")
          GIT_INDEX_FILE="$TMPIDX" git read-tree --empty
          GIT_INDEX_FILE="$TMPIDX" git add -- "$ARTIFACT_DIR" || { rm -f "$TMPIDX"; echo "无法把 $ARTIFACT_DIR 加入临时索引" >&2; exit 3; }
          TREE=$(GIT_INDEX_FILE="$TMPIDX" git write-tree)
          GIT_INDEX_FILE="$TMPIDX" git archive "$TREE" | wsl_bash bash -c 'mkdir -p "$1" && tar -xf - -C "$1"' _ "$BUILD_DIR"
          rm -f "$TMPIDX"
          wsl_bash mv "$BUILD_DIR/$ARTIFACT_DIR" "$BUILD_DIR/app"
        else
          echo '静态产物目录进 WSL 需要 git 仓库(经 git archive 管道);请初始化 git 或改用 FF_ARTIFACT 指定文件' >&2
          exit 3
        fi
        echo "ARTIFACT_DIR=$ARTIFACT_DIR"
      fi
      wsl_bash bash -c 'cat > "$1"' _ "$BUILD_DIR/Dockerfile" < "$TEMPLATE"
      # 基础镜像由 --pull 在 WSL 内拉取并常驻缓存;构建产物镜像只增不删。
      wsl_bash env DOCKER_BUILDKIT=1 docker build --pull -f "$BUILD_DIR/Dockerfile" -t "$IMAGE" "${ARGS[@]}" "$BUILD_DIR"
    else
      if [[ -n "$ARTIFACT" ]]; then
        bash "$HERE/wsl-bridge.sh" plain "$ARTIFACT"
        echo "ARTIFACT=$ARTIFACT"
      else
        echo "ARTIFACT_DIR=$ARTIFACT_DIR"
      fi
      CTX=$(mktemp -d "${TMPDIR:-/tmp}/deliver-ctx.XXXXXX")
      # 清理尽力而为:删除失败只告警不失败,不能让临时目录问题毒化交付结果。
      trap 'rm -rf "$CTX" 2>/dev/null || echo "WARNING: 临时上下文清理失败,可手动删除: $CTX" >&2' EXIT
      if [[ -n "$ARTIFACT" ]]; then
        cp -- "$ARTIFACT" "$CTX/app.jar"
      else
        mkdir -p "$CTX/app"
        cp -R -- "$ARTIFACT_DIR/." "$CTX/app/"
      fi
      cp -- "$TEMPLATE" "$CTX/Dockerfile"
      DOCKER_BUILDKIT=1 docker build --pull -f "$CTX/Dockerfile" -t "$IMAGE" "${ARGS[@]}" "$CTX"
    fi
    if [[ "${FF_REQUIRE_SECURITY_SCAN:-0}" == 1 ]]; then
      if [[ -n "$WSL_DISTRO" ]]; then
        bash "$HERE/wsl-bridge.sh" plain "$SKILL_ROOT/scripts/security-scan.sh"
        cat "$SKILL_ROOT/scripts/security-scan.sh" | wsl_bash bash -s image "$IMAGE"
      else
        bash "$SKILL_ROOT/scripts/security-scan.sh" image "$IMAGE"
      fi
    fi
    echo "IMAGE=$IMAGE"
    docker_cli image inspect --format 'IMAGE_ID={{.Id}}' "$IMAGE"
    ;;
  deploy)
    project_checks
    env_checks
    init_runtime
    bash "$SKILL_ROOT/scripts/deploy-preflight.sh" "$ENV" "$APP"
    docker_cli image inspect "$IMAGE" >/dev/null 2>&1 || { echo "Image missing locally: $IMAGE (build first)" >&2; exit 3; }
    LOCAL_ID=$(docker_cli image inspect --format '{{.Id}}' "$IMAGE")
    # 收据/发布历史与运行状态同侧保存:桥接模式在 WSL 的用户目录,否则在本机用户目录。
    RECEIPT_ROOT=${WSL_HOME:-$HOME}
    RECEIPT_DIR="$RECEIPT_ROOT/.local/share/skills/receipts/$APP"
    RECEIPT_FILE="$RECEIPT_DIR/$LOCAL_ID"
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
      ssh "${SSH_OPTS[@]}" "$SSH_DEST" "mkdir -p '.local/share/skills/$APP' && chmod 700 '.local/share/skills/$APP'"
      # Stream immutable image data; no registry and no remote source compilation.
      docker_cli save "$IMAGE" | ssh "${SSH_OPTS[@]}" "$SSH_DEST" docker load >/dev/null
      LOCAL_ID=$(docker_cli image inspect --format '{{.Id}}' "$IMAGE")
      REMOTE_ID=$(ssh "${SSH_OPTS[@]}" "$SSH_DEST" docker image inspect --format '{{.Id}}' "$IMAGE")
      [[ "$LOCAL_ID" == "$REMOTE_ID" ]] || { echo 'Transferred image ID mismatch' >&2; exit 3; }
      scp "${SCP_OPTS[@]}" "$COMPOSE" "$SSH_DEST:.local/share/skills/$APP/compose.yml" >/dev/null
      scp "${SCP_OPTS[@]}" ".env.$ENV" "$SSH_DEST:.local/share/skills/$APP/.env.$ENV" >/dev/null
      OUTPUT=$(ssh "${SSH_OPTS[@]}" "$SSH_DEST" bash -s -- deploy "$ENV" "$APP" "$IMAGE" "${FF_HEALTH_URL:-}" < "$HERE/target-runner.sh")
      printf '%s\n' "$OUTPUT"
    else
      if [[ -n "$WSL_DISTRO" ]]; then
        APPDIR="$WSL_HOME/.local/share/skills/$APP"
        bash "$HERE/wsl-bridge.sh" push "$COMPOSE" "$APPDIR/compose.yml"
        bash "$HERE/wsl-bridge.sh" push ".env.$ENV" "$APPDIR/.env.$ENV"
        bash "$HERE/wsl-bridge.sh" plain "$HERE/target-runner.sh"
        OUTPUT=$(wsl_bash bash -s -- deploy "$ENV" "$APP" "$IMAGE" "${FF_HEALTH_URL:-}" < "$HERE/target-runner.sh")
      else
        DIR="$HOME/.local/share/skills/$APP"
        mkdir -p "$DIR"
        chmod 700 "$DIR"
        cp -- "$COMPOSE" "$DIR/compose.yml"
        cp -- ".env.$ENV" "$DIR/.env.$ENV"
        OUTPUT=$(bash "$HERE/target-runner.sh" deploy "$ENV" "$APP" "$IMAGE" "${FF_HEALTH_URL:-}")
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
      ssh "${SSH_OPTS[@]}" "$SSH_DEST" bash -s -- "$ACTION" "$ENV" "$APP" '' "${FF_HEALTH_URL:-}" < "$HERE/target-runner.sh"
    else
      init_runtime
      if [[ -n "$WSL_DISTRO" ]]; then
        bash "$HERE/wsl-bridge.sh" plain "$HERE/target-runner.sh"
        wsl_bash bash -s -- "$ACTION" "$ENV" "$APP" '' "${FF_HEALTH_URL:-}" < "$HERE/target-runner.sh"
      else
        bash "$HERE/target-runner.sh" "$ACTION" "$ENV" "$APP" '' "${FF_HEALTH_URL:-}"
      fi
    fi
    ;;
esac
