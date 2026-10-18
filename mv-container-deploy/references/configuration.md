# 配置参考

## 环境变量

| 变量 | 含义 |
|---|---|
| `FF_DEV_SSH` | dev 目标 SSH，如 `devops@dev.example.com`；未设置走本机容器运行时（Windows 为 WSL Docker，Linux/macOS 为宿主 Docker） |
| `FF_PROD_SSH` | prod 目标 SSH；生产部署必填 |
| `FF_DEV_SSH_KEY` / `FF_PROD_SSH_KEY` | 对应环境的 SSH 私钥绝对路径，可留空使用 SSH Agent |
| `FF_COMPOSE_FILE` | 项目自定义的 Compose 文件名 |
| `FF_HEALTH_URL` | 可选目标机本地 HTTP 健康检查 URL，例如 `http://127.0.0.1:8080/actuator/health`；必须能**从目标机访问**，不要求客户端能够访问 |
| `FF_REQUIRE_DEV_PROOF` | 默认 `1`：生产晋级要求同一 Image ID 的 dev 健康验证收据；置 `0` 仅限风险评估后的显式应急，详见 [交付契约](deployment-contract.md) |
| `FF_READY_TIMEOUT` | 目标机就绪轮询上限秒数，默认 `50`；慢启动应用可调大，经 deploy.sh 透传到目标机 |
| `FF_WSL_DISTRO` | （仅 Windows 桥接生效）指定 WSL 发行版；默认取第一个可用发行版。其余宿主忽略 |
| `FF_WSL_BRIDGE` | （仅 Windows 桥接生效）设为 `0` 绕过 WSL 桥接走宿主 Docker；仅供测试/CI，Windows 生产使用违反团队规范。其余宿主忽略 |

Windows 上容器部署一律经 WSL（`scripts/wsl-bridge.sh` 桥接）：镜像由 mv-image-build 在宿主出包后构建，本 skill 经 WSL 执行 docker；运行状态、dev 收据与发布历史保存在 WSL 侧 `~/.mv/container-deploy/`。Linux/macOS 宿主由 `wsl-bridge.sh` 判定后直连本机 Docker，收据与发布历史落本机用户目录同一路径。Windows 缺 WSL 或宿主缺 Docker 时部署直接失败，不虚构部署成功。

项目的 `.env.dev` / `.env.prod` 应包含 `APP_ENV`、`HOST_PORT`、`CONTAINER_PORT` 和应用必须的环境变量；真实密码不能入 Git。示例：

```dotenv
APP_ENV=dev
HOST_PORT=8080
CONTAINER_PORT=8080
SPRING_PROFILES_ACTIVE=dev
```

对生产可在本地受控环境使用 `FF_PROD_SSH` + SSH Agent，私钥权限必须适当；不要把真实地址凭证写进 Skill 或自动生成配置。

## 项目可覆盖的模板

- `compose.delivery.yml` 是项目特定运行定义；默认模板只支持一个名为 `app` 的服务。项目文件必须引用镜像 `${FF_IMAGE}`，不要声明 `build` 导致目标机重新编译。
- Compose 在目标目录运行，默认数据存放在目标用户的 `~/.mv/container-deploy/<app>` 下，而非需要 sudo 的 `/opt`。
- 由于 Compose 会同时用于服务变量替换及容器 env 注入，`APP_ENV` 与真实 env 文件保持一致。
- Node 静态前端在 env 文件中设置 `CONTAINER_PORT=80`。

## 环境一致性

必须在 dev / prod 使用相同镜像 Tag，并检查 Image ID。预先建立的 Docker Runtime image 不应编译进 dev/prod Secrets 或不同构建期 API Endpoint（构建期固化归 `mv-image-build` 出包阶段处理）。

## 限制

默认模板针对常规 Spring Boot uber-jar 和 Node 静态前端的单服务 Compose。多服务 Compose 请提供项目专用 `compose.delivery.yml` 并先单独验证。镜像在本地目标架构构建；跨不同 CPU 架构不能仅靠 `docker save/load` 直接保证可运行。
