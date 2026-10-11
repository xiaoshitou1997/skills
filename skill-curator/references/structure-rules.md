# 仓库结构规则

新建或重构 skill 时逐项核对；由 `tests/validate_bundle.py` 自动兜底的部分已标注。

## Frontmatter

- `name`：kebab-case 小写，≤64 字符，必须与目录名一致（校验覆盖）。
- `description`：≤1024 字符，写触发场景而非功能罗列；包含用户可能的表述关键词；写明负向边界（何时不适用、归哪个 skill 管）。中英文均可，与仓库现有中文风格一致。
- 可选 `allowed-tools`：仅为只读、无副作用的命令预授权；写操作不预授权。

## 正文（SKILL.md）

- ≤500 行，长句拆为一条一行；超出的细节下沉 `references/`，正文只留当前有效工作流。
- 从 SKILL.md 引用脚本用 `${SKILL_ROOT}/scripts/<file>` 并说明 SKILL_ROOT 需显式赋值（校验覆盖路径存在性）。
- 引用 references 用相对链接 `references/<file>`（校验覆盖文件存在）。
- 默认中文工程书面语：不用人称、不用对话痕迹用语、不用无依据夸饰；同概念全文同术语。

## 脚本

- `set -euo pipefail`；入参做格式校验（APP 名、路径等正则白名单），失败退出码非零并输出到 stderr。
- 只读诊断与写操作分开；缺依赖（工具/扫描器）时如实报缺失，不虚构成功。
- Shell/Python 文件必须 LF（`.gitattributes` 已固定 `eol=lf`）。
- 跨 skill 复用的脚本保持字节级一致（DUPLICATE_GROUPS 校验），或干脆不复制。

## 校验与同步点

改动后必须全部过一遍：

1. `python3 tests/validate_bundle.py`（skill 集合、frontmatter、引用、复制脚本一致性、bash/py 语法）。
2. 新增/改名 skill → `tests/validate_bundle.py` 的 `SKILLS` 集合、`README.md` 与 `README.zh-CN.md` 表格、改名迁移记录。
3. 行为类改动 → `tests/test_workflows.py`、`tests/test_enhancements.py`、`tests/test_wsl_bridge.py`，必要时补离线用例（假 docker/假 wsl.exe stub 风格）。

## 命名先例

- 按任务域命名（toolchain-manager、git-publisher、engineering-doc-writer）或按团队硬约束命名（wsl-build-deploy 的 WSL 门禁）。
- 规范型 skill 用 `-standards` 后缀；避免与内置 skill（如 code-review、security-review）撞名。
- 改名成本高（已安装副本会双触发），优先只改 description 与内容，不动名字。
