# 凭证生成与注入

mv-orchestration-standards 关键规则 10 的展开：分类型生成规则、.env 注入机制与轮换周期。基线：**凭据不进 Git**——真实值不入版本控制；生产/CI 环境用 secrets manager（Vault、Kubernetes Secrets、云厂商 Secrets Manager 等），本地开发环境 .env 可明文保存。跨栈凭据生命周期、泄露处置与数据保护政策见 mv-security-standards 的 credentials；本文件只定编排侧生成与注入。

## 分类型生成表

| 类型 | 强度 / 格式 | 生成命令 | 典型字段 |
|---|---|---|---|
| 数据库 / 中间件内部密码（service-to-service，无人输入） | 128-bit → 32-hex | `openssl rand -hex 16` | `MYSQL_PASSWORD`、`POSTGRES_PASSWORD`、redis requirepass |
| 管理端 / Web 登录密码（人输） | 128-bit → 32-hex | `openssl rand -hex 16` | `UI_PASSWORD`、`ADMIN_PASSWORD`、S3 secret key |
| 签名 / 加密 / 派生密钥（机器用，无人输入） | 256-bit → 64-hex | `openssl rand -hex 32` | `*_MASTER_KEY`、`*_SALT_KEY`、`*_COOKIE_SECRET`、`JWT_SECRET` |
| 密码哈希 salt | 每条密码记录独立随机值，不作全局机密复用 | 由密码哈希库生成 | 哈希 salt |
| Web / 管理端访问 token | 256-bit → base64url(32B) 约 43 字符 | `openssl rand -base64 32 \| tr '+/' '-_' \| tr -d '=\n'` | `*_AUTH_TOKEN` |
| 网关 / 客户端 API key | `sk-` + base64url(32B) 约 46 字符 | `printf 'sk-'; openssl rand -base64 32 \| tr '+/' '-_' \| tr -d '=\n'` | `*_CLIENT_API_KEY`、gateway API key |
| 第三方 apiKey | provider 签发格式 | 由 provider 生成 | `OPENAI_API_KEY` 等 |

## 规则

- 账号 / 库名 = 栈名：`db_user = db_name` = 栈名（环境即栈，含环境后缀的栈名去连字符取字母数字形式——SQL 未加引号标识符不允许 `-`）；所有服务账号、数据库账号、控制台登录账号同规则；官方固定用户名例外（`elastic`/`admin`/`root` 一类按官方文档）。
- 每项独立生成，禁复用、禁与示例值相同；`*_ROOT_PASSWORD` 允许与对应业务账号密码同值复用，视为同一凭据多处引用。
- 客户端 API Key 一客户端/用途一 Key，带稳定 ID 与用途名称，可配过期、限额与撤销；不以 default/shared 名义跨客户端复用。
- 多处引用同一密码必须一致（如 `MYSQL_ROOT_PASSWORD`/`MYSQL_PASSWORD`/应用连接串三处同值）。
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
- 轮换时更新 `.env`、客户端本地凭据文件并重建受影响栈。

## 透明加密软件环境

本机启用透明加密/防泄密软件时，命令行工具（curl/重定向/sed）写入的 `.env`、建表 SQL 等文件会被异步加密，容器与 WSL 侧读到密文：此类文件一律用编辑器手写，写入后经容器/WSL 侧读取或 `docker compose config` 实测确认可读。

本文只管编排侧凭证生成与注入；自研应用的配置与 Secret 分离基线归 mv-backend-standards，交付侧 env 预检（被跟踪 env 拦截）归 mv-container-deploy。
