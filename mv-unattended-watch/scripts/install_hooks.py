#!/usr/bin/env python3
"""把 mv-unattended-watch 的值守 Hook 安装/卸载到用户级 Claude settings.json。

安装四个 hook 条目（幂等，重复运行不叠加）：

- UserPromptSubmit                     -> gate.py prompt   每轮注入值守提醒
- SessionStart matcher=compact         -> gate.py compact  压缩后重注入提醒
- SessionStart matcher=startup|resume  -> gate.py session  会话启动/恢复提醒
- PreToolUse   matcher=AskUserQuestion -> gate.py block    硬拦截提问

用法：
- python3 install_hooks.py            安装（写前自动备份 settings.json）
- python3 install_hooks.py --remove   卸载本 skill 的 hook 条目
- python3 install_hooks.py --dry-run  只打印将写入的 JSON，不落盘（stdout 仅含 JSON）

settings.json 路径默认 ~/.claude/settings.json，环境变量 MV_UNATTENDED_SETTINGS
可覆盖（测试用）。settings.json 已存在但无法解析时直接失败，绝不覆盖用户配置。
命令中的解释器与 gate.py 均写绝对路径（POSIX 风格），Git Bash 与 POSIX shell 通用。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

MARKER = 'mv-unattended-watch'

# (事件, matcher, gate 子命令)；matcher 为 None 表示该事件不设 matcher。
EVENTS = [
    ('UserPromptSubmit', None, 'prompt'),
    ('SessionStart', 'compact', 'compact'),
    ('SessionStart', 'startup|resume', 'session'),
    ('PreToolUse', 'AskUserQuestion', 'block'),
]


def settings_path() -> Path:
    override = os.environ.get('MV_UNATTENDED_SETTINGS')
    return Path(override) if override else Path.home() / '.claude' / 'settings.json'


def gate_path() -> str:
    return (Path(__file__).resolve().parent / 'gate.py').as_posix()


def hook_command(mode: str) -> str:
    interpreter = Path(sys.executable).resolve().as_posix()
    return '"' + interpreter + '" "' + gate_path() + '" ' + mode


def is_our_command(command: str) -> bool:
    return MARKER in command and 'gate.py' in command


def load_settings(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise SystemExit('无法解析 ' + str(path) + '，拒绝修改用户配置：' + repr(exc))
    if not isinstance(data, dict):
        raise SystemExit(str(path) + ' 顶层不是 JSON 对象，拒绝修改。')
    return data


def strip_our_hooks(settings: dict) -> int:
    """移除所有属于本 skill 的 hook 条目，返回移除数量；不动用户自有条目。"""
    hooks = settings.get('hooks')
    removed = 0
    if not isinstance(hooks, dict):
        return 0
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        kept_groups = []
        for group in groups:
            entries = group.get('hooks') if isinstance(group, dict) else None
            if not isinstance(entries, list):
                kept_groups.append(group)
                continue
            kept = [h for h in entries
                    if not (isinstance(h, dict) and is_our_command(str(h.get('command', ''))))]
            removed += len(entries) - len(kept)
            if kept:
                group['hooks'] = kept
                kept_groups.append(group)
        if kept_groups:
            hooks[event] = kept_groups
        else:
            del hooks[event]
    if not hooks:
        settings.pop('hooks', None)
    return removed


def add_our_hooks(settings: dict) -> None:
    hooks = settings.setdefault('hooks', {})
    for event, matcher, mode in EVENTS:
        entry = {'type': 'command', 'command': hook_command(mode)}
        group = {'matcher': matcher, 'hooks': [entry]} if matcher else {'hooks': [entry]}
        hooks.setdefault(event, []).append(group)


def backup(path: Path):
    if not path.is_file():
        return None
    target = path.with_name(path.name + '.bak-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    shutil.copy2(path, target)
    return target


def write_settings(path: Path, settings: dict) -> None:
    # 临时文件 + 原子替换:中断也不会留下截断的 settings.json(配合调用前的备份双保险)。
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp-unattended')
    tmp.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + '\n',
                   encoding='utf-8')
    os.replace(tmp, path)


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(
        prog='install_hooks.py',
        description='安装/卸载 mv-unattended-watch 值守 Hook（仓库唯一显式安装例外）。')
    parser.add_argument('--remove', action='store_true', help='卸载本 skill 的 hook 条目')
    parser.add_argument('--dry-run', action='store_true',
                        help='只打印结果 JSON，不写盘（stdout 仅含 JSON）')
    args = parser.parse_args(argv)

    path = settings_path()
    settings = load_settings(path)

    if args.remove:
        removed = strip_our_hooks(settings)
        if removed == 0:
            print('未发现已安装的值守 Hook，无需卸载。')
            return 0
        if args.dry_run:
            print(json.dumps(settings, ensure_ascii=False, indent=2))
            return 0
        bak = backup(path)
        write_settings(path, settings)
        print('已移除 ' + str(removed) + ' 条值守 Hook；备份：' + str(bak))
        return 0

    strip_our_hooks(settings)  # 幂等：先清后装
    add_our_hooks(settings)
    if args.dry_run:
        print(json.dumps(settings, ensure_ascii=False, indent=2))
        return 0
    bak = backup(path)
    write_settings(path, settings)
    print('值守 Hook 已安装到 ' + str(path) + '（4 个条目）；备份：' + str(bak or '（原文件不存在，无备份）'))
    print('配置热加载或重启会话后生效；卸载：python3 install_hooks.py --remove')
    return 0


if __name__ == '__main__':
    sys.exit(main())
