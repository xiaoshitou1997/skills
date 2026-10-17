"""Offline tests for source isolation and trigger verdicts; no model calls."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_trigger_evals as runner


def events(skill='mv-local-debug', plugins=None, result=True):
    output = [json.dumps({'type': 'system', 'subtype': 'init', 'tools': ['Skill'], 'plugins': plugins or [], 'mcp_servers': []})]
    output.append(json.dumps({'type': 'assistant', 'message': {'content': [
        {'type': 'tool_use', 'name': 'Skill', 'input': {'skill': skill}},
    ]}}))
    if result:
        output.append(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False}))
    return '\n'.join(output)


class TriggerRunnerTests(unittest.TestCase):
    def test_plugin_identity_is_not_stripped(self):
        self.assertEqual(runner.skill_invocations(events('old:mv-local-debug')), ['old:mv-local-debug'])
        self.assertEqual(runner.verdict({'skill': 'mv-local-debug', 'kind': 'positive'}, ['old:mv-local-debug'])[0], 'FAIL')

    def test_cooperation_and_required_set(self):
        case = {'skill': 'mv-container-deploy', 'kind': 'positive', 'required': ['mv-image-build']}
        self.assertEqual(runner.verdict(case, ['mv-image-build', 'mv-container-deploy'])[0], 'PASS')
        self.assertEqual(runner.verdict(case, ['mv-container-deploy'])[0], 'FAIL')
        self.assertEqual(runner.verdict({'skill': 'mv-java-backend-standards', 'kind': 'positive'},
                                        ['mv-nfr-intake', 'mv-java-backend-standards'])[0], 'PASS')

    def test_environment_drops_host_modes_and_preserves_environment_auth(self):
        with patch.dict(os.environ, {'CLAUDECODE': '1', 'CLAUDE_CODE_PLUGIN_DIRS': '/old',
                                     'CLAUDE_CODE_OAUTH_TOKEN': 'test-token', 'NODE_OPTIONS': '--require evil'}, clear=False):
            env = runner.isolated_environment(Path('/isolated'))
        self.assertNotIn('CLAUDECODE', env)
        self.assertNotIn('CLAUDE_CODE_PLUGIN_DIRS', env)
        self.assertNotIn('NODE_OPTIONS', env)
        self.assertEqual(env['CLAUDE_CODE_OAUTH_TOKEN'], 'test-token')
        self.assertEqual(env['CLAUDE_CONFIG_DIR'], str(Path('/isolated/config')))

    def prepare(self, root):
        source = root / 'source'
        target = root / 'snapshot'
        for name in runner.SKILLS:
            path = source / name
            path.mkdir(parents=True)
            (path / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: 测试\n---\n# 测试\n', encoding='utf-8')
        return source, target, runner.snapshot(source, target)

    def test_snapshot_and_child_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, snapshot, hashes = self.prepare(root)
            (source / 'mv-local-debug/SKILL.md').write_text('later change', encoding='utf-8')

            def fake_run(command, **kwargs):
                project = kwargs['cwd']
                self.assertEqual(project.name, 'project')
                self.assertIn('--setting-sources', command)
                self.assertEqual(command[command.index('--tools') + 1], 'Skill')
                self.assertEqual(command[command.index('--permission-mode') + 1], 'dontAsk')
                settings = json.loads(Path(command[command.index('--settings') + 1]).read_text())
                self.assertTrue(settings['disableAllHooks'])
                self.assertTrue(settings['disableSkillShellExecution'])
                self.assertTrue(settings['disableBundledSkills'])
                self.assertEqual(json.loads(Path(command[command.index('--mcp-config') + 1]).read_text()), {'mcpServers': {}})
                self.assertNotEqual((project / '.claude/skills/mv-local-debug/SKILL.md').read_text(encoding='utf-8'), 'later change')
                return subprocess.CompletedProcess(command, 0, events(), '')

            with patch.object(runner.subprocess, 'run', side_effect=fake_run):
                self.assertEqual(runner.run_case('claude', '自然请求', snapshot, hashes), ['mv-local-debug'])

    def test_invalid_session_cannot_pass_as_no_trigger(self):
        with tempfile.TemporaryDirectory() as directory:
            _, snapshot, hashes = self.prepare(Path(directory))
            failed_load = events() + '\n' + json.dumps({'type': 'user', 'message': {'content': [
                {'type': 'tool_result', 'is_error': True, 'content': 'skill not found'},
            ]}})
            for output in (events('old:mv-local-debug'), events(plugins=[{'name': 'old'}]), events(result=False), failed_load, ''):
                with self.subTest(output=output), patch.object(runner.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, output, '')):
                    with self.assertRaises(RuntimeError):
                        runner.run_case('claude', '请求', snapshot, hashes)

    def test_snapshot_mutation_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            _, snapshot, hashes = self.prepare(Path(directory))

            def mutate(command, **kwargs):
                (kwargs['cwd'] / '.claude/skills/mv-local-debug/SKILL.md').write_text('changed', encoding='utf-8')
                return subprocess.CompletedProcess(command, 0, events(), '')

            with patch.object(runner.subprocess, 'run', side_effect=mutate):
                with self.assertRaisesRegex(RuntimeError, '快照被修改'):
                    runner.run_case('claude', '请求', snapshot, hashes)

    def test_missing_cli_and_auth_skip_without_running(self):
        with patch.object(runner.sys, 'argv', ['runner']), patch.object(runner.shutil, 'which', return_value=None), patch.object(runner.subprocess, 'run') as run:
            self.assertEqual(runner.main(), 0)
            run.assert_not_called()
        with patch.object(runner.sys, 'argv', ['runner']), patch.object(runner.shutil, 'which', return_value='claude'), patch.dict(os.environ, {}, clear=True), patch.object(runner.subprocess, 'run') as run:
            self.assertEqual(runner.main(), 0)
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
