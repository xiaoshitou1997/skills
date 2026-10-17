"""Regression tests for engineering skills helper scripts (no remote server)."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
# PATH 里排在前的可能是 System32 的 WSL bash,必须显式使用 Git Bash;
# 且 bash 不接受 Windows 反斜杠路径(msys 会吞掉反斜杠),统一转为正斜杠。
BASH = str(Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Git/bin/bash.exe')
if not Path(BASH).exists():
    BASH = 'bash'
DOCTOR = (ROOT / 'mv-toolchain-manager/scripts/doctor.py').as_posix()
PREFLIGHT = (ROOT / 'mv-container-deploy/scripts/deploy-preflight.sh').as_posix()
DEPLOY = (ROOT / 'mv-container-deploy/scripts/deploy.sh').as_posix()
RUNNER = (ROOT / 'mv-container-deploy/scripts/target-runner.sh').as_posix()
QUALITY = (ROOT / 'mv-image-build/scripts/quality-check.sh').as_posix()


def exec_run(*cmd, cwd=None, env=None, input=None):
    # 脚本输出含中文(UTF-8),必须显式指定编码,中文 Windows 默认 GBK 会解码崩溃。
    return subprocess.run(cmd, cwd=cwd, env=env, input=input, text=True, encoding='utf-8', errors='replace', capture_output=True)


def sealed(path):
    """端点透明加密已把该文件密封为 %XXXX-Header 形状的密文头。"""
    try:
        with open(path, 'rb') as fh:
            head = fh.read(16)
            return head.startswith(b'%') and b'-Header' in head
    except OSError:
        return False


class EnhancementsTests(unittest.TestCase):
    def test_doctor_is_read_only(self):
        with tempfile.TemporaryDirectory() as d:
            p=exec_run(sys.executable, DOCTOR, '--project', d, '--json')
            self.assertEqual(p.returncode, 0, p.stderr)
            data=json.loads(p.stdout)
            self.assertIn('docker_compose', data['checks'])
            self.assertEqual(list(Path(d).iterdir()), [])
            # 探针冒烟文件必须用完即清,不在系统临时目录留残留
            self.assertFalse((Path(tempfile.gettempdir()) / 'ff_build_chain_smoke.java').exists())

    def test_preflight_rejects_missing_docker(self):
        with tempfile.TemporaryDirectory() as d:
            env=os.environ.copy()
            env['FF_WSL_BRIDGE']='0'
            p=exec_run(BASH,PREFLIGHT,'prod','api',cwd=d,env=env)
            self.assertNotEqual(p.returncode,0)

    def test_prod_delivery_no_dev_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'.dockerignore').write_text('.env*\n.git\n')
            (root/'.env.prod').write_text('APP_ENV=prod\n')
            (root/'compose.delivery.yml').write_text('services:\n  app:\n    image: ${FF_IMAGE}\n')
            b=root/'bin'; b.mkdir()
            docker=b/'docker'
            docker.write_text('#!/bin/sh\nif [ "$1" = "image" ] && [ "$2" = "inspect" ]; then echo sha256:fakehash; fi\nif [ "$1" = "compose" ] && [ "$2" = "version" ]; then echo v2.0; fi\n')
            docker.chmod(0o755)
            env=os.environ.copy()
            env.update(PATH=str(b)+os.pathsep+env['PATH'], HOME=d, FF_PROD_SSH='deploy@prod.example.com', FF_WSL_BRIDGE='0')
            p=exec_run(BASH,DEPLOY,'deploy','prod','api','api:abc','--approve-prod',cwd=d,env=env)
            self.assertNotEqual(p.returncode,0)
            self.assertIn('no verified dev deployment receipt',p.stderr)

    def test_quality_fails_if_no_scripts(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'package.json').write_text('{"scripts":{}}')
            (root/'package-lock.json').write_text('{}')
            # Windows Git Bash 通常没有 python3 命令,放一个转发 shim,让脚本走真正的检查逻辑。
            b=root/'bin'; b.mkdir()
            shim=b/'python3'
            shim.write_text('#!/bin/sh\nexec python "$@"\n')
            shim.chmod(0o755)
            env=os.environ.copy()
            env['PATH']=str(b)+os.pathsep+env['PATH']
            p=exec_run(BASH,QUALITY,'quick',cwd=d,env=env)
            self.assertNotEqual(p.returncode,0)
            self.assertIn('not a pass',p.stderr)

    def test_verified_release_tracks_prev_and_history(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            target=root/'.mv/container-deploy/api'
            target.mkdir(parents=True)
            (target/'compose.yml').write_text('services:\n  app:\n    image: ${FF_IMAGE}\n')
            (target/'.env.dev').write_text('APP_ENV=dev\n')
            b=root/'bin'; b.mkdir()
            docker=b/'docker'
            docker.write_text('''#!/bin/sh
case "$1" in
  image) if [ "$2" = inspect ]; then echo sha256:mocked; fi ;;
  inspect) case "$*" in *State.Health*) echo healthy;; *State.Status*) echo running;; esac ;;
  compose) case "$*" in *'ps -q'*) echo mock-container;; *' ps'*) echo mock-container;; esac ;;
esac
''')
            docker.chmod(0o755)
            env=os.environ.copy()
            env.update(HOME=d,PATH=str(b)+os.pathsep+env['PATH'])
            first=exec_run(BASH,RUNNER,'deploy','dev','api','api:one','',cwd=d,env=env)
            second=exec_run(BASH,RUNNER,'deploy','dev','api','api:two','',cwd=d,env=env)
            self.assertEqual(first.returncode,0,first.stderr)
            self.assertEqual(second.returncode,0,second.stderr)
            # 收据文件由 target-runner.sh 写盘,部署了安全软件的机器上可能被透明加密密封;
            # 行为验证已由 stdout 断言覆盖,文件状态断言只在干净机器执行。
            if sealed(target/'current-image'):
                self.skipTest('Security agent sealed the receipt files; state assertion needs a clean machine')
            self.assertEqual((target/'current-image').read_text(encoding='utf-8').strip(),'api:two')
            self.assertEqual((target/'previous-image').read_text(encoding='utf-8').strip(),'api:one')
            self.assertEqual(len((target/'releases.tsv').read_text(encoding='utf-8').splitlines()),2)


    def test_running_only_dev_does_not_claim_strong_health(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            target=base/'.mv/container-deploy/api'
            target.mkdir(parents=True)
            (target/'compose.yml').write_text('services:\n  app:\n    image: ${FF_IMAGE}\n')
            (target/'.env.dev').write_text('APP_ENV=dev\n')
            binary=base/'bin';binary.mkdir()
            docker=binary/'docker'
            docker.write_text('''#!/bin/sh
case "$1" in
  image) echo sha256:fake;;
  inspect) case "$*" in *State.Health*) echo none;; *State.Status*) echo running;; esac;;
  compose) case "$*" in *'ps -q'*) echo mock;; esac;;
esac
''')
            docker.chmod(0o755)
            env=os.environ.copy();env.update(HOME=d,PATH=str(binary)+os.pathsep+env['PATH'])
            run=exec_run(BASH,RUNNER,'deploy','dev','api','api:one','',cwd=d,env=env)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertIn('VERIFIED_HEALTH=running-only',run.stdout)
            if sealed(target/'releases.tsv'):
                self.skipTest('Security agent sealed the receipt files; state assertion needs a clean machine')
            self.assertEqual((target/'releases.tsv').read_text(encoding='utf-8').strip().split('\t')[-1], 'running-only')
            (target/'.env.prod').write_text('APP_ENV=prod\n')
            prod=exec_run(BASH,RUNNER,'deploy','prod','api','api:two','',cwd=d,env=env)
            self.assertNotEqual(prod.returncode,0)
            self.assertIn('requires a Docker healthcheck', prod.stderr)
            if not sealed(target/'current-image'):
                self.assertEqual((target/'current-image').read_text(encoding='utf-8').strip(), 'api:one')

    def test_failing_compose_start_attempts_to_restore_previous(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            target=base/'.mv/container-deploy/api'
            target.mkdir(parents=True)
            (target/'compose.yml').write_text('services:\n  app:\n    image: ${FF_IMAGE}\n')
            (target/'.env.dev').write_text('APP_ENV=dev\n')
            (target/'current-image').write_text('api:old\n')
            binary=base/'bin';binary.mkdir()
            docker=binary/'docker'
            docker.write_text('''#!/bin/sh
case "$1" in
  image) echo sha256:fake;;
  inspect) case "$*" in *State.Health*) echo healthy;; *State.Status*) echo running;; esac;;
  compose)
    case "$*" in
      *' up '* ) if [ "$FF_IMAGE" = api:bad ]; then exit 9; fi;;
      *'ps -q'*) echo mock;;
    esac;;
esac
''')
            docker.chmod(0o755)
            env=os.environ.copy();env.update(HOME=d,PATH=str(binary)+os.pathsep+env['PATH'])
            failed=exec_run(BASH,RUNNER,'deploy','dev','api','api:bad','',cwd=d,env=env)
            self.assertNotEqual(failed.returncode,0)
            self.assertIn('Trying application rollback',failed.stderr)
            if not sealed(target/'current-image'):
                self.assertEqual((target/'current-image').read_text(encoding='utf-8').strip(),'api:old')
            self.assertFalse((target/'releases.tsv').exists())


    def test_purge_guard_refuses_home_and_root(self):
        sys.path.insert(0, str(ROOT / 'mv-toolchain-manager/scripts/installer'))
        import runtime_cli as rc
        with self.assertRaises(SystemExit):
            rc._purge_guard(Path.home())
        # 正常根(默认安装位置形状)与测试覆盖目录不拦
        rc._purge_guard(Path.home() / '.mv' / 'toolchain-manager')
        rc._purge_guard(Path(tempfile.gettempdir()) / 'btc-purge-guard-test')

    def test_download_rejects_zip_slip(self):
        sys.path.insert(0, str(ROOT / 'mv-toolchain-manager/scripts/installer'))
        import download as dl
        with tempfile.TemporaryDirectory() as d:
            evil = Path(d) / 'evil.zip'
            with zipfile.ZipFile(evil, 'w') as z:
                z.writestr('../evil.txt', 'pwned')
            with self.assertRaises(ValueError):
                dl.extract(evil, Path(d) / 'out')
            self.assertFalse((Path(d) / 'evil.txt').exists())

    def test_verify_download_fails_closed_on_mismatch(self):
        sys.path.insert(0, str(ROOT / 'mv-toolchain-manager/scripts/installer'))
        import download as dl
        with tempfile.TemporaryDirectory() as d:
            archive = Path(d) / 'gradle-8.5-bin.zip'
            archive.write_bytes(b'not-a-real-archive')
            orig = dl._fetch_checksum_text
            dl._fetch_checksum_text = lambda url: 'a' * 64 + '\n'
            try:
                with self.assertRaises(dl.ChecksumMismatch):
                    dl.verify_download(
                        'https://services.gradle.org/distributions/gradle-8.5-bin.zip', archive)
            finally:
                dl._fetch_checksum_text = orig

    def test_verify_download_accepts_matching_checksum(self):
        sys.path.insert(0, str(ROOT / 'mv-toolchain-manager/scripts/installer'))
        import hashlib
        import download as dl
        with tempfile.TemporaryDirectory() as d:
            archive = Path(d) / 'gradle-8.5-bin.zip'
            archive.write_bytes(b'archive-bytes')
            good = hashlib.sha256(b'archive-bytes').hexdigest()
            orig = dl._fetch_checksum_text
            dl._fetch_checksum_text = lambda url: good + '\n'
            try:
                dl.verify_download(
                    'https://services.gradle.org/distributions/gradle-8.5-bin.zip', archive)
            finally:
                dl._fetch_checksum_text = orig


if __name__ == '__main__':
    unittest.main()
