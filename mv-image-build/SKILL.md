---
name: mv-image-build
description: 把模块的宿主构建结果打包为容器镜像时使用本 skill：Java 模块由模块内 Jib 插件定义镜像（jib-build.sh 编排 tar 产出与载入），非 Java 模块用模块内 Dockerfile.delivery（或 Node 静态前端模板）经瘦上下文构建；Windows 宿主经 WSL 桥接，Linux/macOS 直连本机 Docker。触发场景：打镜像、出镜像包、构建交付镜像、给 Spring Boot 模块打镜像、非 Java 模块交付镜像、排查镜像构建失败。核心原则：镜像定义与模块同源（Java 在 pom/build.gradle 声明 Jib，其他栈在模块内自备 Dockerfile.delivery）；编译出包在宿主完成（宿主工具链由 mv-toolchain-manager 准备）；本 skill 只构建不运行——镜像验证与部署归 mv-container-deploy（本机容器运行时即默认 dev 目标）；镜像常驻不清理。本机直启调试归 mv-local-debug。
---

# 镜像构建

本 skill 只做一件事：**把模块的宿主构建结果打包为一个瘦运行时镜像，输出镜像身份**。镜像定义留在模块内部，脚本只负责编排与取证：

| 模块类型 | 镜像定义位置 | 编排入口 |
| --- | --- | --- |
| Java（Maven/Gradle） | 模块 `pom.xml` / `build.gradle(.kts)` 中的 Jib 插件 | `scripts/jib-build.sh` |
| 非 Java（Node 静态前端） | 本 skill 的 `templates/Dockerfile.web` | `scripts/image-build.sh` |
| 其他栈 | 模块内自备 `Dockerfile.delivery`（只复制产物，不编译） | `scripts/image-build.sh` |

两条路径最终都把镜像载入目标 Docker，并输出同一份镜像身份（`IMAGE=` 与 `IMAGE_ID=`）。不运行镜像、不验证启动——证明镜像能跑是 `mv-container-deploy` 的 dev 交付职责（本机容器运行时即默认目标机）。

- 多模块项目：**每个模块独立定义、独立出镜像**，在目标模块目录执行对应脚本；`jib-build.sh` 支持 `FF_JIB_PROJECT` 指向模块目录。默认不建聚合的 `image-build` 模块；只有确需集中管理时才设聚合目录，且聚合内容仍是各模块自己的镜像定义。

## 硬性规范（无例外）

- **宿主出包**：编译出包在宿主按项目约定执行（`mvn -B package`、`./gradlew bootJar`、`npm run build`），镜像与容器不承担编译；宿主工具链未就绪先走 `mv-toolchain-manager`。
- **镜像定义随模块**：Java 的基镜像、入口、端口、用户等配置在模块的 Jib 插件里；非 Java 模块在 `Dockerfile.delivery` 里。本 skill 的脚本只能传入目标镜像引用（`-Djib.to.image`）与可选基镜像覆盖，**不得在脚本里另写一套镜像配置**，否则镜像行为与模块配置脱节。
- **构建引擎**：Java 走 Jib `jib:buildTar` / `jibBuildTar` 产出镜像 tar，再载入 WSL（Windows）或本机 Docker；非 Java 走 Docker 瘦上下文构建。Windows 宿主容器路径一律经 WSL，没有 WSL 就失败并给安装指引，不在宿主安装 Docker。
- **只构建不运行**：本 skill 不 `docker run`、不起 compose 栈；「在容器里跑/验证镜像」走 `mv-container-deploy` 的 dev 交付。
- **镜像常驻**：构建镜像与拉取的基础镜像一律保留，任何流程不得 `docker rmi`、`docker system prune`；存储不足时报告用户请示。
- **意图分流**：「打镜像 / 出镜像包」= 本 skill；「本地跑一下 / debug / 断点 / 联调」= `mv-local-debug`（宿主直启）；「部署 dev / 在容器里跑 / 上生产 / 回滚」= `mv-container-deploy`。

## 工具入口

