---
name: git-publisher
description: 用户要求提交代码、拆分原子 commit、推送分支、创建 PR 或查看 PR 检查结果时使用。按独立逻辑变更精细暂存，审查最终 staged diff，并遵循仓库提交规范；仅解释 Git 概念时无需加载完整发布流程。
---

# Git Publisher

本 skill 面向团队内跨项目复用；以下已确认的团队规则是默认基线，不因其他团队采用不同工作流而降为可选项。

从加载的 SKILL.md 定位实际 skill 目录并赋给 `SKILL_ROOT`；此变量不保证由 agent 设置。保持用户仓库为工作目录，路径加引号。下文 Python 命令需使用本机可用的 Python 3 解释器。

## 不可违反的原则

**一次提交 = 一个逻辑完整、语义独立且尽量可单独 revert 的 change set。** 相同 `feat` 类型不代表同一个 Feature；同一 Feature 的 Controller、Service、DAO、测试、文档可以归为一个提交。

1. 不使用 `git add .`、`git add -A` 或 `git commit -am` 扫荡所有修改。不擅自清空/重置已有暂存区。
2. 不调用 `git reset --hard`、`git clean -fd`、强制推送、跳过 Git hooks、`--no-verify`。
3. 提交描述以当前最终 staged diff 为事实依据；聊天记录用于理解意图，不能代替实际变更审查。
4. 有已暂存内容时，先识别是谁暂存的、属于哪个逻辑变更集；未经允许不混入别的变更。独立工作区或临时 index 可用于精细分组，但必须保证原始 index 状态不丢失。
5. 每次操作前确认所在仓库/分支，尤其单仓库父目录、多仓库目录、嵌套 Git、子模块。不得跨仓库混提交。
6. 暂存状态不表示改动归属，IDE 或其他会话可能自动暂存。必要时同时审查 HEAD→index 和 index→工作区差异；`AM` 等状态意味着暂存版与最终文件不同。
7. **每次 commit 前先 pull 并解决冲突，再提交。** 同步失败、冲突未解决或 rebase/merge 未结束时停止提交，不先 commit 再补同步。
8. **保持线性提交历史，禁止生成 merge commit。** 远端同步使用 rebase，不用 merge commit 解决分支分歧。
9. **AI 参与生成或修改的提交和 PR 必须添加 AI 署名或归属行。** 署名采用实际工具的默认方式或用户配置，本 skill 不规定具体格式。

## 工作流

1. `git status --short --branch`; `git diff --stat`; `git diff --cached --stat`; `git log -5 --oneline`。查看 untracked 文件与分支上游关系；按下文“远端同步与中间态”保护改动后先 pull、解决冲突并恢复改动，再审查同步后的 diff。每组 commit 前均完成此检查。
2. 阅读对应 diff，形成 change-set 计划：每组写明**业务目的、文件/hunk 范围、type、关联测试、依赖顺序**。文件可能重叠，需要部分 hunk staging；用户已指定特性范围时不要扩展到无关修改。
3. 按依赖顺序逐组操作：`git add -- <explicit paths>`。同文件有多组修改时，交互式终端可用 `git add -p`；无人值守工具使用经过审查的 patch，通过 `git apply --cached --check` 验证后再暂存。保留原始 index，审查最终暂存差异，不猜测修改边界。
4. 对每组 `git diff --cached --check`、`git diff --cached --name-status`、`git diff --cached --`；可运行 `python3 "${SKILL_ROOT}/scripts/stage_audit.py"` 检查常见 secret/大文件风险；确认暂存内容**只**属于当前组。
5. 根据涉及代码运行项目已有且可用的轻量检查，如 lint / typecheck / targeted tests。没有配置的检查不应虚构成功；失败时停止本组提交并报告。
6. 采用用户或仓库约定的提交语言与格式。没有既有约定时可默认中文 Conventional Commits，例如 `feat(auth): 增加短信登录验证码校验`。标题基于本组 staged diff，避免含糊通用信息。
7. `git commit -m '...'` 后再次查看状态及 SHA；所有组处理完再按用户意图 push。用户仅指定 `commit` 时不要自动 push；用户明确要求 `push` 或“提交并推送”时使用安全普通 push，上游缺失时确认远端与分支再设置。
8. 汇报每组提交的 hash、type、变更目的、检查情况、push 结果，以及明确保留的未提交内容。

