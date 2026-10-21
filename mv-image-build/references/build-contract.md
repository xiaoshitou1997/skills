# 镜像构建契约

目标：从同一份提交在宿主用语言工具链构建**一个**产物，打包为**一个**瘦运行时镜像。**镜像定义与模块同源**：Java 在模块的 `pom.xml` / `build.gradle(.kts)` 里声明 Jib，非 Java 在模块内自备 `Dockerfile.delivery`。编译出包在宿主完成（工具链由 `mv-toolchain-manager` 准备），本 skill 的脚本只编排「调用模块定义 → 载入目标 Docker → 输出镜像身份」，不另写一套镜像配置。

## 目录

- Java 模块：模块内 Jib 配置基线
- 非 Java 模块：模块内 Dockerfile.delivery
- 多模块项目
- 产物检测（非 Java Docker 路径）
- 环境变量
- 运行目标与镜像载入
- 镜像身份契约（与 mv-container-deploy 的接口）
- 限制


## Java 模块：模块内 Jib 配置基线

Java 模块必须自己声明 Jib 插件；`jib-build.sh` 只校验声明是否存在，不注入镜像配置。团队基线（插件版本由 `mv-tech-stack-standards` 统一，项目内显式声明）：

Maven（`pom.xml`）：

```xml
<plugin>
  <groupId>com.google.cloud.tools</groupId>
  <artifactId>jib-maven-plugin</artifactId>
  <version>3.5.2</version>
  <configuration>
    <from><image>eclipse-temurin:21-jre</image></from>
    <container>
      <mainClass>com.example.Application</mainClass>
      <ports><port>8080</port></ports>
      <user>10001</user>
      <workingDirectory>/app</workingDirectory>
    </container>
  </configuration>
</plugin>
```

Gradle（`build.gradle` / `build.gradle.kts`）：

```groovy
plugins {
    id 'com.google.cloud.tools.jib' version '3.5.4'
}

jib {
    from { image = 'eclipse-temurin:21-jre' }
    container {
        mainClass = 'com.example.Application'
        ports = ['8080']
        user = '10001'
        workingDirectory = '/app'
    }
}
```

- 基镜像默认 `eclipse-temurin:21-jre`，非 root 用户 `10001`，端口 `8080`；项目可按自身要求调整，但必须写在模块配置里。
- 目标镜像引用由脚本以 `-Djib.to.image=...` 传入，模块配置不得写死固定 Tag；基镜像可用 `-Djib.from.image` 覆盖（对应 `FF_RUNTIME_IMAGE`）。
- Jib 默认 `exploded` 布局：类、依赖与资源分层放入 `/app`，入口由 `mainClass` 生成。需要单 jar 布局的项目自行在模块配置里改用 `containerizingMode=packaged`（此时入口指向实际 jar 名）。
- 插件版本基线：jib-maven-plugin 3.5.2、jib-gradle-plugin 3.5.4。升级先在项目内验证 `buildTar` 产物可载入、可启动，再回写基线。

## 非 Java 模块：模块内 Dockerfile.delivery

- 模块内提供 `Dockerfile.delivery` 时优先使用；它只做产物复制，不做编译（`COPY` 宿主已出包的产物）。
- 只有 `package.json` 且无 `Dockerfile.delivery` 时使用内置 `templates/Dockerfile.web`（静态站点）。
- 其余栈必须自备 `Dockerfile.delivery`，并在其中显式声明基镜像、用户、端口与入口。
- `.dockerignore` 必须显式排除 `.git` 和 `.env*`，不得通过取反规则重新包含秘密文件。检查全部构建上下文，确保不含私钥。

## 多模块项目

- 默认**每个模块独立定义、独立出镜像**：Java 模块的镜像定义随其 `pom.xml`/`build.gradle`，非 Java 模块随其 `Dockerfile.delivery`。
- 在目标模块目录执行对应脚本；`jib-build.sh` 也接受 `FF_JIB_PROJECT=<模块目录>`。
- 默认不建聚合的 `image-build` 模块。只有确需集中管理多个模块的镜像时，才设聚合目录；聚合目录只承载编排（CI 任务、构建矩阵），镜像定义仍留在各模块内，不得在聚合处复制一份配置。
- 各模块的 `APP` 名与 `FF_IMAGE_REPO` 必须可区分，避免不同模块打出同名镜像。

## 产物检测（非 Java Docker 路径）

