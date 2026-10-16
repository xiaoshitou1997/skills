# 镜像构建契约

目标：从同一份提交在宿主用语言工具链构建**一个**产物，打包为**一个**瘦运行时镜像。编译出包在宿主完成（工具链由 `mv-toolchain-manager` 准备），本 skill 只检测产物、打瘦镜像、输出镜像身份；**镜像与容器不承担编译**。

## 项目输入

- `.dockerignore` 必须显式排除 `.git` 和 `.env*`，不得通过取反规则重新包含秘密文件。检查全部构建上下文，确保不含私钥。
- 产物在宿主构建：Gradle `build/libs` 唯一 boot jar、Maven `target` 唯一 jar、Node `dist/` 或 `build/`；多模块或自定义布局用 `FF_ARTIFACT` 指定。可提供 `Dockerfile.delivery`（只做产物复制，不做编译）覆盖内置 jar/web 瘦模板。
- 瘦上下文只含产物与 Dockerfile，源码不出宿主；桥接模式经 git 对象库管道（`hash-object` → `cat-file`，透读通道）或 push 管道进入 WSL，产物不依赖 Windows 盘中间态。

## 环境变量

| 变量 | 含义 |
| --- | --- |
| `FF_ARTIFACT` | 显式指定宿主产物路径（文件→`app.jar`，目录→`app/`）；多模块或自定义布局使用 |
| `FF_IMAGE_REPO` | 镜像仓库前缀，默认应用名 |
| `FF_RUNTIME_IMAGE` | 覆盖运行基础镜像；建议固定摘要 |
| `FF_REQUIRE_SECURITY_SCAN` | 设置为 1 时，构建镜像必须经 Trivy 扫描；源码另用 Gitleaks 扫描 |
| `FF_WSL_DISTRO` | Windows 指定 WSL 发行版；默认取第一个可用发行版 |
| `FF_WSL_BRIDGE` | 设为 `0` 绕过 WSL 桥接；仅供测试/CI，Windows 生产使用违反团队规范 |

Windows 上镜像构建一律经 WSL（`scripts/wsl-bridge.sh` 桥接）；基础镜像由 `--pull` 在 WSL 内拉取并常驻，任何流程不得 `rmi`/`prune`。没有 WSL 时镜像构建直接失败，不回退宿主直接执行。

## 镜像身份契约（与 mv-container-deploy 的接口）

- Tag 公式：`<git sha 前 12 位>[-dirty]-<UTC 时间戳 YYYYMMDDHHMMSS>`；非 Git 目录记 `unversioned` 且强制 `-dirty`。
- 构建输出两行证据：`IMAGE=<repo>:<tag>` 与 `IMAGE_ID=sha256:...`；完整镜像 Tag 与 Image ID 必须如实转记进构建/调测记录。
- `mv-container-deploy` 只消费该镜像引用；`-dirty` 镜像会被部署侧拒绝晋级 prod，需干净工作区重新出包。
- 构建不可重复生成同一 Tag（时间戳参与）；跨环境一致性由**同一 Image ID 晋级**保证，不靠重新构建。

## 限制

内置模板针对常规 Spring Boot uber-jar（`templates/Dockerfile.jar`）和 Node 静态前端（`templates/Dockerfile.web`）。多模块 Maven/Gradle、Next.js SSR、原生扩展、ARM/AMD64 混用，请用 `FF_ARTIFACT` 指定产物并编写项目专用 `Dockerfile.delivery`，并先单独验证。默认镜像在本地目标架构构建；跨不同 CPU 架构不能仅靠 `docker save/load` 直接保证可运行。
