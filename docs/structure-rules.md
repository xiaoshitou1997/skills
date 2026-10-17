# 仓库结构规则

新建或重构 skill 时逐项核对；由 `tests/validate_bundle.py` 自动兜底的部分已标注。

## 新增 skill 流程

按顺序执行；本节只定操作顺序，细则见对应章节。

1. 定职责、按两步法命名，候选名过三条检查（「命名先例」）。
2. 写 frontmatter：`name`、`description`（触发场景、表述关键词、负向边界）、可选 `allowed-tools` 只读预授权（「Frontmatter」）。
3. 写正文：定位语、SKILL_ROOT 段、任务步骤、硬约束、输出（「正文（SKILL.md）」与「章节骨架与句式」）。
4. 超出正文的细节下沉 references，单主题一文件（「正文（SKILL.md）」）。
5. 有脚本时按脚本纪律编写，运行时状态落点按「运行时目录」约定（「脚本」「运行时目录」）。
6. 注册：`tests/validate_bundle.py` 的 `SKILLS` 集合、`README.md` 表格；改名或移除时加同步脚本 STALE 清单（「校验与同步点」第 2 条）。
7. 全量过一遍「校验与同步点」。
8. 为 description 加触发正反例并实测（「触发契约评测」）。
9. 核对与其他 skill 的边界句式：职责归属清楚，允许同一任务按阶段合理协作（「章节骨架与句式」）。
10. 本机安装为可选项（「校验与同步点」末段）。

## Frontmatter

- `name`：kebab-case 小写，≤64 字符，必须与目录名一致，且以 `mv-` 前缀开头（校验覆盖；前缀见「命名先例」）。
- `description`：≤1024 字符，写触发场景而非功能罗列；包含用户可能的表述关键词；写明负向边界（何时不适用、归哪个 skill 管）。面向中文受众，使用中文描述，代码、标识符与必要技术词保留英文（校验覆盖非空与长度）。
- frontmatter 使用仓库支持的标量字段子集：普通单行、引号字符串或块标量；字段唯一，`name`、`description` 必填。校验检查该子集的结构与字段，不宣称支持完整通用 YAML 语法。
- 可选 `allowed-tools`：仅为只读、无副作用的命令预授权；写操作不预授权，不用同时包含写子命令的宽泛模式（如 `git branch:*`、`git remote:*`）。

## 正文（SKILL.md）

- SKILL.md 正文 ≤500 行（不含 frontmatter，校验覆盖），长句拆为一条一行；超出的细节下沉 `references/`，正文只留当前有效工作流。
- 从 SKILL.md 引用脚本用 `${SKILL_ROOT}/scripts/<file>` 并说明 SKILL_ROOT 需显式赋值（校验覆盖路径存在性）。
- 引用 references 用相对链接 `references/<file>`（校验覆盖文件存在）。
- 默认中文工程书面语：不用人称、不用对话痕迹用语、不用无依据夸饰；同概念全文同术语。中文为主，该用英文的用英文：代码、命令、路径、标识符、技术词保留英文，不强行翻译。

## 章节骨架与句式

本节为现有 skills 正文写法的团队约定提炼，非官方规范；与官方规范重合处以外部依据为准。

- H1 为中文主题短语（与正文中文文风一致，专名如 Git、Java 保留英文），下接 1-2 句定位语：面向谁、管什么、不管什么。
- 含脚本的 skill 在正文前部写 SKILL_ROOT 段，三要素：变量需显式赋值（agent 不保证自动提供）、路径恒加引号、工作目录保持为用户项目；正文出现 `${SKILL_ROOT}` 时必须有反引号包裹的 `SKILL_ROOT` 说明文字（校验覆盖）。
- 任务/流程用编号步骤，一步一个动作；硬约束独立成节（如「不可违反的原则」「硬约束」），关键规则写成加粗独句。
- 结尾设输出与边界小节：产物是什么、验证结果记什么、哪些事归别的 skill。
- 边界句式：description 内用「X 归 mv-Y」；正文内用「见 mv-Y」「前置条件」「只负责」；规则冲突优先级写明「用户明确需求 → 本规范 → 框架默认」。
- references：英文名词 kebab-case，单主题一文件；SKILL.md 文末设参考清单，每条一行职责说明，按需加载不全文导入；reference 开头 1-3 句适用范围与优先级，结尾一句边界免责。
- 验证表述三件套：给出命令、如实记录结果、不虚构；未执行的检查明确写「未执行」，不写成「通过」。
- 术语全文一致（本 skill、宿主、会话级、硬约束、收据等），同一概念不用同义词交替。

## 脚本

- `set -euo pipefail`；入参做格式校验（APP 名、路径等正则白名单），失败退出码非零并输出到 stderr。
- 只读诊断与写操作分开；缺依赖（工具/扫描器）时如实报缺失，不虚构成功。
- Shell/Python 文件必须 LF（`.gitattributes` 已固定 `eol=lf`）。
- 跨 skill 复用的脚本保持字节级一致（DUPLICATE_GROUPS 校验），或干脆不复制。

