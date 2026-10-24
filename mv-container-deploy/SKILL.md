---
name: mv-container-deploy
description: 把 mv-image-build 在服务器构建产出的镜像交付到各环境（开发服务器、生产），以及部署更新、健康验证、同镜像晋级生产与回滚时统一使用本 skill。触发场景：部署或更新容器、晋级生产、回滚版本、排查部署或启动失败、确认发布状态。核心原则：容器操作一律在服务器侧执行，宿主不安装 Docker——Windows 宿主的开发服务器为本机 WSL，远端经 SSH；本 skill 只交付不构建、不重编译，编排按不可变镜像运行；集群经镜像仓库分发，单机部署即部署机自身；prod 晋级要求同一 Image ID 的 dev 健康验证收据与用户明确授权。当前编排器为 Docker Compose（swarm/k8s/k3s 为后续扩展，见交付契约限制）。宿主出包与服务器镜像构建归 mv-image-build，本机直启调试归 mv-local-debug。
---

# 容器部署与晋级

本 skill 负责交付管线的后半段：**预检 → 启动 → 健康验证 → 收据 → 晋级/回滚**。镜像由 `mv-image-build` 在构建点产出（接口为 `IMAGE=<repo>:<tag>` 与 `IMAGE_ID`），本 skill 不构建、不重编译，只把不可变镜像交付到目标环境并验证。

`deploy dev（开发服务器）→ 验证健康写收据 → 用户授权 → 同 Image ID 晋级 prod → 异常回滚`

- 容器操作一律在服务器侧执行：单机部署即部署机自身；集群经镜像仓库分发到各节点。Windows 宿主的开发服务器为本机 WSL（它就是一台开发服务器），远端服务器经 SSH。
- 本机直启调测（"本地跑一下"/debug/断点）归 `mv-local-debug`，在宿主前台直启；本 skill 的 dev 是容器部署目标（开发服务器），健康验证后写收据。
- 与 Git 独立，不暗中 commit；生产数据库迁移与外部副作用不随容器回滚。

## 硬性规范（无例外）

- **容器操作在服务器侧**：部署、状态查询、观测与排障一律在目标服务器执行；宿主不安装 Docker，不直接操作容器。目标服务器容器环境不可用时明确报错并给安装指引，不在宿主侧代操作。
- **编排运行**：容器创建与启动一律经编排器声明——当前基线 Docker Compose（swarm/k8s 等按交付契约扩展）；禁止用裸 `docker run`、`docker create` 起服务，排障用 `docker exec` 只读检查不受此限。
- **全量交付默认**：部署默认携带系统完整组件集——全部业务服务（如 a、b）、其依赖的基础设施（MySQL、Redis 等按项目声明）及配套部署脚本与配置文件；「只部署部分组件、其余依赖视为已存在」须用户明确说明依赖关系后才成立，并在发布记录注明本次部署范围与豁免项。
- **镜像常驻**：部署只新增/替换容器，任何流程不得 `docker rmi`、`docker system prune` 等清理动作；目标机保存当前与上一个成功镜像用于回滚。
- **晋级门禁**：prod 只能晋级已有 dev 收据的**同一** Image ID，不能仅凭相同 Git SHA 推断镜像一致；`--approve-prod` 只是脚本保护，不能代替用户对真实生产操作的授权。
- **-dirty 拦截是命名约定**：脚本按 Tag 含 `-dirty` 拒绝向 prod 交付；标记由 mv-image-build 出包时自动携带，在构建流程外手工重打干净 Tag 可绕过检测——属流程违规而非技术边界，交付镜像必须出自 mv-image-build 流程。
- **意图分流**：dev 默认目标是开发服务器——Windows 宿主即本机 WSL，其余宿主为项目声明的开发服务器（未声明时向用户确认，不在宿主直接起容器），`FF_DEV_SSH` 显式指定远端；prod 只能明确指定 SSH 目标，且必须用户明确授权后执行，不因含糊的"跑起来"自动操作 prod。「在 WSL/容器里跑」是部署动作，归本 skill dev 交付，不走旁路。项目文档化的开发拓扑就是容器（如 compose 起全套依赖、宿主无法独立启动）时，"本地跑一下"按项目约定直接走本 skill 的 dev 交付。
- **构建与调试边界**：镜像构建归 `mv-image-build`（宿主出包、服务器构建，只构建不运行）；宿主直启调试归 `mv-local-debug`（不碰容器）；本 skill 拥有全部容器运行路径。

## 工具入口

从本次加载的 SKILL.md 路径确定 skill 目录实际绝对路径，赋给 `SKILL_ROOT`（这是文档中的路径变量，agent 不保证自动提供）；路径始终加引号，工作目录保持为用户应用仓库。Python 按环境选择 `python3`、`python` 或 `py -3`。

```bash
# 目标开发服务器容器环境校验（Windows 校验本机 WSL+Docker，远端目标按 SSH 校验）；非零退出即终止并如实报告
bash "${SKILL_ROOT}/scripts/wsl-bridge.sh" require

# 交付:deploy.sh 只消费 mv-image-build 输出的镜像引用(IMAGE=<repo>:<tag>)
bash "${SKILL_ROOT}/scripts/deploy.sh" deploy dev app-name app-name:TAG
bash "${SKILL_ROOT}/scripts/deploy.sh" status dev app-name
# 生产必须先获得用户明确授权，并验证同一 Image ID 的 dev 收据后才执行
bash "${SKILL_ROOT}/scripts/deploy.sh" deploy prod app-name app-name:TAG --approve-prod
bash "${SKILL_ROOT}/scripts/deploy.sh" rollback prod app-name --approve-prod
```

