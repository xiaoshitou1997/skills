#!/usr/bin/env bash
# 增删改 skill 后同步已安装副本:把本仓库全部 skills 装到配置的 agent 目标,并清理改名/合并前的旧版本。
# 默认从本地检出安装(改动即时生效,无需先 push);--remote 改从 GitHub 源安装(需先 push)。
# 用法:sync-installed.sh [--remote] [-a agent]...
# 环境变量:FF_SKILL_SYNC_AGENTS(默认 "universal claude-code")、FF_SKILL_SYNC_PACKAGE(默认 xiaoshitou1997/skills)。
set -euo pipefail

usage() {
  echo 'Usage: sync-installed.sh [--remote] [-a agent]...' >&2
  exit 2
}

REPO_ROOT=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
SOURCE=local
AGENTS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote) SOURCE=remote; shift ;;
    -a) [[ $# -ge 2 ]] || usage; AGENTS+=("$2"); shift 2 ;;
    *) usage ;;
  esac
done
if [[ ${#AGENTS[@]} -eq 0 ]]; then
  read -r -a AGENTS <<< "${FF_SKILL_SYNC_AGENTS:-universal claude-code}"
fi

command -v npx >/dev/null 2>&1 || { echo 'npx not installed; Node.js is required by the skills CLI' >&2; exit 3; }

agent_args=()
for a in "${AGENTS[@]}"; do
  agent_args+=(-a "$a")
done

# 仓库当前 skills:含 SKILL.md 的一级目录。
repo_skills=()
for d in "$REPO_ROOT"/*/; do
  [[ -f "$d/SKILL.md" ]] || continue
  repo_skills+=("$(basename "$d")")
done
[[ ${#repo_skills[@]} -gt 0 ]] || { echo "No skills found under $REPO_ROOT" >&2; exit 3; }
echo "Repo skills (${#repo_skills[@]}): ${repo_skills[*]}"

if [[ "$SOURCE" == remote ]]; then
  SRC=${FF_SKILL_SYNC_PACKAGE:-xiaoshitou1997/skills}
else
  SRC=.
fi
cd "$REPO_ROOT"
echo "Installing all skills from $SRC to: ${AGENTS[*]} (global)"
npx -y skills@latest add "$SRC" -s '*' -g -y "${agent_args[@]}"

# 改名/合并前的旧版本:装了会导致双触发,必须显式移除(README 迁移记录同步维护此清单)。
for name in "${STALE[@]}"; do
  # 清旧不带 -a:remove 省略 agent 参数才清理全部 agent 链接(带 -a 只清指定 agent,universal 链接会残留)。
  # 未安装时 remove 幂等返回成功;npx 在 Windows 上退出前可能崩溃,退出码不可靠,以清单复核为准。
  npx -y skills@latest remove "$name" -g -y >/dev/null 2>&1 || true
done

# 复核已安装清单(剔除 ANSI 色码),旧版残留则显式告警。
installed_list=$(npx -y skills@latest ls -g 2>/dev/null | sed -r 's/\x1b\[[0-9;]*m//g' || true)
echo "--- installed skills (global) ---"
echo "$installed_list"
stale_left=0
for name in "${STALE[@]}"; do
  if grep -q "^${name}[[:space:]]" <<< "$installed_list"; then
    echo "WARNING: 旧版 $name 仍在全局安装,请重跑本脚本或手动执行 npx skills@latest remove $name -g" >&2
    stale_left=1
  fi
done
[[ $stale_left -eq 0 ]] || exit 4
echo "对照上方清单:凡不在 Repo skills 里且不在 STALE 清单中的条目属于其他来源,本脚本不代删,请人工确认。"