从本次加载的 SKILL.md 路径确定 skill 目录实际绝对路径，赋给 `SKILL_ROOT`（这是文档中的路径变量，agent 不保证自动提供）；路径始终加引号，工作目录保持为用户应用仓库。Python 按环境选择 `python3`、`python` 或 `py -3`；缺失时交 `mv-toolchain-manager` 按需准备（`ensure --python 3.12`，宿主完全没有 Python 时用其 `bootstrap-python.sh`），不要求用户手工安装。

```bash
# 容器运行时门禁（Windows 校验 WSL+Docker，Linux/macOS 校验本机 Docker）
bash "${SKILL_ROOT}/scripts/wsl-bridge.sh" require

# 宿主出包:按项目约定执行构建命令,如实记录命令与结果作为构建证据
mvn -B package              # 或 ./gradlew bootJar / npm run build

# Java 模块:在模块目录执行,调用模块自己声明的 Jib 插件(jib:buildTar / jibBuildTar),
# 产出 tar 后载入 WSL 或本机 Docker;输出唯一镜像 TAG 与 IMAGE_ID
bash "${SKILL_ROOT}/scripts/jib-build.sh" build dev app-name

# 非 Java 模块:在模块目录执行,检测产物(dist|build 或 FF_ARTIFACT)与 Dockerfile.delivery,
# 组装瘦上下文出镜像;输出唯一镜像 TAG 与 IMAGE_ID
bash "${SKILL_ROOT}/scripts/image-build.sh" build dev app-name
```

## 构建流程

1. 出包前检查：宿主工具链就绪（见 `mv-toolchain-manager`）、Maven/Gradle Wrapper、Node lockfile；Java 模块已按 [构建契约](references/build-contract.md) 声明 Jib 插件；非 Java 模块的 `.dockerignore` 显式排除 `.git` 与 `.env*`。用户自有规范优先。
2. 检查版本与前端环境变量是否编译期固化：Vite 构建期嵌入不同 API 地址就不能宣称跨环境同一镜像，必须改为相对路径或运行时配置注入，或明确例外。
3. 宿主出包：按项目约定在宿主执行构建，记录实际命令、退出状态与产物路径；构建失败不进入镜像步骤。构建基于当前工作区时明确 staged、unstaged、untracked 和删除项的范围，如实记录构建输入不是纯 Git SHA。agent shell 内构建失败且特征为 `Unable to establish loopback connection` 时是进程链被安全软件 hook（仅 Windows 宿主现象，非工具链问题），改走 `templates/schtasks-build.cmd` 干净链，或交由用户手动构建并如实记录。
4. 出镜像：按模块类型选入口。Java 模块执行 `jib-build.sh build dev <app>`——脚本校验模块内确有 Jib 插件、宿主已有 `target/` 或 `build/libs/`，调用插件产出 tar（默认 `target/jib-image.tar` / `build/jib-image.tar`），Windows 经 `push-bin` 管道送入 WSL 后 `docker load`，其余宿主直接 `docker load`；非 Java 模块执行 `image-build.sh build dev <app>`——自动检测产物（Node `dist|build`、`Dockerfile.delivery` 项目的 jar 或显式 `FF_ARTIFACT`），组装瘦上下文并经 WSL/本机 Docker 构建。两条路径都输出 `IMAGE` 与 `IMAGE_ID`，如实转记作为镜像身份证据；构建失败则不进入后续流程。
5. 出包前可先跑宿主侧检查 `bash "${SKILL_ROOT}/scripts/quality-check.sh" quick` 或 `full`；安全扫描 `bash "${SKILL_ROOT}/scripts/security-scan.sh" source .` 用已有 Gitleaks；`FF_REQUIRE_SECURITY_SCAN=1` 后镜像构建要求已有 Trivy，缺失则失败。缺扫描器不能宣称扫描通过。
6. 只读诊断：`python3 "${SKILL_ROOT}/scripts/doctor.py" --project .`（`host_build_chain` 项十秒判定构建链路是否被安全软件拦截，`wsl_resources` 项查 WSL 资源；两项均仅 Windows 宿主执行，其余宿主自动跳过）。

## 验证边界与验收报告

