#!/usr/bin/env bash
# Crane engine path: assemble runtime images on the host, no Docker daemon and no WSL.
# 适用:无 WSL(或显式选择 crane)时的 Java(Gradle/Maven)与 Node 项目,任意产物通用。
# 团队规范不变式:编译出包在宿主完成;不在宿主安装 Docker;镜像常驻,任何流程不得清理镜像。
# crane 走 registry 只读中转:拉取基础镜像必需;经 mutate --output 直出本地 tar,不要求可写仓库。
# 与 mv-container-deploy 的接口不变:输出 IMAGE=<repo>:<tag> 与 IMAGE_ID=sha256:...。
set -euo pipefail
umask 077

HERE=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SKILL_ROOT=$(dirname "$HERE")
ACTION=${1:-}
ENV=${2:-}
APP=${3:-}

usage() {
  echo 'Usage: crane-build.sh build dev|prod APP' >&2
  exit 2
}

[[ "$ACTION" == build ]] || usage
[[ "$ENV" =~ ^(dev|prod)$ ]] || usage
[[ "$APP" =~ ^[a-z][a-z0-9_-]{0,62}$ ]] || { echo 'APP must be lowercase letters/digits/hyphens/underscores' >&2; exit 2; }

command -v crane >/dev/null 2>&1 || { echo '未找到 crane;交 mv-toolchain-manager 按需准备(ensure --crane)并在同一会话激活后重试' >&2; exit 3; }

# Python 按环境选择(python3 / python / py -3),用于解析镜像 tar 与计算摘要。
pick_python() {
  if command -v python3 >/dev/null 2>&1; then echo python3
  elif command -v python >/dev/null 2>&1; then echo python
  elif command -v py >/dev/null 2>&1 && py -3 -c '' >/dev/null 2>&1; then echo 'py -3'
  else echo ''; fi
}

REPO=${FF_IMAGE_REPO:-$APP}
[[ "$REPO" =~ ^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,140}$ ]] || { echo 'Unsafe image repo' >&2; exit 2; }
# 镜像身份契约与 Docker 路径同源:Tag 公式、-dirty 规则、两行证据输出完全一致。
SHA=$(git rev-parse --short=12 HEAD 2>/dev/null || echo unversioned)
DIRTY=''
if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if [[ -n "$(git status --porcelain)" ]]; then DIRTY='-dirty'; fi
else
  DIRTY='-dirty'
fi
TAG="${SHA}${DIRTY}-$(date -u +%Y%m%d%H%M%S)"
IMAGE="$REPO:$TAG"

# 栈与模式:FF_STACK 显式指定(java|web|server);缺省按项目文件推断,与 Docker 路径同规则。
# 三种模式与瘦模板逐项对齐:java=eclipse-temurin:21-jre + /app/app.jar;web=nginx:alpine + html 根;server=node:24-alpine + /app。
STACK=${FF_STACK:-}
if [[ -z "$STACK" ]]; then
  if [[ -f pom.xml || -f build.gradle || -f build.gradle.kts ]]; then STACK=java
  elif [[ -f package.json ]]; then STACK=web
  else echo '无法识别项目栈(需 pom.xml、build.gradle(.kts) 或 package.json);用 FF_STACK=java|web|server 显式指定' >&2; exit 3; fi
fi
[[ "$STACK" == java || "$STACK" == web || "$STACK" == server ]] || { echo 'FF_STACK 只支持 java|web|server' >&2; exit 2; }

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

# 产物定位:java=单个 jar(→/app/app.jar);web/server=产物目录。FF_ARTIFACT 优先,其余按栈约定定位。
ARTIFACT=''
PAYLOAD_DIR=''
if [[ -n "${FF_ARTIFACT:-}" ]]; then
  [[ -e "$FF_ARTIFACT" ]] || { echo "FF_ARTIFACT 不存在: $FF_ARTIFACT" >&2; exit 3; }
  if [[ -d "$FF_ARTIFACT" ]]; then PAYLOAD_DIR=$FF_ARTIFACT; else ARTIFACT=$FF_ARTIFACT; fi
