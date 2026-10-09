#!/usr/bin/env bash
# Runs at the delivery target; does not print env contents. Records only verified releases.
set -euo pipefail
umask 077
ACTION=${1:-}
ENV=${2:-}
APP=${3:-}
IMAGE=${4:-}
HEALTH_URL=${5:-}
[[ "$ACTION" =~ ^(deploy|rollback|status)$ && "$ENV" =~ ^(dev|prod)$ ]] || exit 2
[[ "$APP" =~ ^[a-z][a-z0-9_-]{0,62}$ ]] || exit 2
DIR="$HOME/.local/share/skills/$APP"
cd "$DIR"
[[ -f compose.yml && -f ".env.$ENV" ]] || { echo 'Missing deployed Compose/env files' >&2; exit 3; }
chmod 600 ".env.$ENV"
DOCKER=(docker compose --env-file ".env.$ENV" -f compose.yml -p "$APP")

check_service() {
  local candidate=$1
  local attempt id health status all_ok probe_ok=0 missing_health=0
  for attempt in {1..25}; do
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
          if [[ -z "$HEALTH_URL" && "$ENV" == prod ]]; then
            echo 'Production requires a Docker healthcheck or FF_HEALTH_URL' >&2; return 1
          fi
          ;;
        *) echo "Container health: $health" >&2; return 1 ;;
      esac
    done
    if [[ -n "$HEALTH_URL" ]]; then
      command -v curl >/dev/null 2>&1 || { echo 'curl required for HTTP probe' >&2; return 1; }
      if curl --fail --silent --show-error --max-time 4 "$HEALTH_URL" >/dev/null 2>&1; then
        probe_ok=1
      else
        probe_ok=0
      fi
    else
      probe_ok=1
    fi
    if [[ "$all_ok" == 1 && "$probe_ok" == 1 ]]; then
      if [[ -n "$HEALTH_URL" || "$missing_health" == 0 ]]; then
        VERIFIED_HEALTH=strong
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

case "$ACTION" in
  status)
    IMG=$(cat current-image 2>/dev/null || true)
    [[ -n "$IMG" ]] || { echo 'No previously verified deployment' >&2; exit 3; }
    FF_IMAGE="$IMG" "${DOCKER[@]}" ps
    echo "CURRENT_IMAGE=$IMG"
    ;;
  deploy|rollback)
    if [[ "$ACTION" == rollback ]]; then
      [[ -f previous-image ]] || { echo 'No previous verified image' >&2; exit 3; }
      IMAGE=$(cat previous-image)
    fi
    [[ "$IMAGE" =~ ^[a-zA-Z0-9][a-zA-Z0-9._:/@-]{0,199}$ ]] || { echo 'Invalid image ref' >&2; exit 2; }
    docker image inspect "$IMAGE" >/dev/null 2>&1 || { echo 'Image absent on target' >&2; exit 3; }
    OLD=$(cat current-image 2>/dev/null || true)
    # Must attempt restore on startup failure as well as readiness failure.
    if ! FF_IMAGE="$IMAGE" "${DOCKER[@]}" up -d --no-build --pull never || ! check_service "$IMAGE"; then
      echo 'Deployment verification failed' >&2
      if [[ -n "$OLD" && "$OLD" != "$IMAGE" ]] && docker image inspect "$OLD" >/dev/null 2>&1; then
        echo "Trying application rollback to $OLD (database state is NOT rolled back)" >&2
        FF_IMAGE="$OLD" "${DOCKER[@]}" up -d --no-build --pull never || true
        check_service "$OLD" || echo 'Previous application did not become healthy' >&2
      fi
      exit 4
    fi
    if [[ -n "$OLD" && "$OLD" != "$IMAGE" ]]; then printf '%s\n' "$OLD" > previous-image; fi
    printf '%s\n' "$IMAGE" > current-image
    ID=$(docker image inspect --format '{{.Id}}' "$IMAGE")
    # TSV history contains no secret environment values.
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$ACTION" "$ENV" "$IMAGE" "$ID" "$VERIFIED_HEALTH" >> releases.tsv
    echo "DEPLOYED_IMAGE=$IMAGE"
    echo "IMAGE_ID=$ID"
    echo "VERIFIED_HEALTH=$VERIFIED_HEALTH"
    FF_IMAGE="$IMAGE" "${DOCKER[@]}" ps
    ;;
esac