- 区分编译、单元测试、mock 运行时联调和真实依赖联调，每项记录实际输入、命令及结果；签名桩或手工 classpath 的验证只覆盖该范围，不等同于项目完整构建或 CI。
- 对机制问题沿"配置读取 → 业务传递 → 框架/依赖消费 → 实际副作用"追踪，结论附关键文件与行号。
- 验收报告输出：Git SHA 与构建输入状态、宿主构建命令与产物路径、镜像 Tag 与 Image ID、未验证的风险。没有真实构建时明确写出未执行，不可虚构成功；**本 skill 不输出"镜像可以正常启动"类结论——那由 `mv-container-deploy` 的健康验证给出**。

## 常见故障

- `jib-build.sh` 报"模块未声明 Jib 插件"：镜像定义属模块配置，先在模块内加入插件与团队基线（见 [构建契约](references/build-contract.md)），不要改用 Docker 路径绕过；确需 Docker 时在模块内提供 `Dockerfile.delivery`。
- `jib-build.sh` 报"未找到 target/ 或 build/libs/"：Jib 消费项目自身产物，先按项目约定在宿主出包；本脚本不做编译。
- Jib 执行后未产出 tar：核对模块 Jib 配置的 `outputPaths.tar`，用 `FF_IMAGE_TAR` 指向实际路径后重试。
- `image-build.sh` 报"未找到可交付产物"或"检测到多个可交付产物"：确认宿主构建命令确实成功且输出目录与栈匹配（Node `dist|build`、`Dockerfile.delivery` 项目的 `target`/`build/libs`），多模块或自定义布局用 `FF_ARTIFACT` 显式指定。
- 宿主无容器运行时（Windows 无 WSL，或 Linux/macOS 未装 Docker）：脚本明确报错并给安装指引；Windows 宿主不得以在宿主安装 Docker 代替，Java 模块同样需要目标 Docker 才能载入镜像。
- 宿主 gradle/mvn 报 `Unable to establish loopback connection`（`Selector.open` 失败，仅 Windows 宿主）：安全软件按**进程链** hook，bash/agent 子进程一律被拦——换 JDK、`preferIPv4Stack`、查 afunix 服务均无效。用 `doctor.py` 的 `host_build_chain` 项十秒判定；构建可改经 `templates/schtasks-build.cmd` 执行（schtasks 拉起的进程链不经过被拦截的子进程链）或请用户手动构建。
- 宿主 Gradle 反复下载依赖：核对实际构建进程的用户目录、`GRADLE_USER_HOME` 与 Wrapper 缓存，区分下载耗时与编译耗时；不得把编译转入 WSL 或容器，详见 [常见故障](references/troubleshooting.md)。
- Mirrored 模式下 WSL Docker 拉取基础镜像停滞：在 WSL 侧检查 DNS、HTTPS 连通性与 Docker 代理；已有兼容的常驻运行时镜像时可用 `FF_RUNTIME_IMAGE` 指定后重试镜像构建，并记录来源与实际结果；入口固定带 `--pull`，不能据此承诺离线成功。镜像启动与健康验证交 `mv-container-deploy`，详见 [常见故障](references/troubleshooting.md)。

## 安全要点

- Java 路径的 tar 经 `wsl-bridge.sh push-bin`（stdin 管道 + 密文头校验）进入 WSL；非 Java 路径的构建上下文只含产物与 Dockerfile，`.dockerignore` 必须显式排除 `.git` 与 `.env*`。秘密与 `.env` 不进上下文、Git 或命令日志。`FF_REQUIRE_SECURITY_SCAN=1` 时构建必须经 Trivy；CI 应落实严格策略。
- 编译出包在宿主完成是团队基线，不得改回容器内编译。Dockerfile 或 Jib 配置过于复杂时，可选用严格遵循同一环境契约的项目内 CI/CD。
- 部署、晋级、回滚的授权与生产验证规则见 `mv-container-deploy`。

产物检测、模块内镜像定义基线、环境变量、镜像 TAG 公式与接口契约读取 [镜像构建契约](references/build-contract.md)；构建期安全要点见 [安全模型](references/security-model.md)。

## 参考

- [references/build-contract.md](references/build-contract.md)：模块内 Jib 配置基线、产物检测、瘦上下文、镜像身份契约与接口约定。
- [references/security-model.md](references/security-model.md)：构建期安全要点（构建上下文、tar 传输、扫描策略）。
- [references/troubleshooting.md](references/troubleshooting.md)：镜像构建链路高频故障按症状对照。
