#!/usr/bin/env bash
# Project-aware checks. Explicit invocation; no implicit dependency installs.
set -euo pipefail
MODE=${1:-quick}
[[ "$MODE" == quick || "$MODE" == full ]] || { echo 'Usage: quality-check.sh quick|full' >&2; exit 2; }
if [[ -f package.json ]]; then
  command -v python3 >/dev/null || { echo 'python3 required for package.json inspection' >&2; exit 3; }
  mapfile -t CHECKS < <(python3 - "$MODE" <<'PY'
import json,sys
p=json.load(open('package.json',encoding='utf-8'))
s=p.get('scripts',{})
for k in ('lint','typecheck','test' if sys.argv[1]=='full' else 'none','build' if sys.argv[1]=='full' else 'none'):
    if k in s: print(k)
PY
)
  if [[ -f pnpm-lock.yaml ]]; then
    PM=pnpm
  elif [[ -f yarn.lock ]]; then
    PM=yarn
  elif [[ -f package-lock.json || -f npm-shrinkwrap.json ]]; then
    PM=npm
  else
    echo 'Missing supported Node lockfile' >&2; exit 3
  fi
  command -v "$PM" >/dev/null || { echo "Missing $PM; use toolchain-manager for local checks" >&2; exit 3; }
  [[ ${#CHECKS[@]} -gt 0 ]] || { echo 'No configured Node quality scripts; not a pass' >&2; exit 3; }
  for check in "${CHECKS[@]}"; do
    echo "Running $PM run $check"
    "$PM" run "$check"
  done
elif [[ -f pom.xml ]]; then
  if [[ -x ./mvnw ]]; then MVN=./mvnw; else MVN=mvn; fi
  command -v "$MVN" >/dev/null || { echo "Missing $MVN; use toolchain-manager" >&2; exit 3; }
  if [[ "$MODE" == quick ]]; then "$MVN" -B -q -DskipTests compile; else "$MVN" -B verify; fi
elif [[ -f build.gradle || -f build.gradle.kts ]]; then
  if [[ -x ./gradlew ]]; then GRADLE=./gradlew; else GRADLE=gradle; fi
  command -v "$GRADLE" >/dev/null || { echo "Missing $GRADLE; use toolchain-manager" >&2; exit 3; }
  if [[ "$MODE" == quick ]]; then "$GRADLE" classes; else "$GRADLE" check; fi
else
  echo 'Unsupported project; configure project quality commands explicitly' >&2
  exit 3
fi
printf 'Quality checks completed (%s)\n' "$MODE"
