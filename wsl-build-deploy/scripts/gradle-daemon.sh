#!/usr/bin/env bash
# Gradle 常驻 daemon 容器:在 WSL/Linux 内执行,由 deliver.sh build 对默认 Gradle 模板路径自动调用,也可手动使用。
# 原理:构建树固定在 <ws_dir>(deliver.sh 将暂存树整树替换到此),daemon 容器常驻挂载该目录,
# Gradle 配置/依赖缓存存于命名卷;相比每次 docker build 内冷启动 JVM,增量构建少付配置开销。
# 镜像常驻:本脚本只新增镜像/容器/卷,任何分支不得 rmi、删卷或 prune。
# 用法:gradle-daemon.sh ensure|build|status <ws_dir> <app> [gradle 任务...]
#   build 未给任务时依次取 FF_GRADLE_TASKS(空格分隔)、默认 build(与镜像内构建行为一致)。
# 环境变量:FF_GRADLE_IMAGE(默认 gradle:8-jdk17)、FF_GRADLE_UID(默认 1000,需与构建树属主一致)。
set -euo pipefail

usage() {
  echo 'Usage: gradle-daemon.sh ensure|build|status <ws_dir> <app> [gradle tasks...]' >&2
  exit 2
}

[[ $# -ge 3 ]] || usage
SUB=$1
WS_DIR=$2
APP=$3
shift 3
[[ "$SUB" =~ ^(ensure|build|status)$ ]] || usage
[[ "$APP" =~ ^[a-z][a-z0-9_-]{0,62}$ ]] || { echo 'APP must be lowercase letters/digits/hyphens/underscores' >&2; exit 2; }
[[ -d "$WS_DIR" ]] || { echo "Not a directory: $WS_DIR" >&2; exit 3; }
if [[ "$SUB" != status ]]; then
  [[ -f "$WS_DIR/build.gradle" || -f "$WS_DIR/build.gradle.kts" ]] || { echo "No Gradle build in $WS_DIR" >&2; exit 3; }
fi

GRADLE_IMAGE=${FF_GRADLE_IMAGE:-gradle:8-jdk17}
GRADLE_UID=${FF_GRADLE_UID:-1000}
CONTAINER=ff-gradle-daemon-$APP
VOLUME=ff-gradle-home-$APP

command -v docker >/dev/null 2>&1 || { echo 'Docker not installed' >&2; exit 3; }

container_running() {
  docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null || true
}

ensure_image() {
  docker image inspect "$GRADLE_IMAGE" >/dev/null 2>&1 || docker pull "$GRADLE_IMAGE"
}

ensure_volume() {
  if ! docker volume inspect "$VOLUME" >/dev/null 2>&1; then
    docker volume create "$VOLUME" >/dev/null
    # 新卷根目录默认 root:root;按目标 uid 一次性初始化,否则 gradle 用户写不进缓存。
    docker run --rm --user 0 -v "$VOLUME":/gradle-home "$GRADLE_IMAGE" \
      chown "$GRADLE_UID:$GRADLE_UID" /gradle-home
  fi
}

ensure_container() {
  local state
  state=$(container_running)
  if [[ -n "$state" && "$state" != true ]]; then
    # 已存在但停止:镜像若与当前 FF_GRADLE_IMAGE 漂移则重建容器(只删容器,不删镜像)。
    if [[ "$(docker inspect -f '{{.Config.Image}}' "$CONTAINER")" != "$GRADLE_IMAGE" ]]; then
      docker rm -f "$CONTAINER" >/dev/null
      state=''
    else
      docker start "$CONTAINER" >/dev/null
      return 0
    fi
  fi
  if [[ "$state" == true ]]; then
    return 0
  fi
  ensure_image
  ensure_volume
  docker run -d --name "$CONTAINER" \
    --restart unless-stopped \
    --user "$GRADLE_UID:$GRADLE_UID" \
    -e GRADLE_USER_HOME=/gradle-home \
    -e HOME=/home/gradle \
    -v "$WS_DIR":/workspace \
    -v "$VOLUME":/gradle-home \
    "$GRADLE_IMAGE" sleep infinity >/dev/null
}

# 与 templates/Dockerfile.gradle 的产物选择规则一致:唯一 boot jar,拒绝歧义。
select_boot_jar() {
  local jars=()
  mapfile -t jars < <(find "$WS_DIR/build/libs" -maxdepth 1 -type f -name '*.jar' \
    ! -name '*-plain.jar' ! -name '*-sources.jar' 2>/dev/null || true)
  if [[ ${#jars[@]} -ne 1 ]]; then
    echo "Expected exactly 1 boot jar under build/libs, found ${#jars[@]}; multi-module or custom layouts need Dockerfile.delivery" >&2
    exit 3
  fi
  mkdir -p "$WS_DIR/out"
  cp "${jars[0]}" "$WS_DIR/out/app.jar"
  [[ -s "$WS_DIR/out/app.jar" ]] || { echo 'out/app.jar is empty' >&2; exit 3; }
  echo "OUT_JAR=$(basename "${jars[0]}")"
}

daemon_build() {
  local tasks=()
  if [[ $# -gt 0 ]]; then
    tasks=("$@")
  elif [[ -n "${FF_GRADLE_TASKS:-}" ]]; then
    read -r -a tasks <<< "$FF_GRADLE_TASKS"
  else
    tasks=(build)
  fi
  local owner
  owner=$(stat -c %u "$WS_DIR")
  if [[ "$owner" != "$GRADLE_UID" ]]; then
    echo "WARNING: ws 目录属主 uid=$owner 与容器 uid=$GRADLE_UID 不一致,Gradle 可能无法写入;" >&2
    echo "请设置 FF_GRADLE_UID=$owner 或修正目录属主后重试" >&2
  fi
  ensure_container
  local launcher=(gradle)
  if [[ -f "$WS_DIR/gradlew" ]]; then
    launcher=(sh ./gradlew)
  fi
  local log rc=0
  log=$(mktemp)
  docker exec -e GRADLE_USER_HOME=/gradle-home -w /workspace "$CONTAINER" \
    "${launcher[@]}" --build-cache --console=plain ${tasks+"${tasks[@]}"} >"$log" 2>&1 || rc=$?
  if [[ $rc -ne 0 ]] && grep -q 'Timeout waiting to lock' "$log"; then
    echo '检测到 Gradle 残留锁(fileHashes.lock 等);清理 .gradle 下 *.lock 后重试一次' >&2
    find "$WS_DIR" \( -path '*/.gradle/*.lock' -o -path '.gradle/*.lock' \) -type f -delete
    rc=0
    docker exec -e GRADLE_USER_HOME=/gradle-home -w /workspace "$CONTAINER" \
      "${launcher[@]}" --build-cache --console=plain ${tasks+"${tasks[@]}"} >"$log" 2>&1 || rc=$?
  fi
  cat "$log"
  rm -f "$log"
  [[ $rc -eq 0 ]] || { echo "Gradle daemon build failed (exit $rc)" >&2; exit "$rc"; }
  select_boot_jar
}

case "$SUB" in
  ensure)
    ensure_container
    echo "daemon=$CONTAINER state=$(container_running)"
    ;;
  build)
    daemon_build "$@"
    ;;
  status)
    echo "container=$CONTAINER volume=$VOLUME image=$GRADLE_IMAGE ws=$WS_DIR"
    local_state=$(container_running)
    if [[ -n "$local_state" ]]; then
      echo "container_state=$local_state image=$(docker inspect -f '{{.Config.Image}}' "$CONTAINER")"
    else
      echo 'container_state=absent'
    fi
    if docker volume inspect "$VOLUME" >/dev/null 2>&1; then
      echo 'volume_state=created'
    else
      echo 'volume_state=absent'
    fi
    ;;
esac
