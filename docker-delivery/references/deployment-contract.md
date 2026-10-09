# Docker 交付契约

目标：从同一份提交在 Docker 内使用语言工具链构建**一个**容器镜像，将该镜像部署到 dev，再将相同 Image ID 晋级到 prod。

## 项目输入

- `.dockerignore` 必须显式排除 `.git` 和 `.env*`，不得通过取反规则重新包含秘密文件。检查全部构建上下文，确保不含私钥。
- `.env.dev` 和 `.env.prod` 由本地准备，**不得被 Git 跟踪**；分别包含 `APP_ENV=dev` 或 `APP_ENV=prod`，以及可选的 `HOST_PORT`、`CONTAINER_PORT` 和应用设置。不打印 env 文件内容，Java 容器通过环境变量接收配置。
- 可提供 `Dockerfile.delivery`；否则选择随附的 Maven/Gradle/Node 静态前端多阶段模板。**目标机不执行构建**，只加载并运行不可变镜像。
- 可提供 `compose.delivery.yml`；否则使用引用 `FF_IMAGE` 且没有 `build:` 段的单服务模板。Node 静态前端在 env 文件中设置 `CONTAINER_PORT=80`。多服务架构需提供项目自己的 Compose 文件。

## 环境变量

| 变量 | 含义 |
| --- | --- |
| `FF_DEV_SSH` | 可选的 `user@devhost`；未设置时使用本机 Docker |
| `FF_PROD_SSH` | 用户指定的 `user@prodhost`；生产部署必填 |
| `FF_DEV_SSH_KEY`, `FF_PROD_SSH_KEY` | 可选的 SSH 私钥文件路径 |
| `FF_IMAGE_REPO` | 镜像仓库前缀 |
| `FF_BUILD_IMAGE`, `FF_RUNTIME_IMAGE` | 覆盖构建和运行基础镜像；建议固定摘要 |
| `FF_COMPOSE_FILE` | 项目自定义的 Compose 文件名 |
| `FF_HEALTH_URL` | 必须能**从目标机访问**的健康检查 URL，不要求客户端能够访问 |
| `FF_REQUIRE_DEV_PROOF` | 默认值为 1：生产晋级要求 dev 成功验证收据 |
| `FF_REQUIRE_SECURITY_SCAN` | 设置为 1 时，构建镜像必须经 Trivy 扫描；源码另用 Gitleaks 扫描 |

## 交付流程

1. `build dev APP` 检查 Docker 构建上下文，在 Docker 内从源码构建不可变的版本镜像，不要求宿主安装 Maven、Gradle、Java、Node 或 npm。
2. `deploy dev APP IMAGE` 预检配置；远端部署使用 `docker save/load` 传输镜像并检查 Image ID，然后启动 Compose、验证健康。仅通过 Docker 健康检查或 HTTP 探活的发布，才在本地 `~/.local/share/skills/receipts/APP/IMAGE_ID` 创建 dev 收据。
3. `deploy prod APP IMAGE --approve-prod` 要求用户明确授权、SSH 目标、目标镜像 ID 一致和真实健康探测，默认还要求本地 dev 验证收据。`FF_REQUIRE_DEV_PROOF=0` 仅用于评估风险后的显式应急处理，不属于常规流程。
4. 目标部署成功后，在 `~/.local/share/skills/APP/releases.tsv` 追加 TSV 发布记录，并保存当前与上一个镜像。部署失败时尝试恢复上一个已验证镜像。
5. `rollback prod APP --approve-prod` 加载可用的上一个镜像，验证并记录结果。**不回滚外部状态和数据库。**

## 已知限制

不内置镜像仓库、发布审批服务、产物签名、多架构 buildx、Helm/Kubernetes、数据库迁移或自动密钥管理。Vite 编译期端点需要改为运行时配置，才能跨环境晋级同一镜像。收据文件不是加密签名的来源证明；团队强制测试与策略应由 CI 执行。
