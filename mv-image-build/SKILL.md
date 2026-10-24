---
name: mv-image-build
description: 宿主出包并在服务器构建容器镜像时使用本 skill：宿主只编译二进制包（Maven/Gradle/npm 按项目约定），包上传服务器后由服务器侧 docker build 出镜像；镜像定义与模块同源，各栈模块内自备 Dockerfile.delivery（Node 静态前端可用内置模板），Java 与非 Java 统一走「出包 → 上传 → 服务器构建」，构建点经 SSH 访问，无宿主侧特例。触发场景：打镜像、出镜像包、构建交付镜像、给 Spring Boot 模块打镜像、非 Java 模块交付镜像、排查镜像构建失败。核心原则：宿主不安装 Docker、不执行镜像构建与容器操作；镜像构建点与部署目标同侧（单机即部署机，集群为镜像仓库所在节点）；包版本标识出包时生成、包与镜像同 Tag 一一对应，包版本管理在服务器侧；本 skill 只构建不运行——镜像验证与部署归 mv-container-deploy；包与镜像常驻不清理。本机直启调试归 mv-local-debug。
---

# 镜像构建

本 skill 负责交付管线的前半段：**宿主编译二进制包 → 上传部署服务器 → 服务器构建镜像，输出镜像身份**。宿主只出包，镜像构建与容器运行都在服务器执行：

| 环节 | 执行位置 | 说明 |
| --- | --- | --- |
| 编译出包 | 宿主 | 语言工具链按项目约定构建（jar、dist 等），工具链由 `mv-toolchain-manager` 准备 |
| 版本标识与上传 | 宿主 → 服务器 | 出包时生成包 Tag，包上传至构建点包目录并核对 SHA-256 |
| 镜像构建 | 服务器 | 按模块内 `Dockerfile.delivery` 执行 `docker build`，输出 `IMAGE=` 与 `IMAGE_ID=` |

- 构建点与部署目标同侧：单机部署为部署机自身；集群部署为镜像仓库所在节点，其余节点经镜像仓库分发。
- 构建点统一经 SSH 通道访问（`FF_BUILD_TARGET=user@host`），开发服务器与生产服务器同一待遇；不设宿主侧容器构建或载入通道，宿主不安装 Docker。
- 多模块项目：**每个模块独立定义、独立出镜像**，在目标模块目录执行；默认不建聚合的 `image-build` 模块。
- 不运行镜像、不验证启动——证明镜像能跑是 `mv-container-deploy` 的 dev 交付职责。

## 硬性规范（无例外）

- **宿主只出包**：编译出包在宿主按项目约定执行（`mvn -B package`、`./gradlew bootJar`、`npm run build`），镜像与容器不承担编译；宿主工具链未就绪先走 `mv-toolchain-manager`。宿主不安装 Docker，不执行镜像构建、镜像载入或任何容器操作。
- **镜像定义随模块**：各栈镜像基线写在模块内 `Dockerfile.delivery`（Node 静态前端可用本 skill 的 `templates/Dockerfile.web`），只复制产物不做编译；脚本与编排层不得另写一套镜像配置，否则镜像行为与模块配置脱节。
- **镜像构建在服务器**：包上传至构建点并核对 SHA-256 后执行 `docker build`；核对不匹配按构建失败处理并如实报告，不静默降级。构建点容器环境不可用时明确报错请示，不改在宿主构建。
- **包与镜像同 Tag**：包版本标识在出包时生成，与镜像共用同一 Tag，同一 Tag 只对应一个包，重出包产生新 Tag；包落服务器 `~/.mv/image-build/packages/<app>/` 并维护包清单（见 [构建契约](references/build-contract.md)）。
- **只构建不运行**：本 skill 不 `docker run`、不起 compose 栈；「在容器里跑/验证镜像」走 `mv-container-deploy` 的 dev 交付。
- **包与镜像常驻**：构建包、构建镜像与拉取的基础镜像一律保留，任何流程不得删除包、`docker rmi`、`docker system prune`；存储不足时报告用户请示。
- **意图分流**：「打镜像 / 出镜像包」= 本 skill；「本地跑一下 / debug / 断点 / 联调」= `mv-local-debug`（宿主直启）；「部署 dev / 在容器里跑 / 上生产 / 回滚」= `mv-container-deploy`。