elif [[ "$STACK" == java ]]; then
  if [[ -f pom.xml ]]; then
    CANDS=$(ls -1t target/*.jar 2>/dev/null | grep -vE -- '-(sources|javadoc)\.jar$' | grep -v '/original-' || true)
    unique_artifact "$CANDS" || { echo '未在 target/ 找到可交付 jar;先在宿主出包(如 mvn -B package,工具链准备见 mv-toolchain-manager),或用 FF_ARTIFACT 指定' >&2; exit 3; }
  else
    CANDS=$(ls -1t build/libs/*.jar 2>/dev/null | grep -vE -- '-(plain|sources)\.jar$' || true)
    unique_artifact "$CANDS" || { echo '未在 build/libs/ 找到可交付 boot jar;先在宿主出包(如 ./gradlew bootJar),或用 FF_ARTIFACT 指定' >&2; exit 3; }
  fi
elif [[ "$STACK" == web ]]; then
  if [[ -d dist ]]; then PAYLOAD_DIR=dist; elif [[ -d build ]]; then PAYLOAD_DIR=build; else
    echo '未找到 dist/ 或 build/ 静态产物;先在宿主出包(如 npm run build),或用 FF_ARTIFACT 指定' >&2; exit 3; fi
else
  echo 'server 模式必须用 FF_ARTIFACT 指定产物目录' >&2
  exit 3
fi
if [[ "$STACK" == java && -z "$ARTIFACT" ]]; then
  echo "FF_ARTIFACT 必须是单个 jar 文件(java 模式): $PAYLOAD_DIR" >&2
  exit 3
fi
if [[ "$STACK" != java ]]; then
  [[ -n "$PAYLOAD_DIR" ]] || { echo "FF_ARTIFACT 必须是产物目录($STACK 模式): $ARTIFACT" >&2; exit 3; }
fi

# 产物守卫与 Docker 路径同源:.git 与 .env* 不进镜像层。
check_artifact_directory() (
  shopt -s dotglob nullglob globstar
  local path
  for path in "$1"/.git "$1"/.env* "$1"/**/.git "$1"/**/.env*; do
    if [[ -e "$path" || -L "$path" ]]; then
      echo "产物目录包含 .git 或 .env*;拒绝打入镜像: $path" >&2
      exit 3
    fi
  done
)
[[ -z "$PAYLOAD_DIR" ]] || check_artifact_directory "$PAYLOAD_DIR"

# 基镜像与配置:缺省值对齐 templates/Dockerfile.jar 与 Dockerfile.web。
case "$STACK" in
  java)   BASE=${FF_RUNTIME_IMAGE:-eclipse-temurin:21-jre} ;;
  web)    BASE=${FF_RUNTIME_IMAGE:-nginx:alpine} ;;
  server) BASE=${FF_RUNTIME_IMAGE:-node:24-alpine} ;;
esac

# 分层:staging 组装 layer tar(java→/app/app.jar,web→nginx 默认根,server→/app),过程文件用完即清。
STAGE=$(mktemp -d "${TMPDIR:-/tmp}/crane-layer.XXXXXX")
LAYER="$STAGE/layer.tar"
trap 'rm -rf "$STAGE" 2>/dev/null || echo "WARNING: 分层暂存清理失败,可手动删除: $STAGE" >&2' EXIT
if [[ "$STACK" == java ]]; then
  LAYER_ROOT='app'
  mkdir -p "$STAGE/app"
  cp -- "$ARTIFACT" "$STAGE/app/app.jar"
elif [[ "$STACK" == web ]]; then
  LAYER_ROOT='usr/share/nginx/html'
  mkdir -p "$STAGE/$LAYER_ROOT"
  cp -R -- "$PAYLOAD_DIR"/. "$STAGE/$LAYER_ROOT/"
else
  LAYER_ROOT='app'
  mkdir -p "$STAGE/app"
  cp -R -- "$PAYLOAD_DIR"/. "$STAGE/app/"
fi
tar -C "$STAGE" -cf "$LAYER" "${LAYER_ROOT%%/*}"

# 运行时配置:与瘦模板的 ENTRYPOINT/WORKDIR/USER/EXPOSE 同源;FF_ENTRYPOINT 可覆盖入口。
MUTATE_ARGS=(--append "$LAYER")
case "$STACK" in
  java)
    MUTATE_ARGS+=(--workdir /app --user 10001 --exposed-ports 8080)
    MUTATE_ARGS+=(--entrypoint "${FF_ENTRYPOINT:-java,-jar,/app/app.jar}")
    ;;
  web)
    MUTATE_ARGS+=(--exposed-ports 80)
    [[ -z "${FF_ENTRYPOINT:-}" ]] || MUTATE_ARGS+=(--entrypoint "$FF_ENTRYPOINT")
    ;;
  server)
    [[ -n "${FF_ENTRYPOINT:-}" ]] || { echo 'server 模式必须用 FF_ENTRYPOINT 指定入口(逗号分隔,如 node,dist/server.js)' >&2; exit 3; }
    MUTATE_ARGS+=(--workdir /app --entrypoint "$FF_ENTRYPOINT")
    ;;
