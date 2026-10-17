# 镜像构建常见故障

本文件收录 mv-image-build 镜像构建链路的高频故障与判定方法；构建卡住时先按症状对照本表，再用 `doctor.py` 复核环境。只覆盖构建范围；宿主直启调试故障见 `mv-local-debug`，部署与容器运行故障见 `mv-container-deploy`。

## 产物检测失败

- `scripts/image-build.sh` 报"未找到可交付产物"时，确认宿主构建命令确实成功且输出目录与栈匹配（Gradle `build/libs`、Maven `target`、Node `dist|build`）；多个候选会被拒绝并点名，多模块或自定义布局用 `FF_ARTIFACT` 显式指定。

## 进程链被安全软件 hook（loopback connection）

- 宿主 gradle/mvn 构建报 `Unable to establish loopback connection`（`Selector.open` 失败）：安全软件按**进程链** hook，bash/agent 子进程一律被拦；换 JDK、`preferIPv4Stack`、查 afunix 服务均无效。用 `doctor.py` 的 `host_build_chain` 项十秒判定；构建可改经 `templates/schtasks-build.cmd` 执行（schtasks 拉起的进程链不经过被拦截的子进程链）或请用户手动构建。

## Gradle 依赖反复全量下载

- WSL 内跑 gradle 时缓存卷必须挂容器用户真实 HOME：gradle 镜像默认用户 `gradle`（HOME=`/home/gradle`），挂 `/root/.gradle` 等于没挂，表现为每次构建全量重新下载依赖与发行版（卷里无 `.ok` 标记即证据）。正确：`-v <vol>:/home/gradle/.gradle` 或统一 `-e GRADLE_USER_HOME=...`。构建慢先分下载时间 vs 编译时间（看日志 Download 行数量），再查 `~/.wslconfig` 的 processors/memory（`doctor.py` 的 `wsl_resources` 项）。

## Mirrored 模式容器出网半残（构建期 `--pull` 卡死）

- DNS 只解析 IPv6、TCP 443 不通，`--pull` 基础镜像或构建期下载**永久卡死且不报错**。探测：`docker exec <c> getent hosts <域>` + `bash -c "echo > /dev/tcp/<域>/443"`；降级：用已有常驻 JDK 镜像当运行时底包（`FF_RUNTIME_IMAGE`）完成构建。

故障不在本表时回到 SKILL.md 构建流程逐步取证；宿主直启问题移交 `mv-local-debug`，部署与容器运行问题移交 `mv-container-deploy`。
