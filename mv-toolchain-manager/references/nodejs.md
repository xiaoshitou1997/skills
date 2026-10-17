# Node.js 官方源

## 版本索引

- `https://nodejs.org/dist/index.json`

JSON 数组，每项形如：

```json
{ "version": "v20.11.0", "lts": "Hydrogen", "security": false, ... }
```

`lts` 字段为 `false`（非 LTS）或代号字符串（LTS）。`sources.resolve_node` 据此优先挑选满足约束的 LTS 版本，再取最高版本号。

## 分发包命名

```
https://nodejs.org/dist/v<ver>/node-v<ver>-<plat>-<arch>.<ext>
```

| 平台 | `<plat>` | `<arch>` | `<ext>` |
|------|----------|----------|---------|
| Windows | `win` | `x64` / `arm64` | `zip` |
| macOS | `darwin` | `x64` / `arm64` | `tar.gz` |
| Linux | `linux` | `x64` / `arm64` | `tar.gz` |

Windows zip 解压后 `node.exe` 在归档根目录（不是 `bin/`），`activate._bin_for` 已对此特判。

## 安装目录约定

```
~/.mv/toolchain-manager/node/v<ver>/
```

`installed.list_installed` 按 `v<ver>` 目录名解析版本（去前导 `v`）。

## 约束解析示例

| 项目声明 | resolve_node 行为 |
|----------|-------------------|
| `.nvmrc` = `20.11.0` | 直接取 20.11.0 |
| `engines.node` = `>=18` | 取最高 LTS（如 20.x 或 22.x），忽略 17 及以下 |
| `engines.node` = `^20` | 取 20.x.x 最高 |
| `--node lts` | 取当前活跃 LTS 最高 |
| `--node 20` | 取 20.x.x 最高（视为 `>=20 <21`） |

## 完整性校验

Node.js 发行目录提供 `SHASUMS256.txt` 和签名文件。自带安装器下载后依次探测 `<url>.sha256`、`<url>.sha512`；对 `nodejs.org` 下载地址还探测同目录的 `SHASUMS256.txt`，找到匹配归档文件名的摘要即计算并比较。不匹配立即失败，不继续换源；未取得可用摘要时输出未验证警告，不能宣称完整性校验通过。命中已有安装缓存时不重新下载或校验。

镜像下载地址只探测同名 `.sha256`/`.sha512`，不自动使用 Node 官方清单；记录实际校验来源。安装器不验证发行签名；需要来源认证时，按发行方指南使用可信签名密钥验证，摘要相符不能替代签名认证。
