#!/usr/bin/env bash
# Docker-only build/deploy driver. Requires bash, Docker/Compose, SSH for remote targets.
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

case "$ACTION" in
  build)
    project_checks
    command -v docker >/dev/null 2>&1 || { echo 'Docker not installed' >&2; exit 3; }
    if [[ -f Dockerfile.delivery ]]; then
      DOCKERFILE=Dockerfile.delivery
    elif [[ -f pom.xml ]]; then
      DOCKERFILE="$SKILL_ROOT/templates/Dockerfile.maven"
    elif [[ -f build.gradle || -f build.gradle.kts ]]; then
      DOCKERFILE="$SKILL_ROOT/templates/Dockerfile.gradle"
    elif [[ -f package.json ]]; then
      DOCKERFILE="$SKILL_ROOT/templates/Dockerfile.node-static"
    else
      echo 'Unsupported project: provide a multistage Dockerfile.delivery' >&2; exit 3
    fi
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
    ARGS=()
    [[ -z "${FF_BUILD_IMAGE:-}" ]] || ARGS+=(--build-arg "BUILD_IMAGE=$FF_BUILD_IMAGE")
    [[ -z "${FF_RUNTIME_IMAGE:-}" ]] || ARGS+=(--build-arg "RUNTIME_IMAGE=$FF_RUNTIME_IMAGE")
    DOCKER_BUILDKIT=1 docker build --pull -f "$DOCKERFILE" -t "$IMAGE" "${ARGS[@]}" .
    if [[ "${FF_REQUIRE_SECURITY_SCAN:-0}" == 1 ]]; then
      bash "$SKILL_ROOT/scripts/security-scan.sh" image "$IMAGE"
    fi
    echo "IMAGE=$IMAGE"
    docker image inspect --format 'IMAGE_ID={{.Id}}' "$IMAGE"
    ;;
  deploy)
    project_checks
    env_checks
    command -v docker >/dev/null 2>&1 || { echo 'Docker not installed' >&2; exit 3; }
    bash "$SKILL_ROOT/scripts/deploy-preflight.sh" "$ENV" "$APP"
    docker image inspect "$IMAGE" >/dev/null 2>&1 || { echo "Image missing locally: $IMAGE (build first)" >&2; exit 3; }
    LOCAL_ID=$(docker image inspect --format '{{.Id}}' "$IMAGE")
    RECEIPT_DIR="$HOME/.local/share/skills/receipts/$APP"
    if [[ "$ENV" == prod && "${FF_REQUIRE_DEV_PROOF:-1}" == 1 ]]; then
      [[ -f "$RECEIPT_DIR/$LOCAL_ID" ]] || { echo 'Image has no verified dev deployment receipt; deploy to dev first (or explicitly set FF_REQUIRE_DEV_PROOF=0 after risk review)' >&2; exit 3; }
    fi
    COMPOSE=${FF_COMPOSE_FILE:-}
    if [[ -z "$COMPOSE" ]]; then
      if [[ -f compose.delivery.yml ]]; then COMPOSE=compose.delivery.yml; else COMPOSE="$SKILL_ROOT/templates/compose.delivery.yml"; fi
    fi
    [[ -f "$COMPOSE" ]] || { echo "Missing Compose file: $COMPOSE" >&2; exit 3; }
    if [[ -n "$SSH_DEST" ]]; then
      ssh "${SSH_OPTS[@]}" "$SSH_DEST" "mkdir -p '.local/share/skills/$APP' && chmod 700 '.local/share/skills/$APP'"
      # Stream immutable image data; no registry and no remote source compilation.
      docker save "$IMAGE" | ssh "${SSH_OPTS[@]}" "$SSH_DEST" docker load >/dev/null
      LOCAL_ID=$(docker image inspect --format '{{.Id}}' "$IMAGE")
      REMOTE_ID=$(ssh "${SSH_OPTS[@]}" "$SSH_DEST" docker image inspect --format '{{.Id}}' "$IMAGE")
      [[ "$LOCAL_ID" == "$REMOTE_ID" ]] || { echo 'Transferred image ID mismatch' >&2; exit 3; }
      scp "${SCP_OPTS[@]}" "$COMPOSE" "$SSH_DEST:.local/share/skills/$APP/compose.yml" >/dev/null
      scp "${SCP_OPTS[@]}" ".env.$ENV" "$SSH_DEST:.local/share/skills/$APP/.env.$ENV" >/dev/null
      OUTPUT=$(ssh "${SSH_OPTS[@]}" "$SSH_DEST" bash -s -- deploy "$ENV" "$APP" "$IMAGE" "${FF_HEALTH_URL:-}" < "$HERE/target-runner.sh")
      printf '%s\n' "$OUTPUT"
    else
      DIR="$HOME/.local/share/skills/$APP"
      mkdir -p "$DIR"
      chmod 700 "$DIR"
      cp -- "$COMPOSE" "$DIR/compose.yml"
      cp -- ".env.$ENV" "$DIR/.env.$ENV"
      OUTPUT=$(bash "$HERE/target-runner.sh" deploy "$ENV" "$APP" "$IMAGE" "${FF_HEALTH_URL:-}")
      printf '%s\n' "$OUTPUT"
    fi
    if [[ "$ENV" == dev && "$OUTPUT" == *"VERIFIED_HEALTH=strong"* ]]; then
      mkdir -p "$RECEIPT_DIR"
      chmod 700 "$RECEIPT_DIR"
      printf '%s\n' "$IMAGE" > "$RECEIPT_DIR/$LOCAL_ID"
      chmod 600 "$RECEIPT_DIR/$LOCAL_ID"
      echo "DEV_RECEIPT=$LOCAL_ID"
    elif [[ "$ENV" == dev ]]; then
      echo 'No promotable dev receipt: configure Docker HEALTHCHECK or FF_HEALTH_URL and redeploy' >&2
    fi
    ;;
  status|rollback)
    if [[ -n "$SSH_DEST" ]]; then
      ssh "${SSH_OPTS[@]}" "$SSH_DEST" bash -s -- "$ACTION" "$ENV" "$APP" '' "${FF_HEALTH_URL:-}" < "$HERE/target-runner.sh"
    else
      bash "$HERE/target-runner.sh" "$ACTION" "$ENV" "$APP" '' "${FF_HEALTH_URL:-}"
    fi
    ;;
esac
