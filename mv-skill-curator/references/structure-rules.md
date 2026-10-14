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
2. 新增/改名 skill → `tests/validate_bundle.py` 的 `SKILLS` 集合、`README.md` 与 `README.en.md` 表格、改名迁移记录。
3. 行为类改动 → `tests/test_workflows.py`、`tests/test_enhancements.py`、`tests/test_wsl_bridge.py`，必要时补离线用例（假 docker/假 wsl.exe stub 风格）。
4. description 或触发边界改动 → `python3 tests/run_trigger_evals.py <skill>` 过该 skill 正反例；无 claude CLI 时按 `tests/trigger_cases.py` 人工核对。
5. 增删改并提交后 → `bash mv-skill-curator/scripts/sync-installed.sh` 刷新全局安装并清理改名前旧版本（脚本内 STALE 清单与 README 迁移记录同步维护）。

## 命名先例

- 统一 `mv-` 前缀标识来源（2026-10 团队决策，取代裸场景名先例）：skills 多来源混装时看名字即知出自本仓库；前缀不承载场景语义，边界信息仍由名字其余部分与 description 提供。
- 名字其余部分对应团队场景的功能与流程（mv-toolchain-manager、mv-engineering-doc-writer-reviewer、mv-git-commit-push）；当机制/硬约束本身是团队标准的一部分时写进名字（mv-wsl-build-deploy 的 WSL 门禁，管镜像构建与容器运行），看到名字即知边界，防误触发与误用。
- 规范型 skill 用 `-standards` 后缀；前缀已大幅降低第三方撞名概率，仍避免与内置 skill（如 code-review、security-review）撞名。
- 名字以名实相符为先：发现核心功能不在名字概括范围内时改名，不因迁移成本回避；改名会使已安装旧副本双触发，必须走「校验与同步点」完整清单（STALE 清单、README 中英文迁移记录）。2026-10 前曾按「成本高、不改名」执行，后经名实核对修正为准确优先。`mv-` 前缀为一次性完成的批量迁移，新增 skill 直接带前缀。
- 官方推荐动名词命名（如 processing-pdfs）；本仓库不采用，属已确认的团队决策，记录见「外部依据」。

## 外部依据

形式规则的基准是 Anthropic 官方 Agent Skills 规范；修改形式规则前先对外核对，不自我循环：

- Specification：name 匹配 `^[a-z0-9]+(-[a-z0-9]+)*$` 且 ≤64 字符；description 必填且 ≤1024 字符。
- Best practices / Authoring：description 写触发场景（what + when + 触发词）；正文 <500 行，细节下沉 references；渐进披露三层（元数据 → 正文 → 按需加载）；反模式：空泛描述、时间敏感信息、假设不存在的上下文。
- 已知偏离：官方建议动名词命名，本仓库采用场景功能命名；这是命名先例确认过的团队决策，不视为违规。

## 触发契约评测

description 的真实职责是路由（该触发时触发、不该触发时安静）；静态校验只查得到非空和长度，行为只能实测：

- 用例集中在 `tests/trigger_cases.py`：每个 skill 正例（应触发）+ 反例（不得触发，标注 instead 正确去向或 none）。
- 触发场景：description 改动、新增 skill、拆分/合并改动边界之后，运行 `python3 tests/run_trigger_evals.py [skill]`；`--list` 离线查看矩阵。运行需 claude CLI 并按用例消耗 token，无 CLI 时人工核对该 skill 正反例。
- 判定口径：正例以目标 skill 触发为准；反例以目标 skill 未触发为准，instead 未触发记 WARN 不计失败。
- 反例失败 = description 边界失效：改 description 或拆边界，不修改用例迁就实现。
