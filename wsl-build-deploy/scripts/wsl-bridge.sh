#!/usr/bin/env bash
# Windows 宿主与 WSL Docker 之间的桥:可用性硬门禁、发行版探测、暂存同步、单文件推送。
# 团队规范:应用一律以 Docker 容器运行;Windows 上容器必须经 WSL,没有 WSL 就失败,
# 禁止本机(宿主)直接启动。镜像常驻:任何流程不得 rmi/prune/清理镜像。
# 环境变量:FF_WSL_DISTRO 指定发行版(默认取第一个);FF_WSL_BRIDGE=0 仅供测试/CI 绕过。
set -euo pipefail

usage() {
  echo 'Usage: wsl-bridge.sh require' >&2
  echo '       wsl-bridge.sh distro' >&2
  echo '       wsl-bridge.sh plain FILE...' >&2
  echo '       wsl-bridge.sh topath WINDOWS_PATH' >&2
  echo '       wsl-bridge.sh home' >&2
  echo '       wsl-bridge.sh stage PROJECT_DIR [head|overlay]' >&2
  echo '       wsl-bridge.sh push LOCAL_FILE WSL_DEST_PATH' >&2
  echo '       wsl-bridge.sh exec WSL_DIR -- COMMAND...' >&2
  exit 2
}

is_windows() {
  local s
  s=$(uname -s)
  [[ "$s" == MINGW* || "$s" == MSYS* || "$s" == CYGWIN* ]]
}

bridge_disabled() {
  [[ "${FF_WSL_BRIDGE:-}" == "0" ]]
}

# Git Bash 会对参数做 MSYS 路径转换;调用 wsl.exe 必须关闭,否则 /mnt、-d 等参数被改写。
wsl_cmd() {
  MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' wsl.exe "$@"
}

# wsl -l 等输出可能是 UTF-16;剔除空字节与回车后按文本处理。
wsl_out() {
  wsl_cmd "$@" 2>/dev/null | tr -d '\0\r'
}

distro_name() {
  if [[ -n "${FF_WSL_DISTRO:-}" ]]; then
    printf '%s\n' "$FF_WSL_DISTRO"
    return 0
  fi
  wsl_out -l -q | grep -v '^$' | head -n 1
}

cmd_require() {
  if is_windows; then
    if bridge_disabled; then
      echo 'WARNING: FF_WSL_BRIDGE=0 bypasses the WSL rule; allowed only for tests/CI' >&2
      command -v docker >/dev/null 2>&1 || { echo 'Docker not installed' >&2; return 3; }
      return 0
    fi
    command -v wsl.exe >/dev/null 2>&1 || {
      echo '未检测到 wsl.exe。团队规范:Windows 上一律经 WSL 运行容器,禁止本机直接启动应用;' >&2
      echo '请先安装 WSL2(管理员 PowerShell 执行 wsl --install -d Ubuntu)后重试。' >&2
      return 3
    }
    local d
    d=$(distro_name) || true
    [[ -n "$d" ]] || { echo 'WSL 已安装但没有可用发行版;请执行 wsl --install -d Ubuntu 后重试' >&2; return 3; }
    wsl_cmd -d "$d" docker version >/dev/null 2>&1 || {
      echo "WSL 发行版 $d 内 docker 不可用;请在该发行版安装 Docker Engine,或启用 Docker Desktop 的 WSL 集成后重试" >&2
      return 3
    }
    echo "WSL_READY=$d"
  else
    command -v docker >/dev/null 2>&1 || { echo 'Docker not installed' >&2; return 3; }
    echo 'WSL_READY=native-linux'
  fi
}

cmd_distro() {
  is_windows || return 0
  bridge_disabled && return 0
  local d
  d=$(distro_name) || {
    echo '未检测到可用的 WSL;团队规范要求 Windows 经 WSL 运行容器,禁止本机直接启动(详见 require 子命令指引)' >&2
    return 3
  }
  [[ -n "$d" ]] || {
    echo '未检测到可用的 WSL;团队规范要求 Windows 经 WSL 运行容器,禁止本机直接启动(详见 require 子命令指引)' >&2
    return 3
  }
  printf '%s\n' "$d"
}

