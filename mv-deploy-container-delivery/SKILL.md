---
name: mv-deploy-container-delivery
description: 把已构建的容器镜像交付到各环境并验证时使用：部署或更新容器、部署到开发服务器、晋级生产、回滚版本、排查部署或启动失败、确认发布状态。容器操作一律在服务器侧执行并经 SSH 访问，宿主不安装 Docker；prod 晋级要求同一 Image ID 的 dev 健康验证收据与用户明确授权。宿主出包与镜像构建归 mv-build-image-builder，本机直启调试归 mv-code-local-debug。
---

# 容器部署与晋级

本 skill 负责交付管线的后半段：**预检 → 启动 → 健康验证 → 收据 → 晋级/回滚**。镜像由 `mv-build-image-builder` 在构建点产出（接口为 `IMAGE=<repo>:<tag>` 与 `IMAGE_ID`），本 skill 不构建、不重编译，只把不可变镜像交付到目标环境并验证。

`deploy dev（开发服务器）→ 验证健康写收据 → 用户授权 → 同 Image ID 晋级 prod → 异常回滚`

- 容器操作一律在服务器侧执行：单机部署即部署机自身；集群经镜像仓库分发到各节点。所有部署目标统一经 SSH 通道访问，宿主不安装 Docker，无宿主侧特例。
- 本机直启调测（"本地跑一下"/debug/断点）归 `mv-code-local-debug`，在宿主前台直启；本 skill 的 dev 是容器部署目标（开发服务器），健康验证后写收据。
- 与 Git 独立，不暗中 commit；生产数据库迁移与外部副作用不随容器回滚。

## 硬性规范（无例外）

- **容器操作在服务器侧**：部署、状态查询、观测与排障一律在目标服务器执行；宿主不安装 Docker，不直接操作容器。目标服务器容器环境不可用时明确报错并给安装指引，不在宿主侧代操作。
- **目标按真实远端对待**：交付目标的实际位置不进入流程判断——即使得知目标实为本机 WSL 等宿主本地实现，也按真实服务器执行全部流程（SSH 交付、健康验证、收据、晋级门禁），不使用 `wsl.exe`、`\\wsl$`/`\\wsl.localhost` 等宿主旁路直接访问或拷贝；查看、执行与文件传输一律经 SSH 通道。
- **编排运行**：容器创建与启动一律经编排器声明——当前基线 Docker Compose（swarm/k8s 等按交付契约扩展）；禁止用裸 `docker run`、`docker create` 起服务，排障用 `docker exec` 只读检查不受此限。
- **同一项目一个 stack/ns**：同一项目的全部组件归属同一个 Compose 项目（stack，交付脚本以 `-p APP` 固定项目名），不拆分到多个 stack，不与其他项目混用；接入 swarm/k8s 后同理对应一个 namespace（见交付契约）。
- **全量交付默认**：部署默认携带系统完整组件集——全部业务服务（如 a、b）、其依赖的基础设施（MySQL、Redis 等按项目声明）及配套部署脚本与配置文件；「只部署部分组件、其余依赖视为已存在」须用户明确说明依赖关系后才成立，并在发布记录注明本次部署范围与豁免项。
- **镜像常驻**：部署只新增/替换容器，任何流程不得 `docker rmi`、`docker system prune` 等清理动作；发布状态以目标机版本清单为准（见交付契约「发布以版本为准」）。
- **晋级门禁**：prod 只能晋级已有 dev 收据的**同一** Image ID，不能仅凭相同 Git SHA 推断镜像一致；`--approve-prod` 只是脚本保护，不能代替用户对真实生产操作的授权。
- **-dirty 拦截是命名约定**：脚本按 Tag 含 `-dirty` 拒绝向 prod 交付；标记由 mv-build-image-builder 出包时自动携带，在构建流程外手工重打干净 Tag 可绕过检测——属流程违规而非技术边界，交付镜像必须出自 mv-build-image-builder 流程。
- **意图分流**：dev 目标是开发服务器，经 `FF_DEV_SSH` 指定；项目未声明开发服务器时向用户确认，不在宿主直接起容器；prod 只能明确指定 SSH 目标，且必须用户明确授权后执行，不因含糊的"跑起来"自动操作 prod。「在 WSL/容器里跑」是部署动作，归本 skill dev 交付，不走旁路。项目文档化的开发拓扑就是容器（如 compose 起全套依赖、宿主无法独立启动）时，"本地跑一下"按项目约定直接走本 skill 的 dev 交付。
- **构建与调试边界**：镜像构建归 `mv-build-image-builder`（宿主出包、服务器构建，只构建不运行）；宿主直启调试归 `mv-code-local-debug`（不碰容器）；本 skill 拥有全部容器运行路径。

