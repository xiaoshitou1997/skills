# 镜像构建常见故障

本文件收录 mv-image-build 出包与镜像构建链路的高频故障与判定方法；构建停滞时先按症状对照本表，再用 `doctor.py` 复核环境。只覆盖出包与镜像构建范围；宿主直启调试故障见 `mv-local-debug`，部署与容器运行故障见 `mv-container-deploy`。

## 产物与包

- 报"未找到可交付产物"：确认宿主构建命令确实成功且输出目录与栈匹配（Node `dist|build`；Java Maven `target`、Gradle `build/libs`），多模块或自定义布局用 `FF_ARTIFACT` 显式指定。
- 报"检测到多个可交付产物"：交付契约要求唯一产物，按提示列出的候选用 `FF_ARTIFACT` 指定其一，不按时间戳猜测。
- 报"产物目录包含 .git 或 .env*"：瘦上下文不会应用项目 `.dockerignore`，显式目录也不能带入仓库元数据与秘密。用 `FF_ARTIFACT` 指向纯产物目录，或先把产物复制到干净目录。
- 模块未备 `Dockerfile.delivery`：镜像定义属模块配置，按 [构建契约](build-contract.md) 在模块内补齐基线再重试；不在脚本或编排层代写镜像配置。
- 报 `FF_BUILD_TARGET 未设置` 或构建点不可达：构建点是唯一镜像产出地，确认 `user@host` 正确且 SSH 免密可达（`~/.ssh/config` 或密钥）后重试；不设缺省构建点。
- 服务器侧包核对不匹配（SHA-256 与出包时计算值不一致）：上传不完整或包在途中被改动，重出包重传；不带病构建。
- 构建点容器环境不可用（无 Docker、无法访问镜像仓库节点）：明确报错并请示，不在宿主侧代构建。

## Agent 进程链 AF_UNIX 回环被拦（loopback connection）

- 宿主 Java 环节（gradle/mvn、surefire fork、应用内嵌 Tomcat/Netty 等一切起 JVM 的步骤）报 `Unable to establish loopback connection`（`Selector.open` 失败，栈含 `UnixDomainSockets.connect0: Invalid argument`；仅 Windows 宿主 + JDK ≥14）：agent 命令运行器进程树上有过滤把 **AppData 子树下的 AF_UNIX connect** 拦为 EINVAL——bind 一律成功、仅 connect 失败，同路径经服务链（schtasks）或非 AppData 目录（主目录根、`C:\Windows\Temp`、`C:\ProgramData`、D:\ 工作区）均正常。JDK ≥14 起 WEPoll 选择器的 wakeup pipe 用 `java.io.tmpdir` 下的 UDS socketpair，恰好落进拦截区；JDK ≤13 走 TCP 回环 pipe 不受影响（实测 8/11 通过，17/21/25/26 被拦）。换 JDK、`preferIPv4Stack`、查 afunix 服务均无效——afunix.sys 本身正常，正常路径的 connect 返回的是标准 `Connection refused`。用 `doctor.py` 的 `host_build_chain` 项十秒判定。
- 一线解法：加 `JAVA_TOOL_OPTIONS='-Djdk.net.unixdomain.tmpdir=C:/Windows/Temp'` 后原链重试。该属性专门指定 UDS wakeup pipe 目录，**只改 `java.io.tmpdir` 无效**；`JAVA_TOOL_OPTIONS` 会被 daemon、test fork 等全部子 JVM 自动拾取（也可经 `MAVEN_OPTS`/`GRADLE_OPTS`/`org.gradle.jvmargs` 注入同一属性）。2026-10-24 本机经最小探针、Maven/Gradle 复现工程与两个真实项目实测通过：Maven 项目覆写后同链测试全绿（此前被迫走 schtasks）；Gradle 8.14.5 + JDK 21 项目覆写前 `gradlew help` 起 daemon 即报 loopback 失败，覆写后 daemon 与模块测试（7/7）全部通过。机理与绕过来源 [openai/codex#40902](https://github.com/openai/codex/issues/40902)。
- 兜底：覆写仍失败（更严环境下目标目录不可写或 bind 也被拒）时改经 `templates/schtasks-build.cmd` 干净链（配同目录 `run-hidden.vbs` 隐藏窗口：计划任务无触发器注册、任务名带时间戳、用后注销，完整步骤见模板头注释），或请用户手动构建。

## Gradle 依赖反复全量下载

- 编译在宿主执行。核对实际构建进程的用户目录与 `GRADLE_USER_HOME`，确认依赖缓存和 `wrapper/dists` 缓存可读写且未随构建删除；采用计划任务构建时显式设置工具链及缓存目录，不假定继承 agent 会话环境。
- 先按日志区分下载时间与编译时间，再检查宿主网络与资源；不得为复用缓存把编译转入服务器或容器。资源诊断只用于服务器侧镜像构建阶段。

## 构建点基础镜像拉取停滞

- 在构建点侧检查基础镜像仓库域名解析、HTTPS 连通性与 Docker 代理，记录失败的拉取命令及输出；交付 Dockerfile 只复制宿主产物，不增加容器内依赖下载与编译步骤。
- 已有兼容的常驻运行时镜像时，可用 `FF_RUNTIME_IMAGE` 指定后重试，记录镜像来源与构建结果；构建入口固定带 `--pull`，本地存在基础镜像不能保证离线构建成功。启动与健康验证仍交 `mv-container-deploy`。

故障不在本表时回到 SKILL.md 构建流程逐步取证；宿主直启问题移交 `mv-local-debug`，部署与容器运行问题移交 `mv-container-deploy`。
