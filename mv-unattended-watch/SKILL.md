---
name: mv-unattended-watch
description: 用户明确宣布离场并把后续事务全权交给 AI 时使用，也用于用户回归或要求取消无人值守。典型激活语义是「我要睡觉了，后面你自己看着办」「我离开了，全权交给你」；「无人值守」「别再问我」等词须结合离场与全权委托上下文判断，单独命中不激活。激活后写机器级状态并记录决策日志；Claude Code 已显式安装且正常运行值守 Hook 时，每轮及压缩/恢复后注入提醒并拦截 AskUserQuestion；未安装 Hook 或非 Claude Code 时仅当前上下文有效，不保证跨压缩与会话持续执行。用户回来、「取消无人值守」或「恢复正常模式」时解除并汇总。用户在线时的一次性委托或单点问题不激活；提交发布归 mv-git-publisher，出包打镜像归 mv-image-build，本机直启调试归 mv-local-debug，部署晋级归 mv-container-deploy，本 skill 只负责模式开关与值守纪律。
---

# 离场无人值守

在用户离场且全权委托后接管决策：不提问、自行选择最优方案、留痕可审计。模式状态保存在上下文之外的机器级状态文件中；跨压缩、恢复或新会话的自动提醒与提问拦截依赖 Claude Code 中已安装且正常运行的值守 Hook。

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

值守 Hook 由用户显式安装（仓库分发不自动安装 Hook，本 skill 是唯一例外）：`python3 "${SKILL_ROOT}/scripts/install_hooks.py"`，`--dry-run` 预览、`--remove` 卸载，写入用户级 `~/.claude/settings.json` 四个条目（路径可用环境变量 `MV_UNATTENDED_SETTINGS` 覆盖，供测试与隔离）：

| Hook | 行为 |
| --- | --- |
| UserPromptSubmit | 每轮用户输入注入值守提醒 |
| SessionStart（matcher=compact） | 上下文压缩后立即重注入提醒 |
| SessionStart（matcher=startup\|resume） | 新会话或恢复会话时注入提醒 |
| PreToolUse（matcher=AskUserQuestion） | 硬拦截提问，stderr 指示自行决策 |

值守 Hook 仅适用于 Claude Code；安装需用户显式授权，激活模式本身不代替安装授权。核对 `~/.claude/settings.json` 中本 skill 的事件条目、解释器及 `gate.py` 绝对路径，并确认配置已加载；仅检索到名称不能证明 Hook 正常运行。

未安装 Hook 时模式仍可激活；非 Claude Code agent 不执行 Hook 安装，按相同纪律降级为仅当前上下文有效。两种情况都应如实声明不保证压缩、恢复或新会话后自动提醒与拦截；状态文件的机器级落点不因此改变。

## 激活流程

按语义确认用户同时表达「离场」与「后续事务全权委托」后激活，不因孤立关键词或引用他人话语激活；仅在线委托一个任务、仅声明离场或仅说「别再问我」均不满足条件。符合条件后不再重复询问是否激活：

1. `python3 "${SKILL_ROOT}/scripts/gate.py" on [--expires-hours N] [--allow-irreversible] [--note "..."]`。用户给了时限或授权就写入参数；默认 24 小时后自动过期。
2. 向用户输出确认块，一次说清，不追问：
   - 生效起止时间、决策日志路径；
   - 边界默认：不可逆/对外操作（push、生产部署、删除数据、对外发消息）挂起并登记「待确认」，回来后逐项处理；如需放开，现在说一句即可写入授权；
   - Hook 未安装、未确认运行或非 Claude Code 时声明「模式仅当前上下文有效」，不承诺跨压缩与会话自动执行；
   - 若当前权限模式会频繁弹出权限确认导致任务停等，建议用户切换权限模式（如 `dontAsk`/`auto`）后再离开。
3. 随后按用户交代的任务继续，进入值守纪律。

## 值守纪律

1. 不调用 AskUserQuestion；看到 Hook 注入的值守提醒按提醒执行，未看到提醒但 `gate.py status` 显示生效中时同样执行。
2. 每项重要决策（方案选择、跳过的步骤、执行的写操作）追加一行到决策日志：`时间 | 决策 | 理由 | 可逆性 | 证据`，证据为命令、路径或输出摘要。
3. 可逆的本地操作直接执行；不可逆/对外操作在 `boundaries.irreversible` 为 `defer` 时一律挂起：登记到日志「待确认」清单，继续其余工作，不空转等待；为 `allowed`（用户显式授权）时执行且必须留日志。
4. 不降低各领域 skill 的既有红线：提交发布走 mv-git-publisher（先 pull、线性历史、AI 署名），出包打镜像走 mv-image-build、宿主直启调试走 mv-local-debug、部署晋级走 mv-container-deploy；无人值守不豁免任何「不可违反的原则」。
5. 遇到必须用户裁决且无最优解的情况（如 Git 冲突无法取舍），停止该事务、登记待确认，转向其余任务。

## 解除流程

用户本人表达回归，或明确要求「取消无人值守」「恢复正常模式」时执行；取消不要求同时出现离场或全权委托语义。引用示例、他人转述不作为解除信号：

1. `python3 "${SKILL_ROOT}/scripts/gate.py" off` 删除状态文件（决策日志保留）。
2. 读取决策日志，向用户汇总：已完成的决策与动作、待确认清单（挂起的不可逆操作，逐项给出现成选项）、遗留风险。
3. 汇总后恢复正常模式。

## 自检

```bash
python3 "${SKILL_ROOT}/scripts/gate.py" status
python3 "${SKILL_ROOT}/scripts/install_hooks.py" --dry-run
```
