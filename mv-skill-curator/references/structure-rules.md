# 仓库结构规则

新建或重构 skill 时逐项核对；由 `tests/validate_bundle.py` 自动兜底的部分已标注。

## Frontmatter

- `name`：kebab-case 小写，≤64 字符，必须与目录名一致，且以 `mv-` 前缀开头（校验覆盖；前缀见「命名先例」）。
- `description`：≤1024 字符，写触发场景而非功能罗列；包含用户可能的表述关键词；写明负向边界（何时不适用、归哪个 skill 管）。中英文均可，与仓库现有中文风格一致。
- 可选 `allowed-tools`：仅为只读、无副作用的命令预授权；写操作不预授权。

## 正文（SKILL.md）

- ≤500 行，长句拆为一条一行；超出的细节下沉 `references/`，正文只留当前有效工作流。
- 从 SKILL.md 引用脚本用 `${SKILL_ROOT}/scripts/<file>` 并说明 SKILL_ROOT 需显式赋值（校验覆盖路径存在性）。
- 引用 references 用相对链接 `references/<file>`（校验覆盖文件存在）。
- 默认中文工程书面语：不用人称、不用对话痕迹用语、不用无依据夸饰；同概念全文同术语。中文为主，该用英文的用英文：代码、命令、路径、标识符、技术词保留英文，不强行翻译。

## 脚本

- `set -euo pipefail`；入参做格式校验（APP 名、路径等正则白名单），失败退出码非零并输出到 stderr。
- 只读诊断与写操作分开；缺依赖（工具/扫描器）时如实报缺失，不虚构成功。
- Shell/Python 文件必须 LF（`.gitattributes` 已固定 `eol=lf`）。
- 跨 skill 复用的脚本保持字节级一致（DUPLICATE_GROUPS 校验），或干脆不复制。

## 校验与同步点

改动后必须全部过一遍：

1. `python3 tests/validate_bundle.py`（skill 集合、frontmatter、引用、复制脚本一致性、bash/py 语法）。
2. 新增/改名 skill → `tests/validate_bundle.py` 的 `SKILLS` 集合、`README.md` 表格、相关引用及同步脚本的 STALE 清单。
3. 行为类改动 → `tests/test_workflows.py`、`tests/test_enhancements.py`、`tests/test_wsl_bridge.py`，必要时补离线用例（假 docker/假 wsl.exe stub 风格）。
4. description 或触发边界改动 → `python3 tests/run_trigger_evals.py <skill>` 过该 skill 正反例；无 claude CLI 时按 `tests/trigger_cases.py` 人工核对。

安装到本机为可选项：需要时执行 `bash mv-skill-curator/scripts/sync-installed.sh`（加 `--remote` 改从 GitHub 源安装），脚本安装全部 skills 并清理改名/合并前旧版本；是否安装、装到哪台机器由使用者决定，不属于校验流程。旧版本清理名称仅维护在脚本内 STALE 清单，不写入文档。

## 命名先例

- 统一 `mv-` 前缀标识来源（用户确认的来源标识）：skills 多来源混装时看名字即知出自本仓库；前缀不承载场景语义。
- 本集合统一采用 `mv-` + 对象 + 职责词，如 `mv-toolchain-manager`、`mv-container-delivery`、`mv-java-backend-standards`；这是用户确认的团队约定，不代表官方形式排名。对象与职责词均用英文名词，不用动名词。
- 命名按顺序走两步：
  1. 定职责：回答「删掉这个 skill，团队缺的哪一种产出或能力」——这就是主体职责，压缩成一个中文名词（如「管理」「交付」「规范」「写作」）。说不出一个、或说出几个并列的，说明 skill 该先拆分，命名放到拆分之后。
  2. 定名字：职责词取该中文名词对应的英文名词，对象取 skill 作用的英文名词，合成 `mv-<对象>-<职责词>`。
- 候选名字过三条检查，任一不过就回到第 1 步：
  1. 代入检验——「负责 <对象> 的 <职责>」是对主体职责的准确概括，语义不变形。
  2. 自解释——职责词单独出现即能传达职责；`handler`、`processor`、`helper` 这类与任何对象都能搭配的万能词不合格。
  3. 一词一义——检索仓库现有 skill，同一职责只用一个词；`publisher` 在位就不另造 `pusher`。
- 具体任务模式（编写、修订、评审、合并、拆分等）是到达职责的路径，写入 description，不进名字。
- 名称明确主体能力、对象与必要的范围限定，与 description 和正文一致；不要求名字列出每个辅助步骤。
- 避免模糊名（helper、utils）、过宽名（documents、data、files）与保留词（anthropic、claude）。
- 改名须说明现名的具体歧义或覆盖缺口、候选名如何改善；依据区分官方规则、团队约定与维护者判断。实施时走「校验与同步点」完整清单。
- 文档只描述当前有效规则和用法，不记录名称迁移、曾用名或讨论演变；旧版本清理名称仅维护在同步脚本的 STALE 清单。

## 外部依据

形式规则的基准是 Anthropic 官方 Agent Skills 规范；修改形式规则前先对外核对，不自我循环：

- Specification：name 匹配 `^[a-z0-9]+(-[a-z0-9]+)*$` 且 ≤64 字符；description 必填且 ≤1024 字符。
- Best practices / Authoring：description 写触发场景（what + when + 触发词）；正文 <500 行，细节下沉 references；渐进披露三层（元数据 → 正文 → 按需加载）；反模式：空泛描述、时间敏感信息、假设不存在的上下文。
- [Agent Skills Specification](https://agentskills.io/specification#name-field)：名称长度、字符、连字符位置与目录名一致性的格式要求。
- [Skill authoring best practices · Naming conventions](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices#naming-conventions)：建议考虑动名词，接受名词短语与动作式；避免模糊、过宽、保留词与集合内不一致的命名。
- 引用外部依据时保留原意，明确区分格式要求、写作建议与团队约定。

## 触发契约评测

description 的真实职责是路由（该触发时触发、不该触发时安静）；静态校验只查得到非空和长度，行为只能实测：

- 用例集中在 `tests/trigger_cases.py`：每个 skill 正例（应触发）+ 反例（不得触发，标注 instead 正确去向或 none）。
- 触发场景：description 改动、新增 skill、拆分/合并改动边界之后，运行 `python3 tests/run_trigger_evals.py [skill]`；`--list` 离线查看矩阵。运行需 claude CLI 并按用例消耗 token，无 CLI 时人工核对该 skill 正反例。
- 判定口径：正例以目标 skill 触发为准；反例以目标 skill 未触发为准，instead 未触发记 WARN 不计失败。
- 反例失败 = description 边界失效：改 description 或拆边界，不修改用例迁就实现。
