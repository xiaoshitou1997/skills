# 宿主调测常见故障

本文件收录 mv-local-debug 宿主链路（直启与宿主构建）的高频故障与判定方法；调测停滞时先按症状对照本表，再用 `doctor.py` 复核环境。只覆盖宿主范围；镜像构建链路故障见 `mv-image-build`，部署与容器运行故障见 `mv-container-deploy`。

## 端口占用

- 宿主直启前停掉占用同端口的进程（IDEA 网关、vite dev server 等）；间歇性 `address already in use` 先查这一层。
- Windows 宿主用 `netstat -ano | findstr <端口>`，Linux/macOS 宿主用 `ss -ltnp | grep <端口>` 或 `lsof -i :<端口>` 查占用进程并停掉或改端口，连不通时再核对防火墙（ufw/firewalld/安全组）。

## Agent 进程链 AF_UNIX 回环被拦（loopback connection）

- 宿主 Java 环节（gradle/mvn、应用内嵌 Tomcat/Netty 直启）出现 `Unable to establish loopback connection`（`Selector.open` 失败，栈含 `UnixDomainSockets.connect0`；仅 Windows 宿主 + JDK ≥14）：agent 命令运行器进程树上有过滤把 AppData 子树下的 AF_UNIX connect 拦为 EINVAL，WEPoll 选择器 wakeup pipe 落在默认 `java.io.tmpdir` 恰好命中——换 JDK、`preferIPv4Stack`、查 afunix 服务均无效。用 `doctor.py` 的 `host_build_chain` 项十秒判定。
- 一线解法（直启与构建通用）：加 `JAVA_TOOL_OPTIONS='-Djdk.net.unixdomain.tmpdir=C:/Windows/Temp'` 后原链重试，daemon、test fork 与应用主进程全部 JVM 自动拾取；注意只改 `java.io.tmpdir` 无效。2026-10-24 本机多项目实测通过，机理来源 [openai/codex#40902](https://github.com/openai/codex/issues/40902)。
- 直启兜底：给出确切启动命令请用户在自己的终端运行（进程链根在用户会话，干净且前台可见），如实记录实际执行者；**不得改用 schtasks 启动应用**——schtasks 无用户会话控制台、属隐藏后台，违反前台可见硬约束。
- 构建兜底：`mv-image-build` 的 `templates/schtasks-build.cmd` 是可选资源，不要求安装该 skill，且仅 Windows 宿主适用。已安装时，从其加载的 SKILL.md 绝对路径定位 skill 根目录，读取该目录下的模板并按项目替换仓库、工具链、构建命令和日志路径；不要把本 skill 的 `SKILL_ROOT` 当作镜像 skill 根目录。模板可借助计划任务执行宿主构建，但不得用于启动应用。未安装、找不到模板或计划任务不可用时，给出确切宿主构建命令，请用户在自己的终端手动执行，记录退出状态与产物路径。

故障不在本表时回到 SKILL.md 工作流逐步取证；镜像与容器侧问题移交 `mv-image-build` 与 `mv-container-deploy`。
