# 镜像构建契约

目标：从同一份提交在宿主用语言工具链构建**一个**二进制包，上传服务器打包为**一个**瘦运行时镜像。**镜像定义与模块同源**：各栈模块内自备 `Dockerfile.delivery`（Node 静态前端可用内置模板），只复制产物、不做编译。编译出包在宿主完成（工具链由 `mv-toolchain-manager` 准备），镜像构建在服务器构建点执行；本 skill 的脚本只编排「出包 → 上传校验 → 服务器构建 → 输出镜像身份」，不另写一套镜像配置。

## 目录

- Java 模块：Dockerfile.delivery 基线
- 非 Java 模块：模块内 Dockerfile.delivery
- 多模块项目
- 产物检测与包版本管理
- 环境变量
- 上传与服务器构建
- 镜像身份契约（与 mv-container-deploy 的接口）
- 限制


## Java 模块：Dockerfile.delivery 基线

Java 模块与非 Java 栈同一条交付路径：模块内自备 `Dockerfile.delivery`，只复制宿主已构建的 jar，不做编译。团队基线（可按项目要求调整，但必须写在模块配置里）：

```dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY app.jar app.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
```

- 基镜像默认 `eclipse-temurin:21-jre`，非 root 用户 `10001`，端口 `8080`。
- `Dockerfile.delivery` 可声明 HEALTHCHECK（指向 liveness 端点，`start_period` 覆盖启动期）；部署门禁仍以 `FF_HEALTH_URL`（readiness）探活为准，见 `mv-container-deploy` 交付契约。
- 需要 `RUN apt-get install` 一类构建期安装时，交付镜像只复制产物不做编译，应评估预装该依赖的基镜像或改用项目内 CI/CD。

## 非 Java 模块：模块内 Dockerfile.delivery

- 模块内提供 `Dockerfile.delivery`，只做产物复制，不做编译（`COPY` 宿主已出包的产物）。
- 只有 `package.json` 且无 `Dockerfile.delivery` 时使用内置 `templates/Dockerfile.web`（静态站点）。
- 其余栈必须自备 `Dockerfile.delivery`，并在其中显式声明基镜像、用户、端口与入口。
- `.dockerignore` 必须显式排除 `.git` 和 `.env*`，不得通过取反规则重新包含秘密文件。检查全部构建上下文，确保不含私钥。

## 多模块项目

- 默认**每个模块独立定义、独立出镜像**：镜像定义随各模块的 `Dockerfile.delivery`。
- 在目标模块目录执行；多模块项目先定位目标模块再出包上传。
- 默认不建聚合的 `image-build` 模块。只有确需集中管理多个模块的镜像时，才设聚合目录；聚合目录只承载编排（CI 任务、构建矩阵），镜像定义仍留在各模块内，不得在聚合处复制一份配置。
- 各模块的 `APP` 名与 `FF_IMAGE_REPO` 必须可区分，避免不同模块打出同名镜像。

## 产物检测与包版本管理

- 产物在宿主构建：Node `dist/` 或 `build/`；Java 模块 Maven `target/` 唯一 jar、Gradle `build/libs/` 唯一 boot jar。检测到多个候选时拒绝并点名，不按时间戳静默猜测；多模块或自定义布局用 `FF_ARTIFACT` 指定（文件→`app.jar`，目录→`app/`）。
- 选定的产物目录（含显式 `FF_ARTIFACT`）若任意层级包含 `.git` 或 `.env*` 会被拒绝；瘦上下文只含包与 Dockerfile，源码不出宿主。
- 包版本标识在宿主出包时生成，Tag 公式见「镜像身份契约」；包文件名携带 `<app>-<tag>`，落服务器侧 `~/.mv/image-build/packages/<app>/`。
- 包清单与包同目录维护，每包一条：包文件名、SHA-256、来源（Git SHA 与工作区状态）、构建所得镜像引用与 Image ID、上传与构建时间。
- 同一 Tag 只对应一个包；重出包产生新 Tag，不覆盖已有包。

## 环境变量

| 变量 | 含义 |
| --- | --- |
| `FF_BUILD_TARGET` | 构建点 SSH 目标（`user@host`），必填；镜像统一在该服务器构建 |
| `FF_ARTIFACT` | 显式指定宿主产物路径（文件→`app.jar`，目录→`app/`） |
| `FF_IMAGE_REPO` | 镜像仓库前缀，默认应用名 |
| `FF_RUNTIME_IMAGE` | 覆盖基镜像，以 `RUNTIME_IMAGE` build-arg 传入 `Dockerfile.delivery`。建议固定摘要 |
| `FF_REQUIRE_SECURITY_SCAN` | 设置为 1 时，构建点侧 Trivy 扫描镜像作硬门禁；源码另用 Gitleaks 扫描 |

## 上传与服务器构建

- 上传与构建统一经 SSH 通道：`FF_BUILD_TARGET=user@host` 指向构建点（单机部署为部署机自身，集群为镜像仓库所在节点），包直传 `~/.mv/image-build/packages/<app>/`。
- 构建点先核对上传包 SHA-256 与出包时计算值一致（不匹配即删除损坏包并中止），再解包组装瘦上下文（只含包与 Dockerfile）执行 `docker build --pull`；不静默降级。
- 基础镜像由构建点拉取并常驻，任何流程不得 `rmi`/`prune`。
- 构建完成后按引用确认镜像可寻址，再输出 `IMAGE_ID`；构建失败或 Image ID 缺失即失败，不输出未经校验的镜像身份，并把包名、校验和、镜像引用与 Image ID 写入包清单。

## 镜像身份契约（与 mv-container-deploy 的接口）

- Tag 公式：`<git sha 前 12 位>[-dirty]-<UTC 时间戳 YYYYMMDDHHMMSS>`，时间戳取出包时刻；非 Git 目录记 `unversioned` 且强制 `-dirty`。包与镜像共用同一 Tag。
- 构建输出两行证据：`IMAGE=<repo>:<tag>` 与 `IMAGE_ID=sha256:...`；完整镜像 Tag、Image ID 与所用包名、校验和必须如实转记进构建记录。
- `mv-container-deploy` 只消费该镜像引用；`-dirty` 镜像会被部署侧拒绝晋级 prod，需干净工作区重新出包。
- 构建不可重复生成同一 Tag（时间戳参与）；跨环境一致性由**同一 Image ID 晋级**保证，不靠重新构建。

## 限制

- 交付镜像只复制产物不做编译：镜像内容边界由模块 `Dockerfile.delivery` 决定，构建期安装应评估预装基镜像或项目内 CI/CD，不在本 skill 另写构建逻辑。
- 内置模板只覆盖 Node 静态前端（`templates/Dockerfile.web`）；Next.js SSR、原生扩展等请提供项目专用 `Dockerfile.delivery` 并用 `FF_ARTIFACT` 指定产物，先单独验证。
- 镜像在构建点所在架构构建；跨不同 CPU 架构不能仅靠 `docker save/load` 直接保证可运行，多架构分发需镜像仓库侧支持。
