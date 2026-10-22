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
import tarfile
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
# PATH 里排在前的可能是 System32 的 WSL bash,必须显式使用 Git Bash;
# 且 bash 不接受 Windows 反斜杠路径(msys 会吞掉反斜杠),统一转为正斜杠。
# 必须用 bin/bash.exe(trampoline):它负责初始化 MSYS 运行时环境;
# 从 Windows 父进程直启 usr/bin/bash.exe 真身后,`exec env VAR=… cmd` 链路
# 会静默断裂(目标命令不执行且无报错),wsl 桥接用例的 env 中转全部失效。
BASH = str(Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Git/bin/bash.exe')
if not Path(BASH).exists():
    BASH = shutil.which('bash') or 'bash'
GIT_AUDIT = (ROOT / 'mv-git-publisher/scripts/stage_audit.py').as_posix()
DETECT = (ROOT / 'mv-toolchain-manager/scripts/detect.py').as_posix()
IMAGE_BUILD = (ROOT / 'mv-image-build/scripts/image-build.sh').as_posix()
JIB_BUILD = (ROOT / 'mv-image-build/scripts/jib-build.sh').as_posix()
DEPLOY = (ROOT / 'mv-container-deploy/scripts/deploy.sh').as_posix()


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

    def test_prod_rejects_without_approval_or_host(self):
        with tempfile.TemporaryDirectory() as d:
            run = subprocess.run([BASH, DEPLOY, 'deploy', 'prod', 'someapp', 'someapp:abc'], cwd=d, capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn('--approve-prod', run.stderr)

    def test_build_packages_prebuilt_artifact(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / '.dockerignore').write_text('.env*\n.git\n')
            (d / 'pom.xml').write_text('<project/>')
            (d / 'Dockerfile.delivery').write_text('FROM scratch\n')
            target = d / 'target'
            target.mkdir()
            (target / 'demo-app-1.0.0.jar').write_bytes(b'fake-jar-bytes')
            (target / 'demo-app-1.0.0-sources.jar').write_bytes(b'not-deliverable')
            bin_dir = d / 'bin'; bin_dir.mkdir()
            fake_docker = bin_dir / 'docker'
            docker_log = d / 'docker.log'
            # build 时把上下文内容记入日志:最后一参数是 context,断言瘦上下文只含产物与 Dockerfile。
            fake_docker.write_text(
                '#!/bin/sh\n'
                'printf "%s\\n" "$*" >> "$DOCKER_LOG"\n'
                'if [ "$1" = "build" ]; then\n'
                '  for a in "$@"; do ctx="$a"; done\n'
                '  ls -A "$ctx" >> "$DOCKER_LOG"\n'
                '  cat "$ctx/Dockerfile" >> "$DOCKER_LOG" 2>/dev/null\n'
                'fi\n'
                'if [ "$1" = "image" ]; then echo "IMAGE_ID=sha256:mocked"; fi\n'
            )
            fake_docker.chmod(0o755)
            env = os.environ.copy()
            env['PATH'] = str(bin_dir) + os.pathsep + env['PATH']
            env['DOCKER_LOG'] = str(docker_log)
            # FF_WSL_BRIDGE=0 仅供测试:走 PATH 里的 fake docker,不触真实 WSL。
            env['FF_WSL_BRIDGE'] = '0'
            run = subprocess.run([BASH, IMAGE_BUILD, 'build', 'dev', 'demo'], cwd=d, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn('IMAGE=demo:', run.stdout)
            self.assertIn('ARTIFACT=', run.stdout)
            log = docker_log.read_text(encoding='utf-8', errors='replace')
            self.assertIn('build --pull', log)
            self.assertIn('Dockerfile', log)
            self.assertIn('app.jar', log)          # 产物改名进瘦上下文
            self.assertNotIn('demo-app-1.0.0.jar', log)  # 原名不进上下文
            self.assertNotIn('-sources.jar', log)  # sources jar 被排除

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
            run = subprocess.run([BASH, IMAGE_BUILD, 'build', 'dev', 'demo'], cwd=d, capture_output=True, text=True, encoding='utf-8', errors='replace')
            self.assertNotEqual(run.returncode, 0)
            self.assertIn('FF_ARTIFACT', run.stderr)

    def test_java_module_without_delivery_dockerfile_points_to_jib(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / '.dockerignore').write_text('.env*\n.git\n')
            (d / 'pom.xml').write_text('<project/>')
            run = subprocess.run([BASH, IMAGE_BUILD, 'build', 'dev', 'demo'], cwd=d, capture_output=True, text=True, encoding='utf-8', errors='replace')
            self.assertNotEqual(run.returncode, 0)
            self.assertIn('jib-build.sh', run.stderr)
            self.assertIn('Dockerfile.delivery', run.stderr)

    # --- Jib 路径:Java 模块由模块内插件定义,脚本只编排 tar 产出与载入 ---

    # 调用记录走 stderr:端点透明加密可能改写脚本写出的日志文件,断言只看进程输出。
    FAKE_MAVEN = r"""#!/bin/sh
printf 'MVN %s\n' "$*" >&2
mkdir -p target
printf 'fake-jib-tar' > target/jib-image.tar
"""

    FAKE_GRADLEW = r"""#!/bin/sh
printf 'GRADLE %s\n' "$*" >&2
mkdir -p build
printf 'fake-jib-tar' > build/jib-image.tar
"""

    FAKE_DOCKER_JIB = r"""#!/bin/sh
printf 'DOCKER %s\n' "$*" >&2
case "$1" in
  load) cat "$3" >/dev/null ;;
  image) echo "IMAGE_ID=sha256:jibmocked" ;;
esac
"""

    def _jib_env(self, d):
        bin_dir = d / 'bin'
        bin_dir.mkdir(exist_ok=True)
        (bin_dir / 'mvn').write_text(self.FAKE_MAVEN, encoding='utf-8', newline='\n')
        (bin_dir / 'docker').write_text(self.FAKE_DOCKER_JIB, encoding='utf-8', newline='\n')
        for name in ('mvn', 'docker'):
            (bin_dir / name).chmod(0o755)
        env = os.environ.copy()
        env['PATH'] = str(bin_dir) + os.pathsep + env['PATH']
        # 仅供测试:走 PATH 里的 fake docker,不触真实 WSL。
        env['FF_WSL_BRIDGE'] = '0'
        return env

    def test_jib_build_loads_tar_and_reports_identity(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'pom.xml').write_text('<project><build><plugins><plugin>jib-maven-plugin</plugin></plugins></build></project>')
            (d / 'target').mkdir()
            run = subprocess.run([BASH, JIB_BUILD, 'build', 'dev', 'demo'], cwd=d, env=self._jib_env(d),
                                 capture_output=True, text=True, encoding='utf-8', errors='replace')
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn('BUILD_TOOL=maven', run.stdout)
            self.assertIn('IMAGE=demo:', run.stdout)
            self.assertIn('IMAGE_ID=sha256:jibmocked', run.stdout)
            self.assertIn('SECURITY_SCAN=skipped', run.stderr)
            self.assertIn('MVN ', run.stderr)
            self.assertIn('jib:buildTar', run.stdout)
            self.assertIn('-Djib.to.image=demo:', run.stdout)
            self.assertIn('DOCKER load -i target/jib-image.tar', run.stderr)

    def test_jib_build_requires_module_plugin(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'pom.xml').write_text('<project/>')
            (d / 'target').mkdir()
            run = subprocess.run([BASH, JIB_BUILD, 'build', 'dev', 'demo'], cwd=d, env=self._jib_env(d),
                                 capture_output=True, text=True, encoding='utf-8', errors='replace')
            self.assertNotEqual(run.returncode, 0)
            self.assertIn('jib-maven-plugin', run.stderr)
            self.assertIn('build-contract.md', run.stderr)
            self.assertNotIn('MVN ', run.stderr)

    def test_jib_build_requires_host_package(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'pom.xml').write_text('<project><build><plugins><plugin>jib-maven-plugin</plugin></plugins></build></project>')
            run = subprocess.run([BASH, JIB_BUILD, 'build', 'dev', 'demo'], cwd=d, env=self._jib_env(d),
                                 capture_output=True, text=True, encoding='utf-8', errors='replace')
            self.assertNotEqual(run.returncode, 0)
            self.assertIn('mvn -B package', run.stderr)
            self.assertIn('mv-toolchain-manager', run.stderr)
            self.assertNotIn('MVN ', run.stderr)

    def test_jib_build_fails_when_tar_missing(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'pom.xml').write_text('<project><build><plugins><plugin>jib-maven-plugin</plugin></plugins></build></project>')
            (d / 'target').mkdir()
            env = self._jib_env(d)
            (d / 'bin/mvn').write_text('#!/bin/sh\nexit 0\n', encoding='utf-8', newline='\n')
            (d / 'bin/mvn').chmod(0o755)
            run = subprocess.run([BASH, JIB_BUILD, 'build', 'dev', 'demo'], cwd=d, env=env,
                                 capture_output=True, text=True, encoding='utf-8', errors='replace')
            self.assertNotEqual(run.returncode, 0)
            self.assertIn('未产出镜像 tar', run.stderr)
            self.assertNotIn('IMAGE_ID=', run.stdout)

    def test_jib_gradle_uses_wrapper_and_build_tar(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'build.gradle').write_text("plugins { id 'com.google.cloud.tools.jib' }\n")
            (d / 'build/libs').mkdir(parents=True)
            (d / 'gradlew').write_text(self.FAKE_GRADLEW, encoding='utf-8', newline='\n')
            run = subprocess.run([BASH, JIB_BUILD, 'build', 'dev', 'demo'], cwd=d, env=self._jib_env(d),
                                 capture_output=True, text=True, encoding='utf-8', errors='replace')
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn('BUILD_TOOL=gradle', run.stdout)
            self.assertIn('GRADLE ', run.stderr)
            self.assertIn('jibBuildTar', run.stdout)
            self.assertIn('-Djib.to.image=demo:', run.stdout)
            self.assertIn('DOCKER load -i build/jib-image.tar', run.stderr)

    def _offline_env(self, d, *, wsl=False):
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
    if [[ "$*" == *'IMAGE_ID='* ]]; then echo IMAGE_ID=sha256:mocked; else echo sha256:mocked; fi ;;
  'compose --env-file')
    if [[ "${@: -2}" == 'ps -q' ]]; then echo fake-container; fi ;;
  'inspect --format')
    if [[ "$3" == *Health* ]]; then echo healthy; else echo running; fi ;;
  'load '*) cat >/dev/null ;;
