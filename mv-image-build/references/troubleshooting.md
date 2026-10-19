# 镜像构建常见故障

本文件收录 mv-image-build 镜像构建链路的高频故障与判定方法；构建卡住时先按症状对照本表，再用 `doctor.py` 复核环境。只覆盖构建范围；宿主直启调试故障见 `mv-local-debug`，部署与容器运行故障见 `mv-container-deploy`。

## 产物检测失败

- `scripts/image-build.sh` 报"未找到可交付产物"时，确认宿主构建命令确实成功且输出目录与栈匹配（Gradle `build/libs`、Maven `target`、Node `dist|build`）；多个候选会被拒绝并点名，多模块或自定义布局用 `FF_ARTIFACT` 显式指定。

## 进程链被安全软件 hook（loopback connection）

- 宿主 java/node/gradle/mvn 构建报 `Unable to establish loopback connection`（`Selector.open` 失败，仅 Windows 宿主现象）：安全软件按**进程链** hook，bash/agent 子进程一律被拦；换 JDK、`preferIPv4Stack`、查 afunix 服务均无效。用 `doctor.py` 的 `host_build_chain` 项十秒判定；构建可改经 `templates/schtasks-build.cmd` 执行（schtasks 拉起的进程链不经过被拦截的子进程链）或请用户手动构建。

## Gradle 依赖反复全量下载

- 编译在宿主执行。核对实际构建进程的用户目录与 `GRADLE_USER_HOME`，确认依赖缓存和 `wrapper/dists` 缓存可读写且未随构建删除；采用计划任务构建时显式设置工具链及缓存目录，不假定继承 agent 会话环境。
- 先按日志区分下载时间与编译时间，再检查宿主网络与资源；不得为复用缓存改成 WSL 或容器内编译。WSL 资源诊断只用于后续镜像构建阶段。

## Mirrored 模式下基础镜像拉取卡住

- 在 WSL 侧检查基础镜像仓库域名解析、HTTPS 连通性与 Docker 代理，记录失败的拉取命令及输出；Dockerfile 只复制宿主产物，不增加容器内依赖下载与编译步骤。
- 已有兼容的常驻运行时镜像时，可用 `FF_RUNTIME_IMAGE` 指定后重试，记录镜像来源与构建结果；当前入口固定带 `--pull`，本地存在基础镜像不能保证离线构建成功。启动与健康验证仍交 `mv-container-deploy`。

## 宿主无 Docker 或 crane 路径故障

- 宿主无容器运行时（Windows 无 WSL，或 Linux/macOS 未装 Docker）：走 `scripts/crane-build.sh`（crane 路径，Java/Node 通用）；Windows 宿主不得以在宿主安装 Docker 代替。
- `crane: command not found`：交 `mv-toolchain-manager` 按需准备（`ensure --crane`，默认最新版或指定精确版本），并在同一会话执行激活片段后重试；不需要安装 Docker 或任何守护进程，也不要求用户手工下载。
- `crane-build.sh` 报缺少 Python：交 `mv-toolchain-manager` 按需准备（`ensure --python 3.12`），并在同一会话执行激活片段后重试；宿主完全没有 Python 时先执行其 `scripts/installer/bootstrap-python.sh 3.12`（stdout 是激活片段，`eval` 后即可用）。Python 只用于补写 `RepoTags` 和核对配置摘要，不参与编译。
- crane 拉取基础镜像失败：crane 走宿主网络直连 registry，按宿主代理与 DNS 排查，私有仓库认证走标准 docker config；已有兼容基础镜像时用 `FF_RUNTIME_IMAGE` 指定（建议固定摘要）后重试。
- `crane-build.sh` 报"无法识别项目栈"：项目根缺少 pom.xml、build.gradle(.kts) 或 package.json（如多模块仓库在子目录构建）；用 `FF_STACK=java|web|server` 显式指定。
- `crane-build.sh` 报镜像 tar 一致性校验失败：manifest Config 文件名与配置摘要不一致，产物格式异常；核对 crane 版本与 tar 结构后重试，不使用未经校验的镜像身份。
- web 模式部署后 SPA 子路由 404：crane 路径不改基镜像配置，history 路由需要 nginx fallback 时自备基镜像（`FF_RUNTIME_IMAGE` 指向含配置的镜像）。
- server 模式启动失败提示入口不存在：核对 `FF_ENTRYPOINT` 的路径与产物目录结构（层根为 `/app`，如 `node,dist/server.js`）。

故障不在本表时回到 SKILL.md 构建流程逐步取证；宿主直启问题移交 `mv-local-debug`，部署与容器运行问题移交 `mv-container-deploy`。
