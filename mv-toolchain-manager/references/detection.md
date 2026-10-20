# 版本检测来源与优先级

本文描述 `scripts/installer/detect.py` 的便携安装器检测逻辑。主入口 `scripts/detect.py` 是只读声明清单，保留多个来源供 agent 判断，不具有相同返回结构或优先级。两者都不能完整解析父 POM、动态 Gradle 配置或所有版本管理器语义；遇到冲突时以项目有效配置与 wrapper 为准，不静默选择一个来源。

每个工具按从高到低的优先级扫描项目文件，命中即停。普通运行时检测返回 `{source, constraint}`；wrapper 与项目内 Yarn 分发还会标记 `project_managed: true`，因此 `ensure --project` 只报告其状态，不另装全局副本。

## Node.js

| 优先级 | 来源 | 解析 |
|--------|------|------|
| 1 | `.nvmrc` | 取首个 token，去前导 `v` |
| 2 | `.node-version` | 同上 |
| 3 | `package.json` → `engines.node` | npm 范围原样（`>=18`、`^20`、`20.11.0`、`lts`） |
| 4 | `.tool-versions` | `nodejs <ver>` 行 |
| 5 | `.mise.toml` | `[tools] node = "<ver>"` |

约束解析支持：`*`、`latest`、`lts`、精确 `X.Y.Z`、主版本 `X`（视为 `>=X <X+1`）、`^`、`~`、`>=`/`<=`/`>`/`<`、空格分隔的 AND、`||` 分隔的 OR。匹配时优先返回 LTS 版本，再取最高版本号。

## JDK

| 优先级 | 来源 | 解析 |
|----|------|------|
| 1 | `.java-version` | 取首个数字为主版本 |
| 2 | `.sdkmanrc` | `java=17.0.9.tem` 取主版本 |
| 3 | `pom.xml` | 依次查 `maven.compiler.release` → `maven.compiler.source` → `maven.compiler.target` → `java.version`，取数字（`1.8` 视为 `8`） |
| 4 | `build.gradle` / `build.gradle.kts` | 匹配 `languageVersion = JavaLanguageVersion.of(N)` → `sourceCompatibility = [JavaVersion.VERSION_]N` → `targetCompatibility ...` |
| 5 | `.tool-versions` / `.mise.toml` | `java` 声明取主版本 |

JDK 一律按**主版本（feature version）**匹配，安装时取该主版本下的最新 GA patch（由 Adoptium API 决定）。

## Maven 与 Gradle

| 工具 | 优先级 | 来源 | 行为 |
|------|--------|------|------|
| Maven | 1 | `.mvn/wrapper/maven-wrapper.properties` | 识别 `apache-maven-<version>`，报告为项目托管；不另装 Maven |
| Maven | 2 | `pom.xml` → `<prerequisites><maven>` | 无 wrapper 时作为便携 Maven 约束 |
| Gradle | 1 | `gradle/wrapper/gradle-wrapper.properties` | 识别 `gradle-<version>-bin`，报告为项目托管；不另装 Gradle |

显式 `--maven` 或 `--gradle` 始终表示需要便携副本，并覆盖项目扫描结果。

## Python 与 uv

| 工具 | 优先级 | 来源 | 解析 |
|------|--------|------|------|
| Python | 1 | `.python-version` | 首个 token，去前导 `v` |
| Python | 2 | `.tool-versions` / `.mise.toml` | `python` 声明 |
| Python | 3 | `pyproject.toml` → `[project].requires-python` | Python 版本范围 |
| uv | 1 | `.tool-versions` / `.mise.toml` | `uv` 声明 |
| uv | 2 | `pyproject.toml` 的 `[tool.uv]` | 使用最新稳定 uv |
| uv | 3 | `uv.lock` | 使用最新稳定 uv |

Python 是项目运行时的一部分，也用于运行本 skill 与 `mv-image-build` 的辅助脚本。其便携来源、布局和启动约束见 [python](python.md)。

## npm、pnpm 与 Yarn

解析顺序是：

1. 提交到项目的 `.yarn/releases/yarn-*.cjs` 或 `.yarnrc.yml` 的有效 `yarnPath`。这是可执行项目状态，优先于 `packageManager`，只报告为项目托管。
2. `package.json#packageManager`：接受 `npm@X.Y.Z`、`pnpm@X.Y.Z`、`yarn@X.Y.Z`。它是非项目内分发时唯一的自动准备版本来源。
3. `pnpm-lock.yaml` 推断需要 pnpm，但没有版本时不会下载安装；请补 `packageManager` 或传递 `--pnpm X.Y.Z`。
4. `package-lock.json` 推断 npm；npm 始终随所选 Node 归档提供，只校验内置版本。
5. 裸 `yarn.lock` 返回明确诊断，绝不猜测 Yarn Classic 或现代 Yarn。

pnpm 与非项目内的 Yarn 必须为精确 `X.Y.Z`。Yarn 2+ 使用 `@yarnpkg/cli-dist`，Yarn Classic 使用 `yarn`；实现不依赖 Node 是否随附 Corepack。

## 同时存在多来源

`detect_all` 对每个工具独立返回第一个命中的来源；CLI `ensure` 会优先采纳命令行显式参数，其次采纳项目扫描结果。wrapper 和项目内 Yarn 不会被显式版本参数以外的缓存副本替代。

## 探测系统已装版本

`installed --system` 会额外调用 PATH 上的 `java`、`mvn`、`gradle`、`node`、`npm`、`pnpm`、`yarn`、`uv` 与 Python 命令解析版本字符串，用于判断“是否其实不用装”。注意：`ensure` 不会自动复用系统版本（避免与项目要求冲突），仅 `list --system` 提供信息供决策。
