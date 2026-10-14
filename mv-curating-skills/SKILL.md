---
name: mv-curating-skills
description: 把用户随手发来的工作习惯、流程片段、团队约定沉淀进本 skills 仓库时使用；判断应并入现有 skill、新建 skill 还是暂存观察，执行合并/拆分/重构并完成校验与原子提交。闲聊、业务代码实现或与工程实践无关的内容不适用。
---

# Curating Skills

把碎片化的团队经验整合为可复用的 skill 条款，保持仓库结构不漂移。

## 核心流程

1. 保留原文语义，不改写用户意图；把内容分类：规则（必须/禁止）、流程（步骤）、偏好（默认倾向）、事实（环境/版本）、未决（Open Question）。
2. 判断归属：
   - 命中现有 skill 范围 → 更新该 skill 的 SKILL.md 或 references，遵守该文件既有结构、术语与文风；改动机械/易错步骤优先落为脚本而非堆叠文字条款。
   - 与现有条款冲突 → 停下指出冲突及两侧出处，由用户裁决；团队已确认基线不静默降级，用户明确改口才更新基线。
   - 独立成主题且可复用 → 新建 skill，结构要求见 references/structure-rules.md。
   - 碎片过小暂不成条款 → 记入仓库根 `INBOX.md`（格式：`- 日期 主题：原文`）；后续每次 intake 优先消化积压，已吸收的条目删除。
3. 结构操作：
   - 合并：同主题多来源碎片聚合为一条规则，保留最严格约定，出处不同的冲突点显式标注而非取平均。
   - 拆分：一个 SKILL.md 覆盖多个不相关触发场景、或正文超过 500 行时，拆出新 skill 并在双方 description 声明互斥边界。
   - 重构：语义不变前提下拆长句为短条目、下沉重复内容到 references、修正漂移的 description、删除被新流程替代的旧指令。
4. 每次改动后：
   - 在仓库根运行 `python3 tests/validate_bundle.py`；新增或改名 skill 必须同步该脚本的 SKILLS 集合、README 中英文表格，改名还要补 README 迁移记录。
   - 增删改 skill 并提交后运行 `bash "${SKILL_ROOT}/scripts/sync-installed.sh"` 同步已安装副本：默认从本地检出把全部 skills 装到配置的 agent 目标（universal、claude-code，可用 `-a` 覆盖），并清理改名/合并前的旧版本；`--remote` 改从 GitHub 源安装（需先 push）。`SKILL_ROOT` 为本 skill 目录的显式绝对路径，agent 不保证自动提供。
   - 按独立逻辑变更分组提交，遵循 mv-publishing-git-changes 的团队约定：中文 Conventional Commits、AI 署名、先 pull 再 commit。
5. 汇报：归类结果（并入哪/新建什么/暂存什么）、改动文件、执行的校验、遗留 Open Question。

## 质量门槛

- 只有用户明确确认的规则才写成硬约束；推断出的倾向写成默认行为并注明可覆盖方式。
- 不写入业务专属路径、凭据、客户名；不虚构用户没说过的规则。
- 条款要带触发场景或反例，能被 agent 直接执行；"注意质量"这类空泛建议不入库。
- description 是触发契约：改动时检查与其他 skill 的触发边界是否仍然互斥、长度是否 ≤1024 字符；改动前后用 `python3 tests/run_trigger_evals.py <skill>` 过该 skill 正反例（无 claude CLI 时按 `tests/trigger_cases.py` 人工核对）。
- 多个 skill 字节级复制的脚本（清单见 tests/validate_bundle.py 的 DUPLICATE_GROUPS）修改必须同步所有副本，否则校验失败。

## 边界

- 本 skill 服务于本仓库维护，需要完整仓库检出；独立安装时没有 tests/，改为人工核对 references/structure-rules.md 清单。
- 拆分/合并/改名等大规模重构先给方案再动手；不静默重排其他人正在依赖的结构。
- 已安装旧版本 skill 的清理由用户显式执行，本 skill 不代做。
