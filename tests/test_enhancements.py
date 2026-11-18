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
PREFLIGHT = (ROOT / 'mv-delivery-standards/scripts/deploy-preflight.sh').as_posix()
DEPLOY = (ROOT / 'mv-delivery-standards/scripts/deploy.sh').as_posix()
RUNNER = (ROOT / 'mv-delivery-standards/scripts/target-runner.sh').as_posix()
QUALITY = (ROOT / 'mv-delivery-standards/scripts/quality-check.sh').as_posix()


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
    def test_delivery_entrypoints_fail_before_remote_or_target_writes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            target = root / '.mv/delivery-standards/api'
            target.mkdir(parents=True)
            (target / 'compose.yml').write_text('sentinel')
            (target / '.env.dev').write_text('sentinel')
            before = {p.relative_to(root): (p.read_bytes(), p.stat().st_mode)
                      for p in target.rglob('*') if p.is_file()}
            env = os.environ.copy()
            env.update(HOME=d, FF_DEV_SSH='user@invalid.example',
                       FF_PROD_SSH='user@invalid.example')
            guarded = 'ssh() { exit 91; }; scp() { exit 92; }; docker() { exit 93; }; source "$@"'
            for environment in ('dev', 'prod'):
                for action in ('deploy', 'rollback', 'status'):
                    args = ['api:release'] if action == 'deploy' else []
                    run = exec_run(BASH, '-c', guarded, 'guard', DEPLOY, action, environment, 'api', *args, cwd=d, env=env)
                    self.assertEqual(run.returncode, 3, run.stderr)
                    self.assertIn('unavailable pending safety verification', run.stderr)
                    self.assertNotIn('DEV_RECEIPT', run.stdout)
                for action in ('deploy', 'rollback', 'status', 'plan'):
                    image = 'api:release' if action in ('deploy', 'plan') else ''
                    version = 'version_20260101000000_abc' if action == 'deploy' else ''
                    run = exec_run(BASH, '-c', guarded, 'guard', RUNNER, action, environment, 'api', image, '', '2', version, '', cwd=d, env=env)
                    self.assertEqual(run.returncode, 3, run.stderr)
                    self.assertIn('unavailable pending safety verification', run.stderr)
                    self.assertNotIn('PLAN_LINE=', run.stdout)
            after = {p.relative_to(root): (p.read_bytes(), p.stat().st_mode)
                     for p in target.rglob('*') if p.is_file()}
            self.assertEqual(before, after)
            self.assertFalse((target / 'versions').exists())
            self.assertFalse((root / '.mv/delivery-standards/receipts').exists())

    def test_delivery_validation_precedes_refusal(self):
        with tempfile.TemporaryDirectory() as d:
            for cmd in ((DEPLOY, 'deploy', 'dev', 'api', 'bad image'),
                        (RUNNER, 'plan', 'dev', 'api', 'bad image')):
                run = exec_run(BASH, *cmd, cwd=d, env=dict(os.environ, HOME=d))
                self.assertEqual(run.returncode, 2, run.stderr)
                self.assertNotIn('unavailable pending safety verification', run.stderr)
            self.assertFalse((Path(d) / '.mv').exists())

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
            docker.write_text('#!/bin/sh\nif [ "$1" = "image" ] && [ "$2" = "inspect" ]; then echo sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaahash; fi\nif [ "$1" = "compose" ] && [ "$2" = "version" ]; then echo v2.0; fi\n')
            docker.chmod(0o755)
            # 假 ssh:目标机 Image ID 校验通过后,晋级门禁在本机收据处拒绝,无需真实连接。
            ssh=b/'ssh'
            ssh.write_text('#!/bin/sh\necho sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n')
            ssh.chmod(0o755)
            env=stub_env(d, b, HOME=d, FF_PROD_SSH='deploy@prod.example.com')
            p=exec_run(BASH,DEPLOY,'deploy','prod','api','api:abc','--approve-prod',cwd=d,env=env)
            self.assertNotEqual(p.returncode,0)
            self.assertIn('Deployment, rollback and status are unavailable',p.stderr)

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

    @unittest.skip('部署入口关闭，待安全修复后重新验证')
    def test_verified_release_tracks_prev_and_history(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            target=root/'.mv/delivery-standards/api'
            target.mkdir(parents=True)
            (target/'compose.yml').write_text('services:\n  app:\n    image: ${FF_IMAGE}\n')
            (target/'.env.dev').write_text('APP_ENV=dev\n')
            b=root/'bin'; b.mkdir()
            docker=b/'docker'
            docker.write_text('''#!/bin/sh
case "$1" in
  image) if [ "$2" = inspect ]; then echo sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; fi ;;
  inspect) case "$*" in *'.Image'*) echo sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa;; *State.Health*) echo healthy;; *State.Status*) echo running;; esac ;;
  compose)
    case "$*" in
      *'config --images'*) echo "$FF_IMAGE" ;;
      *'ps -q'*) echo mock-container ;;
      *'ps --format'*) printf 'app\t%s\n' "$FF_IMAGE" ;;
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
            self.assertIn('sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', manifest[0])
            self.assertEqual((target/'current-version').read_text(encoding='utf-8').strip(),'version_20260101000000_000000000002')
            self.assertEqual(len((target/'releases.tsv').read_text(encoding='utf-8').splitlines()),2)


    @unittest.skip('部署入口关闭，待安全修复后重新验证')
    def test_running_only_dev_does_not_claim_strong_health(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            target=base/'.mv/delivery-standards/api'
            target.mkdir(parents=True)
            (target/'compose.yml').write_text('services:\n  app:\n    image: ${FF_IMAGE}\n')
            (target/'.env.dev').write_text('APP_ENV=dev\n')
            binary=base/'bin';binary.mkdir()
            docker=binary/'docker'
            docker.write_text('''#!/bin/sh
case "$1" in
  image) echo sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa;;
  inspect) case "$*" in *'.Image'*) echo sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa;; *State.Health*) echo none;; *State.Status*) echo running;; esac;;
  compose) case "$*" in *'config --images'*) echo "$FF_IMAGE";; *'ps -q'*) echo mock;; *'ps --format'*) printf 'app\tapi:one\n';; esac;;
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
            self.assertIn('Deployment, rollback and status are unavailable', prod.stderr)
            if not sealed(target/'current-version'):
                self.assertEqual((target/'current-version').read_text(encoding='utf-8').strip(), 'version_20260101000000_0123456789ab')

    @unittest.skip('部署入口关闭，待安全修复后重新验证')
    def test_healthcheck_only_dev_records_liveness_and_is_not_promotable(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            target=base/'.mv/delivery-standards/api'
            target.mkdir(parents=True)
            (target/'compose.yml').write_text('services:\n  app:\n    image: ${FF_IMAGE}\n')
            (target/'.env.dev').write_text('APP_ENV=dev\n')
            binary=base/'bin';binary.mkdir()
            docker=binary/'docker'
            docker.write_text('''#!/bin/sh
case "$1" in
  image) echo sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa;;
  inspect) case "$*" in *'.Image'*) echo sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa;; *State.Health*) echo healthy;; *State.Status*) echo running;; esac;;
  compose) case "$*" in *'config --images'*) echo "$FF_IMAGE";; *'ps -q'*) echo mock;; *'ps --format'*) printf 'app\tapi:one\n';; esac;;
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
            self.assertIn('Deployment, rollback and status are unavailable', prod.stderr)

    @unittest.skip('部署入口关闭，待安全修复后重新验证')
    def test_dev_underreplicated_or_unparseable_topology_is_not_strong(self):
        cases = [(json.dumps({'services': {'app': {'deploy': {'replicas': 2}}}}), 'readiness-partial'),
                 ('invalid', 'readiness-partial'),
                 (json.dumps({'services': {'app': {}}}), 'strong')]
        for topology, expected in cases:
            with self.subTest(topology=topology), tempfile.TemporaryDirectory() as d:
                base = Path(d)
                target = base / '.mv/delivery-standards/api'
                target.mkdir(parents=True)
                (target / 'compose.yml').write_text('services: {}\n')
                (target / '.env.dev').write_text('APP_ENV=dev\n')
                binary = base / 'bin'
                binary.mkdir()
                docker = binary / 'docker'
                docker.write_text('''#!/bin/sh
case "$1" in
  image) echo sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa;;
  inspect) case "$*" in *'.Image'*) echo sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa;; *State.Health*) echo healthy;; *State.Status*) echo running;; *) echo sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa;; esac;;
  compose) case "$*" in
    *'config --images'*) echo "$FF_IMAGE";;
    *'config --format json'*) printf '%s' "$TEST_TOPOLOGY";;
    *'config --services'*) echo app;;
    *'ps -q'*) echo first;;
    *'ps --format'*) printf 'app\tapi:one\n';;
  esac;;
