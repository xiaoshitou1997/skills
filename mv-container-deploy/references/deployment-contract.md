# Docker 交付契约

目标：加载运行 `mv-image-build` 从同一份提交构建的**一个**不可变镜像，先部署到 dev 验证健康，再以相同 Image ID 晋级到 prod。本 skill 不构建镜像；镜像身份以 `mv-image-build` 输出的 `IMAGE=<repo>:<tag>` 与 `IMAGE_ID` 为准。

## 项目输入

- `.env.dev` 和 `.env.prod` 由本地准备，**不得被 Git 跟踪**；分别包含 `APP_ENV=dev` 或 `APP_ENV=prod`，以及可选的 `HOST_PORT`、`CONTAINER_PORT` 和应用设置。不打印 env 文件内容，Java 容器通过环境变量接收配置。
- 部署范围默认为系统完整组件集：Compose 文件声明全部业务服务、其依赖的基础设施（MySQL、Redis 等，固定版本 Tag，不用 `latest`）及配套配置与初始化脚本，基础设施镜像与业务镜像一样须在目标机就位；多服务系统的 `compose.delivery.yml` 由项目提供。
- 用户明确说明依赖关系（如数据库使用现成实例）时，部署范围按声明缩减，并在发布记录注明范围与豁免项；仅单服务且无基础设施依赖时使用单服务模板（`templates/compose.delivery.yml`，引用 `FF_IMAGE`、没有 `build:` 段）。Node 静态前端在 env 文件中设置 `CONTAINER_PORT=80`。
- **部署身份按独立生命周期划定**：独立升级、独立回滚、独立数据卷、独立端口与环境配置的一组组件是一个部署身份，对应一个 APP 名与一条完整交付链（各自的 `.env.<env>`、`compose.delivery.yml`、`releases.tsv`、收据与晋级记录）。同一系统需要多份完全独立部署（如 `order` 与 `order-sandbox`）时按多个部署身份交付，各自携带自己的基础设施容器；共享某项基础设施即不再独立，按上一条声明依赖。同一部署的横向扩容不是新身份：在同一个 Compose 项目内用 replicas 扩容，不另起部署身份；接入 swarm/k8s 后对应不同 stack 名或不同 namespace。
- **目标机不执行构建**，只加载并运行不可变镜像；`docker compose` 一律 `--no-build --pull never`。
- 建议应用带 Docker HEALTHCHECK；无 HEALTHCHECK 时用 `FF_HEALTH_URL` 提供目标机可达的探活地址，否则 dev 不会产生可晋级收据、prod 直接拒绝部署。

## 环境变量

环境变量（`FF_DEV_SSH`、`FF_PROD_SSH`、`FF_HEALTH_URL`、`FF_REQUIRE_DEV_PROOF`、`FF_READY_TIMEOUT` 等）的语义与默认值以 [配置参考](configuration.md) 的表格为单一事实源，本契约不再重复维护。

## 交付流程

1. `deploy dev APP IMAGE` 预检配置（`deploy-preflight.sh` 与脚本内 `project_checks`/`env_checks`），检查镜像在本地存在；远端部署使用 `docker save/load` 传输镜像并核对传输前后 Image ID，然后启动 Compose、验证健康。仅通过 Docker 健康检查或 HTTP 探活（`VERIFIED_HEALTH=strong`）的发布，才在 `~/.mv/container-deploy/receipts/APP/IMAGE_ID` 创建 dev 收据（文件名为 Image ID、冒号替换为 `-`，规避 Windows 备用数据流语义；Windows 桥接模式下收据在 WSL 侧用户目录）。
2. `deploy prod APP IMAGE --approve-prod` 要求用户明确授权、SSH 目标、目标镜像 ID 一致和真实健康探测，默认还要求本地 dev 验证收据。`FF_REQUIRE_DEV_PROOF=0` 仅用于评估风险后的显式应急处理，不属于常规流程。
3. 目标部署成功后，在 `~/.mv/container-deploy/APP/releases.tsv` 追加 TSV 发布记录，并保存当前与上一个镜像。部署失败时尝试恢复上一个已验证镜像。
4. `rollback prod APP --approve-prod` 加载可用的上一个镜像，验证并记录结果。**不回滚外部状态和数据库。**

## 已知限制

不内置镜像仓库、发布审批服务、产物签名、多架构分发、Helm/Kubernetes、数据库迁移或自动密钥管理。当前编排器为 Docker Compose；swarm/k8s/k3s 等编排器为后续扩展，接入时按"传输不变、apply 与回滚机制按编排器差异放 references"扩展，不改变收据与晋级门禁。收据文件不是加密签名的来源证明；团队强制测试与策略应由 CI 执行。
