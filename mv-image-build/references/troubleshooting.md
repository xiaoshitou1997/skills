# 镜像构建常见故障

本文件收录 mv-image-build 镜像构建链路的高频故障与判定方法；构建停滞时先按症状对照本表，再用 `doctor.py` 复核环境。只覆盖构建范围；宿主直启调试故障见 `mv-local-debug`，部署与容器运行故障见 `mv-container-deploy`。

## Java 模块：Jib 相关

- `jib-build.sh` 报"本模块未声明 jib-maven-plugin / 未应用 com.google.cloud.tools.jib"：镜像定义属模块配置。先在模块的 `pom.xml` / `build.gradle(.kts)` 按 [构建契约](build-contract.md) 加入插件与基线配置，再重试；不要改用 Docker 路径绕过。多模块项目确认当前目录或 `FF_JIB_PROJECT` 指向的是目标模块。
- `jib-build.sh` 报"未找到 target/ 或 build/libs/"：Jib 消费项目自身产物，本脚本不做编译。先按项目约定在宿主出包（`mvn -B package` / `./gradlew bootJar`），再重试。
- Jib 执行成功但脚本报"未产出镜像 tar"：模块配置了自定义 `outputPaths.tar`。用 `FF_IMAGE_TAR` 指向实际 tar 路径；同时核对该路径不在 `.gitignore` 之外的特殊目录、且构建用户可写。
- `push-bin` 报"文件已被端点透明加密"：镜像 tar 落在端点透明加密目录，被加密后无法载入。用 `FF_IMAGE_TAR` 把 tar 输出到白名单目录后重试；仍被加密时改为在 WSL 内执行 Jib 构建，或请用户在白名单进程中构建并记录实际路径。
- `docker load` 失败或之后 `IMAGE_ID` 缺失：核对 tar 是否完整（构建期间被中断、磁盘满、杀毒软件隔离都可能截断），删除残缺 tar 后重新执行 `jib-build.sh`；不要手工输出 Image ID。
- WSL 缺失或 WSL 内 Docker 不可用：脚本明确报错，不给回退路径。按提示安装 WSL2 / 在发行版内安装 Docker Engine，或启用 Docker Desktop 的 WSL 集成；Windows 宿主不得改用 Windows 侧 Docker。
- 需要 `RUN apt-get install` 一类构建期安装，Jib 无法表达：在模块内评估预装该依赖的基镜像（`from.image`），或改用项目内 CI/CD；不要在本 skill 里另写 Dockerfile 绕过模块定义。

## 非 Java 模块：产物与上下文

- `image-build.sh` 报"未找到可交付产物"：确认宿主构建命令确实成功且输出目录与栈匹配（Node `dist|build`；`Dockerfile.delivery` 项目的 Maven `target`、Gradle `build/libs`），多模块或自定义布局用 `FF_ARTIFACT` 显式指定。
- 报"检测到多个可交付产物"：交付契约要求唯一产物，按提示列出的候选用 `FF_ARTIFACT` 指定其一，不按时间戳猜测。
- 报"Java 模块镜像由模块内 Jib 插件定义"：该模块没有 `Dockerfile.delivery`，属预期行为。改用 `jib-build.sh`；确需 Docker 路径时在模块内提供 `Dockerfile.delivery`（只复制产物，不编译）。
- 报"产物目录包含 .git 或 .env*"：瘦上下文不会应用项目 `.dockerignore`，显式目录也不能带入仓库元数据与秘密。用 `FF_ARTIFACT` 指向纯产物目录，或先把产物复制到干净目录。

## 进程链被安全软件 hook（loopback connection）

- 宿主 java/node/gradle/mvn 构建报 `Unable to establish loopback connection`（`Selector.open` 失败，仅 Windows 宿主现象）：安全软件按**进程链** hook，bash/agent 子进程一律被拦；换 JDK、`preferIPv4Stack`、查 afunix 服务均无效。用 `doctor.py` 的 `host_build_chain` 项十秒判定；构建可改经 `templates/schtasks-build.cmd` 执行（schtasks 拉起的进程链不经过被拦截的子进程链）或请用户手动构建。

## Gradle 依赖反复全量下载

- 编译在宿主执行。核对实际构建进程的用户目录与 `GRADLE_USER_HOME`，确认依赖缓存和 `wrapper/dists` 缓存可读写且未随构建删除；采用计划任务构建时显式设置工具链及缓存目录，不假定继承 agent 会话环境。
- 先按日志区分下载时间与编译时间，再检查宿主网络与资源；不得为复用缓存改成 WSL 或容器内编译。WSL 资源诊断只用于后续镜像构建阶段。

## Mirrored 模式下基础镜像拉取停滞

- 在 WSL 侧检查基础镜像仓库域名解析、HTTPS 连通性与 Docker 代理，记录失败的拉取命令及输出。Jib 路径的基镜像由 Jib 在构建时拉取；Dockerfile 只复制宿主产物，不增加容器内依赖下载与编译步骤。
- 已有兼容的常驻运行时镜像时，可用 `FF_RUNTIME_IMAGE` 指定后重试（Jib 路径映射为 `-Djib.from.image`），记录镜像来源与构建结果；Docker 路径入口固定带 `--pull`，本地存在基础镜像不能保证离线构建成功。启动与健康验证仍交 `mv-container-deploy`。

故障不在本表时回到 SKILL.md 构建流程逐步取证；宿主直启问题移交 `mv-local-debug`，部署与容器运行问题移交 `mv-container-deploy`。
