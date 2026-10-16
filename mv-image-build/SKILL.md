---
name: mv-image-build
description: 本机 Windows 工作机上把 Java（Gradle/Maven）/Node 项目的宿主产物打包为容器镜像，以及"本地跑一下"/启动/debug/断点/热更新/本机联调时统一使用本 skill。触发场景：本地启动应用、出包/打镜像、本机起容器调测、排查宿主构建或启动失败。核心原则：编译出包在宿主完成（宿主工具链由 mv-toolchain-manager 准备）；启动类意图默认宿主直启，且必须前台可见 shell 运行、禁止后台静默；镜像构建与容器调测一律经 WSL，没有 WSL 即明确失败，容器路径不回退宿主；镜像常驻不清理。部署到环境、晋级生产与回滚归 mv-container-deploy，宿主工具链安装切换归 mv-toolchain-manager，Git 提交发布归 mv-git-publisher。
---

# 镜像出包与本地调测

本 skill 负责交付管线的前半段：**宿主出包 → 宿主直启（默认）或 WSL 瘦镜像 → 容器调测（显式）**。产物镜像与镜像身份（`IMAGE=<repo>:<tag>`、`IMAGE_ID`）是交给 `mv-container-deploy` 的唯一接口，部署、晋级、回滚一律在部署侧完成。

`detect → 宿主出包（mvn/gradlew/npm）→ 宿主直启调测（默认）｜瘦上下文进 WSL → docker build 镜像 → 容器调测（显式）`

- 宿主工具链准备见 `mv-toolchain-manager`，它是出包的前置条件；镜像与容器不承担编译。
- 与 Spec Kit `implement` 兼容，不重写需求规划、测试编排或版本管理；与 Git 独立，不暗中 commit。

## 硬性规范（无例外）

- **宿主直启默认**：启动类意图（"本地跑一下 / 跑起来 / debug / 断点 / 热更新 / 联调"）默认在宿主直接启动应用（`java -jar`、`mvn spring-boot:run`、`./gradlew bootRun`、`npm run dev`、`pnpm dev` 等）；仅当用户明确要求"在容器里跑 / 验证镜像"时才走容器调测。
- **前台可见硬约束**：宿主直启一律在用户可见的前台 shell 运行（agent 终端面板或新终端窗口），日志实时可见、用户可随时 Ctrl-C 停止；禁止 `start /b`、`&`/`nohup` 后台化、隐藏窗口、把输出整体重定向到日志文件等静默运行。收尾时如实交代仍在运行的进程与其所在窗口。
- **WSL 硬门禁（容器路径）**：Windows 上镜像构建与容器调测一律经 WSL；WSL、发行版或 WSL 内 Docker 不可用时容器路径明确报错并给出安装指引，不得静默改走宿主直启（可提示宿主直启是另一模式）。宿主承担编译出包、宿主侧检查与应用直启；容器路径不回退宿主。
- **镜像常驻**：构建镜像与拉取的基础镜像一律保留，任何流程不得 `docker rmi`、`docker system prune` 等清理动作；存储不足时报告用户请示。构建缓存 volume 可能被 prune 清空，依赖重复下载先查 volume 是否还在。
- **意图分流**："启动 / 本地跑一下 / debug / 断点 / 联调" = 宿主直启（本 skill，前台可见）；"在容器里跑 / 验证镜像" = 容器调测（本 skill，显式要求）；"部署 dev / 上生产 / 回滚" = `mv-container-deploy`。"上生产"只在用户明确授权后操作，不因含糊的"跑起来"自动操作 prod。

## 工具入口

从本次加载的 SKILL.md 路径确定 skill 目录实际绝对路径，赋给 `SKILL_ROOT`（这是文档中的路径变量，agent 不保证自动提供）；路径始终加引号，工作目录保持为用户应用仓库。Python 按环境选择 `python3`、`python` 或 `py -3`。