## 同文件不同 Feature

按 hunk 临时 staged 后审查 `git diff --cached`，测试通过才提交。不要依赖自动语义分类脚本“猜”提交边界；这种判断需要 Agent 结合代码上下文完成。

## 远端同步与中间态

- 提交顺序固定为：保护未提交改动 → `git fetch` → `git pull --rebase <remote> <branch>` → 解决冲突并完成 rebase → 恢复改动并解决恢复冲突 → 审查、验证、commit。remote/branch 使用已确认的上游，不猜测。项目指令与团队规则冲突时先明确冲突，不自行改用 merge commit。
- 未配置上游时先检查远端并确认同步目标；纯本地仓库或尚无对应远端分支的首次提交，明确记录没有可 pull 的目标，不伪称同步成功。已有同步目标但网络、权限或 pull 失败时停止提交。
- 需要同步且工作区不干净时，先确认改动归属与恢复方式；stash 会影响共享工作区，不自动把他人 staged/untracked 内容一起藏起。若使用 stash，记录标识，并在恢复后核对文件与暂存状态。
- merge/rebase 尚未结束时，先处理或明确退出当前操作，不叠加新的 pull 或 stash 恢复；失败命令不得被输出管道的末端成功掩盖。
- 命令使用明确工作目录，管道检查原始 Git 退出码。提交和 PR 发布前检查最终消息，确保 AI 参与的内容带有准确的 AI 署名或归属行。

## 权限与风险

- 不能自动改 `.gitignore` 来隐藏秘密，再照常提交；被怀疑含 secret 直接停止并报告。
- 多个仓库各自分别完成事务，不自动批量 push 不相干仓库。
- 推送失败不得重试 `--force` 或自动 rebase/merge 用户未同意的远端改动。
- 如果 Spec Kit Git 扩展默认全量暂存，绕过该自动提交步骤，使用本 Skill 的语义暂存规则；其他 Spec Kit 阶段保持原生实现。

## GitHub PR 工作流（明确请求才执行）

1. 检查本次 PR 相对目标分支的全部提交与 diff；已有合适提交时直接复用，无需为了创建 PR 新增 commit。仍有待提交修改时按独立功能分组，避免加入无关变更。
2. 用户明确要求 Push 才执行 `git push`。确认当前分支正确、上游已设置及远端没有不明变更。
3. GitHub 项目可复用 `gh`，先运行 `gh auth status`；用户要求创建 PR 后，使用 `bash "${SKILL_ROOT}/scripts/pr.sh" create <base> <title> <body.md>`，该脚本要求干净工作区及已配置上游，不会自动 Push。
4. `bash "${SKILL_ROOT}/scripts/pr.sh" checks` 获取 CI 状态；失败不能宣称发布质量通过。审查意见用 agent 可用工具或 gh 读取，不自动合并或覆盖别人提交。
5. PR 检查应覆盖相对目标分支的实际变更，而不是依赖此时可能为空的 staged diff。按项目需求使用 `bash "${SKILL_ROOT}/scripts/quality-check.sh" quick` 或 `full`；缺工具时停止或明确报告未执行。

## 可用增强工具

- `bash "${SKILL_ROOT}/scripts/security-scan.sh" source .` 调用已有 Gitleaks（可选；缺失应如实报告）。
- 本 skill 不安装自动 Hook。平台保护和项目自身 Hook 按原有约定运行。
- 仓库保护、CODEOWNERS、PR 审查和 CI 仍由 Git 平台管理，不在 Skill 内重新实现。