esac
""",
            # OpenSSH joins command arguments with spaces and sends the result to a login shell.
            'ssh': r"""#!/bin/bash
while [[ "$1" == -o || "$1" == -i ]]; do shift 2; done
shift
cd "$FAKE_RUNTIME_ROOT"
exec "$REAL_BASH" -c "$*"
""",
            'scp': '#!/bin/bash\nexit 0\n',
            'uname': '#!/bin/bash\necho MINGW64_NT\n',
            'wsl.exe': r"""#!/bin/bash
unset MSYS_NO_PATHCONV MSYS2_ARG_CONV_EXCL
# WSL does not inherit arbitrary host variables. Only explicit env arguments survive.
unset FF_REQUIRE_SECURITY_SCAN
[[ "$1" == -d && "$2" == FakeDistro ]] || exit 91
shift 2
if [[ "$1" == sh && "$2" == -c ]]; then
  cd "$FAKE_RUNTIME_ROOT" && pwd
  exit
fi
[[ "$1" != --exec && "$1" != -e && "$1" != -- ]] || shift
{ printf wsl; printf '\t%s' "$@"; printf '\n'; } >&2
exec "$@"
""",
        }
        for name, text in scripts.items():
            path = bin_dir / name
            path.write_text(text, encoding='utf-8', newline='\n')
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
            'for offline_tool in docker ssh scp wsl.exe uname; do\n'
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
            'WSL_LOG': (d / 'wsl.log').as_posix(),
            'RUNNER_LOG': (d / 'runner.log').as_posix(),
            'BASH_ENV': bash_env.as_posix(),
            'FF_WSL_BRIDGE': '1' if wsl else '0',
            'FF_WSL_DISTRO': 'FakeDistro',
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
        self.assertEqual([line for line in log.splitlines() if line.startswith('CONTEXT=')],
                         ['CONTEXT=Dockerfile', 'CONTEXT=app'])
        for label, content in [('STATIC', b'<html>static delivery</html>\n'),
                               ('HIDDEN', b'hidden asset\n'),
                               ('NESTED', b'console.log("ready");\n')]:
            blob = b'blob ' + str(len(content)).encode() + b'\0' + content
            self.assertIn(f'{label}_BLOB={hashlib.sha1(blob).hexdigest()}', log)

    def _run_native_static(self, name):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            env = self._offline_env(d)
            (d / 'package.json').write_text('{}', encoding='utf-8')
            self._static_artifact(d / name)
            run = self._workflow(IMAGE_BUILD, d, env, 'build', 'dev', 'demo')
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn(f'ARTIFACT_DIR={name}', run.stdout)
            self._assert_static_context(run.stderr)

    def test_native_build_packages_dist_directory(self):
        self._run_native_static('dist')

    def test_native_build_packages_build_directory(self):
        self._run_native_static('build')

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

    def _run_wsl_variant(self, name):
        with tempfile.TemporaryDirectory() as directory, \
                tempfile.TemporaryDirectory() as external:
            d = Path(directory)
            env = self._offline_env(d, wsl=True)
            (d / 'package.json').write_text('{}', encoding='utf-8')
            (d / '.gitignore').write_text('dist/\nbuild/\nstatic output/\n', encoding='utf-8')
            if name == 'external':
                artifact = Path(external) / 'external output'
                env['FF_ARTIFACT'] = artifact.as_posix() + '/'
            elif name == 'absolute':
                artifact = d / 'static output'
                env['FF_ARTIFACT'] = artifact.as_posix() + '/'
            elif name.startswith('./'):
                artifact = d / 'static output'
                env['FF_ARTIFACT'] = name
            else:
                artifact = d / name
            self._static_artifact(artifact)
            (d / 'unrelated.txt').write_text('staged content\n', encoding='utf-8')
            subprocess.run(['git', '-C', str(d), 'add', 'unrelated.txt'], check=True)
            before = subprocess.check_output(['git', '-C', str(d), 'ls-files', '--stage'])
            run = self._workflow(IMAGE_BUILD, d, env, 'build', 'dev', 'demo')
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self._assert_static_context(run.stderr)
            self.assertEqual(subprocess.check_output(['git', '-C', str(d), 'ls-files', '--stage']), before)
            log = run.stderr
            self.assertIn('/.mv/image-build/build/demo', log)
            self.assertNotIn('/.mv/local-debug/', log)

    def test_wsl_build_discovers_gitignored_dist(self):
        self._run_wsl_variant('dist')

    def test_wsl_build_discovers_gitignored_build(self):
        self._run_wsl_variant('build')

    def test_wsl_build_normalizes_relative_artifact_path(self):
        self._run_wsl_variant('./static output/../static output/')

    def test_wsl_build_accepts_in_tree_absolute_path(self):
        self._run_wsl_variant('absolute')

    def test_wsl_build_accepts_external_directory(self):
        self._run_wsl_variant('external')

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
            self.assertNotIn('docker\tbuild', run.stderr)

    def test_directory_artifact_rejects_repository_root(self):
        self._run_directory_artifact_guard('.', '.git')

    def test_directory_artifact_rejects_nested_env_file(self):
        self._run_directory_artifact_guard('dist', 'assets/.env.dev')

    def _run_strict_scan_gate(self, wsl):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            env = self._offline_env(d, wsl=wsl)
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
            if wsl:
                self.assertIn('env\tFF_REQUIRE_SECURITY_SCAN=1\tbash\t-s\t--\timage\tdemo:',
                              run.stderr)

    def test_strict_scan_fails_when_trivy_missing_native(self):
        self._run_strict_scan_gate(False)

    def test_strict_scan_fails_when_trivy_missing_wsl(self):
        self._run_strict_scan_gate(True)

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
    # 日常按改动精准跑,如 python3 tests/test_workflows.py -k wsl_build -k ssh_runner;
    # --serial 模式下 -k 由 unittest 原生支持,语义一致。
    patterns = [v for flag, v in zip(sys.argv, sys.argv[1:] + ['']) if flag == '-k' and v]
    if patterns:
        cases = [c for c in cases if any(p.lower() in c.id().lower() for p in patterns)]
    if not cases:
        print('no tests found')
        sys.exit(2)
    # 最长作业优先:重用例先占满工人、轻用例填空隙,否则字母序会让
    # 最重的 ssh 部署链最后才开跑,拖长关键路径。权重来自实测耗时档位。
    weight = {'test_ssh_runner': 420, 'test_wsl_build': 64, 'test_strict_scan_fails_when_trivy_missing_wsl': 80}
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
