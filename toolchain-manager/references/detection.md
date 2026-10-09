# 版本检测来源与优先级

本文描述 `scripts/installer/detect.py` 的便携安装器检测逻辑。主入口 `scripts/detect.py` 是只读声明清单，保留多个来源供 agent 判断，不具有相同返回结构或优先级。两者都不能完整解析父 POM、动态 Gradle 配置或所有版本管理器语义；遇到冲突时以项目有效配置与 wrapper 为准，不静默选择一个来源。

每个工具按从高到低的优先级扫描项目文件，命中即停。所有检测返回 `{source, constraint}`，`constraint` 为字符串。

## Node.js

| 优先级 | 来源 | 解析 |
|--------|------|------|
| 1 | `.nvmrc` | 取首个 token，去前导 `v` |
| 2 | `.node-version` | 同上 |
| 3 | `package.json` → `engines.node` | npm 范围原样（`>=18`、`^20`、`20.11.0`、`lts`） |
| 4 | `.tool-versions` | `nodejs <ver>` 行 |

约束解析支持：`*`、`latest`、`lts`、精确 `X.Y.Z`、主版本 `X`（视为 `>=X <X+1`）、`^`、`~`、`>=`/`<=`/`>`/`<`、空格分隔的 AND、`||` 分隔的 OR。匹配时优先返回 LTS 版本，再取最高版本号。

## JDK

| 优先级 | 来源 | 解析 |
|----|------|------|
| 1 | `.java-version` | 取首个数字为主版本 |
| 2 | `.sdkmanrc` | `java=17.0.9.tem` 取主版本 |
| 3 | `pom.xml` | 依次查 `maven.compiler.release` → `maven.compiler.source` → `maven.compiler.target` → `java.version`，取数字（`1.8` 视为 `8`） |
| 4 | `build.gradle` / `build.gradle.kts` | 匹配 `languageVersion = JavaLanguageVersion.of(N)` → `sourceCompatibility = [JavaVersion.VERSION_]N` → `targetCompatibility ...` |
| 5 | `.tool-versions` | `java temurin-17...` 取数字 |

JDK 一律按**主版本（feature version）**匹配，安装时取该主版本下的最新 GA patch（由 Adoptium API 决定）。

## Maven

| 优先级 | 来源 | 解析 |
|----|------|------|
| 1 | `.mvn/wrapper/maven-wrapper.properties` | 正则 `apache-maven-([\d.]+)` |
| 2 | `pom.xml` → `<prerequisites><maven>` | 旧式最低版本要求 |

无 wrapper 且未显式指定时，取 `dlcdn.apache.org/maven/maven-3/` 列出的最新稳定版。

## Gradle

| 优先级 | 来源 | 解析 |
|----|------|------|
| 1 | `gradle/wrapper/gradle-wrapper.properties` | 正则 `gradle-([\d.]+)-bin` |

无 wrapper 且未显式指定时，取 `services.gradle.org/versions/current` 的 `version` 字段。

## 同时存在多来源

`detect_all` 对每个工具独立返回第一个命中的来源；CLI `ensure` 会优先采纳命令行显式参数（`--jdk` / `--node` / ...），其次采纳项目扫描结果。

## 探测系统已装版本

`installed --system` 会额外调用 PATH 上的 `java -version` / `mvn --version` / `gradle --version` / `node --version` 解析版本字符串，用于判断"是否其实不用装"。注意：`ensure` 不会自动复用系统版本（避免与项目要求冲突），仅 `list --system` 提供信息供决策。
