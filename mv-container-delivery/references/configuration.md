# 配置参考

## 环境变量

| 变量 | 含义 |
|---|---|
| `FF_DEV_SSH` | dev 目标 SSH，如 `devops@dev.example.com`；未设置走本机 Docker |
| `FF_PROD_SSH` | prod 目标 SSH；生产部署必填 |
| `FF_DEV_SSH_KEY` / `FF_PROD_SSH_KEY` | 对应环境的 SSH 私钥绝对路径，可留空使用 SSH Agent |
| `FF_IMAGE_REPO` | 镜像名称，默认应用名 |
| `FF_RUNTIME_IMAGE` | 自定义运行基础镜像的完整引用；应固定版本/digest |
| `FF_ARTIFACT` | 显式指定宿主产物路径（文件→`app.jar`，目录→`app/`）；多模块或自定义布局使用 |
| `FF_HEALTH_URL` | 可选目标机本地 HTTP 健康检查 URL，例如 `http://127.0.0.1:8080/actuator/health` |
| `FF_REQUIRE_DEV_PROOF` | 默认 `1`：生产晋级要求同一 Image ID 的 dev 健康验证收据；置 `0` 仅限风险评估后的显式应急，详见 [部署契约](deployment-contract.md) |
| `FF_WSL_DISTRO` | Windows 指定 WSL 发行版；默认取第一个可用发行版 |
| `FF_WSL_BRIDGE` | 设为 `0` 绕过 WSL 桥接；仅供测试/CI，Windows 生产使用违反团队规范 |

Windows 上容器与镜像构建一律经 WSL（`scripts/wsl-bridge.sh` 桥接）：编译出包在宿主完成，产物与 Dockerfile 经 git 透读管道进入 WSL 后 `docker build`，运行状态与 dev 收据保存在 WSL 侧 `~/.local/share/skills/`。没有 WSL 时镜像构建/部署直接失败，不回退本机直接启动。构建镜像与基础镜像常驻，任何流程不得 `rmi`/`prune`。

项目的 `.env.dev` / `.env.prod` 应包含 `APP_ENV`、`HOST_PORT`、`CONTAINER_PORT` 和应用必须的环境变量；真实密码不能入 Git。示例：

```dotenv
APP_ENV=dev
HOST_PORT=8080
CONTAINER_PORT=8080
SPRING_PROFILES_ACTIVE=dev
```

对生产可在本地受控环境使用 `FF_PROD_SSH` + SSH Agent，私钥权限必须适当；不要把真实地址凭证写进 Skill 或自动生成配置。

## 项目可覆盖的模板

- `Dockerfile.delivery` 是项目自定义的瘦构建定义；优先于内置 jar/web 瘦模板。与内置模板一样只做产物复制，不做编译；产物按栈约定路径放置或用 `FF_ARTIFACT` 指定。
- `compose.delivery.yml` 是项目特定运行定义；默认模板只支持一个名为 `app` 的服务。项目文件必须引用镜像 `${FF_IMAGE}`，不要声明 `build` 导致目标机重新编译。
- Compose 在目标目录运行，默认数据存放在目标用户的 `~/.local/share/skills/<app>` 下，而非需要 sudo 的 `/opt`。
- 由于 Compose 会同时用于服务变量替换及容器 env 注入，`APP_ENV` 与真实 env 文件保持一致。

## 环境一致性

必须在 dev / prod 使用相同镜像 Tag，并检查 Image ID。预先建立的 Docker Runtime image 不应编译进 dev/prod Secrets 或不同构建期 API Endpoint。

## 限制

模板针对常规 Spring Boot uber-jar 和 Node 静态前端。多模块 Maven/Gradle、Next.js SSR、原生扩展、ARM/AMD64 混用或多服务 Compose，请用 `FF_ARTIFACT` 指定产物并编写项目专用 `Dockerfile.delivery` 和 `compose.delivery.yml`，并先单独验证。默认镜像在本地目标架构构建；跨不同 CPU 架构不能仅靠 `docker save/load` 直接保证可运行。
