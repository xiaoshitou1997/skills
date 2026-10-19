# CPython 便携源（python-build-standalone）

## 使用场景

Python 是受支持的项目运行时：安装器会依次读取 `.python-version`、`.tool-versions`、`.mise.toml` 与 `pyproject.toml` 的 `[project].requires-python`。它不替代项目已有的解释器、虚拟环境、uv 或 conda；项目现有方案可用时应直接使用。`mv-image-build` 的 crane 路径同样可复用这个便携 Python：`crane-build.sh` 需要它读取并重写镜像 tar 的 `manifest.json`（补 `RepoTags`、校验 Config 摘要）。

## 当前版本接口

最新 release 是日期标签：

```
https://github.com/astral-sh/python-build-standalone/releases/latest
→ https://github.com/astral-sh/python-build-standalone/releases/tag/<date>
```

版本清单来自该 release 的 `SHA256SUMS`：资产名为 `cpython-<ver>+<date>-<triple>-install_only.tar.gz`。`resolve_python` 只接受严格 `X.Y.Z`，预发布（如 `3.16.0a1`）被忽略。

## 分发地址

```
https://github.com/astral-sh/python-build-standalone/releases/download/<date>/cpython-<ver>+<date>-<triple>-install_only.tar.gz
```

| 宿主 | triple |
|------|--------|
| Windows x64 / arm64 | `x86_64-pc-windows-msvc` / `aarch64-pc-windows-msvc` |
| Linux x64 / arm64 | `x86_64-unknown-linux-gnu` / `aarch64-unknown-linux-gnu` |
| macOS x64 / arm64 | `x86_64-apple-darwin` / `aarch64-apple-darwin` |

## 版本解析

| 输入 | `resolve_python` 行为 |
|------|-----------------------|
| `latest` / `*` / 空 | 最新 release 中该 triple 的最高稳定版 |
| `3.12` | 最高 `3.12.x` |
| `3.12.15` | 必须出现在最新 release 中，否则报错 |
| 范围（如 `>=3.12`） | 最高匹配的稳定版；无匹配报错 |

版本只在**最新** release 内解析；上游不再随最新 release 发布的旧补丁版无法用精确版本安装。需要旧版本时人工下载并放入同一目录。

## 安装目录与布局

```
~/.mv/toolchain-manager/python/v<ver>/
```

`install_only` 归档只有一个顶层 `python/` 目录，安装时整体折叠到目标目录：Windows 解释器在根目录 `python.exe`，Unix 在 `bin/python3`。激活只把根目录（Windows）或 `bin`（Unix）前置到当前会话 `PATH`。

## 宿主完全没有 Python

`scripts/installer/bootstrap-python.sh` 是不依赖 Python 的纯 Shell 引导器，支持 `latest`、`X.Y`、`X.Y.Z`：

```bash
eval "$(bash "${SKILL_ROOT}/scripts/installer/bootstrap-python.sh" 3.12)"
```

它要求 `curl`、`tar` 以及 `sha256sum`/`shasum`/`openssl` 之一；自行解析最新 release 标签、核对 `SHA256SUMS`、解压到同一安装目录，并在 stdout 输出激活片段（诊断信息走 stderr）。安装完成后即可改用 `runtime_cli.py` 管理其余工具。Git Bash 的 `PATH` 不识别 `C:/...`，引导器输出前会转换为 `/c/...`。

## 校验

python-build-standalone 的发布资产统一由 release 的 `SHA256SUMS` 覆盖；`download._checksum_candidates` 对匹配该仓库的下载地址自动追加此候选，命中即校验，不匹配立即失败。
