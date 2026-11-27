---
name: mv-delivery-standards
description: 宿主出包并上传服务器构建镜像时使用（打镜像、出镜像包、构建期镜像扫描、给 Spring Boot 与非 Java 模块交付镜像、排查镜像构建失败），核对镜像身份与包校验（Tag 公式、SHA-256 核对、包清单）时使用；处理部署、晋级、回滚契约与健康验证口径、部署失败排查、确认发布状态时使用；编写或审查 Docker Compose 编排（应用加自带数据库的完整栈）、定 healthcheck 探针、定资源限额与日志轮转、凭证分级生成与注入、规划 k3s/k8s 部署映射时使用。容器操作一律在服务器侧经 SSH 访问，宿主不安装 Docker；当前 dev/prod 部署、回滚、状态查询及目标 plan 入口 fail-closed 关闭，参数校验后拒绝、不访问远端，不得宣称部署可用。编码与测试写法归 mv-coding-standards；交付后稳态运维与事故响应归 mv-ops-standards。
---

# 容器交付规范

本 skill 负责 mv 团队自研应用的容器交付全链路与编排规范：宿主出包并上传服务器构建镜像、镜像身份与包校验、部署/晋级/回滚契约与诊断，以及 Docker Compose 编排文件的编写、审查与整改（含探针、凭据分级、k8s 映射）。宿主只编译二进制包，不安装 Docker，容器操作一律在服务器侧经 SSH 访问；编码与测试写法、交付后稳态运维不归本 skill。

**当前 dev/prod 的部署、回滚和状态查询均关闭，目标端 plan 也关闭。** 部署脚本（宿主侧 deploy.sh 与目标侧 target-runner.sh）在参数校验后拒绝执行，不访问远端、不写目标文件、不生成收据。状态查询原会修改目标文件权限和创建目录，因此也不可用。宿主上传会覆盖共享配置，目标端锁无法保护上传；回滚历史排序和记录完整性也未得到保证。修复并验证这些问题后才能重新开放；需要交付时如实报告阻塞，不宣称部署可用。

## SKILL_ROOT 与工具前提

从本次加载的 SKILL.md 路径确定 skill 目录实际绝对路径，显式赋给 `SKILL_ROOT`（这是文档中的路径变量，agent 不保证自动提供）；路径始终加引号，工作目录保持为用户应用仓库。Python 按环境选择 `python3`、`python` 或 `py -3`；缺失时交 `mv-toolchain-manager` 按需准备（`ensure --python 3.12`，宿主完全没有 Python 时用其 `bootstrap-python.sh`），不要求用户手工安装。

## 职责分工与意图分流

| 环节 | 执行位置 | 说明 |
| --- | --- | --- |
| 编译出包 | 宿主 | 语言工具链按项目约定构建（jar、dist 等），工具链由 `mv-toolchain-manager` 准备 |
| 版本标识与上传 | 宿主 → 服务器 | 出包时生成包 Tag，包上传至构建点包目录并核对 SHA-256 |
| 镜像构建 | 服务器 | 按模块内 `Dockerfile.delivery` 执行 `docker build`，输出 `IMAGE=` 与 `IMAGE_ID=` |
| 部署、晋级与回滚 | 服务器 | 按交付契约部署、健康验证、同镜像晋级与回滚（入口当前关闭，见容器交付节） |
| 编排文件 | 项目仓库 | Docker Compose 编写评审、探针、限额、凭据与 k8s 映射规范 |

- 构建点与部署目标同侧：单机部署为部署机自身；集群部署为镜像仓库所在节点，其余节点经镜像仓库分发。
- 构建点统一经 SSH 通道访问（`FF_BUILD_TARGET=user@host`），开发服务器与生产服务器同一待遇；不设宿主侧容器构建或载入通道，宿主不安装 Docker。构建点的实际位置不进入流程判断——即使恰为本机 WSL，出包上传、SHA-256 核对与 `docker build` 仍全部经 SSH 执行，不使用 `wsl.exe`、`\\wsl$` 等宿主旁路直访或拷贝。
- 意图分流：「打镜像 / 出镜像包」走镜像构建节；「部署 dev / 在容器里跑 / 上生产 / 回滚 / 确认发布状态」走容器交付节（当前关闭）；「写 compose / 定探针 / 定限额 / 管凭证 / 排查编排配置」走 Compose 编排节。
- 多模块项目：每个模块独立定义、独立出镜像，在目标模块目录执行；默认不建聚合的 `image-build` 模块。

