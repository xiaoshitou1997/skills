"""mv-unattended-watch 离线用例：gate.py 状态机与 install_hooks.py 干跑。

状态目录与 settings 路径分别通过 MV_UNATTENDED_HOME / MV_UNATTENDED_SETTINGS
环境变量重定向到临时目录，不触碰真实用户配置。运行：
python -m unittest discover -s tests -p 'test_*.py'
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / 'mv-unattended-watch' / 'scripts' / 'gate.py'
INSTALL = ROOT / 'mv-unattended-watch' / 'scripts' / 'install_hooks.py'


def base_env(**extra):
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    env.update(extra)
    return env


class GateTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state_dir = Path(tmp.name) / 'unattended'
        self.env = base_env(MV_UNATTENDED_HOME=str(self.state_dir))

    def run_gate(self, *args):
        return subprocess.run(
            [sys.executable, str(GATE), *args],
            capture_output=True, env=self.env, text=True, encoding='utf-8')

    def activate(self, *extra):
        result = self.run_gate('on', *extra)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_inactive_remind_silent(self):
        for mode in ('prompt', 'compact', 'session'):
            with self.subTest(mode=mode):
                result = self.run_gate(mode)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')

    def test_active_remind_mentions_watch_and_log(self):
        self.activate()
        for mode in ('prompt', 'compact', 'session'):
            with self.subTest(mode=mode):
                result = self.run_gate(mode)
                self.assertEqual(result.returncode, 0)
                self.assertIn('无人值守', result.stdout)
                self.assertIn('decisions-', result.stdout)
                self.assertIn('AskUserQuestion', result.stdout)

    def test_expired_state_silent(self):
        self.state_dir.mkdir(parents=True)
        expired = {
            'active': True,
            'scope': 'machine',
            'activated_at': '2020-01-01T00:00:00+08:00',
            'expires_at': '2020-01-02T00:00:00+08:00',
            'boundaries': {'irreversible': 'defer', 'notes': ''},
            'log_path': 'x/decisions-20200101-000000.md',
        }
        (self.state_dir / 'state.json').write_text(
            json.dumps(expired, ensure_ascii=False), encoding='utf-8')
        for mode in ('prompt', 'compact', 'session'):
            with self.subTest(mode=mode):
                result = self.run_gate(mode)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')

    def test_block_active_denies(self):
        self.activate()
        result = self.run_gate('block')
        self.assertEqual(result.returncode, 2)
        self.assertIn('无人值守', result.stderr)

    def test_block_inactive_allows(self):
        result = self.run_gate('block')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, '')

    def test_block_corrupt_state_fails_closed(self):
        self.state_dir.mkdir(parents=True)
        (self.state_dir / 'state.json').write_text('{not-json', encoding='utf-8')
        result = self.run_gate('block')
        self.assertEqual(result.returncode, 2)

    def test_lifecycle_on_off(self):
        self.activate()
        state_file = self.state_dir / 'state.json'
        self.assertTrue(state_file.is_file())
        logs = list(self.state_dir.glob('decisions-*.md'))
        self.assertEqual(len(logs), 1)
        self.assertIn('无人值守决策日志', logs[0].read_text(encoding='utf-8'))
        status = self.run_gate('status')
        self.assertEqual(status.returncode, 0)
        self.assertIn('生效中', status.stdout)
        off = self.run_gate('off')
        self.assertEqual(off.returncode, 0)
        self.assertFalse(state_file.exists())
        self.assertTrue(logs[0].is_file())
        after = self.run_gate('status')
        self.assertEqual(after.returncode, 0)
        self.assertIn('未激活', after.stdout)

    def test_on_refuses_when_already_active(self):
        self.activate()
        again = self.run_gate('on')
        self.assertNotEqual(again.returncode, 0)

    def test_on_writes_boundaries_and_note(self):
        self.activate('--allow-irreversible', '--note', '允许 push 当前分支')
        state = json.loads(
            (self.state_dir / 'state.json').read_text(encoding='utf-8'))
        self.assertEqual(state['boundaries']['irreversible'], 'allowed')
        self.assertEqual(state['boundaries']['notes'], '允许 push 当前分支')
        remind = self.run_gate('prompt')
        self.assertIn('授权放行', remind.stdout)

    def test_on_rejects_bad_expiry(self):
        result = self.run_gate('on', '--expires-hours', '0')
        self.assertNotEqual(result.returncode, 0)
        result = self.run_gate('on', '--expires-hours', '1000')
        self.assertNotEqual(result.returncode, 0)

    def test_off_idempotent(self):
        first = self.run_gate('off')
        self.assertEqual(first.returncode, 0)
        second = self.run_gate('off')
        self.assertEqual(second.returncode, 0)


class InstallHooksTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.settings = Path(tmp.name) / 'settings.json'
        self.env = base_env(MV_UNATTENDED_SETTINGS=str(self.settings))

    def run_install(self, *args):
        return subprocess.run(
            [sys.executable, str(INSTALL), *args],
            capture_output=True, env=self.env, text=True, encoding='utf-8')

    def test_dry_run_prints_json_without_writing(self):
        result = self.run_install('--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.settings.exists())
        data = json.loads(result.stdout)
        hooks = data['hooks']
        self.assertEqual(set(hooks), {'UserPromptSubmit', 'SessionStart', 'PreToolUse'})
        matchers = sorted(g['matcher'] for g in hooks['SessionStart'])
        self.assertEqual(matchers, ['compact', 'startup|resume'])
        pre = hooks['PreToolUse']
        self.assertEqual([g['matcher'] for g in pre], ['AskUserQuestion'])
        commands = [h['command'] for groups in hooks.values() for g in groups
                    for h in g['hooks']]
        self.assertEqual(len(commands), 4)
        for command in commands:
            self.assertIn('gate.py', command)
            self.assertIn('mv-unattended-watch', command)

    def test_install_remove_roundtrip(self):
        installed = self.run_install()
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertTrue(self.settings.is_file())
        data = json.loads(self.settings.read_text(encoding='utf-8'))
        dumped = json.dumps(data, ensure_ascii=False)
        self.assertIn('mv-unattended-watch', dumped)
        removed = self.run_install('--remove')
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertNotIn('mv-unattended-watch',
                         self.settings.read_text(encoding='utf-8'))
        backups = list(self.settings.parent.glob('settings.json.bak-*'))
        self.assertEqual(len(backups), 1)

    def test_install_preserves_existing_hooks(self):
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        existing = {'hooks': {'PreToolUse': [
            {'matcher': 'Bash', 'hooks': [
                {'type': 'command', 'command': 'echo user-own-hook'}]}]}}
        self.settings.write_text(json.dumps(existing), encoding='utf-8')
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(self.settings.read_text(encoding='utf-8'))
        pre = data['hooks']['PreToolUse']
        own = [h for g in pre for h in g['hooks']
               if 'user-own-hook' in h.get('command', '')]
        ours = [h for g in pre for h in g['hooks']
                if 'mv-unattended-watch' in h.get('command', '')]
        self.assertEqual(len(own), 1)
        self.assertEqual(len(ours), 1)

    def test_remove_without_install_is_noop(self):
        result = self.run_install('--remove')
        self.assertEqual(result.returncode, 0)
        self.assertFalse(self.settings.exists())


if __name__ == '__main__':
    unittest.main()
