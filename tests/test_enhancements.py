"""Regression tests for engineering skills helper scripts (no remote server)."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOCTOR = ROOT / 'toolchain-manager/scripts/doctor.py'
PREFLIGHT = ROOT / 'docker-delivery/scripts/deploy-preflight.sh'
DELIVER = ROOT / 'docker-delivery/scripts/deliver.sh'
RUNNER = ROOT / 'docker-delivery/scripts/target-runner.sh'
QUALITY = ROOT / 'local-development/scripts/quality-check.sh'


def exec_run(*cmd, cwd=None, env=None, input=None):
    return subprocess.run(cmd, cwd=cwd, env=env, input=input, text=True, capture_output=True)


class EnhancementsTests(unittest.TestCase):
    def test_doctor_is_read_only(self):
        with tempfile.TemporaryDirectory() as d:
            p=exec_run(sys.executable, str(DOCTOR), '--project', d, '--json')
            self.assertEqual(p.returncode, 0, p.stderr)
            data=json.loads(p.stdout)
            self.assertIn('docker_compose', data['checks'])
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_preflight_rejects_missing_docker(self):
        with tempfile.TemporaryDirectory() as d:
            p=exec_run('bash',str(PREFLIGHT),'prod','api',cwd=d)
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
            env.update(PATH=str(b)+os.pathsep+env['PATH'], HOME=d, FF_PROD_SSH='deploy@prod.example.com')
            p=exec_run('bash',str(DELIVER),'deploy','prod','api','api:abc','--approve-prod',cwd=d,env=env)
            self.assertNotEqual(p.returncode,0)
            self.assertIn('no verified dev deployment receipt',p.stderr)

    def test_quality_fails_if_no_scripts(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'package.json').write_text('{"scripts":{}}')
            (root/'package-lock.json').write_text('{}')
            p=exec_run('bash',str(QUALITY),'quick',cwd=d)
            self.assertNotEqual(p.returncode,0)
            self.assertIn('not a pass',p.stderr)

    def test_verified_release_tracks_prev_and_history(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            target=root/'.local/share/workbelt/api'
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
            first=exec_run('bash',str(RUNNER),'deploy','dev','api','api:one','',cwd=d,env=env)
            second=exec_run('bash',str(RUNNER),'deploy','dev','api','api:two','',cwd=d,env=env)
            self.assertEqual(first.returncode,0,first.stderr)
            self.assertEqual(second.returncode,0,second.stderr)
            self.assertEqual((target/'current-image').read_text().strip(),'api:two')
            self.assertEqual((target/'previous-image').read_text().strip(),'api:one')
            self.assertEqual(len((target/'releases.tsv').read_text().splitlines()),2)


    def test_running_only_dev_does_not_claim_strong_health(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            target=base/'.local/share/workbelt/api'
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
            run=exec_run('bash',str(RUNNER),'deploy','dev','api','api:one','',cwd=d,env=env)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertIn('VERIFIED_HEALTH=running-only',run.stdout)
            self.assertEqual((target/'releases.tsv').read_text().strip().split('\t')[-1], 'running-only')
            (target/'.env.prod').write_text('APP_ENV=prod\n')
            prod=exec_run('bash',str(RUNNER),'deploy','prod','api','api:two','',cwd=d,env=env)
            self.assertNotEqual(prod.returncode,0)
            self.assertIn('requires a Docker healthcheck', prod.stderr)
            self.assertEqual((target/'current-image').read_text().strip(), 'api:one')

    def test_failing_compose_start_attempts_to_restore_previous(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            target=base/'.local/share/workbelt/api'
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
            failed=exec_run('bash',str(RUNNER),'deploy','dev','api','api:bad','',cwd=d,env=env)
            self.assertNotEqual(failed.returncode,0)
            self.assertIn('Trying application rollback',failed.stderr)
            self.assertEqual((target/'current-image').read_text().strip(),'api:old')
            self.assertFalse((target/'releases.tsv').exists())


if __name__ == '__main__':
    unittest.main()
