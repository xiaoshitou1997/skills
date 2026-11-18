# 凭证生成与注入

SKILL.md「Compose 编排」关键规则 10 的展开：分类型生成规则、.env 注入机制与轮换周期。基线：**凭据不进 Git**——真实值不入版本控制；生产/CI 环境用 secrets manager（Vault、Kubernetes Secrets、云厂商 Secrets Manager 等），本地开发环境 .env 可明文保存。跨栈凭据生命周期、泄露处置与数据保护政策见 mv-security-standards 的 credentials；本文件只定编排侧生成与注入。

## 分类型生成表

| 类型 | 强度 / 格式 | 生成命令 | 典型字段 |
|---|---|---|---|
| 数据库 / 中间件内部密码（service-to-service，无人输入） | 128-bit → 32-hex | `openssl rand -hex 16` | `MYSQL_PASSWORD`、`POSTGRES_PASSWORD`、redis requirepass |
| 管理端 / Web 登录密码（人输） | 128-bit → 32-hex | `openssl rand -hex 16` | `UI_PASSWORD`、`ADMIN_PASSWORD`、S3 secret key |
| 自研应用管理员口令哈希（env 存哈希，应用启动期 upsert 入库） | 口令按上行生成后 BCrypt cost ≥10 | `htpasswd -bnBC 12 "" "$(openssl rand -hex 16)" \| tr -d ':\n'` | `*_ADMIN_PASSWORD_HASH` |
| 签名 / 加密 / 派生密钥（机器用，无人输入） | 256-bit → 64-hex | `openssl rand -hex 32` | `*_MASTER_KEY`、`*_SALT_KEY`、`*_COOKIE_SECRET`、`JWT_SECRET` |
| 密码哈希 salt | 每条密码记录独立随机值，不作全局机密复用 | 由密码哈希库生成 | 哈希 salt |
| Web / 管理端访问 token | 256-bit → base64url(32B) 约 43 字符 | `openssl rand -base64 32 \| tr '+/' '-_' \| tr -d '=\n'` | `*_AUTH_TOKEN` |
| 网关 / 客户端 API key | `sk-` + base64url(32B) 约 46 字符 | `printf 'sk-'; openssl rand -base64 32 \| tr '+/' '-_' \| tr -d '=\n'` | `*_CLIENT_API_KEY`、gateway API key |
| 第三方 apiKey | provider 签发格式 | 由 provider 生成 | `OPENAI_API_KEY` 等 |

## 规则

- 账号 / 库名 = 栈名：`db_user = db_name` = 栈名（环境即栈，含环境后缀的栈名去连字符取字母数字形式——SQL 未加引号标识符不允许 `-`）；所有服务账号、数据库账号、控制台登录账号同规则；官方固定用户名例外（`elastic`/`admin`/`root` 一类按官方文档）。
- 不同账号及用途的凭据分别独立生成，禁止复用和使用示例值；数据库 root/管理员与业务账号使用不同密码，业务连接只使用最小权限账号。组件不支持账号分离时记录限制与风险，按项目安全评审处理。
- 客户端 API Key 一客户端/用途一 Key，带稳定 ID 与用途名称，可配过期、限额与撤销；不以 default/shared 名义跨客户端复用。
- 同一账号的多处引用保持一致（如 `MYSQL_PASSWORD` 与业务应用连接配置）；`MYSQL_ROOT_PASSWORD` 单独生成并限制为管理用途，不注入业务服务。
- 字符集偏好：内部生成值只用字母数字（hex 天然满足；base64url 输出含 `-`/`_` 时重新生成，重试数次即得）；避开引号转义、连接串拼接与命令行写入的坑。组件硬性要求复杂字符时以官方为准并在项目内登记。
- 外部 / 第三方凭据沿用 provider 格式，不强求内部强度规则。
- 栈重建（`down -v`）时按本表重新生成内部生成的凭据。

## 注入机制

- 所有敏感值放项目目录 `.env`，compose 经 `environment: KEY: ${KEY}` 插值注入（`cd {栈名} && docker compose up -d` 自动读取，无需声明 env_file）；容器内进程需读环境变量时同样插值提供。
- 版本化 compose/JSON/YAML 只保存 `${VAR}` 引用、空值或明确占位符，不保存真实值。
- 凭据类文件（`.env`、secrets）不入 Git：项目 `.gitignore` 排除 `**/.env` 与 secrets 目录；生产/CI 环境改用 secrets manager 下发。

## 轮换

- 第三方 API Key 与客户端 API Key：每 90 天。
- 数据库 / 中间件内部密码：每 180 天。
- 签名 / 加密 / 派生密钥：每 365 天。
- 兼任客户端 API key 的网关 master key：按客户端 API key 分级 90 天。
- 轮换前登记签发方、所有消费方、权限、配置版本、切换窗口和验证方式；确认服务端是否支持新旧凭据并存，以及旧凭据泄露时是否必须立即撤销。记录标识和版本，不记录凭据值。
- 支持并存时先在签发方创建同权限的新凭据，受控下发到 secrets manager、`.env` 或客户端配置，再逐个更新并重建或重载受影响服务；逐个验证新凭据的实际连接及业务操作，确认所有消费方完成后撤销旧凭据，再验证旧凭据失效。
- 不支持并存时先安排切换窗口，准备服务端修改、所有客户端同步更新和恢复方案；执行服务端更改后立即更新并重建或重载消费方，验证实际连接。仅更改环境变量或重建容器不代表数据库已有账号密码已修改，须按组件的账号管理机制操作。
- 验证失败时记录失败消费方与影响；旧凭据未泄露时停止撤销，若其仍有效，可按已验证方案恢复旧配置并验证。旧凭据已泄露或已撤销时不要重新启用，按安全事件流程处置；签名或加密密钥还须先验证历史数据解密与令牌兼容方案，不能仅按连接成功判定完成。

## 透明加密软件环境

检测到透明加密/防泄密软件时，先核验当前宿主可用的透明读写通道，按宿主说明生成 `.env` 与 SQL，不把命令行或编辑器一概认定为明文通道。文件经 SSH 上传后，在目标服务器确认内容可读并执行配置解析；解析可能展开凭据，只在受控会话核对，不将完整输出写入日志。不使用 WSL 旁路读取或拷贝目标文件。

本文只管编排侧凭证生成与注入；自研应用的配置与 Secret 分离基线归 mv-coding-standards，交付侧 env 预检（被跟踪 env 拦截）属本 skill 容器交付职责。
