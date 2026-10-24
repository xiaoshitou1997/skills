#!/usr/bin/env bash
# 镜像构建编排(宿主侧):出包 → 打包上传 → 服务器构建。
# 宿主只编译二进制产物并打包上传,不装 Docker、不做任何容器操作;
# 镜像统一在 FF_BUILD_TARGET 指向的服务器上由服务器侧 docker build 产出。
# 流程:项目检查与产物定位 → 打包 tgz(产物 + Dockerfile)→ 生成版本 Tag
#   → SSH 上传到服务器 ~/.mv/image-build/packages/<app>/ → 服务器核对 SHA-256
#   → 解包 docker build --pull(按需 trivy 门禁)→ 追加包清单 manifest.tsv。
# 包与镜像同 Tag 一一对应,服务器侧常驻不自动清理;契约见 references/build-contract.md。
# 与 mv-container-deploy 的接口:输出 IMAGE=<repo>:<tag> 与 IMAGE_ID=...,部署侧只消费该镜像引用。
set -euo pipefail
umask 077

HERE=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SKILL_ROOT=$(dirname "$HERE")
ACTION=${1:-}
ENV=${2:-}
APP=${3:-}

usage() {
  echo 'Usage: image-build.sh build dev|prod APP' >&2
  echo '  FF_BUILD_TARGET   构建点 SSH 目标(user@host),必填;镜像统一在该服务器构建' >&2
  echo '  FF_ARTIFACT       可选。显式产物路径(文件或目录),缺省按栈自动发现' >&2
  echo '  FF_IMAGE_REPO     可选。镜像仓库名,缺省为 APP' >&2
  echo '  FF_RUNTIME_IMAGE  可选。基镜像 build-arg(Dockerfile.delivery 以 ARG RUNTIME_IMAGE 接收)' >&2
  echo '  FF_REQUIRE_SECURITY_SCAN=1  构建点 trivy 镜像扫描门禁(HIGH/CRITICAL 不过即失败)' >&2
  exit 2
}

[[ "$ACTION" == build ]] || usage
[[ "$ENV" =~ ^(dev|prod)$ ]] || usage
[[ "$APP" =~ ^[a-z][a-z0-9_-]{0,62}$ ]] || { echo 'APP must be lowercase letters/digits/hyphens/underscores' >&2; exit 2; }

# 构建点是唯一的镜像产出地,没有缺省:未显式指定时不猜。
TARGET=${FF_BUILD_TARGET:-}
[[ -n "$TARGET" ]] || { echo 'FF_BUILD_TARGET 未设置:构建点 SSH 目标(user@host)必填,镜像统一在该服务器构建' >&2; exit 2; }
[[ "$TARGET" =~ ^[A-Za-z0-9._-]{1,64}@[A-Za-z0-9][A-Za-z0-9.-]{0,253}$ ]] || { echo "FF_BUILD_TARGET 需为 user@host 形式: $TARGET" >&2; exit 2; }

