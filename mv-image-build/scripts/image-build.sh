#!/usr/bin/env bash
# Docker engine path: package prebuilt host artifacts into thin runtime images inside WSL.
# 团队规范:镜像构建默认经 WSL;无 WSL 时走同目录 crane-build.sh(crane 路径,Java/Node 通用);不在宿主安装 Docker。
# 编译出包在宿主完成(工具链见 mv-toolchain-manager);本脚本只检测产物、打瘦镜像、输出镜像身份。
# 镜像常驻:构建只新增镜像,任何流程不得 rmi/prune/清理镜像。
# 与 mv-container-deploy 的接口:输出 IMAGE=<repo>:<tag> 与 IMAGE_ID=...,部署侧只消费该镜像引用。
set -euo pipefail
umask 077

HERE=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SKILL_ROOT=$(dirname "$HERE")
ACTION=${1:-}
ENV=${2:-}
APP=${3:-}
WSL_DISTRO=''
WSL_HOME=''

usage() {
  echo 'Usage: image-build.sh build dev|prod APP' >&2
  exit 2
}

[[ "$ACTION" == build ]] || usage
[[ "$ENV" =~ ^(dev|prod)$ ]] || usage
[[ "$APP" =~ ^[a-z][a-z0-9_-]{0,62}$ ]] || { echo 'APP must be lowercase letters/digits/hyphens/underscores' >&2; exit 2; }

project_checks() {
  [[ -f .dockerignore ]] || { echo 'Missing .dockerignore; refuse sending unsanitized Docker build context' >&2; exit 3; }
  # This is a minimum guard; negative patterns and other secrets still need human review.
  grep -Eq '^\.env\*([[:space:]]|$)' .dockerignore || { echo '.dockerignore must contain .env*' >&2; exit 3; }
  grep -Eq '^\.git([[:space:]]|$)' .dockerignore || { echo '.dockerignore must contain .git' >&2; exit 3; }
  if grep -Eq '^![[:space:]]*\.env' .dockerignore; then
    echo 'Dangerous negated env ignore rule' >&2; exit 3
  fi
}

init_runtime() {
  # Windows 无 WSL 时 bridge distro 返回空走 native 前需先过 require;非 Windows 宿主 distro 直接返回空,native 分支查宿主 Docker。
  # FF_WSL_BRIDGE=0 仅供测试/CI。
  WSL_DISTRO=$(bash "$HERE/wsl-bridge.sh" distro)
  WSL_HOME=''
  if [[ -n "$WSL_DISTRO" ]]; then
    bash "$HERE/wsl-bridge.sh" require >/dev/null
    WSL_HOME=$(bash "$HERE/wsl-bridge.sh" home)
  else
    command -v docker >/dev/null 2>&1 || { echo 'Docker not installed' >&2; exit 3; }
  fi
}

# 契约要求唯一可交付产物:多候选拒绝并点名,由 FF_ARTIFACT 显式消歧,不按 mtime 静默猜测。
unique_artifact() {
  local cands=$1
  [[ -n "$cands" ]] || return 1
  case $cands in
    *$'\n'*)
      echo '检测到多个可交付产物,交付契约要求唯一;用 FF_ARTIFACT 显式指定其一:' >&2
      printf '%s\n' "$cands" >&2
      exit 3 ;;
  esac
  ARTIFACT=$cands
}