## 镜像构建

### 构建流程

1. 出包前检查：宿主工具链就绪（见 `mv-toolchain-manager`）、Maven/Gradle Wrapper、Node lockfile；目标模块已按 [构建契约](references/build-contract.md) 备好 `Dockerfile.delivery`；`.dockerignore` 显式排除 `.git` 与 `.env*`。用户自有规范优先。
2. 检查版本与前端环境变量是否编译期固化：Vite 构建期嵌入不同 API 地址就不能宣称跨环境同一镜像，必须改为相对路径或运行时配置注入，或明确例外。
3. 宿主出包：按项目约定在宿主执行构建，记录实际命令、退出状态与产物路径；构建失败不进入上传。构建基于当前工作区时明确 staged、unstaged、untracked 和删除项的范围，如实记录构建输入不是纯 Git SHA。Windows 宿主出包前一律预设 Windows JDK loopback 参数 `JAVA_TOOL_OPTIONS`（预设内容与排查见 `mv-toolchain-manager`「Windows 宿主 JDK 预设」），构建报 `Unable to establish loopback connection` 即预设未生效，核查环境变量覆盖源后重试。
4. 生成包版本并上传：出包时按 Tag 公式生成包 Tag（见 [构建契约](references/build-contract.md)），包上传至构建点 `~/.mv/delivery-standards/packages/<app>/`，上传与构建统一经 SSH（`FF_BUILD_TARGET`）。
5. 服务器构建镜像：构建点核对上传包 SHA-256 与出包时计算值一致后，按模块 `Dockerfile.delivery` 组装瘦上下文（只含包与 Dockerfile，源码不出宿主）执行 `docker build`；输出 `IMAGE` 与 `IMAGE_ID` 如实转记作为镜像身份证据，并把包名、校验和、镜像引用写入包清单。核对不匹配或构建失败不输出镜像身份。
6. 出包前可先跑宿主侧检查 `bash "${SKILL_ROOT}/scripts/quality-check.sh" quick` 或 `full`；安全扫描 `bash "${SKILL_ROOT}/scripts/security-scan.sh" source .` 用已有 Gitleaks；`FF_REQUIRE_SECURITY_SCAN=1` 时由构建点侧 Trivy 做镜像门禁，构建点缺 Trivy 即在构建前失败。缺扫描器不能宣称扫描通过。
7. 只读诊断：`python3 "${SKILL_ROOT}/scripts/image-doctor.py" --project .`（工具链与基础命令可用性自检）。

一条龙命令（`FF_BUILD_TARGET` 指向构建点 `user@host`，必填）：

```bash
FF_BUILD_TARGET=user@host bash "${SKILL_ROOT}/scripts/image-build.sh" build dev app-name

# 宿主出包:按项目约定执行构建命令,如实记录命令与结果作为构建证据
mvn -B package              # 或 ./gradlew bootJar / npm run build
```

### 验证边界与验收报告

- 区分编译、单元测试、mock 运行时联调和真实依赖联调，每项记录实际输入、命令及结果；签名桩或手工 classpath 的验证只覆盖该范围，不等同于项目完整构建或 CI。
- 对机制问题沿「配置读取 → 业务传递 → 框架/依赖消费 → 实际副作用」追踪，结论附关键文件与行号。
- 验收报告输出：Git SHA 与构建输入状态、宿主构建命令与产物路径、包名与 SHA-256、镜像 Tag 与 Image ID、未验证的风险。没有真实构建时明确写出未执行，不可虚构成功；不输出「镜像可以正常启动」类结论——那由容器交付的健康验证给出（入口当前关闭时如实报告阻塞）。

### 常见故障

高频故障按症状对照 [常见故障](references/troubleshooting.md)：模块未备 `Dockerfile.delivery`（先在模块内补齐基线再重试，不在脚本或编排层代写镜像配置）；服务器侧包核对不匹配（重出包重传，不带病构建）；构建点容器环境不可用（明确报错请示，不在宿主侧代构建）；基础镜像拉取停滞（在构建点侧检查仓库域名解析、HTTPS 连通性与 Docker 代理，已有兼容的常驻运行时镜像时用 `FF_RUNTIME_IMAGE` 指定后重试并记录来源与结果，构建入口固定带 `--pull`）；宿主 Gradle 反复下载依赖（核对实际构建进程的用户目录、`GRADLE_USER_HOME` 与 Wrapper 缓存，区分下载耗时与编译耗时，不把编译转入服务器或容器）。

