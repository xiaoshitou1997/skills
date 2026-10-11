---
name: wsl-build-deploy
description: 本机 Windows 工作机上 Java（Gradle/Maven）/Node 项目的构建出包（jar/dist）、本地启动调测、Docker Compose 部署 dev/prod、容器健康验证、同镜像晋级与回滚统一使用本 skill。触发场景：需要出包、"本地跑一下"/debug/断点/热更新/本机联调、部署或更新容器、排查构建/部署/启动失败。核心原则：编译构建一律在 WSL 容器内完成，应用进程一律容器化，没有 WSL 即明确失败，禁止宿主直接启动；镜像常驻不清理。宿主工具链准备使用 toolchain-manager。
---

# WSL 构建部署统一管线

构建、本地调测、部署统一走 **WSL 容器管线**。本地调试与 dev/prod 交付是同一条管线，差异只在目标环境与治理门禁：

`detect → wsl-bridge 暂存源码 → 容器内构建 → compose 起栈 → 验证 → 记录/恢复`

- 宿主工具链准备见 `toolchain-manager`；容器内构建不依赖宿主 JDK/Node。
- 与 Spec Kit `implement` 兼容，不重写需求规划、测试编排或版本管理；与 Git 独立，不暗中 commit。

## 硬性规范（无例外）

- **WSL 硬门禁**：Windows 上构建、启动、部署一律经 WSL；WSL、发行版或 WSL 内 Docker 不可用时明确报错并给出安装指引，不得回退为宿主直接执行。
- **禁止宿主启动应用**：本机直接执行 `java -jar`、`mvn spring-boot:run`、`./gradlew bootRun`、`npm run dev`、`pnpm dev` 或 IDE Run 启动应用一律禁止；用户自行在 IDE 启动时提示团队规范，不代为执行宿主启动命令。
- **镜像常驻**：构建镜像与拉取的基础镜像一律保留，任何流程不得 `docker rmi`、`docker system prune` 等清理动作；存储不足时报告用户请示。构建缓存 volume 可能被 prune 清空，依赖重复下载先查 volume 是否还在。
- **意图分流**："本地跑一下 / debug / 断点 / 联调" = 本机容器；"部署 dev" 用 dev；"上生产"只在用户明确授权后选择 prod，不因含糊的"跑起来"自动操作 prod。

## 工具入口

从本次加载的 SKILL.md 路径确定 skill 目录实际绝对路径，赋给 `SKILL_ROOT`（这是文档中的路径变量，agent 不保证自动提供）；路径始终加引号，工作目录保持为用户应用仓库。Python 按环境选择 `python3`、`python` 或 `py -3`。

```bash
# WSL 硬门禁；非零退出即终止并如实报告，不得改用宿主直接执行
bash "${SKILL_ROOT}/scripts/wsl-bridge.sh" require
# 源码暂存：git archive HEAD 基线叠加未提交变更，排除 .env*；校验不过以脚本退出码为准
bash "${SKILL_ROOT}/scripts/wsl-bridge.sh" stage "$PWD" overlay

# 交付：build 输出唯一镜像 TAG，deploy 复用同一镜像；status 只读
bash "${SKILL_ROOT}/scripts/deliver.sh" build dev app-name
bash "${SKILL_ROOT}/scripts/deliver.sh" deploy dev app-name app-name:TAG
bash "${SKILL_ROOT}/scripts/deliver.sh" status dev app-name
# 生产必须先获得用户明确授权，并验证同一 Image ID 的 dev 收据后才执行
bash "${SKILL_ROOT}/scripts/deliver.sh" deploy prod app-name app-name:TAG --approve-prod
bash "${SKILL_ROOT}/scripts/deliver.sh" rollback prod app-name --approve-prod
```

- 本地调试也可直接经 bridge 执行容器命令：`bash "${SKILL_ROOT}/scripts/wsl-bridge.sh" exec "<暂存目录>" -- docker compose -f <compose> -p <app> up -d --build`；单容器场景也可 `docker build` + `docker run -d`。
- `FF_WSL_DISTRO` 指定发行版；dev 默认本机容器，设置 `FF_DEV_SSH` 后为开发服务器；prod 只能明确指定 SSH 目标。

