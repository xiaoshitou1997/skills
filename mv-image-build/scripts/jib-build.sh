#!/usr/bin/env bash
# Java 模块镜像路径:调用模块自己声明的 Jib 插件产出镜像 tar,再载入目标 Docker。
# 团队规范:镜像定义与模块同源(Java 在 pom/build.gradle 声明 Jib);本脚本只编排
# 「调用插件 -> 载入 WSL/本机 Docker -> 输出镜像身份」,不做任何编译或镜像配置覆盖。
# 编译出包在宿主完成(工具链见 mv-toolchain-manager);镜像常驻,不得 rmi/prune。
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
  echo 'Usage: jib-build.sh build dev|prod APP' >&2
  exit 2
}

[[ "$ACTION" == build ]] || usage
[[ "$ENV" =~ ^(dev|prod)$ ]] || usage
[[ "$APP" =~ ^[a-z][a-z0-9_-]{0,62}$ ]] || { echo 'APP must be lowercase letters/digits/hyphens/underscores' >&2; exit 2; }

# 项目文件可能位于端点透明加密目录;优先让 git 读工作区(git 进程读明文),
# 读不到再退回 grep。只用于判断插件是否在模块内声明,不解析构建文件。
file_contains() {
  local pattern=$1 file=$2
  if command -v git >/dev/null 2>&1 &&
     git -C . rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git grep --no-index -q -e "$pattern" -- "$file" 2>/dev/null && return 0
  fi
  grep -q -e "$pattern" -- "$file" 2>/dev/null
}

# 模块目录:默认当前目录;多模块项目在目标模块目录执行,或显式 FF_JIB_PROJECT 指定。
PROJECT_DIR=${FF_JIB_PROJECT:-.}
[[ -d "$PROJECT_DIR" ]] || { echo "FF_JIB_PROJECT 不是目录: $PROJECT_DIR" >&2; exit 3; }
cd "$PROJECT_DIR"

BUILD_TOOL=''
if [[ -f pom.xml ]]; then
  BUILD_TOOL=maven
  file_contains 'jib-maven-plugin' pom.xml || {
    echo '本模块 pom.xml 未声明 jib-maven-plugin;镜像定义属模块配置,请先在模块内加入 Jib 插件与团队基线配置(见 references/build-contract.md)' >&2
    exit 3
  }
elif [[ -f build.gradle || -f build.gradle.kts ]]; then
  BUILD_TOOL=gradle
  GRADLE_FILE=build.gradle
  [[ -f build.gradle ]] || GRADLE_FILE=build.gradle.kts
  file_contains 'com.google.cloud.tools.jib' "$GRADLE_FILE" || {
    echo "本模块 $GRADLE_FILE 未应用 com.google.cloud.tools.jib;镜像定义属模块配置,请先在模块内应用 Jib 插件(见 references/build-contract.md)" >&2
    exit 3
  }
else
  echo '未找到 pom.xml 或 build.gradle(.kts);Java 模块镜像需由模块内的 Jib 插件定义' >&2
  exit 3
fi

# 宿主已出包的前置条件:Jib 消费项目自身产物,本脚本不做编译。
case "$BUILD_TOOL" in
  maven)
    [[ -d target ]] || {
      echo '未找到 target/;先在宿主出包(如 mvn -B package,工具链准备见 mv-toolchain-manager)' >&2
      exit 3
    }
    ;;
  gradle)
    [[ -d build/libs ]] || {
      echo '未找到 build/libs/;先在宿主出包(如 ./gradlew bootJar,工具链准备见 mv-toolchain-manager)' >&2
      exit 3
    }
    ;;
esac

init_runtime() {
  WSL_DISTRO=$(bash "$HERE/wsl-bridge.sh" distro)
  WSL_HOME=''
  if [[ -n "$WSL_DISTRO" ]]; then
    bash "$HERE/wsl-bridge.sh" require >/dev/null
    WSL_HOME=$(bash "$HERE/wsl-bridge.sh" home)
  else
    command -v docker >/dev/null 2>&1 || { echo 'Docker not installed' >&2; exit 3; }
  fi
}