镜像身份交接、包清单核对、`-dirty` 镜像拒绝晋级 prod 等契约细节读取 [构建契约](references/build-contract.md)；构建期安全要点（出包、上传校验、扫描策略）见 [构建安全模型](references/build-security-model.md)。

## 容器交付

出包与镜像构建见镜像构建节；镜像构建期扫描与包版本管理按镜像构建节执行。

### 可用诊断

- `bash "${SKILL_ROOT}/scripts/deploy-preflight.sh" dev APP` 或 `prod APP` 检查配置并经 SSH 检查目标机；此独立预检会访问远端，不表示交付入口可用。
- `python3 "${SKILL_ROOT}/scripts/doctor.py" --project .` 执行只读本机诊断（`ssh` 项：交付宿主只需 Git 与 SSH 客户端，容器环境在目标机校验），不构成发布门禁。
- 需要交付时报告阻塞及未执行的部署、健康验证和业务验证，不声称已有新的部署记录或收据。

### 发布门禁与自检

- 本地预检：`bash "${SKILL_ROOT}/scripts/deploy-preflight.sh" dev APP` 或 `prod APP`（需对应 `FF_DEV_SSH` / `FF_PROD_SSH`），检查 env 跟踪、构建上下文配置与目标机 SSH 连通及 Compose v2。
- 环境契约（`.env` 文件、SSH、Compose 项目描述、目标目录布局）读取 [配置参考](references/configuration.md)；详细契约（项目输入、部署身份、双探针、迁移与部署后验证、身份交接与回滚证据）见 [交付契约](references/deployment-contract.md)；部署侧安全要求见 [交付安全模型](references/deploy-security-model.md)。
- 环境变量（`FF_DEV_SSH`、`FF_PROD_SSH`、`FF_HEALTH_URL`、`FF_READY_TIMEOUT` 等）的语义与默认值以 [配置参考](references/configuration.md) 的表格为单一事实源。

## Compose 编排

面向 mv 团队自托管与自研应用共用的编排编写规范：项目部署栈按环境隔离；dev 可使用跨项目共享 infra。这是规范型 Skill，在编写、审查、整改 compose 与 k8s 编排时引用；不执行部署动作，不写部署收据，不做交付后巡检。容器交付落到目标机的 compose 文件同样遵守本节规范。优先级：用户明确需求和项目已采纳的规范 / ADR → 本规范 → 官方默认。规范中的数值（探针间隔、限额表、轮转参数）为默认基线，项目按实际负载调整并记录。三条铁律见硬约束节。

### 关键规则