## 本地调测流程

1. 检查项目、README、Dockerfile/compose、运行参数和现有占用端口；默认只启动用户目标组件，不改变仓库或系统配置。
2. 硬门禁 `wsl-bridge.sh require`，非零退出即终止并向用户如实报告失败原因。
3. `wsl-bridge.sh stage "$PWD" overlay` 同步源码到 WSL 暂存目录；需要 `.env*` 时用 `push` 单独传输，不入暂存。
4. 启动应用容器：项目有 compose 就经 `exec` 执行 `docker compose up -d --build`；没有则先补一个最小自测 compose（参考 `templates/`：多阶段构建、固定基础镜像、发布端口）。基础镜像由 `--build`/`pull` 拉取并常驻。
5. 观测与调试：经 `exec` 执行 `docker compose logs -f`、`docker compose ps`、`docker exec -it <容器> sh` 进入排障。端口经 compose `ports` 发布后从 Windows 侧 `127.0.0.1:<端口>` 访问（WSL2 localhost 转发）。断点调试在 compose 中开启 JDWP，端口映射仅绑定本机回环。
6. 只加载 `.env.local` 或项目已允许的开发环境设置，不自动复用 `.env.prod`、密钥或服务器配置；确认 API 请求目标为本地/dev，绝不默认连生产数据库或对生产数据做写操作。
7. 单元测试与本地集成测试按变更影响范围运行，记录实际命令与结果，不暗示完整 CI 已通过；宿主侧编译/单测（quality-check）不受容器规范限制。
8. 停止与清理：经 `exec` 执行 `docker compose -p <app> down`（只停删容器，镜像保留）；停止前重新核对标识，只清理本次创建的容器。端口占用者不是本次启动的容器时，报告冲突并选择其他端口或征求用户决定。

## 交付流程

1. 交付前检查：项目 `Dockerfile.delivery`、Maven/Gradle Wrapper、Node lockfile、`.dockerignore`、`compose.delivery.yml`、`.env.<env>`。用户自有规范优先，其次使用 `templates/` 中适配技术栈的多阶段模板。构建必须在 Docker 内完成，不把 `.env.prod`、私钥、`.git` 纳入构建上下文；env 不在 Git 跟踪之下。
2. 检查 Java/Node 版本与前端环境变量是否编译期固化：Vite 构建期嵌入不同 API 地址就不能宣称跨环境同一镜像，必须改为相对路径或运行时配置注入，或明确例外。
3. 构建当前工作区时明确 staged、unstaged、untracked 和删除项的范围；bridge 的 stage 已实现"HEAD 基线 + 工作区叠加"，如实记录构建输入不是纯 Git SHA。构建验证失败则不进入部署步骤。
4. dev 交付成功后记录当前 Image ID 的验证收据；prod 只能晋级已有 dev 收据的**同一** Image ID，不能仅凭相同 Git SHA 推断镜像一致。生产还需确认备份/回滚预案及业务变更影响；数据库迁移必须单独审批，不随 Docker 回滚自动执行。
5. prod 必须具有 Docker HEALTHCHECK 或可从目标机访问的 `FF_HEALTH_URL`；仅 `running` 对 prod 不算健康。目标机保存当前与上一个成功镜像，验证失败时尝试应用级回滚，发布历史写在受控用户目录的 `releases.tsv`。
6. 默认使用 Docker save/load 复用同一镜像，后续可替换 Registry；切换环境绝不重新生成不同编译结果。`--pull never` 保证目标机只用已有镜像。

## 构建提速与常见故障

