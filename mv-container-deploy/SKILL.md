---
name: mv-container-deploy
description: 把已构建的容器镜像包部署到各环境与服务器（本机 WSL、开发服务器、生产），以及部署更新、健康验证、同镜像晋级生产与回滚时统一使用本 skill。触发场景：部署或更新容器、晋级生产、回滚版本、排查部署或启动失败、确认发布状态。核心原则：目标机不执行构建，只加载运行 mv-image-build 产出的不可变镜像；Windows 上容器操作一律经 WSL，没有 WSL 即明确失败；prod 晋级要求同一 Image ID 的 dev 健康验证收据与用户明确授权。当前编排器为 Docker Compose（swarm/k8s/k3s 为后续扩展，见交付契约限制）。出包、打镜像与本地调测归 mv-image-build，宿主工具链安装归 mv-toolchain-manager，Git 提交发布归 mv-git-publisher。
---

# 容器部署与晋级

本 skill 负责交付管线的后半段：**预检 → 镜像传输 → 启动 → 健康验证 → 收据 → 晋级/回滚**。镜像包来自 `mv-image-build`（接口为 `IMAGE=<repo>:<tag>` 与 `IMAGE_ID`），本 skill 不构建、不重编译，只把不可变镜像送到目标环境并验证。

`deploy dev（本机/开发服务器）→ 验证健康写收据 → 用户授权 → 同 Image ID 晋级 prod → 异常回滚`

- 本机调测（"本地跑一下"/debug/断点）归 `mv-image-build`；本 skill 的本机 dev 是**走门禁的交付目标**（健康验证后写收据），两者共用同一 WSL Docker。
- 与 Git 独立，不暗中 commit；生产数据库迁移与外部副作用不随容器回滚。

## 硬性规范（无例外）

- **WSL 硬门禁**：Windows 上容器部署、状态查询一律经 WSL；WSL、发行版或 WSL 内 Docker 不可用时明确报错并给出安装指引，不得回退为宿主直接执行。
- **镜像常驻**：部署只新增/替换容器，任何流程不得 `docker rmi`、`docker system prune` 等清理动作；目标机保存当前与上一个成功镜像用于回滚。
- **晋级门禁**：prod 只能晋级已有 dev 收据的**同一** Image ID，不能仅凭相同 Git SHA 推断镜像一致；`--approve-prod` 只是脚本保护，不能代替用户对真实生产操作的授权。
- **意图分流**：dev 用 `FF_DEV_SSH`（未设为本机）；prod 只能明确指定 SSH 目标，且必须用户明确授权后执行，不因含糊的"跑起来"自动操作 prod。

## 工具入口

从本次加载的 SKILL.md 路径确定 skill 目录实际绝对路径，赋给 `SKILL_ROOT`（这是文档中的路径变量，agent 不保证自动提供）；路径始终加引号，工作目录保持为用户应用仓库。Python 按环境选择 `python3`、`python` 或 `py -3`。

```bash
# WSL 硬门禁；非零退出即终止并如实报告，不得改用宿主直接执行
bash "${SKILL_ROOT}/scripts/wsl-bridge.sh" require

# 交付:deploy.sh 只消费 mv-image-build 输出的镜像引用(IMAGE=<repo>:<tag>)
bash "${SKILL_ROOT}/scripts/deploy.sh" deploy dev app-name app-name:TAG
bash "${SKILL_ROOT}/scripts/deploy.sh" status dev app-name
# 生产必须先获得用户明确授权，并验证同一 Image ID 的 dev 收据后才执行
bash "${SKILL_ROOT}/scripts/deploy.sh" deploy prod app-name app-name:TAG --approve-prod
bash "${SKILL_ROOT}/scripts/deploy.sh" rollback prod app-name --approve-prod
```

## 交付流程

1. 交付前检查：镜像已在本地（`docker image inspect`，由 `mv-image-build` 产出）、`compose.delivery.yml` 或 `templates/compose.delivery.yml`、`.env.<env>`（未跟踪、`APP_ENV` 匹配）、`.dockerignore`；脚本内 `project_checks`/`env_checks` 与 `deploy-preflight.sh` 会先做只读预检。
2. `deploy dev`：默认本机 WSL 容器，设置 `FF_DEV_SSH` 后为开发服务器。远端用 `docker save/load` 传输镜像并核对传输前后 Image ID 一致；随后启动 Compose、轮询健康（Docker HEALTHCHECK 或 `FF_HEALTH_URL`）。
3. dev 健康验证通过（`VERIFIED_HEALTH=strong`）后在 `~/.local/share/skills/receipts/<app>/<IMAGE_ID>` 写 dev 收据；仅 `running` 不产生可晋级收据。
4. `deploy prod`：要求用户明确授权、`FF_PROD_SSH` 目标、同一 Image ID 的 dev 收据（`FF_REQUIRE_DEV_PROOF=0` 仅限风险评估后的显式应急）。生产必须有真实健康信号，仅 `running` 不算健康。
5. 部署成功后在目标机 `~/.local/share/skills/<app>/releases.tsv` 追加发布记录，并保存当前与上一个成功镜像；验证失败时脚本自动尝试恢复上一个已验证镜像（应用级回滚）。
6. `rollback prod` 加载可用的上一个镜像并验证记录结果；**不回滚外部状态和数据库**。
7. 默认 Docker save/load 复用同一镜像，后续可替换 Registry；`--pull never` 保证目标机只用已有镜像，切换环境绝不重新生成不同编译结果。

## 常见故障

- `Image missing locally`：部署侧不构建，先回 `mv-image-build` 出镜像（或确认镜像名/Tag 拼写与构建输出一致）。
- dev 部署成功但提示 `No promotable dev receipt`：容器无 Docker HEALTHCHECK 且未设 `FF_HEALTH_URL`，补齐后重新部署才能拿到可晋级收据。
- `Transferred image ID mismatch`：save/load 传输前后不一致即终止，检查目标机磁盘空间与 Docker 存储驱动，不跳过校验。
- 远端启动失败但脚本已回滚：`releases.tsv` 与 `previous-image` 是事实源，用 `status` 核对当前镜像后再决定重试或人工介入。
- Windows 侧连不上本机容器端口：确认 compose `ports` 已发布、目标端口未被占用（Mirrored 网络模式与 Windows 侧进程共享端口，见 `mv-image-build` 常见故障）。

## 发布门禁与自检

- 本地预检：`bash "${SKILL_ROOT}/scripts/deploy-preflight.sh" dev APP` 或 `prod APP`，检查 Docker/Compose、env 跟踪和构建上下文配置。
- 只读诊断：`python3 "${SKILL_ROOT}/scripts/doctor.py" --project .`（`wsl_docker`/`wsl_resources`/`docker_compose` 项），不构成发布门禁。
- 环境契约（`.env` 文件、SSH、Compose 项目描述、目标目录布局）读取 [配置参考](references/configuration.md)；详细契约见 [交付契约](references/deployment-contract.md) 与 [安全模型](references/security-model.md)。

## 安全要点

- 禁止以开发命令或本地容器冒充 dev/prod 部署成功；禁止生产 Debug Agent、明文输出 secret、无确认修改数据库 schema。应用回滚不回滚数据库迁移或外部副作用。
- `.env.<env>` 与私钥不得进入 Git 或命令日志；远端传输前 `wsl-bridge.sh push` 做密文校验。主机密钥按 SSH `known_hosts` 机制验证，不禁用该检查；不将不可信的镜像名或环境值传入部署命令。
- 出包与镜像构建的安全基线（构建上下文、扫描）见 `mv-image-build`。
