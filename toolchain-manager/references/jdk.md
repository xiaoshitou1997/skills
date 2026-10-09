# JDK（Eclipse Temurin）官方源

仅使用 Eclipse Temurin（Adoptium 工作组维护的 OpenJDK 发行版），通过 Adoptium API 获取最新 GA 便携包。

## 最新 GA 二进制（按主版本）

```
https://api.adoptium.net/v3/binary/latest/<feature>/ga/<os>/<arch>/jdk/hotspot/normal/eclipse
```

- `<feature>`：主版本，如 `17`、`21`
- `<os>`：`windows` / `mac` / `linux`
- `<arch>`：`x64` / `aarch64`（macOS arm64 也用 `aarch64` 或 `arm64`，API 两者都接受；本 skill 对 mac 统一发 `arm64`）
- 端点会 302 重定向到 GitHub Release 资产，`urllib` 默认跟随重定向。

返回的归档：

| 平台 | 扩展名 |
|------|--------|
| Windows | `.zip` |
| macOS / Linux | `.tar.gz` |

均为便携归档，**无 installer**，符合本 skill 的硬约束。

## 安装目录约定

```
~/.local/sdks/jdk/temurin-<feature>/
```

按主版本命名。同一主版本下，API 永远返回最新 GA patch；重新 `ensure` 同一主版本时，若目录已存在则视为 `cached` 跳过。要强制升级到新 patch，先 `purge --tool jdk` 再 `ensure`。

解压后归档顶层目录形如 `jdk-17.0.9+9`，`install_portable` 会把它折叠到 `temurin-<feature>`。

## feature → GA 可用性

并非所有主版本都有 GA（例如某些版本只有 EA）。API 对无 GA 的主版本返回 404。本 skill 的 `ensure --jdk <feat>` 在此情况下会在 `actions` 里记录 `error`，继续处理其它工具。

## 可用版本查询（调试用）

- `https://api.adoptium.net/v3/info/available_releases` — 列出所有 feature 版本与当前 LTS。

## 为什么只用 Temurin

- license 清晰（GPL v2 + CE）。
- Windows 提供 portable zip（很多发行版只给 exe/msi installer）。
- Adoptium API 是官方、稳定、带重定向的元数据接口，免去自己拼版本号。

如未来需要 Corretto / Zulu 兜底，可在 `sources.jdk_url` 增加候选，但当前范围限定 Temurin。
