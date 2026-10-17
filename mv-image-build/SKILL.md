---
name: mv-image-build
description: 把 Java（Gradle/Maven）/Node 项目的宿主产物打包为容器镜像时统一使用本 skill：宿主出包、WSL 瘦镜像构建、镜像身份输出、镜像构建失败排查。触发场景：打镜像、出镜像包、构建交付镜像、排查镜像构建失败。核心原则：编译出包在宿主完成（宿主工具链由 mv-toolchain-manager 准备）；镜像构建一律经 WSL，没有 WSL 即明确失败，不回退宿主；本 skill 只构建不运行——镜像验证与部署归 mv-container-deploy（本机 WSL 即默认 dev 目标）；镜像常驻不清理。本机直启调试归 mv-local-debug，部署晋级回滚归 mv-container-deploy，宿主工具链安装归 mv-toolchain-manager。
---

# 镜像构建

本 skill 只做一件事：**把宿主产物打包为一个瘦运行时镜像，输出镜像身份**。不运行镜像、不验证启动——证明镜像能跑是 `mv-container-deploy` 的 dev 交付职责（本机 WSL 即默认目标机）。

`detect → 宿主出包（mvn/gradlew/npm）→ 瘦上下文进 WSL → docker build → 输出 IMAGE 与 IMAGE_ID`

- 与 `mv-container-deploy` 的唯一接口是镜像身份（`IMAGE=<repo>:<tag>` 与 `IMAGE_ID`）；部署、验证、晋级、回滚一律在部署侧完成。

## 硬性规范（无例外）

- **宿主出包**：编译出包在宿主按项目约定执行（`mvn -B package`、`./gradlew bootJar`、`npm run build`），镜像与容器不承担编译；宿主工具链未就绪先走 `mv-toolchain-manager`。
- **WSL 硬门禁**：Windows 上镜像构建一律经 WSL；WSL、发行版或 WSL 内 Docker 不可用时明确报错并给出安装指引，不得回退宿主直接构建。
- **只构建不运行**：本 skill 不 `docker run`、不起 compose 栈；「在容器里跑/验证镜像」是部署动作，走 `mv-container-deploy` 的 dev 交付。
- **镜像常驻**：构建镜像与拉取的基础镜像一律保留，任何流程不得 `docker rmi`、`docker system prune`；存储不足时报告用户请示。
- **意图分流**：「打镜像 / 出镜像包」= 本 skill；「本地跑一下 / debug / 断点 / 联调」= `mv-local-debug`（宿主直启）；「部署 dev / 在 WSL 里跑 / 上生产 / 回滚」= `mv-container-deploy`。

## 工具入口

从本次加载的 SKILL.md 路径确定 skill 目录实际绝对路径，赋给 `SKILL_ROOT`（这是文档中的路径变量，agent 不保证自动提供）；路径始终加引号，工作目录保持为用户应用仓库。Python 按环境选择 `python3`、`python` 或 `py -3`。

```bash
# WSL 硬门禁(镜像构建前置);非零退出即终止并如实报告,不得改走宿主构建
bash "${SKILL_ROOT}/scripts/wsl-bridge.sh" require

# 宿主出包:按项目约定执行构建命令,如实记录命令与结果作为构建证据
mvn -B package              # 或 ./gradlew bootJar / npm run build

# 出镜像:image-build.sh 检测产物(build/libs、target、dist|build,或 FF_ARTIFACT),
# 经管道把瘦上下文(产物+Dockerfile)送入 WSL 出镜像;输出唯一镜像 TAG 与 IMAGE_ID
bash "${SKILL_ROOT}/scripts/image-build.sh" build dev app-name
```

## 构建流程

1. 出包前检查：宿主工具链就绪（见 `mv-toolchain-manager`）、Maven/Gradle Wrapper、Node lockfile、`.dockerignore`。用户自有规范优先；特殊产物布局自备 `Dockerfile.delivery`（同样只做产物复制，不做编译）。
2. 检查 Java/Node 版本与前端环境变量是否编译期固化：Vite 构建期嵌入不同 API 地址就不能宣称跨环境同一镜像，必须改为相对路径或运行时配置注入，或明确例外。
3. 宿主出包：按项目约定在宿主执行构建，记录实际命令、退出状态与产物路径；构建失败不进入镜像步骤。构建基于当前工作区时明确 staged、unstaged、untracked 和删除项的范围，如实记录构建输入不是纯 Git SHA。agent shell 内构建失败且特征为 `Unable to establish loopback connection` 时是进程链被安全软件 hook（非工具链问题），改走 `templates/schtasks-build.cmd` 干净链，或交由用户手动构建并如实记录。
4. `image-build.sh build dev <app>` 自动检测产物（Gradle `build/libs` 唯一 boot jar、Maven `target`、Node `dist|build`，或 `FF_ARTIFACT` 显式指定），组装瘦上下文并在 WSL 出镜像；输出 `IMAGE` 与 `IMAGE_ID`，如实转记作为镜像身份证据。镜像构建失败则不进入后续流程。
5. 出包前可先跑宿主侧检查 `bash "${SKILL_ROOT}/scripts/quality-check.sh" quick` 或 `full`；安全扫描 `bash "${SKILL_ROOT}/scripts/security-scan.sh" source .` 用已有 Gitleaks；`FF_REQUIRE_SECURITY_SCAN=1` 后镜像构建要求已有 Trivy，缺失则失败。缺扫描器不能宣称扫描通过。
6. 只读诊断：`python3 "${SKILL_ROOT}/scripts/doctor.py" --project .`（`host_build_chain` 项十秒判定构建链路是否被安全软件拦截，`wsl_resources` 项查 WSL 资源）。

