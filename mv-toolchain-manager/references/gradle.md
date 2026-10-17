# Gradle 官方源

## 当前版本接口

```
https://services.gradle.org/versions/current
```

JSON，形如：

```json
{ "version": "8.5", "buildTime": "...", "downloadUrl": "https://services.gradle.org/distributions/gradle-8.5-bin.zip", ... }
```

`sources.resolve_gradle` 对精确 `X.Y` / `X.Y.Z` 直接返回、不查询索引；无约束或 `latest` 时读取 `version` 字段，范围约束仅在最新版本满足时返回该版本。

## 分发地址

```
https://services.gradle.org/distributions/gradle-<ver>-bin.zip
```

- 跨平台统一为 `.zip`（Gradle 自带 native 平台检测，无需按 OS 分包）。
- `-bin.zip` 是只含二进制的最小包；`-all.zip` 含源码与文档，本 skill 不用。

旧版本同样在 `services.gradle.org/distributions/` 下长期保留；范围约束不匹配最新版本或 current 接口不可用时，`resolve_gradle` 抓取该目录列表并选择最高匹配版本。

## 版本解析

| 输入 | `resolve_gradle` 行为 |
|------|-----------------------|
| `8.5` / `8.5.1`（精确 X.Y / X.Y.Z） | 原样返回，解析阶段不发请求 |
| `*` / `latest` / 空 | 读 `/versions/current`，无法取得版本时报错 |
| 范围（如 `>=8`） | latest 满足则返回，否则抓 distributions 页取最高匹配；无匹配或解析失败时报错 |

免联网仅指精确版本的解析阶段，缺少归档时安装仍需 probe 与下载。范围解析不回退到不匹配的 latest 或原始范围字符串。

## 安装目录约定

```
~/.mv/toolchain-manager/gradle/gradle-<ver>/
```

归档顶层目录名恰好是 `gradle-<ver>`，`install_portable` 直接折叠。

## Gradle Wrapper 协同

若项目含 `gradle/wrapper/gradle-wrapper.properties`，`detect` 会解析出 Wrapper 锁定的 Gradle 版本，`ensure` 据此准备同版本便携安装；执行构建仍优先使用 `./gradlew`。便携安装目录与 Wrapper 的 `GRADLE_USER_HOME/wrapper/dists` 缓存相互独立，安装便携 Gradle 不会自动填充 Wrapper 缓存，首次 Wrapper 构建可能仍需下载其分发包。