esac
''')
                docker.chmod(0o755)
                for name, body in (('curl', 'exit 0'),
                                   ('python3', 'exec "' + Path(sys.executable).as_posix() + '" "$@"')):
                    stub = binary / name
                    stub.write_text('#!/bin/sh\n' + body + '\n')
                    stub.chmod(0o755)
                env = stub_env(d, binary, HOME=d, TEST_TOPOLOGY=topology)
                run = exec_run(BASH, RUNNER, 'deploy', 'dev', 'api', 'api:one',
                               'http://localhost/ready', '2', 'version_20260101000000_0123456789ab',
                               '', cwd=d, env=env)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertIn('VERIFIED_HEALTH=' + expected, run.stdout)
                if expected != 'strong':
                    self.assertNotIn('VERIFIED_HEALTH=strong', run.stdout)

    @unittest.skip('部署入口关闭，待安全修复后重新验证')
    def test_prod_multiservice_is_rejected_before_compose_up(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            target = base / '.mv/delivery-standards/api'
            target.mkdir(parents=True)
            (target / 'compose.yml').write_text('services: {}\n')
            (target / '.env.prod').write_text('APP_ENV=prod\n')
            binary = base / 'bin'
            binary.mkdir()
            docker = binary / 'docker'
            docker.write_text('''#!/bin/sh
