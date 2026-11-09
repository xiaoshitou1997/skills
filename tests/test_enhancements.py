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
# PATH 里排在前的可能是 System32 自带的 bash,必须显式使用 Git Bash;
# 且 bash 不接受 Windows 反斜杠路径(msys 会吞掉反斜杠),统一转为正斜杠。
BASH = str(Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Git/bin/bash.exe')
if not Path(BASH).exists():
    BASH = 'bash'
DOCTOR = (ROOT / 'mv-toolchain-manager/scripts/doctor.py').as_posix()
PREFLIGHT = (ROOT / 'mv-deploy-container-delivery/scripts/deploy-preflight.sh').as_posix()
DEPLOY = (ROOT / 'mv-deploy-container-delivery/scripts/deploy.sh').as_posix()
RUNNER = (ROOT / 'mv-deploy-container-delivery/scripts/target-runner.sh').as_posix()
QUALITY = (ROOT / 'mv-build-image-builder/scripts/quality-check.sh').as_posix()


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


def stub_env(d, bin_dir, **updates):
    # MSYS 运行时会对继承的 Windows 形式 PATH 前置自带目录,PATH 里的假命令永远轮不到
    # (真 /usr/bin/ssh 抢先);与 test_workflows._offline_env 同法:
    # 经 BASH_ENV 在每个 bash 启动时以 POSIX 形式重新前置。
    fix = Path(d) / 'path-fix.sh'
    fix.write_text(f'export PATH="$(cd -- "{bin_dir.as_posix()}" && pwd):$PATH"\n', newline='\n')
    env = os.environ.copy()
    env['PATH'] = str(bin_dir) + os.pathsep + env['PATH']
    env['BASH_ENV'] = fix.as_posix()
    env.update(updates)
    return env


class EnhancementsTests(unittest.TestCase):
    def test_doctor_is_read_only(self):
        with tempfile.TemporaryDirectory() as d:
            p=exec_run(sys.executable, DOCTOR, '--project', d, '--json')
            self.assertEqual(p.returncode, 0, p.stderr)
            data=json.loads(p.stdout)
            self.assertIn('git', data['checks'])
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_preflight_requires_target_and_remote_compose(self):
        with tempfile.TemporaryDirectory() as d:
            env=os.environ.copy()
            p=exec_run(BASH,PREFLIGHT,'prod','api',cwd=d,env=env)
            self.assertNotEqual(p.returncode,0)
            self.assertIn('FF_PROD_SSH',p.stderr)
            # 静态配置齐备后,目标机 Compose v2 经 SSH 校验,不可达即拒绝。
            root=Path(d)
            (root/'.dockerignore').write_text('.env*\n.git\n')
            (root/'.env.prod').write_text('APP_ENV=prod\n')
            b=root/'bin'; b.mkdir()
            ssh=b/'ssh'
            ssh.write_text('#!/bin/sh\nexit 127\n')
            ssh.chmod(0o755)
            env=stub_env(d, b, FF_PROD_SSH='deploy@prod.example.com')
            p=exec_run(BASH,PREFLIGHT,'prod','api',cwd=d,env=env)
            self.assertEqual(p.returncode,3)
            self.assertIn('Compose',p.stderr)

    def test_prod_delivery_no_dev_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'.dockerignore').write_text('.env*\n.git\n')
            (root/'.env.prod').write_text('APP_ENV=prod\n')
            (root/'compose.delivery.yml').write_text('services:\n  app:\n    image: ${FF_IMAGE}\n')
            # 干净 Git 基线:空提交给出真实 SHA;status 不计未跟踪文件,运行产物不致 dirty;
            # .env* 始终未被跟踪,env_checks 才放行。不依赖 .gitignore——它经进程落盘会被
            # 透明加密封密,git 读到密文后忽略规则失效。
            subprocess.run(['git','init','-q'],cwd=root,check=True)
            subprocess.run(['git','-c','user.email=t@example.com','-c','user.name=t',
                            'commit','-q','--allow-empty','-m','baseline'],cwd=root,check=True)
            subprocess.run(['git','config','status.showUntrackedFiles','no'],cwd=root,check=True)
            b=root/'bin'; b.mkdir()
            docker=b/'docker'
            docker.write_text('#!/bin/sh\nif [ "$1" = "image" ] && [ "$2" = "inspect" ]; then echo sha256:fakehash; fi\nif [ "$1" = "compose" ] && [ "$2" = "version" ]; then echo v2.0; fi\n')
            docker.chmod(0o755)
            # 假 ssh:目标机 Image ID 校验通过后,晋级门禁在本机收据处拒绝,无需真实连接。
            ssh=b/'ssh'
            ssh.write_text('#!/bin/sh\necho sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n')
            ssh.chmod(0o755)
            env=stub_env(d, b, HOME=d, FF_PROD_SSH='deploy@prod.example.com')
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
            env=stub_env(d, b)
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
  compose)
    case "$*" in
      *'ps -q'*) echo mock-container ;;
      *'ps --format'*) printf 'app\tapi:one\n' ;;
      *' ps'*) echo mock-container ;;
    esac ;;
