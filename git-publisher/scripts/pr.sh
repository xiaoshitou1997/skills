#!/usr/bin/env bash
# Minimal gh wrapper: explicit create/check; never force pushes or auto-push.
set -euo pipefail
ACTION=${1:-}
command -v gh >/dev/null 2>&1 || { echo 'Missing gh CLI' >&2; exit 3; }
git rev-parse --show-toplevel >/dev/null || { echo 'Not in git repository' >&2; exit 3; }
gh auth status >/dev/null || { echo 'gh is not authenticated' >&2; exit 3; }
case "$ACTION" in
  create)
    [[ $# == 4 ]] || { echo 'Usage: pr.sh create BASE TITLE BODY_FILE' >&2; exit 2; }
    BASE=$2; TITLE=$3; BODY_FILE=$4
    [[ "$BASE" =~ ^[a-zA-Z0-9._/-]+$ ]] || { echo 'Unsafe base branch' >&2; exit 2; }
    [[ -s "$BODY_FILE" ]] || { echo 'PR description file missing/empty' >&2; exit 2; }
    CURRENT=$(git branch --show-current)
    [[ -n "$CURRENT" ]] || { echo 'Detached HEAD; cannot open PR' >&2; exit 3; }
    [[ -z "$(git status --porcelain)" ]] || { echo 'Uncommitted changes remain; only committed feature should be PR content' >&2; exit 3; }
    git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' >/dev/null 2>&1 || { echo 'No upstream; push explicitly before creating PR' >&2; exit 3; }
    gh pr create --base "$BASE" --head "$CURRENT" --title "$TITLE" --body-file "$BODY_FILE"
    ;;
  checks)
    [[ $# == 1 ]] || exit 2
    gh pr checks
    ;;
  view)
    [[ $# == 1 ]] || exit 2
    gh pr view --json number,title,url,state,baseRefName,headRefName
    ;;
  *) echo 'Usage: pr.sh create BASE TITLE BODY_FILE | checks | view' >&2; exit 2 ;;
esac
