# Gradle 官方源

## 当前版本接口

```
https://services.gradle.org/versions/current
```

JSON，形如：

```json
{ "version": "8.5", "buildTime": "...", "downloadUrl": "https://services.gradle.org/distributions/gradle-8.5-bin.zip", ... }
```

`sources.resolve_gradle` 在无约束或约束命中最新时直接读 `version` 字段。

## 分发地址

```
https://services.gradle.org/distributions/gradle-<ver>-bin.zip
```

- 跨平台统一为 `.zip`（Gradle 自带 native 平台检测，无需按 OS 分包）。
- `-bin.zip` 是只含二进制的最小包；`-all.zip` 含源码与文档，本 skill 不用。

旧版本同样在 `services.gradle.org/distributions/` 下长期保留；`resolve_gradle` 在约束不匹配 latest 时会抓取该目录列表正则解析。

## 版本解析

| 输入 | `resolve_gradle` 行为 |
|------|-----------------------|
| `8.5`（精确 X.Y 或 X.Y.Z） | 直接返回，不发请求（X.Y 时也直接透传，因为分发页按完整版本号命名） |
| `*` / `latest` / 空 | 读 `/versions/current` |
| 范围（如 `>=8`） | latest 不满足则抓 distributions 页匹配 |

> 注：Gradle 的"精确"判断只对 `X.Y.Z` 跳过网络；`8.5` 这种 X.Y 会走一次 `/versions/current` 核对（成本低）。

## 安装目录约定

```
~/.local/sdks/gradle/gradle-<ver>/
```

归档顶层目录名恰好是 `gradle-<ver>`，`install_portable` 直接折叠。

## Gradle Wrapper 协同

若项目含 `gradle/wrapper/gradle-wrapper.properties`，`detect` 会解析出 wrapper 锁定的 Gradle 版本，`ensure` 据此安装同版本，使 `gradle` 与 `./gradlew` 行为一致。已装好 `gradle-<ver>` 后，`gradlew` 也会复用 `~/.gradle/wrapper/dists` 的缓存，互不冲突。