1. 栈名全小写 DNS-1123 label（小写字母数字、连字符分段，形如 `halo-dev`），取官方产品名小写、连字符保留（`open-webui`），跨产品聚合类用语义词；目录名 = 栈名 = compose 项目名，不设顶层 `name:`，不设 `container_name`。k8s 侧 namespace 同规则。
2. 一个项目一个目录：`{栈名}/docker-compose.yaml` 与项目配置文件同目录；部署命令 `cd {栈名} && docker compose up -d`。
3. 显式声明网络 `networks.default.name: {栈名}-net`，随栈名同步；跨栈通信走共享 external 网络，禁止经宿主机发布端口或 `localhost` 绕行；目标是宿主机原生进程时才允许 `host.docker.internal` 并声明 `extra_hosts`，不为「将来可能用」保留投机映射。
4. 端口判定逐服务自上而下：反代终结 TLS → 后端只发布 HTTP 端口；栈内数据库/中间件 → 不发布端口，映射以注释声明；官方文档有 host 端口示例 → 取示例值；无示例 → host 端口 = 容器内官方监听端口；同一 compose 内多服务端口冲突 → 后者 +1 递增；跨栈重复不处理，按需启停。偏离必须行内注释写明原因，无注释偏离即违规。
5. 镜像固定具体版本，禁 `latest`/`main`/无标签；有 Alpine 变体一律用 Alpine（glibc 依赖或 C 扩展本地编译不兼容时退 `-slim`/官方变体并注释）；晋级使用已验证的同一镜像身份，验证、发布和回滚期间环境可暂时运行不同版本；上游仅维护 latest 的镜像允许 latest，EOL 镜像继续使用须行内注释登记理由与评估日期。
6. healthcheck 必须证明「服务在履职」：专用健康端点 > 官方探针/脚本 > 不配；纯 TCP 探测与根路径探针是假绿，禁止作为手段；探针工具与端点都须实测核实，无法确认即按「不配」处理——假红探针比没有探针更糟。判定树与 start_period 初始值见 [references/healthcheck-probes.md](references/healthcheck-probes.md)。
7. 启动顺序用 `depends_on` + `condition: service_healthy`；被依赖方无探针时退 `service_started`；一次性初始化容器不配探针、restart 省略，依赖方用 `service_completed_successfully` fail-closed；每服务 `restart: unless-stopped`（初始化容器除外）。
8. YAML 写法：`command` 内联列表、`environment` map、`volumes`/`ports` 列表；service 键按 image→privileged→command→environment→volumes→ports→networks→extra_hosts→init→shm_size→stop_grace_period→secrets→healthcheck→depends_on→logging→restart→deploy 排列，顶层键 volumes→networks→secrets→services；删除注释掉的配置行，偏离注释与分块标题保留。
9. 数据卷默认命名卷（`{用途}-data`/`{用途}-home`，判定见 [references/compose-rules.md](references/compose-rules.md)）；仅预置仓库配置与挂载宿主机资源两类例外用 bind，bind 源路径用 `./` 或绝对路径，禁 `~`。
10. 凭据分级生成与注入：按 [references/credentials.md](references/credentials.md) 的分级表选强度与命令生成，统一 `.env` 插值注入；凭据不进 Git（真实值不入版本控制，生产/CI 环境用 secrets manager），分类型生成命令与轮换周期见 [references/credentials.md](references/credentials.md)。
11. Spring Boot 项目经环境变量宽松绑定注入（`spring.datasource.url` → `SPRING_DATASOURCE_URL`），不走 PARAMS 转发或启动包装；禁止自定义 entrypoint 包装脚本改配置，配置走组件官方渠道，发现自建包装脚本即回归官方方式并删除脚本。
12. 所有服务配 `deploy.resources.limits`（防止单服务耗尽宿主机）与 logging 限额（`max-size`/`max-file`）；参数按服务类型取值表执行，见 [references/resources-logging.md](references/resources-logging.md)。
13. 检测到透明加密软件时，按当前宿主已验证的透明通道读写 `.env`、SQL 等文件，不预设所有命令行或编辑器具有相同行为；传输与部署仍经 SSH，在目标服务器验证文件可读、配置可解析，不以宿主读取正常代替目标侧验证。
14. 新增栈按 SOP 执行，部署后过校验清单；两份清单见 [references/sop-checklist.md](references/sop-checklist.md)。
15. k3s/k8s 部署映射（namespace、probe、Secret、requests/limits）见 [references/k8s-mapping.md](references/k8s-mapping.md)；compose 规则到 k8s 的对应关系与差异点以该文件为准。

### 编排输出

交付说明列出：栈名与目录、逐服务判定记录（端口、探针、卷形态、限额）、偏离项及行内注释位置、凭据生成与落点（不含值）、部署后校验结果；未执行的检查如实写「未执行」。

## 硬约束

镜像构建：

- **宿主只出包**：编译出包在宿主按项目约定执行（`mvn -B package`、`./gradlew bootJar`、`npm run build`），镜像与容器不承担编译；宿主工具链未就绪先走 `mv-toolchain-manager`。宿主不安装 Docker，不执行镜像构建、镜像载入或任何容器操作。编译出包在宿主完成、镜像构建在服务器执行是团队基线，不得把镜像构建改回宿主；Dockerfile 过于复杂时，可选用严格遵循同一环境契约的项目内 CI/CD。
- **镜像定义随模块**：各栈镜像基线写在模块内 `Dockerfile.delivery`（Node 静态前端可用 `${SKILL_ROOT}/templates/Dockerfile.web`），只复制产物不做编译；脚本与编排层不得另写一套镜像配置，否则镜像行为与模块配置脱节。
- **镜像构建在服务器**：包上传至构建点并核对 SHA-256 后执行 `docker build`；核对不匹配按构建失败处理并如实报告，不静默降级。构建点容器环境不可用时明确报错请示，不改在宿主构建。
- **包与镜像同 Tag**：包版本标识在出包时生成，与镜像共用同一 Tag，同一 Tag 只对应一个包，重出包产生新 Tag；包落服务器 `~/.mv/delivery-standards/packages/<app>/` 并维护包清单。
- **只构建不运行**：镜像构建不 `docker run`、不起 compose 栈；「在容器里跑/验证镜像」属容器交付职责。
- **包与镜像常驻**：构建包、构建镜像与拉取的基础镜像一律保留，任何流程不得删除包、`docker rmi`、`docker system prune`；存储不足时报告用户请示。

