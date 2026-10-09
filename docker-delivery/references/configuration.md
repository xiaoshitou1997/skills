# 配置参考

## 环境变量

| 变量 | 含义 |
|---|---|
| `FF_DEV_SSH` | dev 目标 SSH，如 `devops@dev.example.com`；未设置走本机 Docker |
| `FF_PROD_SSH` | prod 目标 SSH；生产部署必填 |
| `FF_DEV_SSH_KEY` / `FF_PROD_SSH_KEY` | 对应环境的 SSH 私钥绝对路径，可留空使用 SSH Agent |
| `FF_IMAGE_REPO` | 镜像名称，默认应用名 |
| `FF_BUILD_IMAGE` / `FF_RUNTIME_IMAGE` | 自定义构建与运行基础镜像的完整引用；应固定版本/digest |
| `FF_HEALTH_URL` | 可选目标机本地 HTTP 健康检查 URL，例如 `http://127.0.0.1:8080/actuator/health` |

项目的 `.env.dev` / `.env.prod` 应包含 `APP_ENV`、`HOST_PORT`、`CONTAINER_PORT` 和应用必须的环境变量；真实密码不能入 Git。示例：

```dotenv
APP_ENV=dev
HOST_PORT=8080
CONTAINER_PORT=8080
SPRING_PROFILES_ACTIVE=dev
```

对生产可在本地受控环境使用 `FF_PROD_SSH` + SSH Agent，私钥权限必须适当；不要把真实地址凭证写进 Skill 或自动生成配置。

## 项目可覆盖的模板

- `Dockerfile.delivery` 是自定义 Docker 多阶段构建定义；优先于内置 Maven/Gradle/Node 模板。必须在镜像内完成依赖安装与编译。
- `compose.delivery.yml` 是项目特定运行定义；默认模板只支持一个名为 `app` 的服务。项目文件必须引用镜像 `${FF_IMAGE}`，不要声明 `build` 导致目标机重新编译。
- Compose 在目标目录运行，默认数据存放在目标用户的 `~/.local/share/skills/<app>` 下，而非需要 sudo 的 `/opt`。
- 由于 Compose 会同时用于服务变量替换及容器 env 注入，`APP_ENV` 与真实 env 文件保持一致。

## 环境一致性

必须在 dev / prod 使用相同镜像 Tag，并检查 Image ID。预先建立的 Docker Runtime image 不应编译进 dev/prod Secrets 或不同构建期 API Endpoint。

## 限制

模板针对常规 Spring Boot uber-jar 和 Node 静态前端。多模块 Maven/Gradle、Next.js SSR、原生扩展、ARM/AMD64 混用或多服务 Compose，请编写项目专用 `Dockerfile.delivery` 和 `compose.delivery.yml`，并先单独验证。默认镜像在本地目标架构构建；跨不同 CPU 架构不能仅靠 `docker save/load` 直接保证可运行。