# 端点透明加密会把文件变成 %ENC-MARKER 密文;经管道分发的脚本/配置必须先校验明文。
cmd_plain() {
  [[ $# -ge 1 ]] || usage
  local f
  for f in "$@"; do
    [[ -f "$f" ]] || { echo "Missing file: $f" >&2; return 3; }
    if grep -q '%ENC-MARKER-[0-9]' "$f" 2>/dev/null; then
      echo "文件已被端点透明加密为 %ENC-MARKER 密文,无法使用: $f" >&2
      echo '请用白名单编辑器重新保存明文,或从仓库重新安装本 skill' >&2
      return 3
    fi
  done
}

cmd_topath() {
  [[ $# -eq 1 ]] || usage
  local d
  d=$(cmd_distro) || return 3
  [[ -n "$d" ]] || { echo 'topath 仅在经 WSL 桥接时可用' >&2; return 3; }
  wsl_out -d "$d" wslpath -u "$1"
}

cmd_home() {
  local d
  d=$(cmd_distro) || return 3
  [[ -n "$d" ]] || { echo 'home 仅在经 WSL 桥接时可用' >&2; return 3; }
  wsl_out -d "$d" sh -c 'echo $HOME'
}

verify_staging() {
  local d=$1 dest=$2
  wsl_cmd -d "$d" bash -c 'ls -A "$1" | grep -q .' _ "$dest" || {
    echo "暂存同步失败:目标目录为空 $dest" >&2
    return 3
  }
  local hits
  hits=$(wsl_cmd -d "$d" bash -c 'grep -rl "%ENC-MARKER-[0-9]" "$1" 2>/dev/null' _ "$dest" | tr -d '\0\r') || hits=''
  if [[ -n "$hits" ]]; then
    echo '暂存目录存在 %ENC-MARKER 密文文件,已中止(不得把密文带进构建):' >&2
    printf '%s\n' "$hits" >&2
    echo '请在白名单编辑器中将这些文件另存为明文后重试。' >&2
    return 3
  fi
}

cmd_stage() {
  [[ $# -ge 1 && $# -le 2 ]] || usage
  local proj=$1
  local mode=${2:-overlay}
  [[ "$mode" == head || "$mode" == overlay ]] || usage
  [[ -d "$proj" ]] || { echo "Not a directory: $proj" >&2; return 3; }
  local d
  d=$(cmd_distro) || return 3
  [[ -n "$d" ]] || { echo 'stage 仅在经 WSL 桥接时可用' >&2; return 3; }
  (cd "$proj" && git rev-parse --is-inside-work-tree >/dev/null 2>&1) || {
    echo 'stage 需要 git 仓库:暂存管线经 git archive 从对象库取明文基线' >&2
    return 3
  }
  local stamp dest
  stamp=$(date -u +%Y%m%d%H%M%S)-$$
  dest="$(cmd_home)/skills-staging/$(basename "$proj")-$stamp"
  # HEAD 基线:git 对象库内容可靠,经管道直灌 WSL ext4,不落回 Windows 盘(落回即变密文)。
  (cd "$proj" && git archive HEAD) | wsl_cmd -d "$d" bash -c 'mkdir -p "$1" && tar -x -C "$1"' _ "$dest"
  if [[ "$mode" == overlay ]]; then
    # 叠加工作区未提交/未跟踪文件;.env* 不入暂存,需要时用 push 单独传输。
    # 已删除文件无法经 tar 表达,需提交后再同步或改用 head 模式。
    if (cd "$proj" && git ls-files --others --exclude-standard --modified | grep -v -E '(^|/)\.env' | grep -q .); then
      (cd "$proj" && git ls-files -z --others --exclude-standard --modified | grep -zv -E '(^|/)\.env' | tar --null -cf - -T -) \
        | wsl_cmd -d "$d" bash -c 'tar -x -C "$1"' _ "$dest"
    fi
  fi
  verify_staging "$d" "$dest"
  printf '%s\n' "$dest"
}

cmd_push() {
  [[ $# -eq 2 ]] || usage
  local f=$1 t=$2 d
  cmd_plain "$f" || return 3
  d=$(cmd_distro) || return 3
  [[ -n "$d" ]] || { echo 'push 仅在经 WSL 桥接时可用' >&2; return 3; }
  wsl_cmd -d "$d" bash -c 'mkdir -p "$(dirname "$1")" && cat > "$1"' _ "$t" < "$f"
  wsl_cmd -d "$d" bash -c 'test -s "$1"' _ "$t" || { echo "推送后文件为空: $t" >&2; return 3; }
}

cmd_exec() {
  [[ $# -ge 3 ]] || usage
  local dir=$1
  shift
  [[ "${1:-}" == "--" ]] || usage
  shift
  local d
  d=$(cmd_distro) || return 3
  [[ -n "$d" ]] || { echo 'exec 仅在经 WSL 桥接时可用' >&2; return 3; }
  wsl_cmd -d "$d" --cd "$dir" -- "$@"
}

main() {
  # 端点可能把本脚本加密为密文;先自检,给出可执行的处理指引。
  if grep -q '%ENC-MARKER-[0-9]' "$0" 2>/dev/null; then
    echo 'wsl-bridge.sh 已被端点透明加密为密文,无法执行' >&2
    echo '请用白名单编辑器重新保存明文,或从仓库重新安装本 skill' >&2
    exit 3
  fi
  local action=${1:-}
  [[ -n "$action" ]] || usage
  shift
  case "$action" in
    require) cmd_require "$@" ;;
    distro)  cmd_distro "$@" ;;
    plain)   cmd_plain "$@" ;;
    topath)  cmd_topath "$@" ;;
    home)    cmd_home "$@" ;;
    stage)   cmd_stage "$@" ;;
    push)    cmd_push "$@" ;;
    exec)    cmd_exec "$@" ;;
    *) usage ;;
  esac
}

main "$@"