esac
''')
            docker.chmod(0o755)
            env=stub_env(d,b,HOME=str(d))
            first=exec_run(BASH,RUNNER,'deploy','dev','api','api:one','','','version_20260101000000_000000000001','',cwd=d,env=env)
            second=exec_run(BASH,RUNNER,'deploy','dev','api','api:two','','','version_20260101000000_000000000002','',cwd=d,env=env)
            self.assertEqual(first.returncode,0,first.stderr)
            self.assertEqual(second.returncode,0,second.stderr)
            self.assertIn('VERSION=version_20260101000000_000000000002',second.stdout)
            # 运行状态源是版本清单:每次部署落一份 versions/<版本>.tsv,
            # current-version 指向当前版本,发布记录逐版本追加。
            versions=target/'versions'
            manifest_file=versions/'version_20260101000000_000000000002.tsv'
            if sealed(manifest_file):
                self.skipTest('Security agent sealed the state files; state assertion needs a clean machine')
            manifest=manifest_file.read_text(encoding='utf-8').splitlines()
            self.assertEqual(len(manifest),1)
            self.assertEqual(manifest[0].split('\t')[1],'api:two')
            self.assertEqual((target/'current-version').read_text(encoding='utf-8').strip(),'version_20260101000000_000000000002')
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
  compose) case "$*" in *'ps -q'*) echo mock;; *'ps --format'*) printf 'app\tapi:one\n';; esac;;
esac
''')
            docker.chmod(0o755)
            env=stub_env(d,binary,HOME=str(d))
            run=exec_run(BASH,RUNNER,'deploy','dev','api','api:one','','','version_20260101000000_0123456789ab','',cwd=d,env=env)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertIn('VERIFIED_HEALTH=running-only',run.stdout)
            if sealed(target/'releases.tsv'):
                self.skipTest('Security agent sealed the receipt files; state assertion needs a clean machine')
            self.assertEqual((target/'releases.tsv').read_text(encoding='utf-8').strip().split('\t')[-1], 'running-only')
            (target/'.env.prod').write_text('APP_ENV=prod\n')
            prod=exec_run(BASH,RUNNER,'deploy','prod','api','api:two','','','version_20260101000000_0123456789ab','',cwd=d,env=env)
            self.assertNotEqual(prod.returncode,0)
            self.assertIn('requires FF_HEALTH_URL', prod.stderr)
            if not sealed(target/'current-image'):
                self.assertEqual((target/'current-image').read_text(encoding='utf-8').strip(), 'api:one')

    def test_healthcheck_only_dev_records_liveness_and_is_not_promotable(self):
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
  inspect) case "$*" in *State.Health*) echo healthy;; *State.Status*) echo running;; esac;;
  compose) case "$*" in *'ps -q'*) echo mock;; *'ps --format'*) printf 'app\tapi:one\n';; esac;;
esac
''')
            docker.chmod(0o755)
            env=stub_env(d,binary,HOME=str(d))
            run=exec_run(BASH,RUNNER,'deploy','dev','api','api:one','','','version_20260101000000_0123456789ab','',cwd=d,env=env)
            self.assertEqual(run.returncode,0,run.stderr)
            # 收据门禁只认 readiness(FF_HEALTH_URL):HEALTHCHECK 属 liveness 观测位。
            self.assertIn('VERIFIED_HEALTH=liveness-only',run.stdout)
            self.assertNotIn('DEV_RECEIPT',run.stdout)
            if sealed(target/'releases.tsv'):
                self.skipTest('Security agent sealed the receipt files; state assertion needs a clean machine')
            self.assertEqual((target/'releases.tsv').read_text(encoding='utf-8').strip().split('\t')[-1], 'liveness-only')
            receipts=target.parent/'receipts'/'api'
            self.assertFalse(receipts.exists() and any(receipts.iterdir()))
            (target/'.env.prod').write_text('APP_ENV=prod\n')
            prod=exec_run(BASH,RUNNER,'deploy','prod','api','api:two','','','version_20260101000000_0123456789ab','',cwd=d,env=env)
            self.assertNotEqual(prod.returncode,0)
            self.assertIn('requires FF_HEALTH_URL', prod.stderr)

    def test_failing_compose_start_attempts_to_restore_previous(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            target=base/'.mv/container-deploy/api'
            target.mkdir(parents=True)
            (target/'compose.yml').write_text('services:\n  app:\n    image: ${FF_IMAGE}\n')
            (target/'.env.dev').write_text('APP_ENV=dev\n')
            # 新契约:回退目标是上一版本清单,current-version 指向当前版本。
            versions=target/'versions'
            versions.mkdir(parents=True)
            (versions/'version_20260101000000_000000000001.tsv').write_text('app\tapi:old\tsha256:fake\n')
            (target/'current-version').write_text('version_20260101000000_000000000001\n')
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
      *'ps --format'*) printf 'app\\tapi:one\\n';;
    esac;;
esac
''')
            docker.chmod(0o755)
            env=stub_env(d,binary,HOME=str(d))
            failed=exec_run(BASH,RUNNER,'deploy','dev','api','api:bad','','','version_20260101000000_0123456789ab','',cwd=d,env=env)
            self.assertNotEqual(failed.returncode,0)
            # 启动失败时按上一版本清单回退整栈;数据库迁移不随回滚。
            self.assertIn('Trying application rollback to version_20260101000000_000000000001',failed.stderr)
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
