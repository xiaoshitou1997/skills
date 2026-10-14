"""Safe unit/smoke tests with sandbox git repos and a fake docker binary."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
# PATH 里排在前的可能是 System32 的 WSL bash,必须显式使用 Git Bash;
# 且 bash 不接受 Windows 反斜杠路径(msys 会吞掉反斜杠),统一转为正斜杠。
BASH = str(Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Git/bin/bash.exe')
if not Path(BASH).exists():
    BASH = 'bash'
GIT_AUDIT = (ROOT / 'mv-publishing-git-changes/scripts/stage_audit.py').as_posix()
DETECT = (ROOT / 'mv-managing-toolchains/scripts/detect.py').as_posix()
DELIVER = (ROOT / 'mv-delivering-containers/scripts/deliver.sh').as_posix()


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
            run = subprocess.run([BASH, DELIVER, 'deploy', 'prod', 'someapp', 'someapp:abc'], cwd=d, capture_output=True, text=True)
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
            run = subprocess.run([BASH, DELIVER, 'build', 'dev', 'demo'], cwd=d, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn('IMAGE=demo:', run.stdout)
            self.assertIn('ARTIFACT=', run.stdout)
            log = docker_log.read_text(encoding='utf-8', errors='replace')
            self.assertIn('build --pull', log)
            self.assertIn('Dockerfile', log)
            self.assertIn('app.jar', log)          # 产物改名进瘦上下文
            self.assertNotIn('demo-app-1.0.0.jar', log)  # 原名不进上下文
            self.assertNotIn('-sources.jar', log)  # sources jar 被排除

    def test_build_without_artifact_fails_with_guidance(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / '.dockerignore').write_text('.env*\n.git\n')
            (d / 'pom.xml').write_text('<project/>')
            run = subprocess.run([BASH, DELIVER, 'build', 'dev', 'demo'], cwd=d, capture_output=True, text=True, encoding='utf-8', errors='replace')
            self.assertNotEqual(run.returncode, 0)
            self.assertIn('mvn -B package', run.stderr)
            self.assertIn('mv-managing-toolchains', run.stderr)


if __name__ == '__main__':
    unittest.main()