```bash
# 宿主直启(启动类默认):前台可见 shell 运行,用户 Ctrl-C 停止,禁止后台静默
# agent 有可见终端面板时用面板执行;CLI 环境开新终端窗口,例:
MSYS_NO_PATHCONV=1 cmd.exe /c start "app" /d "D:\repo" cmd /k "java -jar target\app.jar"
# 或 wt.exe -d "D:\repo" cmd /k "npm run dev"

# WSL 硬门禁(容器路径);非零退出即终止并如实报告,不得静默改走宿主直启
bash "${SKILL_ROOT}/scripts/wsl-bridge.sh" require

# 宿主出包:按项目约定执行构建命令,如实记录命令与结果作为构建证据
mvn -B package              # 或 ./gradlew bootJar / npm run build

# 出镜像:image-build.sh 检测产物(build/libs、target、dist|build,或 FF_ARTIFACT),
# 经管道把瘦上下文(产物+Dockerfile)送入 WSL 出镜像;输出唯一镜像 TAG 与 IMAGE_ID
bash "${SKILL_ROOT}/scripts/image-build.sh" build dev app-name
```

## 宿主出包与镜像构建流程

1. 出包前检查：宿主工具链就绪（见 `mv-toolchain-manager`）、Maven/Gradle Wrapper、Node lockfile、`.dockerignore`。用户自有规范优先；特殊产物布局自备 `Dockerfile.delivery`（同样只做产物复制，不做编译）。
2. 检查 Java/Node 版本与前端环境变量是否编译期固化：Vite 构建期嵌入不同 API 地址就不能宣称跨环境同一镜像，必须改为相对路径或运行时配置注入，或明确例外。
3. 宿主出包：按项目约定在宿主执行构建（如 `mvn -B package`、`gradle bootJar`、`npm run build`），记录实际命令、退出状态与产物路径；构建失败不进入镜像步骤。构建基于当前工作区时明确 staged、unstaged、untracked 和删除项的范围，如实记录构建输入不是纯 Git SHA。agent shell 内构建失败且特征为 `Unable to establish loopback connection` 时是进程链被安全软件 hook（非工具链问题），改走 `templates/schtasks-build.cmd` 干净链，或交由用户手动构建并如实记录。
4. `image-build.sh build dev <app>` 自动检测产物（Gradle `build/libs` 唯一 boot jar、Maven `target`、Node `dist|build`，或 `FF_ARTIFACT` 显式指定），组装瘦上下文并在 WSL 出镜像；输出 `IMAGE` 与 `IMAGE_ID`，如实转记作为镜像身份证据。镜像构建失败则不进入后续流程。
5. 出包前可先跑宿主侧检查 `bash "${SKILL_ROOT}/scripts/quality-check.sh" quick` 或 `full`；安全扫描 `bash "${SKILL_ROOT}/scripts/security-scan.sh" source .` 用已有 Gitleaks；`FF_REQUIRE_SECURITY_SCAN=1` 后镜像构建要求已有 Trivy，缺失则失败。缺扫描器不能宣称扫描通过。
6. 只读诊断：`python3 "${SKILL_ROOT}/scripts/doctor.py" --project .`（`host_build_chain` 项十秒判定构建链路是否被安全软件拦截）。

## 本地调测流程

### 宿主直启（默认）

