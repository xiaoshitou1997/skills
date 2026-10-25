# Docker 交付契约

目标：加载运行 `mv-image-build` 从同一份提交构建的**一个**不可变镜像，先部署到 dev 验证健康，再以相同 Image ID 晋级到 prod。本 skill 不构建镜像；镜像身份以 `mv-image-build` 输出的 `IMAGE=<repo>:<tag>` 与 `IMAGE_ID` 为准。

## 项目输入

- `.env.dev` 和 `.env.prod` 由本地准备，**不得被 Git 跟踪**；分别包含 `APP_ENV=dev` 或 `APP_ENV=prod`，以及可选的 `HOST_PORT`、`CONTAINER_PORT` 和应用设置。不打印 env 文件内容，Java 容器通过环境变量接收配置。
- 部署范围默认为系统完整组件集：Compose 文件声明全部业务服务、其依赖的基础设施（MySQL、Redis 等，固定版本 Tag，不用 `latest`）及配套配置与初始化脚本，基础设施镜像与业务镜像一样须在目标机就位；多服务系统的 `compose.delivery.yml` 由项目提供。
- 用户明确说明依赖关系（如数据库使用现成实例）时，部署范围按声明缩减，并在发布记录注明范围与豁免项；仅单服务且无基础设施依赖时使用单服务模板（`templates/compose.delivery.yml`，引用 `FF_IMAGE`、没有 `build:` 段）。Node 静态前端在 env 文件中设置 `CONTAINER_PORT=80`。
- **交付上传只携带两个文件**：交付上传目标机的只有 Compose 文件与 `.env.<env>`，落 `~/.mv/container-deploy/<app>/`；`compose.delivery.yml` 不得引用其他项目侧文件，初始化 SQL、挂载配置等配套内容随镜像打包（镜像不可变自包含），不假设目标机存在其他文件。
- **部署身份按独立生命周期划定**：独立升级、独立回滚、独立数据卷、独立端口与环境配置的一组组件是一个部署身份，对应一个 APP 名与一条完整交付链（各自的 `.env.<env>`、`compose.delivery.yml`、`releases.tsv`、收据与晋级记录）。同一系统需要多份完全独立部署（如 `order` 与 `order-sandbox`）时按多个部署身份交付，各自携带自己的基础设施容器；共享某项基础设施即不再独立，按上一条声明依赖。同一部署的横向扩容不是新身份：在同一个 Compose 项目内用 replicas 扩容，不另起部署身份。**同一个项目必须一个 stack/ns**：一个部署身份（APP）的全部组件归属同一个 stack——Compose 项目名由交付脚本固定为 `-p APP`，即 stack 名；接入 swarm/k8s 后对应一个 namespace。不把同一项目拆到多个 stack/ns，不同部署身份不共用 stack/ns（如 `order` 与 `order-sandbox` 各占一个）。APP 名在同一目标机上全局唯一——默认取模块目录名，多个项目共用目标机时 APP 名带项目前缀（如 `<项目>-<模块>`）；交付目录、stack 名、包目录与发布记录都按它区分，撞名即串栈。
- **发布以版本为准**：每次部署生成版本号 `version_<UTC yyyyMMddHHmmSS>_<git sha 前12位>[-dirty]`——hash 锚发布时工作区 HEAD（发版基准点），非 Git 目录记 `unversioned` 且强制 `-dirty`；`-dirty` 版本拒绝上 prod。验证通过后目标机在 `~/.mv/container-deploy/<app>/versions/<版本>.tsv` 落版本清单（全服务 `服务\t镜像\tImage ID` 快照），`current-version` 指向当前版本。**版本清单是运行状态源**：回退按上一版清单经 `compose.override.yml` 整栈恢复，`--service` 可限定单服务（不移动 `current-version`）。
- **部署流程不构建镜像**，只加载并运行不可变镜像；`docker compose` 一律 `--no-build --pull never`。
- **双探针**：可运行服务暴露 readiness 与 liveness 两个健康端点（Spring Boot 服务经 Actuator 健康组实现，条款见 `mv-java-backend-standards` 的 spring-guide「健康探测」）。liveness 只反映进程内状态、不聚合外部依赖；readiness 反映可接流状态并聚合关键依赖，是部署验证与晋级门禁的探活依据。`FF_HEALTH_URL` 指向 readiness 端点；未配置时 dev 不产生可晋级收据、prod 直接拒绝部署。
- 编排映射：收据与 prod 门禁**只认 readiness**——`FF_HEALTH_URL` 必须指向 readiness 端点；HEALTHCHECK 仅作 liveness 观测位，单独通过记 `liveness-only` 档、不产生可晋级收据。Compose 基线只有容器级 HEALTHCHECK（liveness 语义，仅标记状态、不自动重启）；镜像内 HEALTHCHECK 由模块 `Dockerfile.delivery` 声明（指向 liveness 端点，`start_period` 覆盖启动期）。swarm/k8s 接入后按 `livenessProbe`/`readinessProbe` 原生分列（失败重启/摘流），替换上述映射。

## 环境变量

环境变量（`FF_DEV_SSH`、`FF_PROD_SSH`、`FF_HEALTH_URL`、`FF_REQUIRE_DEV_PROOF`、`FF_READY_TIMEOUT` 等）的语义与默认值以 [配置参考](configuration.md) 的表格为单一事实源，本契约不再重复维护。

## 交付流程

1. `deploy dev APP IMAGE` 预检配置（`deploy-preflight.sh` 与脚本内 `project_checks`/`env_checks`），生成版本号后把 compose 声明的全部镜像在目标机分发就位（缺失经镜像仓库 `docker pull` 并核对 Image ID），启动 Compose、整栈验证健康。验证通过（`VERIFIED_HEALTH=strong`）后快照版本清单写入 `versions/<版本>.tsv` 并前移 `current-version`，在本机（执行部署的工作机）按清单逐 Image ID 写 dev 收据（`~/.mv/container-deploy/receipts/APP/`，文件名为 Image ID、冒号替换为 `-`，规避 Windows 备用数据流语义）。
2. `deploy prod APP IMAGE --approve-prod` 要求用户明确授权、SSH 目标和真实健康探测；晋级门禁两段核对（`FF_REQUIRE_DEV_PROOF=1` 默认）：上传前按目标机 Image ID 核对主镜像的本机收据，启动前经 `plan` 取目标机完整镜像清单、逐镜像核对收据并拒绝 `-dirty`。`FF_REQUIRE_DEV_PROOF=0` 仅用于评估风险后的显式应急处理，不属于常规流程。
3. 目标部署成功后，在 `~/.mv/container-deploy/APP/releases.tsv` 追加 TSV 发布记录（时间/动作/环境/版本/服务/镜像/Image ID/验证档位，每服务一行）。部署失败时按上一版本清单自动恢复应用并如实报告。
4. `rollback prod APP --approve-prod` 按上一版本清单整栈恢复、验证并记录结果；`--service NAME` 限定单服务回退。**不回滚外部状态和数据库。**

## 已知限制

不内置镜像仓库、发布审批服务、产物签名、多架构分发、Helm/Kubernetes、数据库迁移或自动密钥管理。当前编排器为 Docker Compose；swarm/k8s/k3s 等编排器为后续扩展，接入时按"传输不变、apply 与回滚机制按编排器差异放 references"扩展，不改变收据与晋级门禁。收据文件不是加密签名的来源证明；团队强制测试与策略应由 CI 执行。
