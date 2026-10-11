#!/usr/bin/env python3
"""运行触发契约用例（tests/trigger_cases.py）。

对每条用例启动一个 headless claude 会话，从 stream-json 事件中检测
Skill 工具调用，按正/反例判定路由是否符合 description 声明的契约。
运行需要本机可用的 claude CLI 并按用例消耗 token；无 CLI 时跳过，
可先用 --list 离线查看用例矩阵做人工核对。

判定口径：
- 正例 FAIL 仅当目标 skill 未触发；同时触发多个记 WARN（互斥存疑）。
- 反例 FAIL 仅当目标 skill 被触发；instead 未触发只记 WARN。

用法:
  python3 tests/run_trigger_evals.py            # 全部用例
  python3 tests/run_trigger_evals.py <skill>    # 单个 skill 的用例
  python3 tests/run_trigger_evals.py --list     # 只打印用例矩阵，不运行
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trigger_cases import CASES

TIMEOUT_S = 240
MAX_TURNS = 3


def skill_invocations(stdout):
    """从 stream-json 输出提取被调用的 skill 名（去掉插件前缀）。"""
    names = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith('{'):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get('type') != 'assistant':
            continue
        for item in event.get('message', {}).get('content') or []:
            if not isinstance(item, dict) or item.get('type') != 'tool_use':
                continue
            if item.get('name') != 'Skill':
                continue
            raw = item.get('input') or {}
            name = raw.get('skill') or raw.get('command') or ''
            names.append(str(name).lstrip('/').split(':')[-1])
    return names


def run_case(claude, query):
    cmd = [claude, '-p', query,
           '--output-format', 'stream-json', '--verbose',
           '--max-turns', str(MAX_TURNS),
           '--allowedTools', 'Skill']
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or '').strip()[:300]
        raise RuntimeError(f'claude 退出码 {proc.returncode}: {detail}')
    return skill_invocations(proc.stdout)


def verdict(case, fired):
    skill = case['skill']
    if case['kind'] == 'positive':
        if skill not in fired:
            return 'FAIL', f'应触发 {skill}，实际触发 {fired or "无"}'
        if len(fired) > 1:
            return 'WARN', f'同时触发 {fired}，互斥边界存疑'
        return 'PASS', ''
    if skill in fired:
        return 'FAIL', f'不得触发 {skill}，实际触发 {fired}'
    instead = case.get('instead')
    if instead and instead not in fired:
        return 'WARN', f'未触发 {skill}（正确），但预期去向 {instead} 未触发，实际 {fired or "无"}'
    return 'PASS', ''


def main():
    parser = argparse.ArgumentParser(description='运行触发契约评测')
    parser.add_argument('skill', nargs='?', help='只跑该 skill 的用例')
    parser.add_argument('--list', action='store_true', help='只打印用例矩阵，不运行')
    args = parser.parse_args()

    cases = CASES
    if args.skill:
        cases = [c for c in CASES if c['skill'] == args.skill]
        if not cases:
            known = sorted({c['skill'] for c in CASES})
            sys.exit(f'没有 skill={args.skill} 的用例；可用: {known}')

    if args.list:
        for c in cases:
            mark = 'P' if c['kind'] == 'positive' else 'N'
            dest = c.get('instead', 'none') if mark == 'N' else ''
            print(f'[{mark}] {c["skill"]:<24} {c["query"]}'
                  + (f'  -> {dest}' if dest else ''))
        return

    claude = shutil.which('claude')
    if not claude:
        print('SKIP: 未找到 claude CLI，触发契约未验证。'
              '可先 `python3 tests/run_trigger_evals.py --list` 离线核对用例，'
              '或安装 claude CLI 后重跑。')
        return

    counts = {'PASS': 0, 'WARN': 0, 'FAIL': 0}
    findings = []
    for i, case in enumerate(cases, 1):
        tag = f'[{i}/{len(cases)}] {"P" if case["kind"] == "positive" else "N"} {case["skill"]}'
        try:
            fired = run_case(claude, case['query'])
        except subprocess.TimeoutExpired:
            counts['FAIL'] += 1
            findings.append(f'FAIL {tag} 超时(>{TIMEOUT_S}s): {case["query"]}')
            print(f'{tag} TIMEOUT')
            continue
        except RuntimeError as exc:
            counts['FAIL'] += 1
            findings.append(f'FAIL {tag} 运行错误: {exc}')
            print(f'{tag} ERROR')
            continue
        state, detail = verdict(case, fired)
        counts[state] += 1
        line = f'{tag} {state}' + (f' {detail}' if detail else '')
        print(line)
        if state != 'PASS':
            findings.append(line)

    print(f'-- 共 {len(cases)} 例: PASS {counts["PASS"]}, '
          f'WARN {counts["WARN"]}, FAIL {counts["FAIL"]}')
    for line in findings:
        print(line)
    if counts['FAIL']:
        sys.exit(1)


if __name__ == '__main__':
    main()
