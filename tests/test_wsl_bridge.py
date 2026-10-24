"""Offline tests for wsl-bridge.sh using a fake wsl.exe stub (no real WSL needed)."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
# PATH 里排在前的可能是 System32 的 WSL bash,必须显式使用 Git Bash。
BASH = str(Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Git/bin/bash.exe')
if not Path(BASH).exists():
    BASH = 'bash'
# bash 不接受 Windows 反斜杠路径(msys 会吞掉反斜杠),统一转为正斜杠。
# wsl-bridge.sh 只服务 mv-container-deploy(mv-image-build 已统一走 SSH 服务器通道)。
BRIDGE = (ROOT / 'mv-container-deploy/scripts/wsl-bridge.sh').as_posix()

# 伪造 wsl.exe:$FAKE_WSL_HOME 映射 WSL 侧 /home/tester;仅实现 bridge 用到的调用形态。
STUB = '''#!/usr/bin/env bash
# bridge 为 wsl.exe 调用禁用了 MSYS 路径转换;stub 内部的 mkdir/tar/cat 是 MSYS 程序,
# 需要正常转换,先还原,避免参数被改写成 //tmp 或 /C\\: 形式。
unset MSYS_NO_PATHCONV MSYS2_ARG_CONV_EXCL
FAKE_ROOT="${FAKE_WSL_HOME:-/tmp/nonexistent-fake-wsl}"
map_path() {
  local p="$1"
  # 注意:${p//模式/替换} 在第一个未转义 / 处分割,替换串不能再带前导 /,
  # 否则与 FAKE_ROOT 的头斜杠叠成 //tmp,被 MSYS 当作只读 UNC 路径。
  echo "${p//\\/home\\/tester/$FAKE_ROOT}"
}
args="$*"
last="${@: -1}"
case "$args" in
  *-l\\ -q*) printf 'FakeDistro\\r\\n' ;;
  *wslpath*)
    drive="$(printf '%s' "$last" | cut -d: -f1 | tr 'A-Z' 'a-z')"
    rest="$(printf '%s' "$last" | cut -d: -f2-)"
    echo "/mnt/$drive$rest" ;;
  *"echo \\$HOME"*) echo "/home/tester" ;;
  *' tar -x'*)
    target="$(map_path "$last")"
    mkdir -p "$target"
    tar -xf - -C "$target" ;;
  *"cat >"*)
    target="$(map_path "$last")"
    mkdir -p "$(dirname "$target")"
    cat > "$target" ;;
  *"grep -rl"*) exit 1 ;;
  *"ls -A"*)
    target="$(map_path "$last")"
    ls -A "$target" | grep -q . ;;
  *"test -s"*)
    target="$(map_path "$last")"
    test -s "$target" ;;
  *"docker version"*)
    if [ "${FAKE_DOCKER_FAIL:-0}" = "1" ]; then exit 9; fi
    echo "fake docker inside wsl" ;;
  *'echo bridge-exec-ok'*) echo "bridge-exec-ok" ;;
  *) exit 0 ;;
esac
'''

NT_ONLY = unittest.skipUnless(os.name == 'nt', 'bridge pipeline paths are Windows-specific')


def sealed(path):
    """端点透明加密已把该文件密封为 %XXXX-Header 形状的密文头。"""
    try:
        with open(path, 'rb') as fh:
            head = fh.read(16)
            return head.startswith(b'%') and b'-Header' in head
    except OSError:
        return False


class WslBridgeTests(unittest.TestCase):
    def _run(self, *args, env_extra=None, cwd=None):
        env = os.environ.copy()
        env.update(env_extra or {})
        # 脚本输出含中文(UTF-8),必须显式指定编码,中文 Windows 默认 GBK 会解码崩溃。
        return subprocess.run([BASH, BRIDGE, *args], env=env, cwd=cwd, text=True, encoding='utf-8', errors='replace', capture_output=True)

    def _stub_env(self, d):
        bin_dir = Path(d) / 'bin'
        bin_dir.mkdir(exist_ok=True)
        stub = bin_dir / 'wsl.exe'
        stub.write_text(STUB)
        stub.chmod(0o755)
        return {
            'PATH': str(bin_dir) + os.pathsep + os.environ['PATH'],
            'FF_WSL_DISTRO': 'FakeDistro',
            # Git Bash 视图:Windows 用户 TEMP 目录映射为 /tmp。stub 开头已还原 MSYS 转换,
            # /tmp 风格路径可被 mkdir/tar 正常解析;盘符路径反而会被转义成 /C\\: 形式。
            'FAKE_WSL_HOME': '/tmp/' + Path(d).name + '/fakesl',
        }

    def test_distro_empty_when_bridge_disabled(self):
        run = self._run('distro', env_extra={'FF_WSL_BRIDGE': '0'})
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip(), '')

    def test_plain_flags_ciphertext(self):
        with tempfile.TemporaryDirectory() as d:
            good = Path(d) / 'good.sh'
            good.write_text('#!/usr/bin/env bash\necho ok\n')
            bad = Path(d) / 'bad.sh'
            bad.write_text('%ENC-Header-001\x00binary garbage')
            # 回归:本机真实密文头形态尾部是 # 占位而非数字,字符类必须覆盖
            bad2 = Path(d) / 'bad2.sh'
            bad2.write_text('%TSD-Header-###%\x00binary garbage')
            run = self._run('plain', good.as_posix())
            self.assertEqual(run.returncode, 0, run.stderr)
            for badf in (bad, bad2):
                run = self._run('plain', badf.as_posix())
                self.assertEqual(run.returncode, 3, badf.name)
                self.assertIn('-Header', run.stderr)

    @NT_ONLY
    def test_require_passes_with_fake_wsl_docker(self):
        with tempfile.TemporaryDirectory() as d:
            run = self._run('require', env_extra=self._stub_env(d))
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('WSL_READY=FakeDistro', run.stdout)

    @NT_ONLY
    def test_require_fails_when_wsl_docker_missing(self):
        with tempfile.TemporaryDirectory() as d:
            env = self._stub_env(d)
            env['FAKE_DOCKER_FAIL'] = '1'
            run = self._run('require', env_extra=env)
            self.assertEqual(run.returncode, 3)
            self.assertIn('docker', run.stderr)

    @NT_ONLY
    def test_push_transfers_file_content(self):
        with tempfile.TemporaryDirectory() as d:
            env = self._stub_env(d)
            src = Path(d) / 'env.dev'
            src.write_text('APP_ENV=dev\nHOST_PORT=8080\n')
            run = self._run('push', src.as_posix(), '/home/tester/app/.env.dev', env_extra=env)
            self.assertEqual(run.returncode, 0, run.stderr)
            dest = Path(d) / 'fakesl' / 'app' / '.env.dev'
            # stub 写盘的文件在部署了安全软件的机器上可能被透明加密密封,内容断言只能在干净机器执行;
            # 传输行为本身已由 returncode 与管道输出覆盖。
            if sealed(dest):
                self.skipTest('Security agent sealed the pushed file; content assertion needs a clean machine')
            self.assertEqual(dest.read_text(encoding='utf-8'), 'APP_ENV=dev\nHOST_PORT=8080\n')

    @NT_ONLY
    def test_exec_runs_command_in_wsl(self):
        with tempfile.TemporaryDirectory() as d:
            run = self._run('exec', '/home/tester/app', '--', 'echo', 'bridge-exec-ok', env_extra=self._stub_env(d))
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('bridge-exec-ok', run.stdout)


if __name__ == '__main__':
    unittest.main()
