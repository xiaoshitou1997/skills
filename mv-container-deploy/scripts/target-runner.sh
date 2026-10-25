#!/usr/bin/env bash
# Runs at the delivery target; does not print env contents. Records only verified releases.
# 版本化交付:版本清单 versions/<VERSION>.tsv(service<TAB>image<TAB>imageID)是运行状态源;
# 部署=整栈启动验证后快照为新版本清单;回退=按上一版清单经 compose.override.yml 恢复,
# 默认整栈回退,FF_ROLLBACK_SERVICE 限定单服务(不移动 current-version)。
# 镜像常驻:本脚本只启动/替换容器并追加记录文件,任何分支都不得 rmi/prune/删除镜像。
set -euo pipefail
umask 077
ACTION=${1:-}
ENV=${2:-}
APP=${3:-}
IMAGE=${4:-}
HEALTH_URL=${5:-}
READY_SECS=${6:-50}
VERSION=${7:-}
SERVICE=${8:-}
[[ "$ACTION" =~ ^(deploy|rollback|status|plan)$ && "$ENV" =~ ^(dev|prod)$ ]] || exit 2
[[ "$APP" =~ ^[a-z][a-z0-9_-]{0,62}$ ]] || exit 2
[[ "$READY_SECS" =~ ^[0-9]+$ ]] || { echo 'READY_SECS must be a positive integer (seconds)' >&2; exit 2; }
if [[ "$ACTION" == deploy ]]; then
  [[ "$VERSION" =~ ^version_[0-9]{14}_[a-z0-9]{1,40}(-dirty)?$ ]] || { echo "Invalid version id: $VERSION" >&2; exit 2; }
else
  [[ -z "$VERSION" ]] || { echo 'VERSION only applies to deploy' >&2; exit 2; }
  [[ -z "$SERVICE" || "$SERVICE" =~ ^[a-zA-Z0-9][a-zA-Z0-9_-]*$ ]] || { echo 'Invalid service name' >&2; exit 2; }
fi
DIR="$HOME/.mv/container-deploy/$APP"
cd "$DIR"
[[ -f compose.yml && -f ".env.$ENV" ]] || { echo 'Missing deployed Compose/env files' >&2; exit 3; }
chmod 600 ".env.$ENV"
DOCKER=(docker compose --env-file ".env.$ENV" -f compose.yml -p "$APP")
VERSIONS_DIR="$DIR/versions"
CURRENT="$DIR/current-version"
mkdir -p "$VERSIONS_DIR"

check_service() {
  local candidate=$1
  local attempt id health status all_ok missing_health=0
  # prod 门禁只认 readiness:必须显式提供 FF_HEALTH_URL;HEALTHCHECK 属 liveness 观测位,不构成门禁。
  if [[ "$ENV" == prod && -z "$HEALTH_URL" ]]; then
    echo 'Production requires FF_HEALTH_URL pointing at the readiness endpoint' >&2
    return 1
  fi
  # 就绪轮询上限默认 50 秒(25 次 × 2 秒),覆盖常规 Spring Boot/静态前端的启动窗口;
  # 慢启动大应用用 FF_READY_TIMEOUT(秒)放大,由 deploy.sh 透传到目标机。
  local attempts=$(( READY_SECS / 2 ))
  if (( attempts < 1 )); then attempts=1; fi
  for attempt in $(seq 1 "$attempts"); do
    id=$(FF_IMAGE="$candidate" "${DOCKER[@]}" ps -q)
    [[ -n "$id" ]] || { echo 'No compose containers started' >&2; return 1; }
    all_ok=1
    missing_health=0
    for container in $id; do
      health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container")
      status=$(docker inspect --format '{{.State.Status}}' "$container")
      [[ "$status" == running ]] || { echo "Container status: $status" >&2; return 1; }
      case "$health" in
        healthy) ;;
        starting) all_ok=0 ;;
        none)
          missing_health=1
          ;;
        *) echo "Container health: $health" >&2; return 1 ;;
      esac
    done
    # 收据门禁只认 readiness(FF_HEALTH_URL 指向的 HTTP 端点);
    # Docker HEALTHCHECK 属 liveness 观测位,单独通过不产生可晋级收据。
    if [[ -n "$HEALTH_URL" ]]; then
      command -v curl >/dev/null 2>&1 || { echo 'curl required for HTTP probe' >&2; return 1; }
      if curl --fail --silent --show-error --max-time 4 "$HEALTH_URL" >/dev/null 2>&1; then
        VERIFIED_HEALTH=strong
        return 0
      fi
    elif [[ "$all_ok" == 1 ]]; then
      if [[ "$missing_health" == 0 ]]; then
        VERIFIED_HEALTH=liveness-only
        echo 'NOTE: liveness (Docker HEALTHCHECK) only; set FF_HEALTH_URL to the readiness endpoint for a promotable receipt' >&2
      else
        VERIFIED_HEALTH=running-only
        echo 'NOTE: dev running without a health probe; cannot promote this deployment to prod' >&2
      fi
      return 0
    fi
    sleep 2
  done
  echo 'Timed out waiting for container or HTTP readiness' >&2
  return 1
}