# 产物检测:编译出包由项目在宿主完成,这里只按栈约定定位产物,不做任何编译。
# Gradle 取 build/libs 唯一 boot jar(排除 -plain/-sources);Maven 取 target 唯一 jar
# (排除 -sources/-javadoc/original-*);Node 取 dist/ 或 build/。FF_ARTIFACT 显式指定
# 时优先(文件→app.jar,目录→app/),供多模块或自定义布局使用。
find_artifact() {
  ARTIFACT=''
  ARTIFACT_DIR=''
  if [[ -n "${FF_ARTIFACT:-}" ]]; then
    [[ -e "$FF_ARTIFACT" ]] || { echo "FF_ARTIFACT 不存在: $FF_ARTIFACT" >&2; exit 3; }
    if [[ -d "$FF_ARTIFACT" ]]; then ARTIFACT_DIR=$FF_ARTIFACT; else ARTIFACT=$FF_ARTIFACT; fi
    return 0
  fi
  if [[ -f pom.xml ]]; then
    CANDS=$(ls -1t target/*.jar 2>/dev/null | grep -vE -- '-(sources|javadoc)\.jar$' | grep -v '/original-' || true)
    unique_artifact "$CANDS" || { echo '未在 target/ 找到可交付 jar;先在宿主出包(如 mvn -B package,工具链准备见 mv-toolchain-manager),或用 FF_ARTIFACT 指定产物' >&2; exit 3; }
  elif [[ -f build.gradle || -f build.gradle.kts ]]; then
    CANDS=$(ls -1t build/libs/*.jar 2>/dev/null | grep -vE -- '-(plain|sources)\.jar$' || true)
    unique_artifact "$CANDS" || { echo '未在 build/libs/ 找到可交付 boot jar;先在宿主出包(如 ./gradlew bootJar),或用 FF_ARTIFACT 指定产物' >&2; exit 3; }
  elif [[ -f package.json ]]; then
    if [[ -d dist ]]; then ARTIFACT_DIR=dist; elif [[ -d build ]]; then ARTIFACT_DIR=build; fi
    [[ -n "$ARTIFACT_DIR" ]] || { echo '未找到 dist/ 或 build/ 静态产物;先在宿主出包(如 npm run build),或用 FF_ARTIFACT 指定产物目录' >&2; exit 3; }
  fi
  [[ -n "$ARTIFACT" || -n "$ARTIFACT_DIR" ]] || { echo '未找到可交付产物;先在宿主出包,并用 FF_ARTIFACT 指定产物文件或目录' >&2; exit 3; }
}

# 瘦上下文不会应用项目 .dockerignore;显式目录也不能把仓库元数据或环境秘密带入。
check_artifact_directory() (
  shopt -s dotglob nullglob globstar
  local path
  for path in "$ARTIFACT_DIR"/.git "$ARTIFACT_DIR"/.env* "$ARTIFACT_DIR"/**/.git "$ARTIFACT_DIR"/**/.env*; do
    if [[ -e "$path" || -L "$path" ]]; then
      echo "产物目录包含 .git 或 .env*;拒绝打入镜像,请用 FF_ARTIFACT 指定纯产物目录: $path" >&2
      exit 3
    fi
  done
)

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
    if [[ -n "$ARTIFACT_DIR" ]]; then check_artifact_directory; fi
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
      # 守卫:home 异常返回空串时 BUILD_DIR 会变成 WSL 根下的 /.mv,rm -rf 将误伤;为空即中止。
      [[ -n "$WSL_HOME" ]] || { echo '无法解析 WSL 用户目录(WSL_HOME 为空);中止,避免 rm -rf 误伤' >&2; exit 3; }
      BUILD_DIR="$WSL_HOME/.mv/image-build/build/$APP"
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
          # 选定目录本身作为临时工作树,归档根就是 app/ 的内容。先规范化目录,
          # 兼容 ./dist/、带空格路径与仓库内外的绝对目录,不拼接归档内部路径。
          ARTIFACT_DIR=$(CDPATH='' cd -- "$ARTIFACT_DIR" && pwd -P)
          PROJECT_GIT_DIR=$(git rev-parse --absolute-git-dir)
          TMPIDX=$(mktemp "${TMPDIR:-/tmp}/deliver-idx.XXXXXX")
          trap 'rm -f "$TMPIDX" 2>/dev/null || echo "WARNING: 临时索引清理失败,可手动删除: $TMPIDX" >&2' EXIT
          GIT_INDEX_FILE="$TMPIDX" git read-tree --empty
          # dist/build 通常被 .gitignore 忽略;只对显式选定的产物目录强制收录。
          GIT_INDEX_FILE="$TMPIDX" git -C "$ARTIFACT_DIR" --git-dir="$PROJECT_GIT_DIR" --work-tree="$ARTIFACT_DIR" add -f -- . || { echo "无法把 $ARTIFACT_DIR 加入临时索引" >&2; exit 3; }
          TREE=$(GIT_INDEX_FILE="$TMPIDX" git write-tree)
          git archive "$TREE" | wsl_bash bash -c 'mkdir -p "$1" && tar -xf - -C "$1"' _ "$BUILD_DIR/app"
          rm -f "$TMPIDX" 2>/dev/null || echo "WARNING: 临时索引清理失败,可手动删除: $TMPIDX" >&2
          trap - EXIT
        else
          echo '静态产物目录进 WSL 需要 git 仓库(经 git archive 管道);请初始化 git 或改用 FF_ARTIFACT 指定文件' >&2
          exit 3
        fi
        echo "ARTIFACT_DIR=$ARTIFACT_DIR"
      fi
      # Dockerfile 同样先过密文校验,不依赖 wsl_bash 通道自带的检查。
      bash "$HERE/wsl-bridge.sh" plain "$TEMPLATE"
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
        wsl_bash env "FF_REQUIRE_SECURITY_SCAN=$FF_REQUIRE_SECURITY_SCAN" bash -s -- image "$IMAGE" < "$SKILL_ROOT/scripts/security-scan.sh"
      else
        bash "$SKILL_ROOT/scripts/security-scan.sh" image "$IMAGE"
      fi
    else
      # 与 security-scan.sh 的诚实 SKIP 口径一致:默认路径也要明示未扫描,不留给读者猜测。
      echo 'SECURITY_SCAN=skipped: FF_REQUIRE_SECURITY_SCAN!=1,本镜像未做漏洞扫描(不是安全通过)' >&2
    fi
    echo "IMAGE=$IMAGE"
    docker_cli image inspect --format 'IMAGE_ID={{.Id}}' "$IMAGE"
    ;;
esac
