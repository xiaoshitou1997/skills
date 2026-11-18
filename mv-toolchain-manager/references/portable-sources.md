# 便携工具链官方源

自带便携安装器（`scripts/installer/runtime_cli.py`）的下载源、版本解析与安装目录约定，覆盖 JDK、Node.js、Maven、Gradle、Python 与其余包管理器；镜像启用方式见 [mirrors](mirrors.md)，检测优先级见 [detection](detection.md)。安装器下载后自动核对发行方校验和，命中即校验、不匹配立即失败；未取得可用校验和时如实提示未验证，不把下载成功当作校验通过。与项目已确立基线冲突时以项目为准。

## JDK（仅 Eclipse Temurin）

仅使用 Eclipse Temurin（Adoptium 工作组维护的 OpenJDK 发行版），经 Adoptium assets API 解析指定主版本的最新 GA：

```
https://api.adoptium.net/v3/assets/latest/<feature>/hotspot?architecture=<arch>&image_type=jdk&os=<os>&vendor=eclipse
```

- `<os>`：`windows`/`mac`/`linux`；`<arch>`：`x64`/`aarch64`（本机 `arm64` 统一映射为 `aarch64`）。
- 归档链接取首个资产的 `binary.package.link` 与 `name`，核对一致且扩展名符合平台后再交下载器 probe、下载与摘要校验；Windows 为 `.zip`，macOS/Linux 为 `.tar.gz`，均为便携归档、无 installer。
- 官方归档链接通常指向 GitHub Release，下载跟随重定向；不把无扩展名 API 地址或短期签名跳转地址作为归档候选。
- 可用版本查询（调试用）：`https://api.adoptium.net/v3/info/available_releases`。
- 安装目录：`~/.mv/toolchain-manager/jdk/temurin-<feature>/`；API 永远返回该主版本最新 GA patch，目录已存在视为 `cached` 跳过，强制升级 patch 先 `purge --tool jdk` 再 `ensure`。
- 只用 Temurin 的理由：license 清晰（GPLv2 + CE）、Windows 提供 portable zip（多数发行版只给 installer）、Adoptium API 官方稳定；范围外发行版需要时在 `sources.jdk_url` 增加候选。

## Node.js

- 版本索引：`https://nodejs.org/dist/index.json`；`lts` 字段为 `false`（非 LTS）或代号字符串，优先挑选满足约束的 LTS，再取最高版本号。
- 分发包：`https://nodejs.org/dist/v<ver>/node-v<ver>-<plat>-<arch>.<ext>`（Windows `win`+`zip`、macOS `darwin`+`tar.gz`、Linux `linux`+`tar.gz`；arch `x64`/`arm64`）。
- Windows zip 解压后 `node.exe` 在归档根目录（不是 `bin/`），激活逻辑已对此特判。
- 校验：依次探测 `<url>.sha256`/`<url>.sha512`，对 nodejs.org 下载地址再探测同目录 `SHASUMS256.txt`，按归档文件名匹配摘要；镜像地址只探测同名校验和并记录实际校验来源。不匹配立即失败，不换源继续；安装器不验证发行签名，需来源认证时按发行方指南验证签名。
- 安装目录：`~/.mv/toolchain-manager/node/v<ver>/`（按目录名去前导 `v` 解析已装版本）。

## Maven

- 主站（仅当前与近期版本）：`https://dlcdn.apache.org/maven/maven-3/<ver>/binaries/apache-maven-<ver>-bin.<ext>`；归档（全历史，主站下架后回退）：`https://archive.apache.org/dist/maven/maven-3/<ver>/binaries/apache-maven-<ver>-bin.<ext>`。两者均为 Apache 官方基础设施而非第三方镜像；未启用镜像时按 `[primary, archive]` 顺序 probe 后下载。
- 版本列表：`https://dlcdn.apache.org/maven/maven-3/` HTML 目录，按 `href="(\d+\.\d+\.\d+)/"` 解析；精确 `X.Y.Z` 免联网解析，`3.9` 取 3.9.x 最高，`*`/`latest`/空取列表最高，范围按约束匹配；列表获取失败或无匹配时明确报错，不把原始范围字符串当作版本下载。
- Windows `.zip`、其余 `.tar.gz`，无 installer，符合硬约束。
- 安装目录：`~/.mv/toolchain-manager/maven/apache-maven-<ver>/`（归档顶层目录名恰为 `apache-maven-<ver>`，直接折叠）。
- `~/.m2/settings.xml`（镜像仓库、私服）由用户/项目管理，本 skill 不介入。