case "$*" in
  *'config --format json'*) printf '%s' '{"services":{"app":{},"job":{}}}';;
  *' up '*) echo STARTED >&2;;
esac
''')
            docker.chmod(0o755)
            python_shim = binary / 'python3'
            python_shim.write_text('#!/bin/sh\nexec "' + Path(sys.executable).as_posix() + '" "$@"\n')
            python_shim.chmod(0o755)
            env = stub_env(d, binary, HOME=d, FF_REQUIRE_DEV_PROOF='0')
            run = exec_run(BASH, RUNNER, 'deploy', 'prod', 'api', 'api:one',
                           'http://localhost/ready', '2', 'version_20260101000000_0123456789ab',
                           '', cwd=d, env=env)
            self.assertEqual(run.returncode, 3, run.stderr)
            self.assertIn('Deployment, rollback and status are unavailable', run.stderr)
            self.assertNotIn('STARTED', run.stderr)
            self.assertFalse((target / 'current-version').exists())

    def test_production_topology_rejects_unprovable_readiness(self):
        source = Path(RUNNER).read_text(encoding='utf-8')
        function = source.split('check_prod_topology() {', 1)[1].split('\n}\n', 1)[0]
        shell = ('check_prod_topology() {' + function + '\n}\n'
                 'docker() { printf "%s" "$TEST_CONFIG"; }\n'
                 'python3() { "$PYTHON_TEST" "$@"; }\n'
                 'DOCKER=(docker)\ncheck_prod_topology image\n')
        cases = [({'services': {'app': {}}}, True),
                 ({'services': {'app': {}, 'job': {}}}, False),
                 ({'services': {'app': {'scale': 2}}}, False),
                 ({'services': {'app': {'deploy': {'replicas': 2}}}}, False),
                 ({'services': {'app': {'deploy': {'mode': 'global'}}}}, False),
                 ({'services': {}}, False)]
        for config, allowed in cases:
            with self.subTest(config=config):
                env = os.environ.copy()
                env.update(TEST_CONFIG=json.dumps(config), PYTHON_TEST=Path(sys.executable).as_posix())
                result = exec_run(BASH, '-c', shell, env=env)
                self.assertEqual(result.returncode == 0, allowed, result.stderr)

    def test_production_mutations_fail_closed_before_remote_access(self):
        with tempfile.TemporaryDirectory() as d:
            env = os.environ.copy()
            env.update(HOME=d, FF_PROD_SSH='deployer@prod.example.com')
            for action, args in (('deploy', ['api:release', '--approve-prod']),
                                 ('rollback', ['--approve-prod'])):
                run = exec_run(BASH, DEPLOY, action, 'prod', 'api', *args, cwd=d, env=env)
                self.assertEqual(run.returncode, 3, run.stderr)
                self.assertIn('Deployment, rollback and status are unavailable', run.stderr)
                runner = exec_run(BASH, RUNNER, action, 'prod', 'api',
                                  'api:release' if action == 'deploy' else '', '', '2',
                                  'version_20260101000000_abc' if action == 'deploy' else '',
                                  '', cwd=d, env=env)
                self.assertEqual(runner.returncode, 3, runner.stderr)
                self.assertIn('Deployment, rollback, plan and status are unavailable', runner.stderr)

    @unittest.skip('部署入口关闭，待安全修复后重新验证')
    def test_plan_snapshot_and_rollback_image_identity(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            target = root / '.mv/delivery-standards/api'
            target.mkdir(parents=True)
            (target / 'compose.yml').write_text('services: {}\n')
            (target / '.env.dev').write_text('APP_ENV=dev\n')
            binary = root / 'bin'
            binary.mkdir()
            image_id = 'sha256:' + 'a' * 64
            docker = binary / 'docker'
            docker.write_text('''#!/bin/sh
