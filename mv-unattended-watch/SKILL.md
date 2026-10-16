---
name: mv-unattended-watch
description: 用户宣布离场并把后续事务全权交给 AI 时使用：典型表述如「无人值守」「全权交给AI」「全权交给你」「我要睡觉了」「我要下班了」「我要去玩了」「我离开了」「后面你自己看着办」「别再问我」。激活后写入机器级状态文件，由用户显式安装的值守 Hook 每轮重新注入值守提醒并硬拦截 AskUserQuestion，保证跨上下文压缩仍不提问；值守期间按保守边界自行做最优决策并记录决策日志，用户回来后解除并汇总。负向边界：用户在线时的一次性委托或单点问题不激活本模式；值守期间遇到的提交发布归 mv-git-publisher，构建出包与本地调试归 mv-image-build，部署晋级归 mv-container-deploy，本 skill 只负责模式开关与值守纪律。
---

# Unattended Watch

在用户离场期间接管决策：不提问、自行选择最优方案、留痕可审计。模式状态保存在上下文之外的机器级状态文件中，上下文压缩或更换会话都不丢失。

下文 `${SKILL_ROOT}` 指向本 skill 目录；`SKILL_ROOT` 变量需显式赋值，不保证由 agent 自动设置。Python 命令使用本机可用的 Python 3 解释器。

## 模式与机制

状态文件是模式是否生效的唯一事实源，位于 `~/.mv/unattended-watch/`（测试可用环境变量 `MV_UNATTENDED_WATCH_HOME` 覆盖）：

```json
{
  "active": true,
  "scope": "machine",
  "activated_at": "2026-10-16T23:00:00+08:00",
  "expires_at": "2026-10-17T23:00:00+08:00",
  "boundaries": {"irreversible": "defer", "notes": "用户补充的授权或说明"},
  "log_path": "……/decisions-20261016-230000.md"
}
```

值守 Hook 由用户显式安装（仓库分发不自动安装 Hook，本 skill 是唯一例外）：`python3 "${SKILL_ROOT}/scripts/install_hooks.py"`，`--dry-run` 预览、`--remove` 卸载，写入用户级 `~/.claude/settings.json` 四个条目：

| Hook | 行为 |
| --- | --- |
| UserPromptSubmit | 每轮用户输入注入值守提醒 |
| SessionStart（matcher=compact） | 上下文压缩后立即重注入提醒 |
| SessionStart（matcher=startup\|resume） | 新会话或恢复会话时注入提醒 |
| PreToolUse（matcher=AskUserQuestion） | 硬拦截提问，stderr 指示自行决策 |

未安装 Hook 时模式仍可激活，但只对当前上下文有效，压缩后可能失效；激活时应向用户如实声明这一点。是否已安装可通过检索 `~/.claude/settings.json` 中的 `mv-unattended-watch` 判断。

## 激活流程

触发词命中后立即激活，不提问：

1. `python3 "${SKILL_ROOT}/scripts/gate.py" on [--expires-hours N] [--allow-irreversible] [--note "..."]`。用户给了时限或授权就写入参数；默认 24 小时后自动过期。
2. 向用户输出确认块，一次说清，不追问：
   - 生效起止时间、决策日志路径；
   - 边界默认：不可逆/对外操作（push、生产部署、删除数据、对外发消息）挂起并登记「待确认」，回来后逐项处理；如需放开，现在说一句即可写入授权；
   - Hook 未安装时声明「模式仅当前上下文有效」；
   - 若当前权限模式会频繁弹出权限确认导致任务停等，建议用户切换权限模式（如 `dontAsk`/`auto`）后再离开。
3. 随后按用户交代的任务继续，进入值守纪律。

## 值守纪律

1. 不调用 AskUserQuestion；看到 Hook 注入的值守提醒按提醒执行，未看到提醒但 `gate.py status` 显示生效中时同样执行。
2. 每项重要决策（方案选择、跳过的步骤、执行的写操作）追加一行到决策日志：`时间 | 决策 | 理由 | 可逆性 | 证据`，证据为命令、路径或输出摘要。
3. 可逆的本地操作直接执行；不可逆/对外操作在 `boundaries.irreversible` 为 `defer` 时一律挂起：登记到日志「待确认」清单，继续其余工作，不空转等待；为 `allowed`（用户显式授权）时执行且必须留日志。
4. 不降低各领域 skill 的既有红线：提交发布走 mv-git-publisher（先 pull、线性历史、AI 署名），构建调试走 mv-image-build、部署晋级走 mv-container-deploy；无人值守不豁免任何「不可违反的原则」。
5. 遇到必须用户裁决且无最优解的情况（如 Git 冲突无法取舍），停止该事务、登记待确认，转向其余任务。

## 解除流程

触发词：「我回来了」「取消无人值守」「我在」等本人回归信号：

1. `python3 "${SKILL_ROOT}/scripts/gate.py" off` 删除状态文件（决策日志保留）。
2. 读取决策日志，向用户汇总：已完成的决策与动作、待确认清单（挂起的不可逆操作，逐项给出现成选项）、遗留风险。
3. 汇总后恢复正常模式。

## 自检

```bash
python3 "${SKILL_ROOT}/scripts/gate.py" status
python3 "${SKILL_ROOT}/scripts/install_hooks.py" --dry-run
```
