# Docker 交付契约

目标：加载运行 `mv-image-build` 从同一份提交构建的**一个**不可变镜像，先部署到 dev 验证健康，再以相同 Image ID 晋级到 prod。本 skill 不构建镜像；镜像身份以 `mv-image-build` 输出的 `IMAGE=<repo>:<tag>` 与 `IMAGE_ID` 为准。

## 项目输入

- `.env.dev` 和 `.env.prod` 由本地准备，**不得被 Git 跟踪**；分别包含 `APP_ENV=dev` 或 `APP_ENV=prod`，以及可选的 `HOST_PORT`、`CONTAINER_PORT` 和应用设置。不打印 env 文件内容，Java 容器通过环境变量接收配置。
- 可提供 `compose.delivery.yml`；否则使用引用 `FF_IMAGE` 且没有 `build:` 段的单服务模板（`templates/compose.delivery.yml`）。多服务架构需提供项目自己的 Compose 文件；Node 静态前端在 env 文件中设置 `CONTAINER_PORT=80`。
- **目标机不执行构建**，只加载并运行不可变镜像；`docker compose` 一律 `--no-build --pull never`。
- 建议应用带 Docker HEALTHCHECK；无 HEALTHCHECK 时用 `FF_HEALTH_URL` 提供目标机可达的探活地址，否则 dev 不会产生可晋级收据、prod 直接拒绝部署。

## 环境变量

| 变量 | 含义 |
| --- | --- |
| `FF_DEV_SSH` | 可选的 `user@devhost`；未设置时使用本机 WSL Docker |
| `FF_PROD_SSH` | 用户指定的 `user@prodhost`；生产部署必填 |
| `FF_DEV_SSH_KEY`, `FF_PROD_SSH_KEY` | 可选的 SSH 私钥文件路径 |
| `FF_COMPOSE_FILE` | 项目自定义的 Compose 文件名 |
| `FF_HEALTH_URL` | 必须能**从目标机访问**的健康检查 URL，不要求客户端能够访问 |
| `FF_REQUIRE_DEV_PROOF` | 默认值为 1：生产晋级要求 dev 成功验证收据 |

## 交付流程

1. `deploy dev APP IMAGE` 预检配置（`deploy-preflight.sh` 与脚本内 `project_checks`/`env_checks`），检查镜像在本地存在；远端部署使用 `docker save/load` 传输镜像并核对传输前后 Image ID，然后启动 Compose、验证健康。仅通过 Docker 健康检查或 HTTP 探活（`VERIFIED_HEALTH=strong`）的发布，才在 `~/.local/share/skills/receipts/APP/IMAGE_ID` 创建 dev 收据（Windows 桥接模式下收据在 WSL 侧用户目录）。
2. `deploy prod APP IMAGE --approve-prod` 要求用户明确授权、SSH 目标、目标镜像 ID 一致和真实健康探测，默认还要求本地 dev 验证收据。`FF_REQUIRE_DEV_PROOF=0` 仅用于评估风险后的显式应急处理，不属于常规流程。
3. 目标部署成功后，在 `~/.local/share/skills/APP/releases.tsv` 追加 TSV 发布记录，并保存当前与上一个镜像。部署失败时尝试恢复上一个已验证镜像。
4. `rollback prod APP --approve-prod` 加载可用的上一个镜像，验证并记录结果。**不回滚外部状态和数据库。**

## 已知限制

不内置镜像仓库、发布审批服务、产物签名、多架构分发、Helm/Kubernetes、数据库迁移或自动密钥管理。当前编排器为 Docker Compose；swarm/k8s/k3s 等编排器为后续扩展，接入时按"传输不变、apply 与回滚机制按编排器差异放 references"扩展，不改变收据与晋级门禁。收据文件不是加密签名的来源证明；团队强制测试与策略应由 CI 执行。