## 验证边界与验收报告

- 区分编译、单元测试、mock 运行时联调和真实依赖联调，每项记录实际输入、命令及结果；签名桩或手工 classpath 的验证只覆盖该范围，不等同于项目完整构建或 CI。
- 对机制问题沿"配置读取 → 业务传递 → 框架/依赖消费 → 实际副作用"追踪，结论附关键文件与行号。
- 验收报告输出：Git SHA 与构建输入状态、宿主构建命令与产物路径、镜像 Tag 与 Image ID、未验证的风险。没有真实构建时明确写出未执行，不可虚构成功；**本 skill 不输出"镜像可以正常启动"类结论——那由 `mv-container-deploy` 的健康验证给出**。

## 常见故障

- `image-build.sh` 报"未找到可交付产物"或"检测到多个可交付产物"时，确认宿主构建命令确实成功且输出目录与栈匹配（Gradle `build/libs`、Maven `target`、Node `dist|build`），多模块或自定义布局用 `FF_ARTIFACT` 显式指定。
- 宿主 gradle/mvn 报 `Unable to establish loopback connection`（`Selector.open` 失败）：安全软件按**进程链** hook，bash/agent 子进程一律被拦——换 JDK、`preferIPv4Stack`、查 afunix 服务均无效。用 `doctor.py` 的 `host_build_chain` 项十秒判定；构建可改经 `templates/schtasks-build.cmd` 执行（schtasks 拉起的进程链不经过被拦截的子进程链）或请用户手动构建。
- WSL 内跑 gradle 时缓存卷必须挂容器用户真实 HOME：gradle 镜像默认用户 `gradle`（HOME=`/home/gradle`），挂 `/root/.gradle` 等于没挂，表现为每次构建全量重新下载依赖与发行版（卷里无 `.ok` 标记即证据）。正确：`-v <vol>:/home/gradle/.gradle` 或统一 `-e GRADLE_USER_HOME=...`。构建慢先分下载时间 vs 编译时间（看日志 Download 行数量），再查 `~/.wslconfig` 的 processors/memory（`doctor.py` 的 `wsl_resources` 项）。
- Mirrored 模式下容器出网可能半残：DNS 只解析 IPv6、TCP 443 不通，`--pull` 基础镜像或构建期下载**永久卡死且不报错**。探测：`docker exec <c> getent hosts <域>` + `bash -c "echo > /dev/tcp/<域>/443"`；降级：用已有常驻 JDK 镜像当运行时底包完成本机验证。WSL Mirrored 网络细节见 [常见故障](references/troubleshooting.md)。

## 安全要点

- 构建上下文只含产物与 Dockerfile，`.dockerignore` 必须显式排除 `.git` 与 `.env*`；秘密与 `.env` 不进上下文、Git 或命令日志。`FF_REQUIRE_SECURITY_SCAN=1` 时构建必须经 Trivy；CI 应落实严格策略。
- 编译出包在宿主完成是团队基线，不得改回容器内编译。Dockerfile 过于复杂时，可选用严格遵循同一环境契约的项目内 CI/CD。
- 部署、晋级、回滚的授权与生产验证规则见 `mv-container-deploy`。

构建输入约定（产物检测、`.dockerignore` 规则、`FF_ARTIFACT`/`FF_RUNTIME_IMAGE`、镜像 TAG 公式与接口契约）读取 [镜像构建契约](references/build-contract.md)；构建期安全要点见 [安全模型](references/security-model.md)。

## 参考

- [references/build-contract.md](references/build-contract.md)：产物检测、瘦上下文、镜像身份契约与接口约定。
- [references/security-model.md](references/security-model.md)：构建期安全要点（构建上下文、扫描策略）。
- [references/troubleshooting.md](references/troubleshooting.md)：镜像构建链路高频故障按症状对照。