- **Gradle 常驻 daemon 自动提速**：`deliver.sh build` 对默认 Gradle 模板路径自动经常驻 daemon 构建——暂存树整树替换到 `~/.local/share/skills/build/<app>/ws`，容器 `ff-gradle-daemon-<app>`（默认任务 `build`，行为与镜像内构建一致）与缓存卷 `ff-gradle-home-<app>` 常驻，配置/依赖缓存跨构建复用；对比 `FF_GRADLE_DAEMON=0` 的多阶段镜像内构建，每次冷启动 JVM 多付 40-60s 纯配置开销。任务可用 `FF_GRADLE_TASKS`（如 `bootJar -x test`）覆盖；`FF_GRADLE_UID` 指定容器 uid（默认 1000，需与构建树属主一致）。构建报 `Timeout waiting to lock fileHashes.lock` 时脚本自动清理 `.gradle` 残留锁并重试一次。多模块或自定义产物布局请提供 `Dockerfile.delivery`，daemon 不接管；手动使用 `${SKILL_ROOT}/scripts/gradle-daemon.sh`（在 WSL/Linux 内执行，子命令 `ensure|build|status`）。
- WSL Mirrored 网络模式下 Windows 与 WSL 共享端口：起栈前停掉 Windows 侧占用同端口的进程（IDEA 网关、vite dev server 等）；间歇性 `address already in use` 先查这一层。
- git archive 后上游删除过的源文件会在 WSL 构建树残留旧副本：编译报"找不到类"但本地 IDE 能编时，先清构建树残留；并发会话可能 mkdir 出同名暂存目录，删除后重写或让暂存目录名唯一化。

## 验证边界与验收报告

- 区分编译、单元测试、mock 运行时联调和真实依赖联调，每项记录实际输入、命令及结果；签名桩或手工 classpath 的验证只覆盖该范围，不等同于项目完整构建或 CI。
- 对机制问题沿"配置读取 → 业务传递 → 框架/依赖消费 → 实际副作用"追踪，结论附关键文件与行号。
- 入口验证按真实鉴权、Origin 和响应契约执行，并确认目标实例与依赖；共享服务注册中心可能将请求路由到其他实例，不能仅凭成功响应断言本次部署已验证。仅 mock 联调通过时明确外部系统尚未验证。
- 验收报告输出：Git SHA 与构建输入状态、完整镜像 Tag 与 Image ID、目标环境、部署位置、Compose 状态、探活方式与结果、回滚到的上个版本、未验证的风险。没有真实构建/SSH 时明确写出未执行，不可虚构成功。

## 发布门禁与自检

- 本地预检：`bash "${SKILL_ROOT}/scripts/deploy-preflight.sh" dev APP` 或 `prod APP`，检查 Docker、env 跟踪和构建上下文。
- 自检：`python3 "${SKILL_ROOT}/scripts/doctor.py" --project .`，只读信息诊断，不构成发布门禁。
- 安全扫描：`bash "${SKILL_ROOT}/scripts/security-scan.sh" source .` 用已有 Gitleaks；`FF_REQUIRE_SECURITY_SCAN=1` 后镜像构建要求已有 Trivy，缺失则失败。缺扫描器不能宣称扫描通过。
- 宿主侧轻量检查：代码就绪后 `bash "${SKILL_ROOT}/scripts/quality-check.sh" quick` 或 `full`；优先遵循项目已有命令。
- `--approve-prod` 只是额外的脚本保护，不能代替用户对真实生产操作的授权，也不是 RBAC；镜像/Host 授权属于组织安全边界。

## 安全要点

- 禁止以开发命令或本地容器冒充 dev/prod 部署成功；禁止生产 Debug Agent、明文输出 secret、无确认修改数据库 schema。应用回滚不回滚数据库迁移或外部副作用。
- 不需要安装工具时不触发 `toolchain-manager`，避免无谓的工具链准备。Dockerfile 与 Compose 过于复杂时，可选用严格遵循同一环境契约的项目内 CI/CD，但不得偷偷换成宿主编译。

环境契约（env 文件、SSH、Compose 项目描述）读取 [references/configuration.md](references/configuration.md)；详细契约见 [交付契约](references/deployment-contract.md) 与 [安全模型](references/security-model.md)。
