# JDK（Eclipse Temurin）官方源

仅使用 Eclipse Temurin（Adoptium 工作组维护的 OpenJDK 发行版），通过 Adoptium assets API 解析指定主版本的最新 GA 便携归档；下载候选使用元数据返回的真实归档链接。

## 最新 GA 二进制（按主版本）

```
https://api.adoptium.net/v3/assets/latest/<feature>/hotspot?architecture=<arch>&image_type=jdk&os=<os>&vendor=eclipse
```

- `<feature>`：主版本，如 `17`、`21`
- `<os>`：`windows` / `mac` / `linux`
- `<arch>`：`x64` / `aarch64`（本机 `arm64` 统一映射为 `aarch64`）。
- `sources.jdk_url` 从首个资产的 `binary.package.link` 与 `name` 取得真实归档链接和文件名，核对两者一致且扩展名符合平台，再交下载器 probe、下载与摘要校验；元数据不可用或不合法时明确失败。
- 官方归档链接通常指向 GitHub Release；下载时 `urllib` 跟随重定向，不把无扩展名 API 或短期签名跳转地址作为归档候选。

返回的归档：

| 平台 | 扩展名 |
|------|--------|
| Windows | `.zip` |
| macOS / Linux | `.tar.gz` |

均为便携归档，**无 installer**，符合本 skill 的硬约束。

## 安装目录约定

```
~/.mv/toolchain-manager/jdk/temurin-<feature>/
```

按主版本命名。同一主版本下，API 永远返回最新 GA patch；重新 `ensure` 同一主版本时，若目录已存在则视为 `cached` 跳过。要强制升级到新 patch，先 `purge --tool jdk` 再 `ensure`。

解压后归档顶层目录形如 `jdk-17.0.9+9`，`install_portable` 会把它折叠到 `temurin-<feature>`。

## feature → GA 可用性

并非所有主版本都有可用 GA 资产。API 返回失败、空资产或非法归档元数据时，`ensure --jdk <feat>` 在 `actions` 里记录 `error`，继续处理其他工具；任一工具失败会使整体 ensure 非零退出。

## 可用版本查询（调试用）

- `https://api.adoptium.net/v3/info/available_releases` — 列出所有 feature 版本与当前 LTS。

## 为什么只用 Temurin

- license 清晰（GPL v2 + CE）。
- Windows 提供 portable zip（很多发行版只给 exe/msi installer）。
- Adoptium API 是官方、稳定、带重定向的元数据接口，免去自己拼版本号。

如未来需要 Corretto / Zulu 兜底，可在 `sources.jdk_url` 增加候选，但当前范围限定 Temurin。