## 工具入口

从本次加载的 SKILL.md 路径确定 skill 目录实际绝对路径，赋给 `SKILL_ROOT`（这是文档中的路径变量，agent 不保证自动提供）；路径始终加引号，工作目录保持为用户应用仓库。Python 按环境选择 `python3`、`python` 或 `py -3`；缺失时交 `mv-toolchain-manager` 按需准备（`ensure --python 3.12`，宿主完全没有 Python 时用其 `bootstrap-python.sh`），不要求用户手工安装。

```bash
# 出包→上传→服务器构建一条龙:FF_BUILD_TARGET 指向构建点(user@host),必填
FF_BUILD_TARGET=user@host bash "${SKILL_ROOT}/scripts/image-build.sh" build dev app-name

# 宿主出包:按项目约定执行构建命令,如实记录命令与结果作为构建证据
mvn -B package              # 或 ./gradlew bootJar / npm run build

# 宿主侧检查与扫描(不依赖容器运行时)
bash "${SKILL_ROOT}/scripts/quality-check.sh" quick
bash "${SKILL_ROOT}/scripts/security-scan.sh" source .
python3 "${SKILL_ROOT}/scripts/doctor.py" --project .
```

## 构建流程

1. 出包前检查：宿主工具链就绪（见 `mv-toolchain-manager`）、Maven/Gradle Wrapper、Node lockfile；目标模块已按 [构建契约](references/build-contract.md) 备好 `Dockerfile.delivery`；`.dockerignore` 显式排除 `.git` 与 `.env*`。用户自有规范优先。
2. 检查版本与前端环境变量是否编译期固化：Vite 构建期嵌入不同 API 地址就不能宣称跨环境同一镜像，必须改为相对路径或运行时配置注入，或明确例外。
3. 宿主出包：按项目约定在宿主执行构建，记录实际命令、退出状态与产物路径；构建失败不进入上传。构建基于当前工作区时明确 staged、unstaged、untracked 和删除项的范围，如实记录构建输入不是纯 Git SHA。agent shell 内构建失败且特征为 `Unable to establish loopback connection` 时是进程链被安全软件 hook（仅 Windows 宿主现象，非工具链问题），改走 `templates/schtasks-build.cmd` 干净链，或交由用户手动构建并如实记录。
4. 生成包版本并上传：出包时按 Tag 公式生成包 Tag（见 [构建契约](references/build-contract.md)），包上传至构建点 `~/.mv/image-build/packages/<app>/`，上传与构建统一经 SSH（`FF_BUILD_TARGET`）。
5. 服务器构建镜像：构建点核对上传包 SHA-256 与出包时计算值一致后，按模块 `Dockerfile.delivery` 组装瘦上下文（只含包与 Dockerfile，源码不出宿主）执行 `docker build`；输出 `IMAGE` 与 `IMAGE_ID` 如实转记作为镜像身份证据，并把包名、校验和、镜像引用写入包清单。核对不匹配或构建失败不输出镜像身份。
6. 出包前可先跑宿主侧检查 `bash "${SKILL_ROOT}/scripts/quality-check.sh" quick` 或 `full`；安全扫描 `bash "${SKILL_ROOT}/scripts/security-scan.sh" source .` 用已有 Gitleaks；`FF_REQUIRE_SECURITY_SCAN=1` 时由构建点侧 Trivy 做镜像门禁，构建点缺 Trivy 即在构建前失败。缺扫描器不能宣称扫描通过。
7. 只读诊断：`python3 "${SKILL_ROOT}/scripts/doctor.py" --project .`（`host_build_chain` 项十秒判定构建链路是否被安全软件拦截，仅 Windows 宿主执行，其余宿主自动跳过）。