- 产物在宿主构建：Node `dist/` 或 `build/`；`Dockerfile.delivery` 项目的 Maven `target/` 唯一 jar、Gradle `build/libs/` 唯一 boot jar。检测到多个候选时拒绝并点名，不按时间戳静默猜测；多模块或自定义布局用 `FF_ARTIFACT` 指定（文件→`app.jar`，目录→`app/`）。
- 选定的产物目录（含显式 `FF_ARTIFACT`）若任意层级包含 `.git` 或 `.env*` 会被拒绝；瘦上下文不依赖项目 `.dockerignore` 过滤目录内容。
- 瘦上下文只含产物与 Dockerfile，源码不出宿主；桥接模式经 git 对象库管道（`hash-object` → `cat-file`，透读通道）或 push 管道进入 WSL，产物不依赖 Windows 盘中间态。
- Java 模块无 `Dockerfile.delivery` 时，`image-build.sh` 明确指向 `jib-build.sh` 并退出；确需 Docker 路径时必须由模块提供 `Dockerfile.delivery`。

## 环境变量

| 变量 | 含义 |
| --- | --- |
| `FF_JIB_PROJECT` | `jib-build.sh` 使用的模块目录，默认当前目录；多模块项目指定目标模块 |
| `FF_GRADLEW` | `jib-build.sh` 在模块无 `gradlew` 时使用的 Gradle 可执行文件路径 |
| `FF_IMAGE_TAR` | Jib 产出的镜像 tar 路径；默认 Maven `target/jib-image.tar`、Gradle `build/jib-image.tar`，模块配置了 `outputPaths.tar` 时按实际路径指定 |
| `FF_ARTIFACT` | 非 Java Docker 路径显式指定宿主产物路径（文件→`app.jar`，目录→`app/`） |
| `FF_IMAGE_REPO` | 镜像仓库前缀，默认应用名 |
| `FF_RUNTIME_IMAGE` | 覆盖基镜像；Jib 路径作 `-Djib.from.image`，Docker 路径作 `RUNTIME_IMAGE` build-arg。建议固定摘要 |
| `FF_REQUIRE_SECURITY_SCAN` | 设置为 1 时，构建镜像必须经 Trivy 扫描；源码另用 Gitleaks 扫描 |
| `FF_WSL_DISTRO` | （仅 Windows 桥接生效）指定 WSL 发行版；默认取第一个可用发行版。其余宿主忽略 |
| `FF_WSL_BRIDGE` | （仅 Windows 桥接生效）设为 `0` 绕过 WSL 桥接走宿主 Docker；仅供测试/CI，Windows 生产使用违反团队规范。其余宿主忽略 |

## 运行目标与镜像载入

- Windows 上容器路径经 WSL（`scripts/wsl-bridge.sh` 桥接）：Jib tar 经 `push-bin` 管道写入 WSL 后 `docker load -i`；Docker 路径的构建上下文同样只经管道进入 WSL。基础镜像由 `--pull` 在 WSL 内拉取并常驻，任何流程不得 `rmi`/`prune`。Windows 无 WSL 时明确报错并给安装指引，不得改用 Windows 侧 Docker。
- Linux/macOS 宿主由 `wsl-bridge.sh` 判定后直连本机 Docker：Jib tar 直接 `docker load -i`；Docker 路径构建暂存用本地临时目录而非 `~/.mv/image-build/`。
- `docker load` 完成后必须按引用确认镜像可寻址，再输出 `IMAGE_ID`；载入失败或 Image ID 缺失即构建失败，不输出未经校验的镜像身份。

## 镜像身份契约（与 mv-container-deploy 的接口）

- Tag 公式：`<git sha 前 12 位>[-dirty]-<UTC 时间戳 YYYYMMDDHHMMSS>`；非 Git 目录记 `unversioned` 且强制 `-dirty`。两条路径共用同一公式。
- 构建输出两行证据：`IMAGE=<repo>:<tag>` 与 `IMAGE_ID=sha256:...`；完整镜像 Tag 与 Image ID 必须如实转记进构建/调测记录。
- `mv-container-deploy` 只消费该镜像引用；`-dirty` 镜像会被部署侧拒绝晋级 prod，需干净工作区重新出包。
- 构建不可重复生成同一 Tag（时间戳参与）；跨环境一致性由**同一 Image ID 晋级**保证，不靠重新构建。

## 限制

- Java 镜像的能力边界由模块内的 Jib 配置决定：需要 `RUN apt-get install` 等构建期安装时，Jib 无法表达，应在模块内评估预装基镜像或改用项目内 CI/CD，而不是在本 skill 里另写 Dockerfile。
- 内置模板只覆盖 Node 静态前端（`templates/Dockerfile.web`）；多模块 Maven/Gradle、Next.js SSR、原生扩展、ARM/AMD64 混用，请在模块内提供 `Dockerfile.delivery` 并用 `FF_ARTIFACT` 指定产物，先单独验证。
- 默认镜像在本地目标架构构建；跨不同 CPU 架构不能仅靠 `docker save/load` 直接保证可运行。