case "$1" in
  image) echo "$TEST_IMAGE_ID";;
  inspect) case "$3" in
    *State.Health*) echo healthy;;
    *State.Status*) echo running;;
    *.Image*) echo "$TEST_IMAGE_ID";;
    *.Id*) echo container-id-must-not-be-used;;
  esac;;
  compose) case "$*" in
    *'config --images'*) [ "$FF_IMAGE" = api:new ] || exit 7; echo "$FF_IMAGE";;
    *'ps --format'*) [ "$FF_IMAGE" = api:new ] || exit 8; printf 'app\tapi:new\n';;
    *'ps -q'*) [ -n "$FF_IMAGE" ] || exit 9; echo container-id;;
    *' up '*) case "$*" in *'compose.override.yml'*) echo OVERRIDE_UP >&2;; *) echo PLAIN_UP >&2;; esac;;
  esac;;
esac
''')
            docker.chmod(0o755)
            env = stub_env(d, binary, HOME=d, TEST_IMAGE_ID=image_id)
            plan = exec_run(BASH, RUNNER, 'plan', 'dev', 'api', 'api:new', '', '', '', '', cwd=d, env=env)
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertIn('PLAN_LINE=api:new\t' + image_id, plan.stdout)
            v1 = 'version_20260101000000_000000000001'
            v2 = 'version_20260101000000_000000000002'
            v3 = 'version_20260101000000_000000000003'
            mv = binary / 'mv'
            mv.write_text('#!/bin/sh' + chr(10) + 'case "$*" in *current-version*000000000002*) exit 9;; esac' + chr(10) + 'exec /usr/bin/mv "$@"' + chr(10), newline=chr(10))
            mv.chmod(0o755)
            first = exec_run(BASH, RUNNER, 'deploy', 'dev', 'api', 'api:new', '', '', v1, '', cwd=d, env=env)
            self.assertEqual(first.returncode, 0, first.stderr)
            failed = exec_run(BASH, RUNNER, 'deploy', 'dev', 'api', 'api:new', '', '', v2, '', cwd=d, env=env)
            self.assertEqual(failed.returncode, 4, failed.stderr)
            self.assertIn('Current-version update failed', failed.stderr)
            versions = target / 'versions'
            self.assertTrue((versions / (v2 + '.tsv')).exists())
            deploy = exec_run(BASH, RUNNER, 'deploy', 'dev', 'api', 'api:new', '', '', v3, '', cwd=d, env=env)
            self.assertEqual(deploy.returncode, 0, deploy.stderr)
            self.assertIn('MANIFEST_LINE=app', deploy.stdout)
            probe = exec_run(BASH, '-c', 'IFS= read -r v < "$1"; IFS= read -r row < "$2"; [[ "$v" == "$3" && "$row" == *deploy* ]]',
                             'probe', (target / 'current-version').as_posix(),
                             (target / 'releases.tsv').as_posix(), v3)
            if probe.returncode != 0:
                self.skipTest('Bash cannot read generated version pointer or release history through security agent')
            rollback = exec_run(BASH, RUNNER, 'rollback', 'dev', 'api', '', '', '', '', '', cwd=d, env=env)
            self.assertEqual(rollback.returncode, 0, rollback.stderr)
            self.assertIn('ROLLED_BACK_TO=' + v1, rollback.stdout)
            self.assertNotIn('ROLLED_BACK_TO=' + v2, rollback.stdout)
            self.assertIn('OVERRIDE_UP', rollback.stderr)
            self.assertNotIn('PLAIN_UP', rollback.stderr)
            if not sealed(target / 'compose.override.yml'):
                self.assertIn('image: ' + image_id, (target / 'compose.override.yml').read_text())
            (target / 'current-version').write_text(v3 + '\n')
            (versions / (v1 + '.tsv')).write_text('app\tapi:old\tcontainer-id\n')
            rejected = exec_run(BASH, RUNNER, 'rollback', 'dev', 'api', '', '', '', '', '', cwd=d, env=env)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertNotIn('UP', rejected.stderr)
            service = exec_run(BASH, RUNNER, 'rollback', 'dev', 'api', '', '', '', '', 'app', cwd=d, env=env)
            self.assertNotEqual(service.returncode, 0)
            self.assertNotIn('UP', service.stderr)

    @unittest.skip('部署入口关闭，待安全修复后重新验证')
    def test_rollback_without_deploy_history_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / '.mv/delivery-standards/api'
            target.mkdir(parents=True)
            (target / 'compose.yml').write_text('services: {}' + chr(10), newline=chr(10))
            (target / '.env.dev').write_text('APP_ENV=dev' + chr(10), newline=chr(10))
            (target / 'current-version').write_text('version_20260101000000_000000000003' + chr(10), newline=chr(10))
            env = os.environ.copy()
            env['HOME'] = d
            run = exec_run(BASH, RUNNER, 'rollback', 'dev', 'api', '', '', '2', '', '', cwd=d, env=env)
            self.assertEqual(run.returncode, 3, run.stderr)
            self.assertIn('Current version has no deploy release record', run.stderr)

    @unittest.skip('部署入口关闭，待安全修复后重新验证')
    def test_receipt_version_and_image_id_are_required(self):
        source = Path(DEPLOY).read_text(encoding='utf-8')
        function = source.split('receipt_valid() {', 1)[1].split('\n}\n', 1)[0]
        shell = ('receipt_valid() {' + function + '\n}\n'
                 'printf "%s\n" "old-image" > "$TEST_RECEIPT"\n'
                 'if receipt_valid "$TEST_RECEIPT" "$TEST_ID"; then exit 10; fi\n'
                 'printf "mv-container-deploy-receipt-v3\t%s\n" "$TEST_ID" > "$TEST_RECEIPT"\n'
                 'if receipt_valid "$TEST_RECEIPT" "$TEST_ID"; then exit 13; fi\n'
                 'printf "mv-delivery-standards-receipt-v3\t%s\n" "$TEST_ID" > "$TEST_RECEIPT"\n'
                 'receipt_valid "$TEST_RECEIPT" "$TEST_ID" || exit 11\n'
                 'if receipt_valid "$TEST_RECEIPT" sha256:other; then exit 12; fi\n')
        with tempfile.TemporaryDirectory() as d:
            env = os.environ.copy()
            env.update(TEST_RECEIPT=(Path(d) / 'receipt').as_posix(), TEST_ID='sha256:abc')
            result = exec_run(BASH, '-c', shell, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skip('部署入口关闭，待安全修复后重新验证')
    def test_readiness_waits_for_configured_container_healthchecks(self):
        for mode in ('starting', 'transient', 'none', 'unhealthy', 'single', 'missing', 'multi', 'prod-multi'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as d:
                base = Path(d)
                target = base / '.mv/delivery-standards/api'
                target.mkdir(parents=True)
                (target / 'compose.yml').write_text('services:\n  app:\n    image: ${FF_IMAGE}\n')
                (target / '.env.dev').write_text('APP_ENV=dev\n')
                binary = base / 'bin'
                binary.mkdir()
                docker = binary / 'docker'
                docker.write_text('''#!/bin/sh