## 验证边界与验收报告

- 区分编译、单元测试、mock 运行时联调和真实依赖联调，每项记录实际输入、命令及结果；签名桩或手工 classpath 的验证只覆盖该范围，不等同于项目完整构建或 CI。
- 对机制问题沿"配置读取 → 业务传递 → 框架/依赖消费 → 实际副作用"追踪，结论附关键文件与行号。
- 验收报告输出：Git SHA 与构建输入状态、宿主构建命令与产物路径、包名与 SHA-256、镜像 Tag 与 Image ID、未验证的风险。没有真实构建时明确写出未执行，不可虚构成功；**本 skill 不输出"镜像可以正常启动"类结论——那由 `mv-container-deploy` 的健康验证给出**。

## 常见故障

- 模块未备 `Dockerfile.delivery`：镜像定义属模块配置，先在模块内按 [构建契约](references/build-contract.md) 补齐基线再重试；不得在脚本或编排层代写镜像配置。
- 服务器侧包核对不匹配（SHA-256 与出包记录不一致）：上传不完整或包在途中被改动，重出包重传，不带病构建。
- 构建点容器环境不可用（无 Docker、无法访问镜像仓库节点）：明确报错并请示，不在宿主侧代构建。
- 基础镜像拉取停滞：在构建点侧检查仓库域名解析、HTTPS 连通性与 Docker 代理；已有兼容的常驻运行时镜像时可用 `FF_RUNTIME_IMAGE` 指定后重试，并记录来源与实际结果；构建入口固定带 `--pull`，本地存在基础镜像不能承诺离线成功。
- 宿主 gradle/mvn 报 `Unable to establish loopback connection`（`Selector.open` 失败，仅 Windows 宿主）：安全软件按**进程链** hook，bash/agent 子进程一律被拦——换 JDK、`preferIPv4Stack`、查 afunix 服务均无效。用 `doctor.py` 的 `host_build_chain` 项十秒判定；构建可改经 `templates/schtasks-build.cmd`（配同目录 `run-hidden.vbs` 隐藏窗口，完整步骤见模板头注释）或请用户手动构建。
- 宿主 Gradle 反复下载依赖：核对实际构建进程的用户目录、`GRADLE_USER_HOME` 与 Wrapper 缓存，区分下载耗时与编译耗时；不得把编译转入服务器或容器，详见 [常见故障](references/troubleshooting.md)。

## 安全要点

- 包与瘦上下文只含产物与 Dockerfile，源码不出宿主；`.dockerignore` 必须显式排除 `.git` 与 `.env*`，秘密与 `.env` 不进上下文、Git 或命令日志。上传经 SSH 通道并做包密文头检查（透明加密环境防线），构建点核对 SHA-256，不匹配即删除损坏包并中止。`FF_REQUIRE_SECURITY_SCAN=1` 时由构建点 Trivy 把关；CI 应落实严格策略。
- 编译出包在宿主完成、镜像构建在服务器执行是团队基线，不得把镜像构建改回宿主。Dockerfile 过于复杂时，可选用严格遵循同一环境契约的项目内 CI/CD。
- 部署、晋级、回滚的授权与生产验证规则见 `mv-container-deploy`。

产物检测、包目录与清单、各栈 `Dockerfile.delivery` 基线、环境变量、镜像 TAG 公式与包版本管理读取 [镜像构建契约](references/build-contract.md)；构建期安全要点见 [安全模型](references/security-model.md)。

## 参考

- [references/build-contract.md](references/build-contract.md)：包版本与镜像身份契约、各栈 Dockerfile.delivery 基线、产物检测与服务器侧构建约定。
- [references/security-model.md](references/security-model.md)：构建期安全要点（出包、上传校验、扫描策略）。
- [references/troubleshooting.md](references/troubleshooting.md)：出包与镜像构建链路高频故障按症状对照。