容器交付：

- **入口当前关闭**：dev/prod 部署、回滚、状态查询及目标 plan 在参数校验后拒绝执行，不访问远端、不写目标文件、不生成收据；禁止以开发命令或本地容器冒充 dev/prod 部署成功。
- **容器操作在目标服务器**：使用 Compose 管理同一部署身份的组件，不在宿主直接启动容器。
- **生产授权**：恢复生产操作须取得用户明确授权，核对镜像身份、配置、健康和恢复方案；`--approve-prod` 不能代替授权。禁止生产 Debug Agent、明文输出 secret、无确认修改数据库 schema。
- **回滚边界**：应用回滚不恢复数据库迁移或外部副作用。
- **秘密边界**：凭据和 `.env.<env>`、私钥不得进入 Git 或命令日志；配置与 Compose 文件一律经 SSH 通道传输到目标机，落盘即按 600 收口；主机密钥按 SSH `known_hosts` 机制验证，不禁用该检查；不将不可信的镜像名或环境值传入部署命令。

Compose 编排：

- **项目部署一项目一 stack/ns**：项目业务组件按项目与环境划分栈；dev 可连接跨项目共享的独立 infra 栈，UAT、prod 等非 dev 环境的数据库与中间件随项目栈隔离。
- **环境隔离**：项目部署的不同环境使用独立 stack/ns（如 `halo-dev` / `halo-prod`），数据卷、数据库、网络、凭据互不共享；dev 共享 infra 与 UAT、prod 等其他环境隔离，不跨环境连接。
- **共享范围**：跨项目共享数据库、缓存、消息或文件服务仅限 dev 环境，包含本地开发及部署到开发服务器的应用；UAT、prod 等其他环境不跨项目共享这些实例。共享实例以项目专用资源、账户和权限隔离，连接及验收要求见 mv-design-standards 的仓库布局参考。

## 输出与边界

- 镜像构建输出：Git SHA 与构建输入状态、宿主构建命令与产物路径、包名与 SHA-256、镜像 Tag 与 Image ID、未验证的风险；镜像构建证据写明所用包名与校验和，部署收据按 Image ID 关联镜像与包版本，沿 Tag 与 Image ID 可回溯到包。
- 编排输出：见「编排输出」小节。
- 边界：编码与测试写法（含应用侧 readiness/liveness 双探针端点实现、应用内日志规范）归 mv-coding-standards；交付后稳态运维（日志聚合、备份演练、巡检、老化重扫）与事故响应归 mv-ops-standards；跨栈凭据生命周期、数据保护与安全评审归 mv-security-standards；宿主工具链准备归 mv-toolchain-manager。运行期故障排查时探针语义与健康日志核验按 Compose 编排规范执行，容器操作本身属容器交付职责。

## 参考

- [references/build-contract.md](references/build-contract.md)：包版本与镜像身份契约、各栈 Dockerfile.delivery 基线、产物检测与服务器侧构建约定。
- [references/build-security-model.md](references/build-security-model.md)：构建期安全要点（出包、上传校验、扫描策略）。
- [references/troubleshooting.md](references/troubleshooting.md)：出包与镜像构建链路高频故障按症状对照。
- [references/configuration.md](references/configuration.md)：交付环境变量、env 文件样例、目标目录布局与项目可覆盖模板。
- [references/deployment-contract.md](references/deployment-contract.md)：交付契约：项目输入、部署身份、双探针、交付流程、迁移与部署后验证、身份交接与回滚证据。
- [references/deploy-security-model.md](references/deploy-security-model.md)：部署侧安全模型（授权、秘密信息、生产验证、失败恢复）。
- [references/compose-rules.md](references/compose-rules.md)：命名、网络、端口、镜像、YAML 键序、数据卷形态与卷名后缀判定。
- [references/credentials.md](references/credentials.md)：凭据分级生成表、.env 注入机制、轮换周期与透明加密环境注意。
- [references/healthcheck-probes.md](references/healthcheck-probes.md)：探针判定树、假绿清单、start_period 初始值表与实测回填。
- [references/k8s-mapping.md](references/k8s-mapping.md)：compose 规则到 k3s/k8s 的映射与差异点。
- [references/resources-logging.md](references/resources-logging.md)：资源限额表与日志轮转参数。
- [references/sop-checklist.md](references/sop-checklist.md)：新增栈 SOP 与部署后校验清单。