## 运行时目录

- 本仓库 skills 的运行时状态根为 `~/.mv/`，子目录为 skill 目录名去掉 `mv-` 前缀（如 `mv-toolchain-manager` → `~/.mv/toolchain-manager/`）；根承载来源标识，与 `mv-` 前缀同构，整个 `~/.mv/` 可整体重置。
- 目录路径常量必须有环境变量覆盖，命名统一 `MV_<子目录名大写、连字符转下划线>_HOME`（如 `MV_TOOLCHAIN_MANAGER_HOME`、`MV_UNATTENDED_WATCH_HOME`），供测试与隔离使用；该覆盖适用于状态落在本机（执行 skill 的机器）的场景。状态落在目标机（WSL 侧、远端服务器、以本机为交付目标的 native 模式）时路径相对目标用户 HOME 解析，测试隔离经 `HOME`/`WSL_HOME` 重定向与 stub 实现，不另设覆盖变量。
- 状态不写入其他 skill 的子目录；跨 skill 依赖走产物与收据文件，不共享运行时目录。
- 各 skill 的落点在本 skill 文档中写明，与脚本常量同源；WSL 与远端目标机侧写入同一 `~/.mv/<name>` 路径。
- `~/.claude` 与 XDG 目录不是本仓库 skills 的状态落点；宿主自身的配置文件（如 `~/.claude/settings.json`）不受此条约束。

## 校验与同步点

改动后必须全部过一遍：

1. `python3 tests/validate_bundle.py`：skill 集合；frontmatter 标量子集结构、字段唯一、必填元数据、名称格式/限长及目录一致；description 非空/限长；SKILL.md 正文行数（不含 frontmatter）；所有 Markdown 的显式本地链接目标存在性（不验证锚点）；正文脚本/模板路径与 SKILL_ROOT 声明；复制脚本一致性；Bash/Python 语法。
2. 新增/改名 skill → `tests/validate_bundle.py` 的 `SKILLS` 集合、`README.md` 表格、相关引用及同步脚本的 STALE 清单。
3. 行为类改动 → `tests/test_workflows.py`、`tests/test_enhancements.py`、`tests/test_wsl_bridge.py`，必要时补离线用例（假 docker/假 wsl.exe stub 风格）。
4. description 或触发边界改动 → `python3 tests/run_trigger_evals.py <skill>` 在隔离环境评测该 skill 正反例；CLI 或凭据缺失时明确记为未执行，并按 `tests/trigger_cases.py` 人工核对，不能把人工核对写成真实路由通过。

安装到本机为可选项：需要时执行 `bash scripts/sync-installed.sh`（加 `--remote` 改从 GitHub 源安装），脚本安装全部 skills 并清理改名/合并前旧版本；是否安装、装到哪台机器由使用者决定，不属于校验流程。旧版本清理名称仅维护在脚本内 STALE 清单，不写入文档。

## 命名先例

- 统一 `mv-` 前缀标识来源（用户确认的来源标识）：skills 多来源混装时看名字即知出自本仓库；前缀不承载场景语义。
- 本集合统一采用 `mv-` + 对象 + 职责词，如 `mv-toolchain-manager`、`mv-image-build`、`mv-java-backend-standards`；这是用户确认的团队约定，不代表官方形式排名。对象与职责词均用英文名词，不用动名词。
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

description 的真实职责是路由（该触发时触发、不该触发时安静）；静态校验检查字段及长度，路由行为需实测。一个任务可以按职责触发多个 skill，合理协作本身不构成边界问题：

- 用例集中在 `tests/trigger_cases.py`：正例记录应触发目标及必要协作集合，反例记录不得触发目标与预期去向；用例前提须足以排除工具链缺失等无关因素。
- 触发场景：description 改动、新增 skill、拆分/合并改动边界之后，运行 `python3 tests/run_trigger_evals.py [skill]`；`--list` 离线查看矩阵，`--claude` 指定 CLI 路径，`--limit` 限定冒烟范围。运行按用例消耗 token；CLI 缺失或隔离环境缺少 `ANTHROPIC_API_KEY`/`CLAUDE_CODE_OAUTH_TOKEN` 时明确 SKIP，不复制用户登录文件。
- 隔离要求：复制待测工作区的候选 skill 内容并记录 SHA-256；使用临时 HOME 与 `CLAUDE_CONFIG_DIR`、project-only settings，不加载用户已安装 skills、Hook、MCP 或动态 shell 内容，仅允许 Skill 工具。按完整 skill 身份检测调用，并核对会话完成结果；提前退出或达到轮数上限不能视为路由通过。
- 判定口径：正例目标与必要协作集合均须触发，额外的合理协作不记边界告警；反例目标不得触发，预期去向未触发单独报告。先核对隔离、用例前提及实际职责，再判断失败原因；不能仅凭多 skill 调用判为 description 失效。
- 路由缺陷修 description 或职责边界；用例与已确认职责不符时修用例并说明依据，不为消除失败迁就实现。