1. 确认启动意图与命令：启动类意图默认宿主直启（产物 `java -jar`，或按项目约定 `mvn spring-boot:run`、`./gradlew bootRun`、`npm run dev`、`pnpm dev`）；用户点名"在容器里跑 / 验证镜像"时改走容器调测。检查项目运行参数与现有占用端口（含 WSL Mirrored 共享端口层），默认只启动用户目标组件，不改变仓库或系统配置。
2. 只加载 `.env.local` 或项目已允许的开发环境设置，不自动复用 `.env.prod`、密钥或服务器配置；确认 API 请求目标为本地/dev，绝不默认连生产数据库或对生产数据做写操作。
3. 前台可见启动：在用户可见的前台 shell 中运行（终端面板或新终端窗口，见工具入口），日志实时可见；禁止后台化与静默重定向（硬性规范）。宿主直启进程被安全软件 hook 时，给出确切命令请用户在自己的终端运行（进程链根在用户会话，干净且可见），如实记录实际执行者。
4. 观测：以前台窗口实时日志为主，辅以只读探测（如 curl 健康端点）；不接管、不代重启用户窗口中的进程。
5. 断点与热更新：IDE 直连宿主进程（本机调试端口），无需容器 JDWP 映射；前端热更新走 dev server 原生能力。
6. 单元测试与本地集成测试按变更影响范围运行，记录实际命令与结果，不暗示完整 CI 已通过。
7. 停止：用户在窗口 Ctrl-C 或直接关窗；用户明确要求 AI 停止时，先核对进程归属，只结束本次启动的进程。
8. 证据口径：如实记录为"宿主直启"（命令、执行者、结果）；宿主直启不产生镜像验证结论、不写部署收据，不能作为生产晋级依据——晋级仍需 `mv-container-deploy` 的同一 Image ID dev 健康收据。

### 容器调测（显式要求时）

1. 检查项目、README、Dockerfile/compose、运行参数和现有占用端口；默认只启动用户目标组件，不改变仓库或系统配置。
2. 硬门禁 `wsl-bridge.sh require`，非零退出即终止并向用户如实报告失败原因。
3. 出镜像：宿主出包后经 `image-build.sh build dev <app>` 生成镜像；瘦上下文只含产物与 Dockerfile，源码不出宿主。
4. 启动应用容器：经 WSL `exec` 执行 `docker compose -f <compose> -p <app> up -d`（compose 引用 `image:`，不含 `build:`）；没有 compose 就用 `templates/compose.delivery.yml` 起最小自测栈（固定运行时基础镜像、发布端口）。基础镜像由 `--pull` 拉取并常驻。
5. 观测与调试：经 `exec` 执行 `docker compose logs -f`、`docker compose ps`、`docker exec -it <容器> sh` 进入排障。端口经 compose `ports` 发布后从 Windows 侧 `127.0.0.1:<端口>` 访问（WSL2 localhost 转发）。断点调试在 compose 中开启 JDWP，端口映射仅绑定本机回环。
6. 只加载 `.env.local` 或项目已允许的开发环境设置，不自动复用 `.env.prod`、密钥或服务器配置；确认 API 请求目标为本地/dev，绝不默认连生产数据库或对生产数据做写操作。
7. 单元测试与本地集成测试按变更影响范围运行，记录实际命令与结果，不暗示完整 CI 已通过；宿主侧编译/单测（quality-check）不受容器规范限制。
8. 停止与清理：经 `exec` 执行 `docker compose -p <app> down`（只停删容器，镜像保留）；停止前重新核对标识，只清理本次创建的容器。端口占用者不是本次启动的容器时，报告冲突并选择其他端口或征求用户决定。
9. 本机调测不写部署收据；需要可晋级的生产前验证时走 `mv-container-deploy` 的 dev 交付（其健康验证后才产生收据）。

## 常见故障

