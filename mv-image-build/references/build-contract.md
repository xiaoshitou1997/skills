# 镜像构建契约

目标：从同一份提交在宿主用语言工具链构建**一个**产物，打包为**一个**瘦运行时镜像。编译出包在宿主完成（工具链由 `mv-toolchain-manager` 准备），本 skill 只检测产物、打瘦镜像、输出镜像身份；**镜像与容器不承担编译**。默认路径先宿主出包再打瘦镜像（Windows 宿主经 WSL 桥接，Linux/macOS 宿主直连本机 Docker）；宿主 Docker 不可用时走 crane 路径，在宿主把**同一份宿主产物**组装为镜像（见下文）。

## 项目输入

- `.dockerignore` 必须显式排除 `.git` 和 `.env*`，不得通过取反规则重新包含秘密文件。检查全部构建上下文，确保不含私钥。
- 产物在宿主构建：Gradle `build/libs` 唯一 boot jar、Maven `target` 唯一 jar、Node `dist/` 或 `build/`；检测到多个候选时拒绝并点名，不按时间戳静默猜测；多模块或自定义布局用 `FF_ARTIFACT` 指定。可提供 `Dockerfile.delivery`（只做产物复制，不做编译）覆盖内置 jar/web 瘦模板。选定的产物目录（含显式 `FF_ARTIFACT`）若任意层级包含 `.git` 或 `.env*` 会被拒绝；瘦上下文不依赖项目 `.dockerignore` 过滤目录内容。
- 瘦上下文只含产物与 Dockerfile，源码不出宿主；桥接模式经 git 对象库管道（`hash-object` → `cat-file`，透读通道）或 push 管道进入 WSL，产物不依赖 Windows 盘中间态。

## 环境变量

| 变量 | 含义 |
| --- | --- |
| `FF_ARTIFACT` | 显式指定宿主产物路径（文件→`app.jar`，目录→`app/`）；多模块或自定义布局使用。crane 路径 java 模式收单个 jar，web/server 模式收产物目录 |
| `FF_IMAGE_REPO` | 镜像仓库前缀，默认应用名（crane 路径下它是产物镜像的证据引用，不要求可写仓库） |
| `FF_RUNTIME_IMAGE` | 覆盖运行基础镜像；建议固定摘要（Docker 路径作 `RUNTIME_IMAGE` build-arg，crane 路径作 mutate 的基镜像） |
| `FF_STACK` | crane 路径显式指定栈模式 `java\|web\|server`；缺省按项目文件推断（pom/gradle→java，package.json→web） |
| `FF_ENTRYPOINT` | crane 路径入口覆盖（逗号分隔）；server 模式必填，java/web 模式可选覆盖模板缺省 |
| `FF_IMAGE_TAR` | crane 路径产物 tar 输出路径，默认 `crane-image.tar` |
| `FF_REQUIRE_SECURITY_SCAN` | 设置为 1 时，构建镜像必须经 Trivy 扫描（Docker 路径扫镜像引用，crane 路径扫镜像 tar）；源码另用 Gitleaks 扫描 |
| `FF_WSL_DISTRO` | （仅 Windows 桥接生效）指定 WSL 发行版；默认取第一个可用发行版。其余宿主忽略 |
| `FF_WSL_BRIDGE` | （仅 Windows 桥接生效）设为 `0` 绕过 WSL 桥接走宿主 Docker；仅供测试/CI，Windows 生产使用违反团队规范。其余宿主忽略 |

