# 宿主调测常见故障

本文件收录 mv-local-debug 宿主链路（直启与宿主构建）的高频故障与判定方法；调测卡住时先按症状对照本表，再用 `doctor.py` 复核环境。只覆盖宿主范围；镜像构建链路故障见 `mv-image-build`，部署与容器运行故障见 `mv-container-deploy`。

## 端口占用（WSL Mirrored 共享端口层）

- WSL Mirrored 网络模式下 Windows 与 WSL 共享端口：宿主直启前停掉占用同端口的进程（IDEA 网关、vite dev server、WSL 内容器发布端口等）；间歇性 `address already in use` 先查这一层。

## 进程链被安全软件 hook（loopback connection）

- 宿主 java/node/gradle/mvn 出现 `Unable to establish loopback connection`（`Selector.open` 失败）等特征：安全软件按**进程链** hook，bash/agent 子进程一律被拦；换 JDK、`preferIPv4Stack`、查 afunix 服务均无效。用 `doctor.py` 的 `host_build_chain` 项十秒判定。
- 直启兜底：给出确切启动命令请用户在自己的终端运行（进程链根在用户会话，干净且前台可见），如实记录实际执行者；**不得改用 schtasks 启动应用**——schtasks 无用户会话控制台、属隐藏后台，违反前台可见硬约束。
- 构建兜底：改经 `mv-image-build` 的 `templates/schtasks-build.cmd` 执行（schtasks 拉起的进程链不经过被拦截的子进程链），或请用户手动构建。

故障不在本表时回到 SKILL.md 工作流逐步取证；镜像与容器侧问题移交 `mv-image-build` 与 `mv-container-deploy`。