## Gradle

- 当前版本接口：`https://services.gradle.org/versions/current`（取 JSON `version` 字段）；分发：`https://services.gradle.org/distributions/gradle-<ver>-bin.zip`，跨平台统一 `.zip`，用 `-bin` 不用 `-all`（`-all` 含源码与文档）。
- 精确 `X.Y`/`X.Y.Z` 免联网解析；`*`/`latest`/空读 current 接口；范围约束 latest 不满足或接口不可用时抓 distributions 目录列表取最高匹配，无匹配或解析失败时报错，不回退到不匹配的 latest。
- 安装目录：`~/.mv/toolchain-manager/gradle/gradle-<ver>/`（顶层目录名恰为 `gradle-<ver>`，直接折叠）。
- Wrapper 协同：`gradle-wrapper.properties` 锁定的版本由 detect 解析、ensure 据此准备同版本便携安装；执行构建仍优先 `./gradlew`。便携安装不自动填充 Wrapper 的 `dists` 缓存，首次 Wrapper 构建可能仍需下载其分发包。

## Python（python-build-standalone）

- 使用场景：安装器依次读取 `.python-version`、`.tool-versions`、`.mise.toml` 与 `pyproject.toml` 的 `requires-python`；不替代项目已有的解释器、虚拟环境、uv 或 conda，项目现有方案可用时直接使用。本 skill 与 `mv-delivery-standards` 的只读诊断脚本（`doctor.py` 等）同样复用该便携 Python。
- 最新 release 为日期标签：`https://github.com/astral-sh/python-build-standalone/releases/latest`；资产名 `cpython-<ver>+<date>-<triple>-install_only.tar.gz`，版本清单来自该 release 的 `SHA256SUMS`。
- triple：Windows `x86_64-pc-windows-msvc`/`aarch64-pc-windows-msvc`，Linux `x86_64-unknown-linux-gnu`/`aarch64-unknown-linux-gnu`，macOS `x86_64-apple-darwin`/`aarch64-apple-darwin`。
- 只接受严格 `X.Y.Z`，预发布忽略；版本只在最新 release 内解析（`3.12` 取最高 3.12.x，精确版必须出现在最新 release 否则报错）；上游不再随最新 release 发布的旧补丁版需人工下载放入同一目录。
- 安装目录：`~/.mv/toolchain-manager/python/v<ver>/`；`install_only` 归档顶层 `python/` 整体折叠，Windows 解释器在根目录 `python.exe`、Unix 在 `bin/python3`，激活只前置根目录（Windows）或 `bin`（Unix）。
- 宿主完全没有 Python 时用纯 Shell 引导器 `scripts/installer/bootstrap-python.sh`：要求 `curl`、`tar` 与 `sha256sum`/`shasum`/`openssl` 之一；自行解析最新 release、核对 `SHA256SUMS`、解压到同一目录，stdout 输出激活片段（诊断走 stderr）；Git Bash 的 PATH 不识别 `C:/...`，输出前转换为 `/c/...`。

## 其余包管理器

- npm：随选定 Node 归档提供，只验证内置版本，不单独下载。
- pnpm 与非项目内 Yarn：必须有 `packageManager`（或命令行）给出的精确版本，取 npm registry 不可变 tarball 并按该版本 `dist.integrity` 的 SRI 摘要校验；Yarn 2+ 使用 `@yarnpkg/cli-dist`，不依赖 Node 是否内置 Corepack。
- uv：Astral 官方 release 归档，校验和为 `sha256sum.txt`。

本文只描述便携安装的来源与解析约定；安装器行为以 `scripts/installer/` 实现为准，镜像源与网络策略见 [mirrors](mirrors.md)。