project_checks() {
  [[ -f .dockerignore ]] || { echo 'Missing .dockerignore; refuse sending unsanitized Docker build context' >&2; exit 3; }
  # This is a minimum guard; negative patterns and other secrets still need human review.
  grep -Eq '^\.env\*([[:space:]]|$)' .dockerignore || { echo '.dockerignore must contain .env*' >&2; exit 3; }
  grep -Eq '^\.git([[:space:]]|$)' .dockerignore || { echo '.dockerignore must contain .git' >&2; exit 3; }
  if grep -Eq '^![[:space:]]*\.env' .dockerignore; then
    echo 'Dangerous negated env ignore rule' >&2; exit 3
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
# FF_ARTIFACT 显式指定时优先(文件→app.jar,目录→app/),供多模块或自定义布局使用。
find_artifact() {
  ARTIFACT=''
  ARTIFACT_DIR=''
  if [[ -n "${FF_ARTIFACT:-}" ]]; then
    [[ -e "$FF_ARTIFACT" ]] || { echo "FF_ARTIFACT 不存在: $FF_ARTIFACT" >&2; exit 3; }
    if [[ -d "$FF_ARTIFACT" ]]; then ARTIFACT_DIR=$FF_ARTIFACT; else ARTIFACT=$FF_ARTIFACT; fi
    return 0
  fi
  if [[ -f package.json ]]; then
    if [[ -d dist ]]; then ARTIFACT_DIR=dist; elif [[ -d build ]]; then ARTIFACT_DIR=build; fi
    [[ -n "$ARTIFACT_DIR" ]] || { echo '未找到 dist/ 或 build/ 静态产物;先在宿主出包(如 npm run build),或用 FF_ARTIFACT 指定产物目录' >&2; exit 3; }
  elif [[ -f Dockerfile.delivery && -f pom.xml ]]; then
    CANDS=$(ls -1t target/*.jar 2>/dev/null | grep -vE -- '-(sources|javadoc)\.jar$' | grep -v '/original-' || true)
    unique_artifact "$CANDS" || { echo '未在 target/ 找到可交付 jar;先在宿主出包(如 mvn -B package),或用 FF_ARTIFACT 指定产物' >&2; exit 3; }
  elif [[ -f Dockerfile.delivery ]] && { [[ -f build.gradle ]] || [[ -f build.gradle.kts ]]; }; then
    CANDS=$(ls -1t build/libs/*.jar 2>/dev/null | grep -vE -- '-(plain|sources)\.jar$' || true)
    unique_artifact "$CANDS" || { echo '未在 build/libs/ 找到可交付 boot jar;先在宿主出包(如 ./gradlew bootJar),或用 FF_ARTIFACT 指定产物' >&2; exit 3; }
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

# 密文头检查:透明加密机器上读到密文立即失败,不把密文当产物上传。
plain_check() {
  if LC_ALL=C grep -aq '%[A-Z][A-Z0-9]*-Header-[^%]' -- "$1"; then
    echo "读到密文(透明加密改写): $1;拒绝继续,请在可信上下文重试" >&2
    exit 3
  fi
}

case "$ACTION" in
  build)
    # 镜像定义与模块同源:各栈在模块内提供 Dockerfile.delivery(只做产物复制,不做编译);
    # Node 静态前端无自备文件时用本 skill 的瘦交付模板。
    if [[ -f Dockerfile.delivery ]]; then
      TEMPLATE=Dockerfile.delivery
    elif [[ -f package.json ]]; then
      TEMPLATE="$SKILL_ROOT/templates/Dockerfile.web"
    elif [[ -f pom.xml || -f build.gradle || -f build.gradle.kts ]]; then
      echo 'Java 模块的镜像定义随模块提交:在模块目录提供 Dockerfile.delivery(只做产物复制,不做编译),基线见 references/build-contract.md' >&2
      exit 3
    else
      echo 'Unsupported project: build the artifact on the host and provide a thin Dockerfile.delivery' >&2; exit 3
    fi
    project_checks
    find_artifact
    if [[ -n "$ARTIFACT_DIR" ]]; then check_artifact_directory; fi
    REPO=${FF_IMAGE_REPO:-$APP}
    [[ "$REPO" =~ ^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,140}$ ]] || { echo 'Unsafe image repo' >&2; exit 2; }
    [[ -z "${FF_RUNTIME_IMAGE:-}" ]] || [[ "$FF_RUNTIME_IMAGE" =~ ^[a-zA-Z0-9][a-zA-Z0-9._/:@-]{0,200}$ ]] || { echo 'Unsafe FF_RUNTIME_IMAGE' >&2; exit 2; }
    SHA=$(git rev-parse --short=12 HEAD 2>/dev/null || echo unversioned)
    DIRTY=''
    if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      if [[ -n "$(git status --porcelain)" ]]; then DIRTY='-dirty'; fi
    else
      DIRTY='-dirty'
    fi
    TAG="${SHA}${DIRTY}-$(date -u +%Y%m%d%H%M%S)"
    # Tag 会拼进远端路径与远端命令参数,先验证形态再使用,不把未校验值交给远端 shell。
    [[ "$TAG" =~ ^[a-z0-9]+(-dirty)?-[0-9]{14}$ ]] || { echo "非法 Tag: $TAG" >&2; exit 2; }
    IMAGE="$REPO:$TAG"
    UPLOAD_TS=$(date -u +%Y%m%d%H%M%S)

    # 打包:上下文只含产物与 Dockerfile。产物文件统一改名 app.jar,产物目录统一放 app/。
    STAGE=$(mktemp -d "${TMPDIR:-/tmp}/deliver-pkg.XXXXXX")
    trap 'rm -rf "$STAGE" 2>/dev/null || echo "WARNING: 临时打包目录清理失败,可手动删除: $STAGE" >&2' EXIT
    CTX="$STAGE/context"
    mkdir -p "$CTX"
    if [[ -n "$ARTIFACT" ]]; then
      # 透明加密机器上 coreutils 直读源文件可能得密文:git 仓库内走 git 读取通道出包,
      # 仓库外退回 cp,由包密文头检查与构建点 SHA-256 核对兜底。
      if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        BLOB=$(git hash-object -w -- "$ARTIFACT") || { echo "git 读取产物失败: $ARTIFACT" >&2; exit 3; }
        git cat-file blob "$BLOB" > "$CTX/app.jar"
      else
        cp -- "$ARTIFACT" "$CTX/app.jar"
      fi
      plain_check "$CTX/app.jar"
      echo "ARTIFACT=$ARTIFACT"
    else
      mkdir -p "$CTX/app"
      ARTIFACT_SRC=$ARTIFACT_DIR
      if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        # dist/build 通常被 .gitignore 忽略;用临时索引对显式选定的产物目录强制收录后归档。
        ARTIFACT_DIR=$(CDPATH='' cd -- "$ARTIFACT_DIR" && pwd -P)
        PROJECT_GIT_DIR=$(git rev-parse --absolute-git-dir)
        TMPIDX=$(mktemp "${TMPDIR:-/tmp}/deliver-idx.XXXXXX")
        GIT_INDEX_FILE="$TMPIDX" git read-tree --empty
        if ! GIT_INDEX_FILE="$TMPIDX" git -C "$ARTIFACT_DIR" --git-dir="$PROJECT_GIT_DIR" --work-tree="$ARTIFACT_DIR" add -f -- .; then
          rm -f "$TMPIDX" 2>/dev/null || true
          echo "无法把 $ARTIFACT_DIR 加入临时索引" >&2
          exit 3
        fi
        TREE=$(GIT_INDEX_FILE="$TMPIDX" git write-tree)
        git archive "$TREE" | tar -xf - -C "$CTX/app"
        rm -f "$TMPIDX" 2>/dev/null || true
      else
        cp -R -- "$ARTIFACT_DIR/." "$CTX/app/"
      fi
      echo "ARTIFACT_DIR=$ARTIFACT_SRC"
    fi
    cp -- "$TEMPLATE" "$CTX/Dockerfile"
    plain_check "$CTX/Dockerfile"
    PKG_NAME="${APP}-${TAG}.tgz"
    PKG="$STAGE/$PKG_NAME"
    tar -czf "$PKG" -C "$CTX" .
    # 包整体密文头检查:gzip 包首字节不可能是 %,读到即被透明加密改写。
    if [[ "$(head -c 1 -- "$PKG")" == '%' ]]; then
      echo '上传包读到密文头(透明加密);拒绝上传,请在可信上下文重试' >&2
      exit 3
    fi
    SHA256=$(sha256sum -- "$PKG" | cut -d' ' -f1)
    echo "PACKAGE=$PKG_NAME"
    echo "SHA256=$SHA256"
    echo "TARGET=$TARGET"

    # 上传:stdin 直灌服务器包目录;包常驻,不自动清理。
    ssh "$TARGET" "mkdir -p \"\$HOME/.mv/image-build/packages/$APP\" && cat > \"\$HOME/.mv/image-build/packages/$APP/$PKG_NAME\"" < "$PKG"

    # 服务器构建:一段脚本经 stdin 送抵构建点执行,取值只经位置参数传递,
    # 远端 shell 不解析任何宿主侧未校验文本。
    SERVER_SCRIPT="$STAGE/server.sh"
    cat > "$SERVER_SCRIPT" <<'SERVER_EOF'
set -euo pipefail
APP=$1; TAG=$2; PKG_NAME=$3; EXPECT_SHA=$4; GIT_REV=$5; IMAGE=$6; RUNTIME_IMAGE=$7; REQUIRE_SCAN=$8; UPLOAD_TS=$9
case "$APP$TAG" in *[!a-zA-Z0-9._-]*|'') echo 'unsafe build id' >&2; exit 3;; esac
BASE="$HOME/.mv/image-build"
PKG="$BASE/packages/$APP/$PKG_NAME"
ACTUAL=$(sha256sum "$PKG" | cut -d' ' -f1)
if [[ "$ACTUAL" != "$EXPECT_SHA" ]]; then
  echo "SHA-256 校验失败:期望 $EXPECT_SHA,实际 $ACTUAL;已删除损坏包,中止构建" >&2
  rm -f -- "$PKG"
  exit 3
fi
WORK="$BASE/build/$APP/$TAG"
rm -rf -- "$WORK"
mkdir -p "$WORK"
tar -xzf "$PKG" -C "$WORK"
cd "$WORK"
# trivy 是 FF_REQUIRE_SECURITY_SCAN=1 时的硬门禁:构建点缺 trivy 在构建前即失败,不降级。
if [[ "$REQUIRE_SCAN" == 1 ]] && ! command -v trivy >/dev/null 2>&1; then
  echo 'Trivy unavailable; image security gate not satisfied' >&2
  exit 3
fi
BUILD_ARGS=(--pull -f Dockerfile -t "$IMAGE")
if [[ -n "$RUNTIME_IMAGE" ]]; then BUILD_ARGS+=(--build-arg "RUNTIME_IMAGE=$RUNTIME_IMAGE"); fi
DOCKER_BUILDKIT=1 docker build "${BUILD_ARGS[@]}" .
if [[ "$REQUIRE_SCAN" == 1 ]]; then
  trivy image --exit-code 1 --severity HIGH,CRITICAL --no-progress "$IMAGE"
else
  # 与 security-scan.sh 的诚实 SKIP 口径一致:默认路径也要明示未扫描,不留给读者猜测。
  echo 'SECURITY_SCAN=skipped: FF_REQUIRE_SECURITY_SCAN!=1,本镜像未做漏洞扫描(不是安全通过)' >&2
fi
IMAGE_ID=$(docker image inspect --format '{{.Id}}' "$IMAGE")
BUILT_AT=$(date -u +%Y%m%d%H%M%S)
MANIFEST="$BASE/packages/$APP/manifest.tsv"
if [[ ! -f "$MANIFEST" ]]; then
  printf 'tag\tpackage\tsha256\tgit_rev\timage\timage_id\tuploaded_at\tbuilt_at\n' > "$MANIFEST"
fi
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$TAG" "$PKG_NAME" "$ACTUAL" "$GIT_REV" "$IMAGE" "$IMAGE_ID" "$UPLOAD_TS" "$BUILT_AT" >> "$MANIFEST"
echo "IMAGE=$IMAGE"
echo "IMAGE_ID=$IMAGE_ID"
cd "$BASE"
# 构建目录用后即清;安全软件可能短暂持有新提取文件的句柄,重试后仍失败则明示残留。
rm -rf -- "$WORK" 2>/dev/null || { sleep 1; rm -rf -- "$WORK" 2>/dev/null || { sleep 2; rm -rf -- "$WORK" 2>/dev/null || echo "WARNING: 构建目录清理失败,可手动删除: $WORK" >&2; }; }
SERVER_EOF
    # ssh 会把多个参数用空格拼接后交给远端 shell,空串参数会被吞掉;
    # 每个位置参数单引号包裹(取值均已按形态校验),空值才能在远端保持占位。
    ssh "$TARGET" "bash -s -- '$APP' '$TAG' '$PKG_NAME' '$SHA256' '${SHA}${DIRTY}' '$IMAGE' '${FF_RUNTIME_IMAGE:-}' '${FF_REQUIRE_SECURITY_SCAN:-0}' '$UPLOAD_TS'" < "$SERVER_SCRIPT"
    ;;
esac