## 工具入口

从本次加载的 SKILL.md 路径确定 skill 目录实际绝对路径，赋给 `SKILL_ROOT`（这是文档中的路径变量，agent 不保证自动提供）；路径始终加引号，工作目录保持为用户应用仓库。Python 按环境选择 `python3`、`python` 或 `py -3`。

```bash
# 预检:静态配置(构建上下文卫生、env 未跟踪)+ SSH 连通与目标机 Compose v2 校验;非零退出即终止并如实报告
FF_DEV_SSH=devops@dev.example.com bash "${SKILL_ROOT}/scripts/deploy-preflight.sh" dev app-name

# 交付:deploy.sh 只消费 mv-build-image-builder 输出的镜像引用(IMAGE=<repo>:<tag>)
bash "${SKILL_ROOT}/scripts/deploy.sh" deploy dev app-name app-name:TAG
bash "${SKILL_ROOT}/scripts/deploy.sh" status dev app-name
# 生产必须先获得用户明确授权，并验证同一 Image ID 的 dev 收据后才执行
bash "${SKILL_ROOT}/scripts/deploy.sh" deploy prod app-name app-name:TAG --approve-prod
bash "${SKILL_ROOT}/scripts/deploy.sh" rollback prod app-name --approve-prod [--service NAME]
```

## 交付流程

1. 交付前检查：`compose.delivery.yml` 或 `templates/compose.delivery.yml`、`.env.<env>`（未跟踪、`APP_ENV` 匹配）、`.dockerignore`；脚本内 `project_checks`/`env_checks` 与 `deploy-preflight.sh` 会先做只读预检（静态配置 + SSH 连通与目标机 Compose v2）。
2. `deploy dev`：目标为 `FF_DEV_SSH` 指定的开发服务器。生成版本号（`version_<UTC 时间戳>_<sha12>[-dirty]`）后，compose 声明的全部镜像在目标机分发就位——已有直接使用，缺失经镜像仓库 `docker pull` 并核对 Image ID，不经宿主直传；随后启动 Compose、轮询 readiness（`FF_HEALTH_URL` 指向 readiness 端点；Docker HEALTHCHECK 属 liveness 观测位）。
3. dev 健康验证通过（`VERIFIED_HEALTH=strong`）后：目标机快照版本清单写入 `versions/<版本>.tsv`（全服务 `服务\t镜像\tImage ID`）并前移 `current-version`；本机（执行部署的工作机）按清单逐 Image ID 在 `~/.mv/container-deploy/receipts/<app>/` 写 dev 收据。仅 `running-only`、`liveness-only` 不产生可晋级收据。
4. `deploy prod`：要求用户明确授权、`FF_PROD_SSH` 目标、晋级门禁两段核对 dev 收据（上传前主镜像按目标机 Image ID，启动前经 `plan` 按完整镜像清单逐镜像，并拒绝 `-dirty`；`FF_REQUIRE_DEV_PROOF=0` 仅限风险评估后的显式应急）。生产必须有真实健康信号，仅 `running` 不算健康。
5. 部署成功后在目标机 `~/.mv/container-deploy/<app>/releases.tsv` 追加发布记录（每服务一行）；验证失败时脚本按上一版本清单自动恢复应用并如实报告。
6. `rollback prod` 按上一版本清单整栈恢复并验证记录结果，`--service NAME` 可限定单服务回退；**不回滚外部状态和数据库**。
7. 各节点经镜像仓库拉取同一镜像保证 Image ID 一致；`--pull never` 保证 Compose 只用已就位镜像，切换环境绝不重新生成不同编译结果。