脚本尚未按「构建与交付分工」（docs/structure-rules.md）改造：镜像分发仍走宿主侧 save/load，服务器侧包校验未实现；改造前按脚本现状执行并如实记录，不宣称已按目标流程交付。

## 交付流程

1. 交付前检查：构建点已有目标镜像（`docker image inspect`，由 `mv-image-build` 产出，可与包清单对账）、`compose.delivery.yml` 或 `templates/compose.delivery.yml`、`.env.<env>`（未跟踪、`APP_ENV` 匹配）、`.dockerignore`；脚本内 `project_checks`/`env_checks` 与 `deploy-preflight.sh` 会先做只读预检。
2. `deploy dev`：默认开发服务器（Windows 宿主即本机 WSL），设置 `FF_DEV_SSH` 后为远端开发服务器。镜像已在构建点产出，单机部署不再传输镜像；跨机分发经镜像仓库并核对分发前后 Image ID 一致。随后启动 Compose、轮询 readiness（`FF_HEALTH_URL` 指向 readiness 端点；Docker HEALTHCHECK 属 liveness 观测位）。
3. dev 健康验证通过（`VERIFIED_HEALTH=strong`）后在 `~/.mv/container-deploy/receipts/<app>/<IMAGE_ID>` 写 dev 收据；仅 `running-only`、`liveness-only` 不产生可晋级收据。
4. `deploy prod`：要求用户明确授权、`FF_PROD_SSH` 目标、同一 Image ID 的 dev 收据（`FF_REQUIRE_DEV_PROOF=0` 仅限风险评估后的显式应急）。生产必须有真实健康信号，仅 `running` 不算健康。
5. 部署成功后在目标机 `~/.mv/container-deploy/<app>/releases.tsv` 追加发布记录，并保存当前与上一个成功镜像；验证失败时脚本自动尝试恢复上一个已验证镜像（应用级回滚）。
6. `rollback prod` 加载可用的上一个镜像并验证记录结果；**不回滚外部状态和数据库**。
7. 分发复用同一镜像保证各节点 Image ID 一致，后续可替换传输机制；`--pull never` 保证目标机只用已有镜像，切换环境绝不重新生成不同编译结果。

## 部署后观测与调试

- 观测：`docker compose logs -f`、`docker compose ps`，一律在目标服务器执行（Windows 宿主经本机 WSL，远端经 SSH）；端口经 compose `ports` 发布后从宿主侧 `127.0.0.1:<端口>` 访问（Windows 经 WSL2 localhost 转发，远端开发服务器经其地址访问）。
- 进入容器排障：`docker exec -it <容器> sh`；只做只读检查与本次部署相关的操作，不改仓库与系统配置。
- 断点调试：dev 环境可在 Compose 中开启 JDWP（端口映射仅绑定本机回环）；**生产禁止 Debug Agent**（见安全要点）。dev 调试配置的验证结论在验收报告中如实标注。
- 镜像没部署就想"试试能不能起"：就是本 skill 的 `deploy dev`（开发服务器，验证后写收据），不另行旁路起栈。

## 常见故障

- 构建点无目标镜像（`Image missing locally`）：部署侧不构建，先回 `mv-image-build` 确认服务器构建已完成（或确认镜像名/Tag 拼写与构建输出一致）。
- dev 部署成功但提示 `No promotable dev receipt`：未设 `FF_HEALTH_URL`（须指向 readiness 端点），仅靠 Docker HEALTHCHECK 只记 `liveness-only` 档；补设后重新部署才能取得可晋级收据。
- 分发前后 `Transferred image ID mismatch`：不一致即终止，检查目标机磁盘空间与 Docker 存储驱动，不跳过校验。
- 远端启动失败但脚本已回滚：`releases.tsv` 与 `previous-image` 是事实源，用 `status` 核对当前镜像后再决定重试或人工介入。
- 宿主侧连不上本机容器端口：确认 compose `ports` 已发布、目标端口未被占用。Windows 的 Mirrored 网络模式与宿主进程共享端口，排查方法见 [宿主端口占用](../mv-local-debug/references/troubleshooting.md#端口占用wsl-mirrored-共享端口层)；Linux/macOS 宿主用 `ss -ltnp` 或 `lsof -i :<端口>` 查占用并核对防火墙。未安装 `mv-local-debug` 时，按上述命令直接检查端口占用及 Compose 映射。

## 发布门禁与自检

- 本地预检：`bash "${SKILL_ROOT}/scripts/deploy-preflight.sh" dev APP` 或 `prod APP`，检查 Docker/Compose、env 跟踪和构建上下文配置。
- 只读诊断：`python3 "${SKILL_ROOT}/scripts/doctor.py" --project .`（`wsl_docker`/`wsl_resources`/`docker_compose` 项；`wsl_*` 项仅 Windows 宿主执行，其余宿主自动跳过），不构成发布门禁。
- 环境契约（`.env` 文件、SSH、Compose 项目描述、目标目录布局）读取 [配置参考](references/configuration.md)；详细契约见 [交付契约](references/deployment-contract.md) 与 [安全模型](references/security-model.md)。

## 安全要点

- 禁止以开发命令或本地容器冒充 dev/prod 部署成功；禁止生产 Debug Agent、明文输出 secret、无确认修改数据库 schema。应用回滚不回滚数据库迁移或外部副作用。
- `.env.<env>` 与私钥不得进入 Git 或命令日志；向本机 WSL 开发服务器传输经 `wsl-bridge.sh push` 密文校验，远端按 SSH 通道校验。主机密钥按 SSH `known_hosts` 机制验证，不禁用该检查；不将不可信的镜像名或环境值传入部署命令。
- 出包与镜像构建的安全基线（出包、上传校验、扫描）见 `mv-image-build`。