esac

TAR_OUT=${FF_IMAGE_TAR:-crane-image.tar}
echo "MODE=$STACK BASE=$BASE"
echo "BUILD_CMD=crane mutate ${MUTATE_ARGS[*]} -o $TAR_OUT"
# 只读中转:拉取基础镜像、附加产物层、写入运行时配置,结果直出本地 tar,不推送任何仓库。
crane mutate "$BASE" "${MUTATE_ARGS[@]}" -o "$TAR_OUT"
echo "ARTIFACT=$TAR_OUT"

PY=$(pick_python)
[[ -n "$PY" ]] || { echo '需要 Python 解析镜像 tar 的 manifest;未找到 python3/python/py;由 mv-toolchain-manager 按需准备(ensure --python 3.12);宿主完全没有 Python 时先执行其 scripts/installer/bootstrap-python.sh 3.12,在同一会话中激活后重试' >&2; exit 3; }
# RepoTags 补写:mutate --output 的 tar 不携带 Tag,补上 IMAGE 使 docker load 后按引用可寻址;
# 同时返回 Config 文件名;格式异常即失败,不产出损坏镜像。
CONFIG_FILE=$("$PY" - "$TAR_OUT" "$IMAGE" <<'PYEOF'
import io, json, sys, tarfile
tar_path, image = sys.argv[1], sys.argv[2]
with tarfile.open(tar_path) as t:
    manifest = json.load(t.extractfile('manifest.json'))
    if len(manifest) != 1:
        raise SystemExit(f'unexpected manifest entries: {len(manifest)}')
    # 立即读出成员字节:extractfile 返回的是绑定外层 tarfile 的惰性视图,关闭后不可读。
    members = [(m, t.extractfile(m).read() if m.isfile() else None) for m in t.getmembers()]
manifest[0]['RepoTags'] = [image]
with tarfile.open(tar_path + '.tmp', 'w') as out:
    for m, data in members:
        if m.name == 'manifest.json':
            payload = (json.dumps(manifest) + '\n').encode()
            m.size = len(payload)
            out.addfile(m, io.BytesIO(payload))
        else:
            out.addfile(m, io.BytesIO(data) if data is not None else None)
import os
os.replace(tar_path + '.tmp', tar_path)
print(manifest[0]['Config'])
PYEOF
) || { echo '无法解析镜像 tar 的 manifest.json;产物格式异常,人工核对后重试' >&2; exit 3; }
ID_HEX=$("$PY" - "$TAR_OUT" "$CONFIG_FILE" <<'PYEOF'
import hashlib, sys, tarfile
with tarfile.open(sys.argv[1]) as t:
    data = t.extractfile(sys.argv[2]).read()
print(hashlib.sha256(data).hexdigest())
PYEOF
) || { echo '无法从镜像 tar 读取镜像配置并计算摘要' >&2; exit 3; }
# 一致性守卫:manifest Config 文件名即镜像配置摘要,不一致说明产物格式异常,不输出假身份。
CONFIG_ID=${CONFIG_FILE%.json}
CONFIG_ID=${CONFIG_ID#sha256:}
if [[ "$CONFIG_ID" != "$ID_HEX" ]]; then
  echo "镜像 tar 一致性校验失败:manifest Config=$CONFIG_FILE 与配置摘要=$ID_HEX 不一致;人工核对产物后重试" >&2
  exit 3
fi

if [[ "${FF_REQUIRE_SECURITY_SCAN:-0}" == 1 ]]; then
  bash "$SKILL_ROOT/scripts/security-scan.sh" image-tar "$TAR_OUT"
else
  # 与 security-scan.sh 的诚实 SKIP 口径一致:默认路径也要明示未扫描,不留给读者猜测。
  echo 'SECURITY_SCAN=skipped: FF_REQUIRE_SECURITY_SCAN!=1,本镜像未做漏洞扫描(不是安全通过)' >&2
fi

echo "IMAGE=$IMAGE"
echo "IMAGE_ID=sha256:$ID_HEX"
