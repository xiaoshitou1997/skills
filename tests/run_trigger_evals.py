#!/usr/bin/env python3
"""触发契约评测：将当前工作区快照复制到隔离项目，只暴露该快照。

需要 claude CLI 与可在隔离配置中使用的登录或 API 环境；不复制用户凭据、
已安装 skills 或插件。--list 离线查看；缺 CLI 时明确 SKIP。
模型仅有 Skill 工具，不执行构建、部署、提交或安装操作。
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from trigger_cases import CASES
from validate_bundle import SKILLS

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT_S = 240
MAX_TURNS = 6


def skill_invocations(stdout):
    """保留完整身份，插件同名调用不能替代待测 skill。"""
    names = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(event, dict) or event.get('type') != 'assistant':
            continue
        for item in event.get('message', {}).get('content') or []:
            if not isinstance(item, dict) or item.get('type') != 'tool_use':
                continue
            if item.get('name') == 'Skill':
                raw = item.get('input') or {}
                name = raw.get('skill') or raw.get('command') or ''
                names.append(str(name).lstrip('/'))
    return names


def snapshot(source, target):
    """复制完整候选集合，返回内容摘要，包含未提交的修改。"""
    hashes = {}
    for name in sorted(SKILLS):
        skill = source / name
        if not (skill / 'SKILL.md').is_file():
            raise RuntimeError('待测 skill 缺失: ' + name)
        if any(path.is_symlink() for path in [skill, *skill.rglob('*')]):
            raise RuntimeError('待测 skill 不得包含符号链接: ' + name)
        entry = (skill / 'SKILL.md').read_text(encoding='utf-8')
        if any(line.strip() == 'context: fork' for line in entry.splitlines()):
            raise RuntimeError('触发评测暂不支持 context: fork: ' + name)
        shutil.copytree(skill, target / name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for path in sorted((target / name).rglob('*')):
            if path.is_file():
                hashes[path.relative_to(target).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def isolated_environment(home):
    # 仅继承进程启动、网络与明确认证所需变量，不继承插件、Hook 和会话模式。
    allowed = {
        'PATH', 'PATHEXT', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP',
        'APPDATA', 'LOCALAPPDATA', 'LANG', 'LC_ALL', 'PYTHONUTF8',
        'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
        'ANTHROPIC_API_KEY', 'CLAUDE_CODE_OAUTH_TOKEN', 'ANTHROPIC_BASE_URL',
        'NODE_EXTRA_CA_CERTS', 'SSL_CERT_FILE', 'SSL_CERT_DIR',
    }
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env.update(HOME=str(home), USERPROFILE=str(home), CLAUDE_CONFIG_DIR=str(home / 'config'))
    env['CLAUDE_CODE_DISABLE_AUTO_MEMORY'] = '1'
    return env


def run_case(claude, query, candidate_root, expected_hashes):
    with tempfile.TemporaryDirectory(prefix='skills-trigger-case-') as directory:
        root = Path(directory)
        project = root / 'project'
        skill_root = project / '.claude' / 'skills'
        skill_root.parent.mkdir(parents=True)
        shutil.copytree(candidate_root, skill_root)
        home = root / 'home'
        home.mkdir()
        mcp = root / 'mcp.json'
        mcp.write_text('{"mcpServers": {}}\n', encoding='utf-8')
        settings = root / 'settings.json'
        settings.write_text(json.dumps({
            'disableAllHooks': True, 'disableSkillShellExecution': True,
            'disableBundledSkills': True, 'autoMemoryEnabled': False,
            'includeGitInstructions': False,
        }), encoding='utf-8')
        cmd = [claude, '-p', query,
               '--output-format', 'stream-json', '--verbose',
               '--max-turns', str(MAX_TURNS), '--tools', 'Skill',
               '--allowedTools', 'Skill', '--setting-sources', 'project',
               '--permission-mode', 'dontAsk', '--settings', str(settings),
               '--strict-mcp-config', '--mcp-config', str(mcp),
               '--no-session-persistence']
        proc = subprocess.run(cmd, cwd=project, env=isolated_environment(home),
                              capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=TIMEOUT_S)
        if proc.returncode:
            # 不回显第三方 CLI 的原始错误：其输出可能包含认证配置。
            raise RuntimeError(f'claude 退出码 {proc.returncode}；检查 CLI 版本及隔离配置下的认证可用性')
        events = []
        for line in proc.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
        initialized = [event for event in events if event.get('type') == 'system' and event.get('subtype') == 'init']
        results = [event for event in events if event.get('type') == 'result']
        if not initialized or not results or results[-1].get('is_error') or results[-1].get('subtype') != 'success':
            raise RuntimeError('CLI 没有返回完整成功结果，不能判为未触发')
        for event in initialized:
            if set(event.get('tools', [])) - {'Skill'} or event.get('mcp_servers') or event.get('plugins'):
                raise RuntimeError('CLI 加载了非预期工具、MCP 或插件，隔离失败')
        for event in events:
            content = event.get('message', {}).get('content') or []
            if isinstance(content, list) and any(isinstance(item, dict) and item.get('type') == 'tool_result' and item.get('is_error') for item in content):
                raise RuntimeError('Skill 加载失败，不能记为有效触发')
        actual_files = {path.relative_to(skill_root).as_posix() for path in skill_root.rglob('*') if path.is_file()}
        if actual_files != set(expected_hashes):
            raise RuntimeError('待测快照文件集合发生变化')
        for name, digest in expected_hashes.items():
            path = skill_root / name
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise RuntimeError('待测快照被修改: ' + name)
        fired = skill_invocations(proc.stdout)
        unknown = set(fired) - SKILLS
        if unknown:
            raise RuntimeError('出现非快照 skill 身份: ' + ', '.join(sorted(unknown)))
        return fired


def verdict(case, fired):
    skill = case['skill']
    if case['kind'] == 'positive':
        required = set(case.get('required', [skill])) | {skill}
        missing = required - set(fired)
        if missing:
            return 'FAIL', f'缺少应触发项 {sorted(missing)}，实际触发 {fired or "无"}'
        return 'PASS', ''
    if skill in fired:
        return 'FAIL', f'不得触发 {skill}，实际触发 {fired}'
    instead = case.get('instead')
    if instead and instead not in fired:
        return 'WARN', f'未触发 {skill}（正确），但预期去向 {instead} 未触发，实际 {fired or "无"}'
    return 'PASS', ''


def main():
    parser = argparse.ArgumentParser(description='隔离运行当前工作区的 skill 触发契约评测')
    parser.add_argument('skill', nargs='?')
    parser.add_argument('--list', action='store_true', help='离线查看用例矩阵')
    parser.add_argument('--claude', default='claude', help='Claude CLI 可执行文件或命令名')
    parser.add_argument('--limit', type=int, help='只运行前 N 条，用于评测器冒烟')
    args = parser.parse_args()
    cases = [case for case in CASES if not args.skill or case['skill'] == args.skill]
    if not cases:
        parser.error('没有对应的触发用例')
    if args.limit is not None:
        if args.limit < 1:
            parser.error('--limit 必须大于 0')
        cases = cases[:args.limit]
    if args.list:
        for case in cases:
            mark = 'P' if case['kind'] == 'positive' else 'N'
            print(f'[{mark}] {case["skill"]:<30} {case["query"]}')
        return 0
    claude = shutil.which(args.claude)
    if not claude:
        print('SKIP: 未找到 claude CLI，模型触发契约未验证；--list 可离线检查用例。')
        return 0
    if not any(os.environ.get(key) for key in ('ANTHROPIC_API_KEY', 'CLAUDE_CODE_OAUTH_TOKEN')):
        print('SKIP: 隔离评测需要 ANTHROPIC_API_KEY 或 CLAUDE_CODE_OAUTH_TOKEN 环境认证；不复制用户登录凭据，模型触发契约未验证。')
        return 0
    counts = {'PASS': 0, 'WARN': 0, 'FAIL': 0}
    with tempfile.TemporaryDirectory(prefix='skills-trigger-snapshot-') as directory:
        candidates = Path(directory) / 'skills'
        hashes = snapshot(ROOT, candidates)
        digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
        print(f'SNAPSHOT_SHA256={digest} SKILLS={",".join(sorted(SKILLS))}')
        for index, case in enumerate(cases, 1):
            try:
                fired = run_case(claude, case['query'], candidates, hashes)
                state, detail = verdict(case, fired)
            except subprocess.TimeoutExpired:
                state, detail = 'FAIL', f'超时（>{TIMEOUT_S}s）'
            except RuntimeError as exc:
                state, detail = 'FAIL', str(exc)
            counts[state] += 1
            print(f'[{index}/{len(cases)}] {case["skill"]} {state}' + (f' {detail}' if detail else ''), flush=True)
    print(f'共 {len(cases)} 例: PASS {counts["PASS"]}, WARN {counts["WARN"]}, FAIL {counts["FAIL"]}')
    return int(bool(counts['FAIL']))


if __name__ == '__main__':
    sys.exit(main())
