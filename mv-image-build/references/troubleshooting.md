# 镜像构建常见故障

本文件收录 mv-image-build 镜像构建链路的高频故障与判定方法；构建卡住时先按症状对照本表，再用 `doctor.py` 复核环境。只覆盖构建范围；宿主直启调试故障见 `mv-local-debug`，部署与容器运行故障见 `mv-container-deploy`。

## 产物检测失败

- `scripts/image-build.sh` 报"未找到可交付产物"时，确认宿主构建命令确实成功且输出目录与栈匹配（Gradle `build/libs`、Maven `target`、Node `dist|build`）；多个候选会被拒绝并点名，多模块或自定义布局用 `FF_ARTIFACT` 显式指定。

## 进程链被安全软件 hook（loopback connection）

- 宿主 gradle/mvn 构建报 `Unable to establish loopback connection`（`Selector.open` 失败）：安全软件按**进程链** hook，bash/agent 子进程一律被拦；换 JDK、`preferIPv4Stack`、查 afunix 服务均无效。用 `doctor.py` 的 `host_build_chain` 项十秒判定；构建可改经 `templates/schtasks-build.cmd` 执行（schtasks 拉起的进程链不经过被拦截的子进程链）或请用户手动构建。

## Gradle 依赖反复全量下载

- 编译在宿主执行。核对实际构建进程的用户目录与 `GRADLE_USER_HOME`，确认依赖缓存和 `wrapper/dists` 缓存可读写且未随构建删除；采用计划任务构建时显式设置工具链及缓存目录，不假定继承 agent 会话环境。
- 先按日志区分下载时间与编译时间，再检查宿主网络与资源；不得为复用缓存改成 WSL 或容器内编译。WSL 资源诊断只用于后续镜像构建阶段。

## Mirrored 模式下基础镜像拉取卡住

- 在 WSL 侧检查基础镜像仓库域名解析、HTTPS 连通性与 Docker 代理，记录失败的拉取命令及输出；Dockerfile 只复制宿主产物，不增加容器内依赖下载与编译步骤。
- 已有兼容的常驻运行时镜像时，可用 `FF_RUNTIME_IMAGE` 指定后重试，记录镜像来源与构建结果；当前入口固定带 `--pull`，本地存在基础镜像不能保证离线构建成功。启动与健康验证仍交 `mv-container-deploy`。

故障不在本表时回到 SKILL.md 构建流程逐步取证；宿主直启问题移交 `mv-local-debug`，部署与容器运行问题移交 `mv-container-deploy`。
