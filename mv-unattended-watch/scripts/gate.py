#!/usr/bin/env python3
"""mv-unattended-watch 状态闸门。

无人值守模式的唯一状态操作入口，同时是值守 Hook 的执行入口：

- 面向 skill 与用户：on / off / status。
- 面向 Hook 调用：prompt / compact / session 注入值守提醒（exit 0，stdout 进入模型
  上下文）；block 硬拦截 AskUserQuestion（exit 2，stderr 作为拒绝理由反馈给模型）。

状态目录默认 ~/.mv/unattended-watch/，环境变量 MV_UNATTENDED_WATCH_HOME 可覆盖（测试用）。
失败语义：Hook 模式内部异常一律静默 exit 0，不阻塞会话；状态文件存在但损坏时按
无人值守处理（fail-closed）。管理命令失败输出到 stderr 并以非零退出码结束。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path

BLOCK_MESSAGE = (
    '无人值守模式生效中：AskUserQuestion 已被值守 Hook 拦截。\n'
    '改为：依据当前信息自行选择最优方案继续推进；把该决策按「时间 | 决策 | 理由 | '
    '可逆性 | 证据」追加到决策日志；若操作不可逆/对外且未获授权，登记到「待确认」'
    '清单后跳过，继续其他工作。'
)


def state_dir() -> Path:
    override = os.environ.get('MV_UNATTENDED_WATCH_HOME')
    return Path(override) if override else Path.home() / '.mv' / 'unattended-watch'


def state_file() -> Path:
    return state_dir() / 'state.json'


def gate_command() -> str:
    return str(Path(__file__).resolve())


def local_now() -> datetime:
    return datetime.now().astimezone()


def parse_ts(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def fmt_ts(value) -> str:
    ts = parse_ts(value)
    return ts.strftime('%Y-%m-%d %H:%M') if ts else str(value or '(未知)')


def read_state():
    """返回 (status, data)，status 取值 missing / ok / corrupt / expired。"""
    path = state_file()
    if not path.is_file():
        return 'missing', None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('state must be a JSON object')
    except (OSError, ValueError):
        return 'corrupt', None
    expires = parse_ts(data.get('expires_at'))
    if expires is not None and expires <= local_now():
        return 'expired', data
    return 'ok', data


def boundary_line(data: dict) -> str:
    boundaries = data.get('boundaries') or {}
    if boundaries.get('irreversible') == 'allowed':
        return '用户已授权放行；执行前仍须写入决策日志。'
    return '默认挂起：不执行，登记到决策日志「待确认」清单，待用户回来处理。'


def reminder_body(data: dict, header: str) -> str:
    log_path = data.get('log_path', '(未知)')
    note = (data.get('boundaries') or {}).get('notes') or ''
    lines = [header, '']
    if note:
        lines.append('用户备注：' + note)
    lines.append('值守纪律：')
    lines.append('1. 用户已离开：禁止调用 AskUserQuestion；所有疑问依据现状自行选择最优方案并继续推进。')
    lines.append('2. 每项重要决策追加一行到决策日志：' + str(log_path) + '（时间 | 决策 | 理由 | 可逆性 | 证据）。')
    lines.append('3. 不可逆/对外操作（push、生产部署、删除数据、对外发消息）：' + boundary_line(data))
    lines.append('4. 有挂起项不空转：登记后继续其余工作。')
    lines.append('5. 用户本人已回来（如「我回来了」）时先解除：python "' + gate_command() + '" off')
    return '\n'.join(lines)


def cmd_remind(kind: str) -> int:
    status, data = read_state()
    if status in ('missing', 'expired'):
        return 0
    if status == 'corrupt':
        print('【无人值守】状态文件存在但无法解析，为安全起见按无人值守处理；'
              '请运行 gate.py status 检查，必要时由用户运行 gate.py off 解除。')
        return 0
    headers = {
        'prompt': '【无人值守模式生效中】（每轮提醒）',
        'compact': '【无人值守模式生效中】（上下文刚被压缩，此提醒自动重注入）',
        'session': '【无人值守模式生效中】（会话启动/恢复时检测到值守仍在进行）',
    }
    print(reminder_body(data, headers[kind]))
    return 0


def cmd_block() -> int:
    status, _ = read_state()
    if status in ('missing', 'expired'):
        return 0
    if status == 'corrupt':
        print('无人值守状态文件存在但无法解析（可能损坏）：按无人值守 fail-closed 处理，禁止提问；'
              '可运行 gate.py status 检查，或由用户运行 gate.py off 解除。', file=sys.stderr)
    print(BLOCK_MESSAGE, file=sys.stderr)
    return 2


def log_header(start: datetime, hours: float, allow_irreversible: bool, note: str) -> str:
    boundary = '已授权放行' if allow_irreversible else '挂起待确认'
    lines = [
        '# 无人值守决策日志',
        '',
        '- 激活：' + start.strftime('%Y-%m-%d %H:%M:%S') + '（' + ('%g' % hours) + 'h 后自动过期）',
        '- 边界：不可逆/对外操作 = ' + boundary,
    ]
    if note:
        lines.append('- 备注：' + note)
    lines.extend([
        '',
        '## 决策',
        '',
        '<!-- 每行一条：时间 | 决策 | 理由 | 可逆性 | 证据 -->',
        '',
        '## 待确认',
        '',
    ])
    return '\n'.join(lines) + '\n'


def cmd_on(args) -> int:
    status, _ = read_state()
    if status == 'ok':
        print('已处于无人值守状态；先运行 off 解除再重新激活。', file=sys.stderr)
        return 1
    if not (0 < args.expires_hours <= 720):
        print('--expires-hours 必须在 (0, 720] 范围内，单位小时。', file=sys.stderr)
        return 1
    start = local_now()
    end = start + timedelta(hours=args.expires_hours)
    state_dir().mkdir(parents=True, exist_ok=True)
    log_path = state_dir() / ("decisions-%s.md" % start.strftime('%Y%m%d-%H%M%S'))
    log_path.write_text(
        log_header(start, args.expires_hours, args.allow_irreversible, args.note),
        encoding='utf-8')
    state = {
        'active': True,
        'scope': 'machine',
        'activated_at': start.isoformat(timespec='seconds'),
        'expires_at': end.isoformat(timespec='seconds'),
        'boundaries': {
            'irreversible': 'allowed' if args.allow_irreversible else 'defer',
            'notes': args.note,
        },
        'log_path': str(log_path),
    }
    state_file().write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    boundary = '已授权放行' if args.allow_irreversible else '挂起待确认'
    print('无人值守模式已激活')
    print('- 生效：' + fmt_ts(state['activated_at']) + ' 至 ' + fmt_ts(state['expires_at']))
    print('- 边界：不可逆/对外操作 = ' + boundary)
    if args.note:
        print('- 备注：' + args.note)
    print('- 决策日志：' + str(log_path))
    print('解除：python "' + gate_command() + '" off')
    return 0


def cmd_off() -> int:
    status, data = read_state()
    path = state_file()
    if path.exists():
        path.unlink()
    if status == 'missing':
        print('当前未处于无人值守状态。')
        return 0
    print('无人值守模式已解除。')
    log_path = (data or {}).get('log_path')
    if log_path:
        print('决策日志保留在：' + str(log_path) + '（供汇总值守期间决策）')
    return 0


def cmd_status() -> int:
    status, data = read_state()
    if status == 'missing':
        print('无人值守状态：未激活')
        return 0
    if status == 'corrupt':
        print('无人值守状态：状态文件损坏，按无人值守 fail-closed 处理；可运行 off 清除。',
              file=sys.stderr)
        return 1
    if status == 'expired':
        print('无人值守状态：已过期（' + fmt_ts((data or {}).get('expires_at')) +
              '）；可运行 off 清除状态文件。')
        return 0
    boundaries = data.get('boundaries') or {}
    print('无人值守状态：生效中')
    print('- 激活：' + fmt_ts(data.get('activated_at')))
    print('- 到期：' + fmt_ts(data.get('expires_at')))
    print('- 边界：不可逆/对外操作 = ' +
          ('已授权放行' if boundaries.get('irreversible') == 'allowed' else '挂起待确认'))
    if boundaries.get('notes'):
        print('- 备注：' + str(boundaries['notes']))
    print('- 决策日志：' + str(data.get('log_path', '(未知)')))
    return 0


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(
        prog='gate.py',
        description='mv-unattended-watch 状态闸门：模式开关与值守 Hook 入口。')
    sub = parser.add_subparsers(dest='command', required=True)
    p_on = sub.add_parser('on', help='激活无人值守')
    p_on.add_argument('--expires-hours', type=float, default=24.0,
                      help='自动过期时长（小时），默认 24')
    p_on.add_argument('--allow-irreversible', action='store_true',
                      help='放行不可逆/对外操作（默认挂起待确认）')
    p_on.add_argument('--note', default='', help='备注或用户补充的授权说明')
    sub.add_parser('off', help='解除无人值守（决策日志保留）')
    sub.add_parser('status', help='查看当前状态')
    sub.add_parser('prompt', help=argparse.SUPPRESS)
    sub.add_parser('compact', help=argparse.SUPPRESS)
    sub.add_parser('session', help=argparse.SUPPRESS)
    sub.add_parser('block', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.command == 'on':
            return cmd_on(args)
        if args.command == 'off':
            return cmd_off()
        if args.command == 'status':
            return cmd_status()
        if args.command == 'block':
            return cmd_block()
        return cmd_remind(args.command)
    except Exception:
        if args.command in ('on', 'off', 'status'):
            traceback.print_exc()
            print('gate.py 内部错误。', file=sys.stderr)
            return 1
        return 0


if __name__ == '__main__':
    sys.exit(main())