- WSL Mirrored 网络模式下 Windows 与 WSL 共享端口：宿主直启或起栈前停掉占用同端口的进程（IDEA 网关、vite dev server 等）；间歇性 `address already in use` 先查这一层。
- 宿主直启的 java/node 进程出现 `Unable to establish loopback connection`（`Selector.open` 失败）等安全软件 hook 特征：与构建同类拦截（按进程链 hook，bash/agent 子进程被拦），换 JDK、`preferIPv4Stack` 均无效。兜底：给出确切启动命令请用户在自己的终端运行（进程链根在用户会话，干净且前台可见）；不得改用 schtasks 启动应用——schtasks 无用户会话控制台、属隐藏后台，违反前台可见硬约束，仅限构建使用。
- image-build.sh 报"未找到可交付产物"时，确认宿主构建命令确实成功且输出目录与栈匹配（Gradle `build/libs`、Maven `target`、Node `dist|build`），多模块或自定义布局用 `FF_ARTIFACT` 显式指定。
- 宿主 gradle/mvn 报 `Unable to establish loopback connection`（`Selector.open` 失败）：安全软件按**进程链** hook，bash/agent 子进程一律被拦——换 JDK、`preferIPv4Stack`、查 afunix 服务均无效。用 `doctor.py` 的 `host_build_chain` 项十秒判定；构建可改经 `templates/schtasks-build.cmd` 执行（schtasks 拉起的进程链不经过被拦截的子进程链）或请用户手动构建。
- WSL 内跑 gradle 时缓存卷必须挂容器用户真实 HOME：gradle 镜像默认用户 `gradle`（HOME=`/home/gradle`），挂 `/root/.gradle` 等于没挂，表现为每次构建全量重新下载依赖与发行版（卷里无 `.ok` 标记即证据）。正确：`-v <vol>:/home/gradle/.gradle` 或统一 `-e GRADLE_USER_HOME=...`。构建慢先分下载时间 vs 编译时间（看日志 Download 行数量），再查 `~/.wslconfig` 的 processors/memory（`doctor.py` 的 `wsl_resources` 项）。
- Mirrored 模式下容器出网可能半残：DNS 只解析 IPv6、TCP 443 不通，`--pull` 基础镜像或构建期下载**永久卡死且不报错**。探测：`docker exec <c> getent hosts <域>` + `bash -c "echo > /dev/tcp/<域>/443"`；降级：用已有常驻 JDK 镜像当运行时底包完成本机验证。

## 验证边界与验收报告

- 区分编译、单元测试、mock 运行时联调和真实依赖联调，每项记录实际输入、命令及结果；签名桩或手工 classpath 的验证只覆盖该范围，不等同于项目完整构建或 CI。
- 对机制问题沿"配置读取 → 业务传递 → 框架/依赖消费 → 实际副作用"追踪，结论附关键文件与行号。
- 入口验证按真实鉴权、Origin 和响应契约执行，并确认目标实例与依赖；共享服务注册中心可能将请求路由到其他实例，不能仅凭成功响应断言本次已验证。仅 mock 联调通过时明确外部系统尚未验证。
- 验收报告输出：Git SHA 与构建输入状态、宿主构建命令与产物路径、调测方式与结果（宿主直启时明确写出"宿主直启、未验证镜像"；容器调测附完整镜像 Tag 与 Image ID）、未验证的风险。没有真实构建时明确写出未执行，不可虚构成功。

## 安全要点

- 构建上下文只含产物与 Dockerfile，`.dockerignore` 必须显式排除 `.git` 与 `.env*`；秘密与 `.env` 不进上下文、Git 或命令日志。`FF_REQUIRE_SECURITY_SCAN=1` 时构建必须经 Trivy；CI 应落实严格策略。
- 编译出包在宿主完成是团队基线，不得改回容器内编译；应用启动默认宿主直启，但必须前台可见运行（见硬性规范），容器路径不回退宿主。出包前宿主工具链未就绪时先走 `mv-toolchain-manager`，不要临时换用不可控的构建方式。Dockerfile 过于复杂时，可选用严格遵循同一环境契约的项目内 CI/CD。
- 部署、晋级、回滚的授权与生产验证规则见 `mv-container-deploy`。

构建输入约定（产物检测、`.dockerignore` 规则、`FF_ARTIFACT`/`FF_RUNTIME_IMAGE`、镜像 TAG 公式与接口契约）读取 [镜像构建契约](references/build-contract.md)；构建期安全要点见 [安全模型](references/security-model.md)。
