"""Safe unit/smoke tests with sandbox git repos and a fake docker binary.

用例彼此完全隔离(独立临时目录/环境/沙箱仓库),直接运行时默认并行执行;
瓶颈是子进程 spawn 的逐进程安全软件开销而非 CPU,并行可显著缩短总时长。
支持 -k 子串筛选(可多次,按改动精准跑)与 --serial 串行回退。
"""
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
# PATH 里排在前的可能是 System32 自带的 bash,必须显式使用 Git Bash;
# 且 bash 不接受 Windows 反斜杠路径(msys 会吞掉反斜杠),统一转为正斜杠。
# 必须用 bin/bash.exe(trampoline):它负责初始化 MSYS 运行时环境;
# 从 Windows 父进程直启 usr/bin/bash.exe 真身后,`exec env VAR=… cmd` 链路
# 会静默断裂(目标命令不执行且无报错),离线用例的 env 中转全部失效。
BASH = str(Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Git/bin/bash.exe')
if not Path(BASH).exists():
    BASH = shutil.which('bash') or 'bash'
GIT_AUDIT = (ROOT / 'mv-git-publisher/scripts/stage_audit.py').as_posix()
DETECT = (ROOT / 'mv-toolchain-manager/scripts/detect.py').as_posix()
IMAGE_BUILD = (ROOT / 'mv-image-build/scripts/image-build.sh').as_posix()
DEPLOY = (ROOT / 'mv-container-deploy/scripts/deploy.sh').as_posix()
# 假 docker/假 ssh 返回的固定镜像 ID:满足 deploy.sh 对 sha256:<64 位十六进制> 的校验。
MOCK_ID = 'sha256:' + '0123456789abcdef' * 4


class WorkflowTests(unittest.TestCase):
    def test_detect_toolchain(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, '.nvmrc').write_text('22\n')
            Path(d, 'package.json').write_text(json.dumps({'engines': {'node': '>=22'}, 'packageManager': 'npm@10.0.0'}))
            Path(d, 'package-lock.json').write_text('{}')
            run = subprocess.run([sys.executable, DETECT, d], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads(run.stdout)
            self.assertEqual(result['.nvmrc'], '22')
            self.assertEqual(result['node']['engines']['node'], '>=22')
            self.assertIn('package-lock.json', result['lockfiles'])

    def _repo(self, directory):
        subprocess.run(['git', 'init', '-q', directory], check=True)
        subprocess.run(['git', '-C', directory, 'config', 'user.name', 'Test'], check=True)
        subprocess.run(['git', '-C', directory, 'config', 'user.email', 'test@example.com'], check=True)

    def test_stage_audit_does_not_stage_unrelated(self):
        with tempfile.TemporaryDirectory() as d:
            self._repo(d)
            Path(d, 'feat.txt').write_text('hello')
            Path(d, 'unrelated.txt').write_text('not staged')
            subprocess.run(['git', '-C', d, 'add', '--', 'feat.txt'], check=True)
            run = subprocess.run([sys.executable, GIT_AUDIT], cwd=d, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn('staged files: 1', run.stdout)
            names = subprocess.check_output(['git', '-C', d, 'diff', '--cached', '--name-only'], text=True)
            self.assertEqual(names.strip(), 'feat.txt')

    def test_stage_audit_blocks_private_key(self):
        with tempfile.TemporaryDirectory() as d:
            self._repo(d)
            Path(d, 'id_ed25519').write_text('fake private key for test')
            subprocess.run(['git', '-C', d, 'add', '--', 'id_ed25519'], check=True)
            run = subprocess.run([sys.executable, GIT_AUDIT], cwd=d, capture_output=True, text=True)
            self.assertEqual(run.returncode, 1)
            self.assertIn('sensitive path', run.stdout)

    def test_deploy_requires_explicit_target(self):
        # 部署目标一律经 SSH:dev/prod 各自必填,prod 另需显式授权;没有本机缺省目标。
        with tempfile.TemporaryDirectory() as d:
            dev = subprocess.run([BASH, DEPLOY, 'deploy', 'dev', 'someapp', 'someapp:abc'], cwd=d, capture_output=True, text=True)
            self.assertEqual(dev.returncode, 3)
            self.assertIn('FF_DEV_SSH', dev.stderr)
            prod = subprocess.run([BASH, DEPLOY, 'deploy', 'prod', 'someapp', 'someapp:abc'], cwd=d, capture_output=True, text=True)
            self.assertNotEqual(prod.returncode, 0)
            self.assertIn('--approve-prod', prod.stderr)
            approved = subprocess.run([BASH, DEPLOY, 'deploy', 'prod', 'someapp', 'someapp:abc', '--approve-prod'], cwd=d, capture_output=True, text=True)
            self.assertEqual(approved.returncode, 3)
            self.assertIn('FF_PROD_SSH', approved.stderr)

    def test_ssh_build_delivers_prebuilt_artifact(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / '.dockerignore').write_text('.env*\n.git\n')
            (d / 'pom.xml').write_text('<project/>')
            (d / 'Dockerfile.delivery').write_text('FROM scratch\n')
            target = d / 'target'
            target.mkdir()
            (target / 'demo-app-1.0.0.jar').write_bytes(b'fake-jar-bytes')
            (target / 'demo-app-1.0.0-sources.jar').write_bytes(b'not-deliverable')
            env = self._offline_env(d)
            run = self._workflow(IMAGE_BUILD, d, env, 'build', 'dev', 'demo')
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            stdout = {line.split('=', 1)[0]: line.split('=', 1)[1]
                      for line in run.stdout.splitlines()
                      if line.split('=', 1)[0] in ('IMAGE', 'IMAGE_ID', 'PACKAGE', 'SHA256')}
            self.assertIn('ARTIFACT=', run.stdout)
            self.assertEqual(stdout['IMAGE_ID'], MOCK_ID)
            self.assertIn('SECURITY_SCAN=skipped', run.stderr)
            # 构建点收到的上下文只含 Dockerfile 与改名后的 app.jar;原名与 sources 不进包。
            self.assertIn('docker\tbuild\t--pull', run.stderr)
            self.assertIn('CONTEXT=Dockerfile\n', run.stderr)
            self.assertIn('CONTEXT=app.jar\n', run.stderr)
            self.assertNotIn('demo-app-1.0.0.jar', run.stderr)
            self.assertNotIn('-sources.jar', run.stderr)
            # 包与清单常驻构建点 packages/<app>/。行内容不在本机断言:假服务器上 bash
            # 新写的清单会被端点透明加密改写,读回即密文;IMAGE_ID= 在服务器侧清单
            # 落盘之后输出,本身即是清单写成功的证据。
            packages = Path(env['FAKE_RUNTIME_ROOT']) / '.mv/image-build/packages/demo'
            self.assertTrue((packages / stdout['PACKAGE']).is_file(), '包应常驻服务器包目录')
            self.assertTrue((packages / 'manifest.tsv').is_file())

    def test_build_rejects_ambiguous_artifacts(self):
        # 交付契约要求唯一产物:多个候选拒绝并点名 FF_ARTIFACT,不按 mtime 静默猜测
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / '.dockerignore').write_text('.env*\n.git\n')
            (d / 'pom.xml').write_text('<project/>')
            (d / 'Dockerfile.delivery').write_text('FROM scratch\n')
            target = d / 'target'
            target.mkdir()
            (target / 'demo-app-1.0.0.jar').write_bytes(b'fake-jar-bytes')
            (target / 'demo-app-1.0.1.jar').write_bytes(b'another-jar')
            run = self._workflow(IMAGE_BUILD, d, self._offline_env(d), 'build', 'dev', 'demo')
            self.assertNotEqual(run.returncode, 0)
            self.assertIn('FF_ARTIFACT', run.stderr)

    def test_java_module_without_delivery_dockerfile_names_contract(self):
        # Java 与其他栈同一条服务器构建路径:镜像定义随模块提交 Dockerfile.delivery。
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'pom.xml').write_text('<project/>')
            run = self._workflow(IMAGE_BUILD, d, self._offline_env(d), 'build', 'dev', 'demo')
            self.assertNotEqual(run.returncode, 0)
            self.assertIn('Dockerfile.delivery', run.stderr)
            self.assertIn('build-contract.md', run.stderr)

    def _offline_env(self, d):
        """All container/network commands terminate in local stubs, including SSH shell parsing."""
        self._repo(str(d))
        (d / '.dockerignore').write_text('.env*\n.git\n', encoding='utf-8')
        (d / '.env.dev').write_text('APP_ENV=dev\n', encoding='utf-8')
        (d / 'compose.delivery.yml').write_text('services: {}\n', encoding='utf-8')
        bin_dir = d / 'bin'
        bin_dir.mkdir()
        scripts = {
            'docker': r"""#!/bin/bash
unset MSYS_NO_PATHCONV MSYS2_ARG_CONV_EXCL
{ printf docker; printf '\t%s' "$@"; printf '\n'; } >&2
case "$1 $2" in
  'build --pull')
    ctx="${@: -1}"
    for item in "$ctx"/*; do printf 'CONTEXT=%s\n' "${item##*/}"; done >&2
    if [[ -f "$ctx/app/index.html" ]]; then
      printf 'STATIC_BLOB=%s\n' "$(git hash-object -- "$ctx/app/index.html")" >&2
      printf 'HIDDEN_BLOB=%s\n' "$(git hash-object -- "$ctx/app/.asset.js")" >&2
      printf 'NESTED_BLOB=%s\n' "$(git hash-object -- "$ctx/app/assets/main.js")" >&2
    fi ;;
  'image inspect')
    if [[ "$*" == *'IMAGE_ID='* ]]; then echo "IMAGE_ID=@MOCK_ID@"; else echo "@MOCK_ID@"; fi ;;
  'compose --env-file')
    if [[ "${@: -2}" == 'ps -q' ]]; then echo fake-container; fi ;;
  'inspect --format')
    if [[ "$3" == *Health* ]]; then echo healthy; else echo running; fi ;;
esac
""",
            # OpenSSH joins command arguments with spaces and sends the result to a login shell.
            'ssh': r"""#!/bin/bash
while [[ "$1" == -o || "$1" == -i ]]; do shift 2; done
shift
{ printf ssh; printf '\t%s' "$@"; printf '\n'; } >&2
if [[ -n "${FAKE_SSH_ABSENT_IMAGE:-}" && "$*" == *inspect* && "$*" != *format* ]]; then exit 1; fi
if [[ -n "${FAKE_SSH_TAMPER:-}" && "$*" == *'cat >'* ]]; then
  exec "$REAL_BASH" -c "$*; for f in \"\$HOME\"/.mv/image-build/packages/*/*.tgz; do printf X >> \"\$f\"; done"
fi
cd "$FAKE_RUNTIME_ROOT"
exec "$REAL_BASH" -c "$*"
""",
            'scp': r"""#!/bin/bash
{ printf scp; printf '\t%s' "$@"; printf '\n'; } >&2
src=''; dest=''
for a in "$@"; do
  case "$a" in
    -*) ;;
    *:*) dest=$a ;;
    *) src=$a ;;
  esac
done
if [[ -n "$src" && -n "$dest" ]]; then
  remote=${dest#*:}
  mkdir -p "$FAKE_RUNTIME_ROOT/$(dirname "$remote")"
  cp -- "$src" "$FAKE_RUNTIME_ROOT/$remote"
fi
""",
            'uname': '#!/bin/bash\necho MINGW64_NT\n',
        }
        for name, text in scripts.items():
            path = bin_dir / name
            path.write_text(text.replace('@MOCK_ID@', MOCK_ID), encoding='utf-8', newline='\n')
            path.chmod(0o755)
        runtime = d / 'runtime'
        runtime.mkdir()
        app_dir = runtime / '.mv/container-deploy/demo'
        app_dir.mkdir(parents=True)
        (app_dir / 'compose.yml').write_text('services: {}\n', encoding='utf-8')
        (app_dir / '.env.dev').write_text('APP_ENV=dev\n', encoding='utf-8')
        (app_dir / 'current-image').write_text('demo:current\n', encoding='utf-8')
        (app_dir / 'previous-image').write_text('demo:previous\n', encoding='utf-8')
        # Force scanner discovery to report Trivy missing, independent of the host installation.
        bash_env = d / 'bash-env.sh'
        bash_env.write_text(
            'export OFFLINE_BIN="$(cd -- "$OFFLINE_BIN" && pwd)"\n'
            'export PATH="$OFFLINE_BIN:$PATH"\n'
            'command() {\n'
            '  if [[ "$1" == -v && "${2:-}" == trivy ]]; then return 1; fi\n'
            '  builtin command "$@"\n'
            '}\n'
            'bash() {\n'
            '  if [[ "${1:-}" == -s && "${2:-}" == -- ]]; then\n'
            '    { printf runner; printf "\\t%s" "$@"; printf "\\n"; } >&2\n'
            '  fi\n'
            '  "$REAL_BASH" "$@"\n'
            '}\n'
            'for offline_tool in docker ssh scp uname; do\n'
            '  resolved=$(type -P "$offline_tool")\n'
            '  [[ "$resolved" == "$OFFLINE_BIN/"* ]] || exit 90\n'
            'done\n', encoding='utf-8')
        env = {k: v for k, v in os.environ.items() if not k.startswith('FF_')}
        env.update({
            'PATH': str(bin_dir) + os.pathsep + env['PATH'],
            'HOME': runtime.as_posix(),
            'FAKE_RUNTIME_ROOT': runtime.as_posix(),
            'REAL_BASH': BASH,
            'OFFLINE_BIN': bin_dir.as_posix(),
            'DOCKER_LOG': (d / 'docker.log').as_posix(),
            'RUNNER_LOG': (d / 'runner.log').as_posix(),
            'BASH_ENV': bash_env.as_posix(),
            'FF_BUILD_TARGET': 'tester@fakehost',
        })
        return env

    def _workflow(self, script, d, env, *args):
        # 并行执行时多个用例同时 spawn,安全软件逐进程挂钩会拉长单次耗时;
        # Windows 上限放宽到 600s 防止争用误杀,正常完成远低于此。
        return subprocess.run([BASH, script, *args], cwd=d, env=env,
                              capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=600 if os.name == 'nt' else 30)

    def _static_artifact(self, directory):
        directory.mkdir(parents=True)
        (directory / 'index.html').write_bytes(b'<html>static delivery</html>\n')
        (directory / '.asset.js').write_bytes(b'hidden asset\n')
        (directory / 'assets').mkdir()
        (directory / 'assets/main.js').write_bytes(b'console.log("ready");\n')

    def _assert_static_context(self, log):
        self.assertIn('CONTEXT=app\n', log)
        self.assertIn('CONTEXT=Dockerfile\n', log)
        # 目录项顺序取决于文件系统枚举,不构成契约;只断言上下文构成。
        self.assertEqual(sorted(line for line in log.splitlines() if line.startswith('CONTEXT=')),
                         ['CONTEXT=Dockerfile', 'CONTEXT=app'])
        for label, content in [('STATIC', b'<html>static delivery</html>\n'),
                               ('HIDDEN', b'hidden asset\n'),
                               ('NESTED', b'console.log("ready");\n')]:
            blob = b'blob ' + str(len(content)).encode() + b'\0' + content
            self.assertIn(f'{label}_BLOB={hashlib.sha1(blob).hexdigest()}', log)

    def _run_ssh_static(self, name):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            env = self._offline_env(d)
            (d / 'package.json').write_text('{}', encoding='utf-8')
            self._static_artifact(d / name)
            run = self._workflow(IMAGE_BUILD, d, env, 'build', 'dev', 'demo')
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn(f'ARTIFACT_DIR={name}', run.stdout)
            self._assert_static_context(run.stderr)

    def test_ssh_build_packages_dist_directory(self):
        self._run_ssh_static('dist')

    def test_ssh_build_packages_build_directory(self):
        self._run_ssh_static('build')

    def test_static_build_missing_artifact_has_guidance(self):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            env = self._offline_env(d)
            (d / 'package.json').write_text('{}', encoding='utf-8')
            run = self._workflow(IMAGE_BUILD, d, env, 'build', 'dev', 'demo')
            self.assertEqual(run.returncode, 3, run.stdout + run.stderr)
            self.assertIn('npm run build', run.stderr)
            self.assertIn('FF_ARTIFACT', run.stderr)
            self.assertNotIn('unbound variable', run.stderr)
            self.assertFalse((d / 'docker.log').exists())

    def test_custom_dockerfile_missing_artifact_has_guidance(self):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            env = self._offline_env(d)
            (d / 'Dockerfile.delivery').write_text('FROM scratch\n', encoding='utf-8')
            run = self._workflow(IMAGE_BUILD, d, env, 'build', 'dev', 'demo')
            self.assertEqual(run.returncode, 3, run.stdout + run.stderr)
            self.assertIn('FF_ARTIFACT', run.stderr)
            self.assertNotIn('unbound variable', run.stderr)
            self.assertFalse((d / 'docker.log').exists())

    def test_ssh_build_accepts_artifact_path_with_spaces(self):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            env = self._offline_env(d)
            (d / 'package.json').write_text('{}', encoding='utf-8')
            self._static_artifact(d / 'static output')
            env['FF_ARTIFACT'] = './static output/../static output'
            run = self._workflow(IMAGE_BUILD, d, env, 'build', 'dev', 'demo')
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self._assert_static_context(run.stderr)
            self.assertIn('ARTIFACT_DIR=', run.stdout)

    def test_build_requires_build_target(self):
        # 没有构建点就没有镜像产出地:FF_BUILD_TARGET 未设置直接拒绝,不猜缺省。
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            env = self._offline_env(d)
            del env['FF_BUILD_TARGET']
            (d / 'Dockerfile.delivery').write_text('FROM scratch\n', encoding='utf-8')
            (d / 'target').mkdir()
            (d / 'target/app.jar').write_bytes(b'jar')
            run = self._workflow(IMAGE_BUILD, d, env, 'build', 'dev', 'demo')
            self.assertEqual(run.returncode, 2, run.stdout + run.stderr)
            self.assertIn('FF_BUILD_TARGET', run.stderr)
            self.assertNotIn('ssh\t', run.stderr)

    def test_ssh_build_rejects_sha256_mismatch(self):
        # 上传包在构建点核对 SHA-256:不匹配即失败并删除损坏包,不静默降级继续构建。
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            env = self._offline_env(d)
            env['FAKE_SSH_TAMPER'] = '1'
            (d / '.dockerignore').write_text('.env*\n.git\n', encoding='utf-8')
            (d / 'pom.xml').write_text('<project/>', encoding='utf-8')
            (d / 'Dockerfile.delivery').write_text('FROM scratch\n', encoding='utf-8')
            (d / 'target').mkdir()
            (d / 'target/app.jar').write_bytes(b'jar')
            run = self._workflow(IMAGE_BUILD, d, env, 'build', 'dev', 'demo')
            self.assertNotEqual(run.returncode, 0)
            self.assertIn('SHA-256', run.stderr)
            self.assertNotIn('IMAGE_ID=', run.stdout)
            packages = Path(env['FAKE_RUNTIME_ROOT']) / '.mv/image-build/packages/demo'
            # 损坏包删除与清单不落盘:删除动作在本机假服务器上受安全软件干扰无法断言,
            # 清单不创建是服务器侧拒绝的直接证据。
            self.assertFalse((packages / 'manifest.tsv').exists())

    def _run_directory_artifact_guard(self, artifact, secret):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            env = self._offline_env(d)
            (d / 'package.json').write_text('{}', encoding='utf-8')
            env['FF_ARTIFACT'] = artifact
            if artifact != '.':
                self._static_artifact(d / artifact)
                (d / artifact / secret).write_text('secret', encoding='utf-8')
            run = self._workflow(IMAGE_BUILD, d, env, 'build', 'dev', 'demo')
            self.assertEqual(run.returncode, 3, run.stdout + run.stderr)
            self.assertIn('产物目录包含 .git 或 .env*', run.stderr)
            self.assertNotIn('ssh\t', run.stderr)  # 守卫先于上传:失败时不发生任何传输

    def test_directory_artifact_rejects_repository_root(self):
        self._run_directory_artifact_guard('.', '.git')

    def test_directory_artifact_rejects_nested_env_file(self):
        self._run_directory_artifact_guard('dist', 'assets/.env.dev')

    def test_strict_scan_fails_when_trivy_missing(self):
        # FF_REQUIRE_SECURITY_SCAN=1 时 trivy 是构建点硬门禁:缺 trivy 在构建前即失败,不降级。
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            env = self._offline_env(d)
            env['FF_REQUIRE_SECURITY_SCAN'] = '1'
            (d / 'pom.xml').write_text('<project/>', encoding='utf-8')
            (d / 'Dockerfile.delivery').write_text('FROM scratch\n', encoding='utf-8')
            (d / 'target').mkdir()
            (d / 'target/app.jar').write_bytes(b'jar')
            run = self._workflow(IMAGE_BUILD, d, env, 'build', 'dev', 'demo')
            self.assertEqual(run.returncode, 3, run.stdout + run.stderr)
            self.assertIn('Trivy unavailable; image security gate not satisfied', run.stderr)
            self.assertNotIn('SKIP:', run.stdout + run.stderr)
            self.assertNotIn('IMAGE_ID=', run.stdout)
            self.assertIn('ssh\t', run.stderr)  # 门禁在构建点执行:包已上传,由服务器侧拒绝

    def _run_ssh_runner_arguments(self, health, ready):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            env = self._offline_env(d)
            env.update(FF_DEV_SSH='tester@fakehost', FF_HEALTH_URL=health, FF_READY_TIMEOUT=ready)
            # An HTTP probe must also stay offline.
            curl = d / 'bin/curl'
            curl.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
            curl.chmod(0o755)
            output = ''
            for action in ('deploy', 'status', 'rollback'):
                args = [action, 'dev', 'demo'] + (['demo:release'] if action == 'deploy' else [])
                run = self._workflow(DEPLOY, d, env, *args)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                output += run.stderr
            lines = [line for line in output.splitlines() if line.startswith('runner\t')]
            self.assertEqual(lines, [
                '\t'.join(['runner', '-s', '--', action, 'dev', 'demo', image, health, ready])
                for action, image in [('deploy', 'demo:release'), ('status', ''), ('rollback', '')]])
            self.assertIn('docker\timage\tinspect\t--format\t{{.Id}}\tdemo:release\n',
                          output)

    def test_ssh_runner_preserves_empty_arguments(self):
        self._run_ssh_runner_arguments('', '')

    def test_ssh_runner_preserves_empty_health_with_ready_timeout(self):
        self._run_ssh_runner_arguments('', '2')

    def test_ssh_runner_forwards_health_url_and_ready_timeout(self):
        self._run_ssh_runner_arguments('http://127.0.0.1:8080/health', '2')

    def test_deploy_pulls_image_when_absent_on_target(self):
        # 目标机缺镜像时经镜像仓库拉取分发,不经宿主直传;拉取就位后核对 Image ID 再启动。
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            env = self._offline_env(d)
            env['FAKE_SSH_ABSENT_IMAGE'] = '1'
            env.update(FF_DEV_SSH='tester@fakehost', FF_HEALTH_URL='http://127.0.0.1:8080/health')
            curl = d / 'bin/curl'
            curl.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
            curl.chmod(0o755)
            run = self._workflow(DEPLOY, d, env, 'deploy', 'dev', 'demo', 'demo:release')
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn('docker\tpull\tdemo:release\n', run.stderr)
            self.assertIn(f'DEV_RECEIPT={MOCK_ID}', run.stdout)

    def test_dev_receipt_gates_prod_promotion(self):
        # dev 健康收据落本机 receipts/;prod 晋级按目标机 Image ID 核对本机收据,缺收据不上传不启动。
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            env = self._offline_env(d)
            env.update(FF_DEV_SSH='tester@fakedev', FF_HEALTH_URL='http://127.0.0.1:8080/health')
            curl = d / 'bin/curl'
            curl.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
            curl.chmod(0o755)
            (d / '.env.prod').write_text('APP_ENV=prod\n', encoding='utf-8')
            run = self._workflow(DEPLOY, d, env, 'deploy', 'dev', 'demo', 'demo:release')
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn(f'DEV_RECEIPT={MOCK_ID}', run.stdout)
            # 收据文件由部署链路新写,本机可能被透明加密,只断言存在性。
            receipt = Path(env['HOME']) / '.mv/container-deploy/receipts/demo' / MOCK_ID.replace(':', '-')
            self.assertTrue(receipt.is_file(), 'dev 收据应落在本机 receipts 目录')
            prod_env = dict(env)
            prod_env['FF_PROD_SSH'] = 'deployer@fakeprod'
            run = self._workflow(DEPLOY, d, prod_env, 'deploy', 'prod', 'demo', 'demo:release', '--approve-prod')
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn('DEPLOYED_IMAGE=demo:release', run.stdout)
            releases = Path(env['HOME']) / '.mv/container-deploy/demo/releases.tsv'
            self.assertTrue(releases.is_file(), '发布记录应常驻目标机目录')
            # 无收据的镜像不得晋级:门禁在任何上传/启动之前拒绝。
            with tempfile.TemporaryDirectory() as fresh:
                fd = Path(fresh)
                fresh_env = self._offline_env(fd)
                fresh_env.update(FF_PROD_SSH='deployer@fakeprod')
                (fd / '.env.prod').write_text('APP_ENV=prod\n', encoding='utf-8')
                run = self._workflow(DEPLOY, fd, fresh_env, 'deploy', 'prod', 'demo', 'demo:release', '--approve-prod')
                self.assertEqual(run.returncode, 3, run.stdout + run.stderr)
                self.assertIn('receipt', run.stderr)
                self.assertNotIn('scp\t', run.stderr)


def _flatten(suite):
    cases = []
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            cases.extend(_flatten(item))
        else:
            cases.append(item)
    return cases


def main():
    # 每个用例都是独立临时目录/独立环境的子进程沙箱,无共享可变状态;
    # 瓶颈是 spawn 等待(安全软件逐进程挂钩)而非 CPU,线程池即可绕开串行税。
    # --serial 回退串行(与 unittest.main 等价),便于二分定位失败。
    if '--serial' in sys.argv:
        unittest.main(verbosity=1, argv=[a for a in sys.argv if a != '--serial'])
        return
    cases = _flatten(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    # -k 子串筛选(可多次,任一命中即选,大小写不敏感,对完整用例名匹配):
    # 日常按改动精准跑,如 python3 tests/test_workflows.py -k ssh_build -k ssh_runner;
    # --serial 模式下 -k 由 unittest 原生支持,语义一致。
    patterns = [v for flag, v in zip(sys.argv, sys.argv[1:] + ['']) if flag == '-k' and v]
    if patterns:
        cases = [c for c in cases if any(p.lower() in c.id().lower() for p in patterns)]
    if not cases:
        print('no tests found')
        sys.exit(2)
    # 最长作业优先:重用例先占满工人、轻用例填空隙,否则字母序会让
    # 最重的 ssh 部署链最后才开跑,拖长关键路径。权重来自实测耗时档位。
    weight = {'test_ssh_runner': 420, 'test_deploy_pulls': 420, 'test_dev_receipt_gates': 420,
              'test_strict_scan_fails_when_trivy_missing': 80, 'test_ssh_build': 100}
    cases.sort(key=lambda c: next((w for p, w in weight.items() if c.id().split('.')[-1].startswith(p)), 0),
               reverse=True)
    # 4 是实测平衡点:6 路并发时安全软件逐进程挂钩争用加剧,
    # ssh 部署链单次耗时会冲到超时量级;4 路下吞吐仍明显优于串行。
    workers = min(4, len(cases))
    results = [None] * len(cases)

    def run_one(index, case):
        result = unittest.TestResult()
        begin = time.monotonic()
        case.run(result)
        results[index] = (case, result, time.monotonic() - begin)

    started = time.monotonic()
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda pair: run_one(*pair), enumerate(cases)))
    elapsed = time.monotonic() - started

    ran = failures = errors = skipped = 0
    for case, result, _ in results:
        ran += result.testsRun
        failures += len(result.failures)
        errors += len(result.errors)
        skipped += len(result.skipped)
        for kind, bucket in (('FAIL', result.failures), ('ERROR', result.errors)):
            for test, trace in bucket:
                print(f'{kind}: {test.id()}\n{trace}')
    print(f'Ran {ran} tests in {elapsed:.1f}s (parallel x{workers}; --serial for sequential)')
    # 耗时归因:逐用例实测分布,优化与超时调参以这里为准,不拿串行数字外推。
    print('耗时分布(降序):')
    for case, _, seconds in sorted(results, key=lambda item: item[2], reverse=True):
        print(f'  {seconds:7.1f}s  {case.id().rsplit(".", 1)[-1]}')
    if failures or errors:
        print(f'FAILED (failures={failures}, errors={errors}, skipped={skipped})')
        sys.exit(1)
    print(f'OK (skipped={skipped})')


if __name__ == '__main__':
    main()