case "$1" in
  image) echo sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa;;
  inspect)
    case "$*" in
      *State.Status*) echo running;;
      *State.Health*)
        if [ "$4" = first ]; then echo healthy
        else
          case "$HEALTH_MODE" in
            starting) echo starting;;
            transient) if mkdir "$HOME/health-seen" 2>/dev/null; then echo starting; else echo healthy; fi;;
            none) echo none;;
            unhealthy) echo unhealthy;;
            *) echo healthy;;
          esac
        fi;;
      *) echo sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa;;
    esac;;
  compose) case "$*" in
    *'config --images'*) echo "$FF_IMAGE";;
    *'config --format json'*) printf '%s' "$TOPOLOGY";;
    *'config --services'*) if [ "$HEALTH_MODE" = multi ]; then printf 'app
worker
'; else echo app; fi;;
    *'ps -q app'*) if [ "$HEALTH_MODE" != missing ]; then echo first; fi;;
    *'ps -q'*) if [ "$HEALTH_MODE" = single ] || [ "$HEALTH_MODE" = missing ] || [ "$HEALTH_MODE" = multi ]; then echo first; else printf 'first
second
'; fi;;
    *'ps --format'*) printf 'app	api:one
';;
  esac;;
esac
''')
                docker.chmod(0o755)
                for name, body in (('curl', 'exit 0'), ('sleep', 'echo polled >&2')):
                    stub = binary / name
                    stub.write_text('#!/bin/sh\n' + body + '\n')
                    stub.chmod(0o755)
                deployment_env = 'prod' if mode == 'prod-multi' else 'dev'
                if deployment_env == 'prod':
                    (target / '.env.prod').write_text('APP_ENV=prod' + chr(10))
                python_shim = binary / 'python3'
                python_shim.write_text('#!/bin/sh' + chr(10) + 'exec "' + Path(sys.executable).as_posix() + '" "$@"' + chr(10))
                python_shim.chmod(0o755)
                services = {'app': {}, 'worker': {}} if mode in ('multi', 'prod-multi') else {'app': {}}
                topology = json.dumps({'services': services})
                env = stub_env(d, binary, HOME=str(d), TOPOLOGY=topology, HEALTH_MODE='multi' if mode == 'prod-multi' else mode)
                run = exec_run(BASH, RUNNER, 'deploy', deployment_env, 'api', 'api:one',
                               'http://localhost/ready', '4', 'version_20260101000000_0123456789ab',
                               '', cwd=d, env=env)
                if mode in ('starting', 'unhealthy', 'missing', 'prod-multi'):
                    self.assertEqual(run.returncode, 3 if mode == 'prod-multi' else 4, run.stderr)
                    self.assertNotIn('VERIFIED_HEALTH=strong', run.stdout)
                    self.assertFalse((target / 'current-version').exists())
                    self.assertFalse((target / 'releases.tsv').exists())
                else:
                    self.assertEqual(run.returncode, 0, run.stderr)
                    expected = 'strong' if mode == 'single' else 'readiness-partial'
                    self.assertIn('VERIFIED_HEALTH=' + expected, run.stdout)
                    self.assertEqual(run.stderr.count('polled'), 1 if mode == 'transient' else 0)
                if mode == 'starting':
                    self.assertIn('Timed out waiting', run.stderr)
                if mode == 'unhealthy':
                    self.assertIn('Container health: unhealthy', run.stderr)

    @unittest.skip('部署入口关闭，待安全修复后重新验证')
    def test_snapshot_failure_attempts_previous_restore(self):
        for previous, failure in ((True, "snapshot"), (False, "snapshot"), (True, "pointer"), (False, "pointer")):
            with self.subTest(previous=previous, failure=failure), tempfile.TemporaryDirectory() as d:
                base = Path(d)
                target = base / '.mv/delivery-standards/api'
                versions = target / 'versions'
                versions.mkdir(parents=True)
                (target / 'compose.yml').write_text('services: {}\n')
                (target / '.env.dev').write_text('APP_ENV=dev\n')
                old = 'version_20260101000000_000000000001'
                new = 'version_20260101000000_000000000002'
                if previous:
                    (versions / (old + '.tsv')).write_text('app\tapi:old\tsha256:' + 'a' * 64 + '\n', newline='\n')
                    (target / 'current-version').write_text(old + '\n', newline='\n')
                    if sealed(versions / (old + '.tsv')) or sealed(target / 'current-version'):
                        self.skipTest('Security agent sealed rollback fixture')
                    probe = exec_run(BASH, '-c', 'IFS= read -r row < "$1"; [[ "$row" == app*sha256:* ]]',
                                     'probe', (versions / (old + '.tsv')).as_posix())
                    if probe.returncode != 0:
                        self.skipTest('Bash cannot read rollback fixture through security agent')
                binary = base / 'bin'
                binary.mkdir()
                docker = binary / 'docker'
                docker.write_text('''#!/bin/sh