# 目标机镜像分发:清单里缺哪个镜像拉哪个,全部就位并核对 Image ID 后才启动;不构建,不经宿主直传。
ensure_images() {
  local img
  for img in $("${DOCKER[@]}" config --images); do
    if ! docker image inspect "$img" >/dev/null 2>&1; then
      echo "Image absent on target; pulling from registry: $img" >&2
      docker pull "$img" >/dev/null
    fi
    docker image inspect --format '{{.Id}}' "$img" >/dev/null
  done
}

# 运行态快照:service<TAB>image<TAB>imageID,逐行输出。只统计 running 容器。
snapshot_manifest() {
  local line svc img cid
  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    svc=${line%%$'\t'*}
    img=${line#*$'\t'}
    cid=$("${DOCKER[@]}" ps -q "$svc")
    [[ -n "$cid" ]] || { echo "No container for service $svc" >&2; return 1; }
    printf '%s\t%s\t%s\n' "$svc" "$img" "$(docker inspect --format '{{.Id}}' "$cid")"
  done < <("${DOCKER[@]}" ps --format '{{.Service}}\t{{.Image}}')
}

# 把版本清单落为 compose.override.yml 再 up:compose 合并后只重建镜像变化的 service。
apply_manifest() {
  local file=$1 svc img
  {
    printf 'services:\n'
    while IFS=$'\t' read -r svc img _; do
      [[ -n "$svc" ]] || continue
      printf '  %s:\n    image: %s\n' "$svc" "$img"
    done < "$file"
  } > compose.override.yml
  # 单服务模板 image 字段是 ${FF_IMAGE:?};回退/恢复路径以清单首行镜像充当。
  FF_IMAGE=$(head -n 1 "$file" | cut -f2) "${DOCKER[@]}" up -d --no-build --pull never
}

record_releases() {
  # TSV 发布记录:时间/动作/环境/版本/服务/镜像/Image ID/验证档位;不含 secret 环境值。
  local ts action ver file
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  action=$1
  ver=$2
  file=$3
  while IFS=$'\t' read -r svc img id; do
    [[ -n "$svc" ]] || continue
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$ts" "$action" "$ENV" "$ver" "$svc" "$img" "$id" "$VERIFIED_HEALTH" >> releases.tsv
  done < "$file"
}

print_manifest() {
  local svc img id
  while IFS=$'\t' read -r svc img id; do
    [[ -n "$svc" ]] || continue
    printf 'MANIFEST_LINE=%s\t%s\t%s\n' "$svc" "$img" "$id"
  done < "$1"
}

case "$ACTION" in
  status)
    VER=$(cat "$CURRENT" 2>/dev/null || true)
    [[ -n "$VER" ]] || { echo 'No previously verified deployment' >&2; exit 3; }
    "${DOCKER[@]}" ps
    echo "CURRENT_VERSION=$VER"
    ;;
  plan)
    # 只读预检:把即将部署的镜像全部分发就位并输出 PLAN_LINE=<image>\t<imageID>,供本机晋级门禁核对。
    ensure_images
    img=''
    for img in $("${DOCKER[@]}" config --images); do
      printf 'PLAN_LINE=%s\t%s\n' "$img" "$(docker image inspect --format '{{.Id}}' "$img")"
    done
    ;;
  deploy)
    [[ "$IMAGE" =~ ^[a-zA-Z0-9][a-zA-Z0-9._:/@-]{0,199}$ ]] || { echo 'Invalid image ref' >&2; exit 2; }
    rm -f compose.override.yml
    ensure_images
    OLD_VERSION=$(cat "$CURRENT" 2>/dev/null || true)
    # Must attempt restore of the previous version on startup or readiness failure.
    if ! FF_IMAGE="$IMAGE" "${DOCKER[@]}" up -d --no-build --pull never || ! check_service "$IMAGE"; then
      echo 'Deployment verification failed' >&2
      if [[ -n "$OLD_VERSION" && -f "$VERSIONS_DIR/$OLD_VERSION.tsv" ]]; then
        echo "Trying application rollback to $OLD_VERSION (database state is NOT rolled back)" >&2
        apply_manifest "$VERSIONS_DIR/$OLD_VERSION.tsv" || true
        check_service "$(head -n 1 "$VERSIONS_DIR/$OLD_VERSION.tsv" | cut -f3)" || echo 'Previous application did not become healthy' >&2
      fi
      exit 4
    fi
    snapshot_manifest > "$VERSIONS_DIR/$VERSION.tsv"
    [[ -s "$VERSIONS_DIR/$VERSION.tsv" ]] || { echo 'Empty version manifest; refusing to record' >&2; exit 4; }
    printf '%s\n' "$VERSION" > "$CURRENT"
    record_releases deploy "$VERSION" "$VERSIONS_DIR/$VERSION.tsv"
    echo "VERSION=$VERSION"
    echo "DEPLOYED_IMAGE=$IMAGE"
    echo "VERIFIED_HEALTH=$VERIFIED_HEALTH"
    print_manifest "$VERSIONS_DIR/$VERSION.tsv"
    "${DOCKER[@]}" ps
    ;;
  rollback)
    [[ -f "$CURRENT" ]] || { echo 'No deployed version to roll back from' >&2; exit 3; }
    CUR=$(cat "$CURRENT")
    PREV=''
    while IFS= read -r v; do
      v=${v%.tsv}
      if [[ "$v" == "$CUR" ]]; then break; fi
      PREV=$v
    done < <(ls "$VERSIONS_DIR" | sort)
    [[ -n "$PREV" && -f "$VERSIONS_DIR/$PREV.tsv" ]] || { echo "No previous version to roll back to (current: $CUR)" >&2; exit 3; }
    TARGET_MANIFEST="$VERSIONS_DIR/$PREV.tsv"
    TARGET_VER="$PREV"
    if [[ -n "$SERVICE" ]]; then
      awk -F'\t' -v s="$SERVICE" '$1 == s' "$TARGET_MANIFEST" > "$DIR/.rollback-service.tsv"
      [[ -s "$DIR/.rollback-service.tsv" ]] || { echo "Service $SERVICE not in version $PREV" >&2; exit 3; }
      TARGET_MANIFEST="$DIR/.rollback-service.tsv"
    fi
    if ! apply_manifest "$TARGET_MANIFEST" || ! check_service "$(head -n 1 "$TARGET_MANIFEST" | cut -f3)"; then
      echo 'Rollback verification failed; restoring current version' >&2
      apply_manifest "$VERSIONS_DIR/$CUR.tsv" || true
      check_service "$(head -n 1 "$VERSIONS_DIR/$CUR.tsv" | cut -f3)" || true
      exit 4
    fi
    if [[ -z "$SERVICE" ]]; then
      printf '%s\n' "$PREV" > "$CURRENT"
    fi
    record_releases rollback "$TARGET_VER" "$TARGET_MANIFEST"
    echo "ROLLED_BACK_TO=$TARGET_VER"
    echo "VERIFIED_HEALTH=$VERIFIED_HEALTH"
    print_manifest "$TARGET_MANIFEST"
    "${DOCKER[@]}" ps
    ;;
esac
