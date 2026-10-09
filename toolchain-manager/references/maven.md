# Apache Maven 官方源

## 分发地址

主站（仅保留当前与近期版本）：

```
https://dlcdn.apache.org/maven/maven-3/<ver>/binaries/apache-maven-<ver>-bin.<ext>
```

归档（全历史版本，主站下架后回退到此）：

```
https://archive.apache.org/dist/maven/maven-3/<ver>/binaries/apache-maven-<ver>-bin.<ext>
```

两者均为 Apache 官方基础设施，**不是第三方镜像**。`sources.maven_urls` 返回 `(primary, archive)`，`ensure` 先试 primary，失败再试 archive。

| 平台 | `<ext>` |
|------|---------|
| Windows | `zip` |
| macOS / Linux | `tar.gz` |

无 installer，符合硬约束。

## 版本列表

- `https://dlcdn.apache.org/maven/maven-3/` — HTML 目录列表，`sources._list_maven_versions` 用正则 `href="(\d+\.\d+\.\d+)/"` 解析。

## 版本解析

| 输入 | `resolve_maven` 行为 |
|------|----------------------|
| `3.9.6`（精确 X.Y.Z） | 直接返回，不发请求 |
| `3.9` | 取 3.9.x 最高 |
| `*` / `latest` / 空 | 取列表最高 |
| 范围（如 `>=3.8`） | 按约束匹配列表最高 |

## 安装目录约定

```
~/.local/sdks/maven/apache-maven-<ver>/
```

归档顶层目录名恰好是 `apache-maven-<ver>`，`install_portable` 直接折叠即可。

## 配置 settings.xml（可选）

安装本身不写 `~/.m2/settings.xml`。如需配置镜像仓库（如国内私服），由用户/项目自行管理，本 skill 不介入。