## 部署后观测与调试

- 观测：`docker compose logs -f`、`docker compose ps`，一律经 SSH 在目标服务器执行；端口经 compose `ports` 发布后在目标机 `127.0.0.1:<端口>` 访问，跨机访问按目标机地址与防火墙放行。
- 进入容器排障：`docker exec -it <容器> sh`；只做只读检查与本次部署相关的操作，不改仓库与系统配置。
- 断点调试：dev 环境可在 Compose 中开启 JDWP（端口映射仅绑定本机回环）；**生产禁止 Debug Agent**（见安全要点）。dev 调试配置的验证结论在验收报告中如实标注。
- 镜像没部署就想"试试能不能起"：就是本 skill 的 `deploy dev`（开发服务器，验证后写收据），不另行旁路起栈。

## 常见故障

- 目标机无目标镜像且拉取失败（`Image absent on target`/`Image unavailable on target`）：部署侧不构建，先回 `mv-build-image-builder` 确认服务器构建已完成，再核对镜像仓库分发与镜像名/Tag 拼写（与构建输出一致）。
- dev 部署成功但提示 `No promotable dev receipt`：未设 `FF_HEALTH_URL`（须指向 readiness 端点），仅靠 Docker HEALTHCHECK 只记 `liveness-only` 档；补设后重新部署才能取得可晋级收据。
- prod 晋级报无 dev 收据（`no verified dev deployment receipt`）：晋级门禁按目标机 Image ID 核对本机收据（`~/.mv/container-deploy/receipts/<app>/`），同一 Image ID 必须先在 dev 验证健康，不跳过校验。
- 远端启动失败但脚本已回滚：`releases.tsv`、`versions/` 版本清单与 `current-version` 是事实源，用 `status` 核对当前版本与镜像后再决定重试或人工介入。
- 访问不到容器端口：确认 compose `ports` 已发布、目标端口未被占用（目标机用 `ss -ltnp` 或 `lsof -i :<端口>` 查占用）并核对防火墙放行。

## 发布门禁与自检

- 本地预检：`bash "${SKILL_ROOT}/scripts/deploy-preflight.sh" dev APP` 或 `prod APP`（需对应 `FF_*_SSH`），检查 env 跟踪、构建上下文配置与目标机 SSH 连通及 Compose v2。
- 只读诊断：`python3 "${SKILL_ROOT}/scripts/doctor.py" --project .`（`ssh` 项：交付宿主只需 Git 与 SSH 客户端，容器环境在目标机校验），不构成发布门禁。
- 环境契约（`.env` 文件、SSH、Compose 项目描述、目标目录布局）读取 [配置参考](references/configuration.md)；详细契约见 [交付契约](references/deployment-contract.md) 与 [安全模型](references/security-model.md)。

## 安全要点

- 禁止以开发命令或本地容器冒充 dev/prod 部署成功；禁止生产 Debug Agent、明文输出 secret、无确认修改数据库 schema。应用回滚不回滚数据库迁移或外部副作用。
- `.env.<env>` 与私钥不得进入 Git 或命令日志；配置与 Compose 文件一律经 SSH 通道传输到目标机，落盘即按 600 收口。主机密钥按 SSH `known_hosts` 机制验证，不禁用该检查；不将不可信的镜像名或环境值传入部署命令。
- 出包与镜像构建的安全基线（出包、上传校验、扫描）见 `mv-build-image-builder`。