# 统一 docker 入口:桥接模式下在 WSL 内执行,并关闭 MSYS 路径转换。
docker_cli() {
  if [[ -n "$WSL_DISTRO" ]]; then
    MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' wsl.exe -d "$WSL_DISTRO" --exec docker "$@"
  else
    docker "$@"
  fi
}

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

JIB_ARGS=(-Djib.to.image="$IMAGE")
[[ -z "${FF_RUNTIME_IMAGE:-}" ]] || JIB_ARGS+=(-Djib.from.image="$FF_RUNTIME_IMAGE")

if [[ "$BUILD_TOOL" == maven ]]; then
  TAR=${FF_IMAGE_TAR:-target/jib-image.tar}
  if [[ -f ./mvnw ]]; then MVN_CMD=(bash ./mvnw); else MVN_CMD=(mvn); fi
  BUILD_CMD=("${MVN_CMD[@]}" -B "${JIB_ARGS[@]}" jib:buildTar)
else
  TAR=${FF_IMAGE_TAR:-build/jib-image.tar}
  if [[ -f ./gradlew ]]; then
    GRADLE_CMD=(bash ./gradlew)
  elif [[ -n "${FF_GRADLEW:-}" ]]; then
    GRADLE_CMD=(bash "$FF_GRADLEW")
  else
    GRADLE_CMD=(gradle)
  fi
  BUILD_CMD=("${GRADLE_CMD[@]}" "${JIB_ARGS[@]}" jibBuildTar)
fi

rm -f -- "$TAR" 2>/dev/null || true
echo "BUILD_TOOL=$BUILD_TOOL TAR=$TAR"
echo "BUILD_CMD=${BUILD_CMD[*]}"
"${BUILD_CMD[@]}"
[[ -s "$TAR" ]] || {
  echo "Jib 未产出镜像 tar: $TAR;核对模块 Jib 配置的 outputPaths.tar,或用 FF_IMAGE_TAR 指定实际路径" >&2
  exit 3
}

init_runtime
if [[ -n "$WSL_DISTRO" ]]; then
  # 守卫:home 异常返回空串时目录会落到 WSL 根下;为空即中止。
  [[ -n "$WSL_HOME" ]] || { echo '无法解析 WSL 用户目录(WSL_HOME 为空);中止' >&2; exit 3; }
  WSL_DIR="$WSL_HOME/.mv/image-build/jib/$APP"
  MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' wsl.exe -d "$WSL_DISTRO" --exec bash -c 'mkdir -p "$1"' _ "$WSL_DIR"
  bash "$HERE/wsl-bridge.sh" push-bin "$TAR" "$WSL_DIR/jib-image.tar"
  bash "$HERE/wsl-bridge.sh" exec "$WSL_DIR" -- docker load -i "$WSL_DIR/jib-image.tar"
else
  docker load -i "$TAR"
fi

if [[ "${FF_REQUIRE_SECURITY_SCAN:-0}" == 1 ]]; then
  if [[ -n "$WSL_DISTRO" ]]; then
    bash "$HERE/wsl-bridge.sh" plain "$SKILL_ROOT/scripts/security-scan.sh"
    MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' wsl.exe -d "$WSL_DISTRO" --exec \
      env FF_REQUIRE_SECURITY_SCAN=1 bash -s -- image "$IMAGE" \
      < "$SKILL_ROOT/scripts/security-scan.sh"
  else
    bash "$SKILL_ROOT/scripts/security-scan.sh" image "$IMAGE"
  fi
else
  echo 'SECURITY_SCAN=skipped: FF_REQUIRE_SECURITY_SCAN!=1,本镜像未做漏洞扫描(不是安全通过)' >&2
fi

echo "IMAGE=$IMAGE"
docker_cli image inspect --format 'IMAGE_ID={{.Id}}' "$IMAGE"