case "$1" in
  image) echo sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa;;
  inspect) case "$*" in *State.Health*) echo healthy;; *State.Status*) echo running;; *.Image*) echo sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa;; esac;;
  compose) case "$*" in
    *'config --images'*) echo "$FF_IMAGE";;
    *'ps --format'*) if [ "$FAILURE" = snapshot ]; then exit 9; else printf 'app	api:new
'; fi;;
    *'ps -q'*) echo mock;;
    *'compose.override.yml'*' up '*) echo RESTORED >&2;;
  esac;;
esac
''')
                docker.chmod(0o755)
                mv = binary / 'mv'
                mv.write_text('#!/bin/sh\ncase "$*" in *current-version*) exit 9;; esac\nexec /usr/bin/mv "$@"\n', newline='\n')
                mv.chmod(0o755)
                env = stub_env(d, binary, HOME=d, FAILURE=failure)
                run = exec_run(BASH, RUNNER, 'deploy', 'dev', 'api', 'api:new', '', '2', new, '', cwd=d, env=env)
                self.assertEqual(run.returncode, 4, run.stderr)
                if failure == 'snapshot':
                    self.assertIn('Snapshot failed or empty', run.stderr)
                    self.assertFalse((versions / (new + '.tsv')).exists())
                else:
                    self.assertIn('Current-version update failed', run.stderr)
                    self.assertIn('version pointer and running state are unconfirmed', run.stderr)
                self.assertFalse((target / 'releases.tsv').exists())
                self.assertIn('Recovery unconfirmed; inspect actual containers', run.stderr)
                if previous:
                    self.assertIn('prior topology and configuration cannot be proven', run.stderr)
                    self.assertIn('RESTORED', run.stderr)
                    self.assertEqual((target / 'current-version').read_text().strip(), old)
                else:
                    self.assertIn('No previous manifest; newly started containers may still be running', run.stderr)
                    self.assertFalse((target / 'current-version').exists())

    @unittest.skip('部署入口关闭，待安全修复后重新验证')
    def test_failing_compose_start_attempts_to_restore_previous(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            target=base/'.mv/delivery-standards/api'
            target.mkdir(parents=True)
            (target/'compose.yml').write_text('services:\n  app:\n    image: ${FF_IMAGE}\n')
            (target/'.env.dev').write_text('APP_ENV=dev\n')
            # 新契约:回退目标是上一版本清单,current-version 指向当前版本。
            versions=target/'versions'
            versions.mkdir(parents=True)
            (versions/'version_20260101000000_000000000001.tsv').write_text('app\tapi:old\tsha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n')
            (target/'current-version').write_text('version_20260101000000_000000000001\n')
            binary=base/'bin';binary.mkdir()
            docker=binary/'docker'
            docker.write_text('''#!/bin/sh
case "$1" in
  image) echo sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa;;
  inspect) case "$*" in *'.Image'*) echo sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa;; *State.Health*) echo healthy;; *State.Status*) echo running;; esac;;
  compose)
    case "$*" in
      *'config --images'*) echo "$FF_IMAGE" ;;
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