Windows 上镜像构建经 WSL（`scripts/wsl-bridge.sh` 桥接），Docker 路径基础镜像由 `--pull` 在 WSL 内拉取并常驻，任何流程不得 `rmi`/`prune`，Windows 无 WSL 时明确报错并给安装指引，不得改用 Windows 侧 Docker；Linux/macOS 宿主由 `wsl-bridge.sh` 判定后直连本机 Docker，行为与语义同桥接模式（构建暂存用本地临时目录而非 `~/.mv/image-build/`）。宿主 Docker 不可用时改走 [crane 构建路径](#crane-构建路径宿主无-docker-时)，Windows 宿主不得以安装 Docker 代替。

## crane 构建路径（宿主无 Docker 时）

适用与前置：

- 适用 Java（Gradle/Maven）与 Node 项目，任意宿主产物通用；典型场景是 Windows 无 WSL、Linux/macOS 未装 Docker。产物仍由项目按约定在宿主构建，脚本只做分层组装，不做任何编译。
- crane 由 `mv-toolchain-manager` 按需准备（`ensure --crane`，[go-containerregistry releases](https://github.com/google/go-containerregistry/releases) 单文件二进制，会话级激活）；缺失时先走工具链准备，不要求用户手工下载。能从仓库**拉取**基础镜像（只读即可，`crane mutate --output` 直出本地 tar，不推送任何仓库）。私有仓库认证走标准 docker config（`~/.docker/config.json`）。
- 补写 `RepoTags` 与核对配置摘要需要 Python 3；缺失时同样由 `mv-toolchain-manager` 按需准备（`ensure --python 3.12`），宿主完全没有 Python 时先执行其 `bootstrap-python.sh` 并在同一会话激活。Python 只读写 tar，不参与编译。
- 栈模式 `FF_STACK=java|web|server`，缺省按项目文件推断；三种模式与瘦模板逐项对齐：
  - `java`：基镜像 `eclipse-temurin:21-jre`，产物为单个 jar（自动检测 `target`/`build/libs` 唯一 boot jar 或 `FF_ARTIFACT`），置于 `/app/app.jar`，`--workdir /app --user 10001 --exposed-ports 8080 --entrypoint java,-jar,/app/app.jar`（`FF_ENTRYPOINT` 可覆盖入口）；
  - `web`：基镜像 `nginx:alpine`，产物目录置于 `/usr/share/nginx/html`，`--exposed-ports 80`；SPA history 路由需要 fallback 配置时自备基镜像（`FF_RUNTIME_IMAGE`），脚本不改基镜像配置；
  - `server`：基镜像 `node:24-alpine`，产物目录置于 `/app`，`--workdir /app`，`FF_ENTRYPOINT` 必填（如 `node,dist/server.js`）。

驱动与产物：

- `scripts/crane-build.sh build dev|prod APP`：一条 `crane mutate <基镜像> --append <产物层> [运行时配置] -o <tar>` 完成组装；产物层在临时 staging 目录组装（java→`/app/app.jar`，web→nginx 根，server→`/app`），`.git` 与 `.env*` 不进层（与 Docker 路径同源守卫），过程文件用完即清。
- 产物为 docker load 可用的镜像 tar（默认 `crane-image.tar`，`FF_IMAGE_TAR` 指定）；tar 内 `RepoTags` 由脚本补写为 `IMAGE`，`docker load` 后按引用可寻址。
- `IMAGE_ID` 由 tar 内镜像配置的 SHA-256 纯宿主计算（不需要任何 Docker 守护进程），并与 manifest 的 Config 文件名核对一致，不一致即失败——不输出未经校验的镜像身份。Tag 公式、`-dirty` 规则与 `IMAGE=`/`IMAGE_ID=` 两行证据输出与 Docker 路径完全一致。
- 安全：`FF_REQUIRE_SECURITY_SCAN=1` 时以 `security-scan.sh image-tar <tar>`（`trivy image --input`）扫描，不需要守护进程。

边界：crane 路径交付物是镜像 tar，不在任何 Docker daemon 内（该路径本来就没有守护进程）；镜像进入部署前需先在目标 Docker `docker load` 载入，载入后 Image ID 必须与构建证据一致。`mv-container-deploy` 当前流程以「镜像已在目标 Docker」为前提，crane tar 载入这一步的自动化在部署侧另行演进。crane 路径不做镜像层优化（依赖/类分层），交付语义与瘦模板一致为准。

## 镜像身份契约（与 mv-container-deploy 的接口）

- Tag 公式：`<git sha 前 12 位>[-dirty]-<UTC 时间戳 YYYYMMDDHHMMSS>`；非 Git 目录记 `unversioned` 且强制 `-dirty`。
- 构建输出两行证据：`IMAGE=<repo>:<tag>` 与 `IMAGE_ID=sha256:...`；完整镜像 Tag 与 Image ID 必须如实转记进构建/调测记录。
- `mv-container-deploy` 只消费该镜像引用；`-dirty` 镜像会被部署侧拒绝晋级 prod，需干净工作区重新出包。
- 构建不可重复生成同一 Tag（时间戳参与）；跨环境一致性由**同一 Image ID 晋级**保证，不靠重新构建。

## 限制

内置模板针对常规 Spring Boot uber-jar（`templates/Dockerfile.jar`）和 Node 静态前端（`templates/Dockerfile.web`）。多模块 Maven/Gradle、Next.js SSR、原生扩展、ARM/AMD64 混用，请用 `FF_ARTIFACT` 指定产物并编写项目专用 `Dockerfile.delivery`，并先单独验证。默认镜像在本地目标架构构建；跨不同 CPU 架构不能仅靠 `docker save/load` 直接保证可运行。
