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
~/.local/sdks/node/v<ver>/
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

Node.js 发行目录提供 `SHASUMS256.txt` 和签名文件。文件摘要验证应计算归档的 SHA-256，并与清单中对应文件名的值比较；签名验证则需要可信的发行签名密钥，不能简单比较 `.sig` 文件。当前自带安装器未强制执行上述校验，URL 可达及归档扩展名验证不等于内容完整性或来源认证。需要验证时，按发行方当前指南校验后再使用产物。
