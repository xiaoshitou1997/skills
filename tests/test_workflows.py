"""Safe unit/smoke tests with sandbox git repos and a fake docker binary."""
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
# PATH 里排在前的可能是 System32 的 WSL bash,必须显式使用 Git Bash;
# 且 bash 不接受 Windows 反斜杠路径(msys 会吞掉反斜杠),统一转为正斜杠。
BASH = str(Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Git/bin/bash.exe')
if not Path(BASH).exists():
    BASH = shutil.which('bash') or 'bash'
GIT_AUDIT = (ROOT / 'mv-git-publisher/scripts/stage_audit.py').as_posix()
DETECT = (ROOT / 'mv-toolchain-manager/scripts/detect.py').as_posix()
IMAGE_BUILD = (ROOT / 'mv-image-build/scripts/image-build.sh').as_posix()
CRANE_BUILD = (ROOT / 'mv-image-build/scripts/crane-build.sh').as_posix()
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
            target = d / 'target'
            target.mkdir()
            (target / 'demo-app-1.0.0.jar').write_bytes(b'fake-jar-bytes')
            (target / 'demo-app-1.0.1.jar').write_bytes(b'another-jar')
            run = subprocess.run([BASH, IMAGE_BUILD, 'build', 'dev', 'demo'], cwd=d, capture_output=True, text=True, encoding='utf-8', errors='replace')
            self.assertNotEqual(run.returncode, 0)
            self.assertIn('FF_ARTIFACT', run.stderr)

    def test_build_without_artifact_fails_with_guidance(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / '.dockerignore').write_text('.env*\n.git\n')
            (d / 'pom.xml').write_text('<project/>')
            run = subprocess.run([BASH, IMAGE_BUILD, 'build', 'dev', 'demo'], cwd=d, capture_output=True, text=True, encoding='utf-8', errors='replace')
            self.assertNotEqual(run.returncode, 0)
            self.assertIn('mvn -B package', run.stderr)
            self.assertIn('mv-toolchain-manager', run.stderr)

    # --- crane 路径（无 WSL）:基镜像+产物层组装,镜像身份契约与 Docker 路径同源 ---

    # 假 crane:mutate 时在 -o 指定路径写最小 docker 格式镜像 tar(不含 RepoTags,由脚本补写);
    # CRANE_BAD_NAME=1 时故意写错 Config 文件名,测一致性守卫。
    FAKE_CRANE = r"""#!/bin/sh
printf '%s\n' "$*" >> "$CRANE_LOG"
if [ "$1" = "mutate" ]; then
  prev=""
  for a in "$@"; do
    [ "$prev" = "-o" ] && out="$a"
    prev="$a"
  done
  d=$(mktemp -d)
  printf 'image-config-bytes' > "$d/c.json"
  hex=$(sha256sum "$d/c.json" | cut -d' ' -f1)
  if [ -n "$CRANE_BAD_NAME" ]; then nm="deadbeef.json"; else nm="$hex.json"; fi
  mv "$d/c.json" "$d/$nm"
  printf '[{"Config":"%s","Layers":[]}]\n' "$nm" > "$d/manifest.json"
  tar -C "$d" -cf "$out" manifest.json "$nm"
  rm -rf "$d"
fi
"""

    def _crane_env(self, d):
        bin_dir = d / 'bin'
        bin_dir.mkdir(exist_ok=True)
        fake_crane = bin_dir / 'crane'
        fake_crane.write_text(self.FAKE_CRANE)
        fake_crane.chmod(0o755)
        env = os.environ.copy()
        env['PATH'] = str(bin_dir) + os.pathsep + env['PATH']
        env['CRANE_LOG'] = str(d / 'crane.log')
        return env

    def test_crane_java_build_matches_jar_template(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'pom.xml').write_text('<project/>')
            target = d / 'target'
            target.mkdir()
            (target / 'demo-app-1.0.0.jar').write_bytes(b'fake-jar-bytes')
            (target / 'demo-app-1.0.0-sources.jar').write_bytes(b'not-deliverable')
            env = self._crane_env(d)
            run = subprocess.run([BASH, CRANE_BUILD, 'build', 'dev', 'demo'], cwd=d, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            # 模板对齐:temurin 21 基镜像 + /app/app.jar + 非 root + 8080 + java -jar 入口
            self.assertIn('MODE=java BASE=eclipse-temurin:21-jre', run.stdout)
            self.assertIn('--entrypoint java,-jar,/app/app.jar', run.stdout)
            self.assertIn('--user 10001', run.stdout)
            self.assertIn('--exposed-ports 8080', run.stdout)
            self.assertIn('ARTIFACT=crane-image.tar', run.stdout)
            # 非 git 目录:Tag 公式记 unversioned 且强制 -dirty,与 Docker 路径同规则
            self.assertRegex(run.stdout, r'IMAGE=demo:unversioned-dirty-[0-9]{14}')
            expected_id = hashlib.sha256(b'image-config-bytes').hexdigest()
            self.assertIn(f'IMAGE_ID=sha256:{expected_id}', run.stdout)
            # RepoTags 补写:docker load 后按 IMAGE 引用可寻址
            with tarfile.open(d / 'crane-image.tar') as t:
                manifest = json.load(t.extractfile('manifest.json'))
            self.assertEqual(manifest[0]['RepoTags'][0], run.stdout.strip().split('IMAGE=')[1].splitlines()[0])
            self.assertIn('SECURITY_SCAN=skipped', run.stderr)

    def test_crane_web_build_uses_nginx_root(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'package.json').write_text('{}')
            (d / 'dist').mkdir()
            (d / 'dist' / 'index.html').write_text('<html></html>')
            env = self._crane_env(d)
            run = subprocess.run([BASH, CRANE_BUILD, 'build', 'dev', 'demo'], cwd=d, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn('MODE=web BASE=nginx:alpine', run.stdout)
            self.assertIn('--exposed-ports 80', run.stdout)

    def test_crane_server_requires_entrypoint(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'package.json').write_text('{}')
            payload = d / 'srv'
            payload.mkdir()
            (payload / 'server.js').write_text('console.log(1)')
            env = self._crane_env(d)
            env['FF_STACK'] = 'server'
            env['FF_ARTIFACT'] = str(payload)
            run = subprocess.run([BASH, CRANE_BUILD, 'build', 'dev', 'demo'], cwd=d, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
            self.assertNotEqual(run.returncode, 0)
            self.assertIn('FF_ENTRYPOINT', run.stderr)

    def test_crane_rejects_tar_identity_mismatch(self):
        # manifest Config 文件名与配置摘要不一致 = 产物格式异常,必须失败而非输出假身份
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'pom.xml').write_text('<project/>')
            target = d / 'target'
            target.mkdir()
            (target / 'demo-app-1.0.0.jar').write_bytes(b'fake-jar-bytes')
            env = self._crane_env(d)
            env['CRANE_BAD_NAME'] = '1'
            run = subprocess.run([BASH, CRANE_BUILD, 'build', 'dev', 'demo'], cwd=d, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
            self.assertNotEqual(run.returncode, 0)
            self.assertIn('一致性校验失败', run.stderr)

    def test_crane_rejects_payload_with_env_secret(self):
        # 产物目录守卫与 Docker 路径同源:.env* 不进镜像层
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'package.json').write_text('{}')
            payload = d / 'dist'
            payload.mkdir()
            (payload / '.env.local').write_text('SECRET=1')
            env = self._crane_env(d)
            env['FF_ARTIFACT'] = str(payload)
            run = subprocess.run([BASH, CRANE_BUILD, 'build', 'dev', 'demo'], cwd=d, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
            self.assertNotEqual(run.returncode, 0)
            self.assertIn('.env', run.stderr)


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
[[ "$1" != -- ]] || shift
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
        return subprocess.run([BASH, script, *args], cwd=d, env=env,
                              capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120 if os.name == 'nt' else 30)

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

    def test_native_build_packages_static_directory(self):
        for name in ('dist', 'build'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                d = Path(directory)
                env = self._offline_env(d)
                (d / 'package.json').write_text('{}', encoding='utf-8')
                self._static_artifact(d / name)
                run = self._workflow(IMAGE_BUILD, d, env, 'build', 'dev', 'demo')
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                self.assertIn(f'ARTIFACT_DIR={name}', run.stdout)
                self._assert_static_context(run.stderr)

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

    def test_wsl_build_archives_ignored_directories_and_normalizes_paths(self):
        for name in ('dist', 'build', './static output/../static output/', 'absolute', 'external'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory, \
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

    def test_directory_artifact_rejects_repository_and_nested_env(self):
        for artifact, secret in (('.', '.git'), ('dist', 'assets/.env.dev')):
            with self.subTest(artifact=artifact), tempfile.TemporaryDirectory() as directory:
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

    def test_build_strict_scan_fails_when_trivy_missing_native_and_wsl(self):
        for wsl in (False, True):
            with self.subTest(wsl=wsl), tempfile.TemporaryDirectory() as directory:
                d = Path(directory)
                env = self._offline_env(d, wsl=wsl)
                env['FF_REQUIRE_SECURITY_SCAN'] = '1'
                (d / 'pom.xml').write_text('<project/>', encoding='utf-8')
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

    def test_ssh_runner_preserves_empty_arguments_and_inspect_template(self):
        for health, ready in (('', ''), ('', '2'), ('http://127.0.0.1:8080/health', '2')):
            with self.subTest(health=health, ready=ready), tempfile.TemporaryDirectory() as directory:
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


if __name__ == '__main__':
    unittest.main()
