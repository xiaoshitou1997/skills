#!/usr/bin/env bash
# Project-aware checks. Explicit invocation; no implicit dependency installs.
set -euo pipefail
MODE=${1:-quick}
[[ "$MODE" == quick || "$MODE" == full ]] || { echo 'Usage: quality-check.sh quick|full' >&2; exit 2; }
if [[ -f package.json ]]; then
  # Python 命令按环境探测:与 SKILL.md 承诺的 python3/python/py -3 三选一保持一致。
  PYBIN=()
  for c in python3 python; do
    command -v "$c" >/dev/null 2>&1 && { PYBIN=("$c"); break; }
  done
  if [[ ${#PYBIN[@]} -eq 0 ]] && command -v py >/dev/null 2>&1; then PYBIN=(py -3); fi
  [[ ${#PYBIN[@]} -gt 0 ]] || { echo 'python3, python or py -3 required for package.json inspection' >&2; exit 3; }
  mapfile -t CHECKS < <("${PYBIN[@]}" - "$MODE" <<'PY'
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
  command -v "$PM" >/dev/null || { echo "Missing $PM; use mv-toolchain-manager for local checks" >&2; exit 3; }
  [[ ${#CHECKS[@]} -gt 0 ]] || { echo 'No configured Node quality scripts; not a pass' >&2; exit 3; }
  for check in "${CHECKS[@]}"; do
    echo "Running $PM run $check"
    "$PM" run "$check"
  done
elif [[ -f pom.xml ]]; then
  if [[ -x ./mvnw ]]; then MVN=./mvnw; else MVN=mvn; fi
  command -v "$MVN" >/dev/null || { echo "Missing $MVN; use mv-toolchain-manager" >&2; exit 3; }
  if [[ "$MODE" == quick ]]; then "$MVN" -B -q -DskipTests compile; else "$MVN" -B verify; fi
elif [[ -f build.gradle || -f build.gradle.kts ]]; then
  if [[ -x ./gradlew ]]; then GRADLE=./gradlew; else GRADLE=gradle; fi
  command -v "$GRADLE" >/dev/null || { echo "Missing $GRADLE; use mv-toolchain-manager" >&2; exit 3; }
  if [[ "$MODE" == quick ]]; then "$GRADLE" classes; else "$GRADLE" check; fi
else
  echo 'Unsupported project; configure project quality commands explicitly' >&2
  exit 3
fi
printf 'Quality checks completed (%s)\n' "$MODE"
