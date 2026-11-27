# 配置参考

**当前 dev/prod 部署、回滚、状态查询和 target plan 均关闭；不会生成收据。** 下列交付变量仅供未来修复后的契约参考，独立预检仍会使用 SSH 变量连接目标机。

## 环境变量

| 变量 | 含义 |
|---|---|
| `FF_DEV_SSH` | dev 目标 SSH（必填），如 `devops@dev.example.com`；项目未声明开发服务器时向用户确认 |
| `FF_PROD_SSH` | prod 目标 SSH；生产部署必填 |
| `FF_DEV_SSH_KEY` / `FF_PROD_SSH_KEY` | 对应环境的 SSH 私钥绝对路径，可留空使用 SSH Agent |
| `FF_COMPOSE_FILE` | 项目自定义的 Compose 文件名 |
| `FF_HEALTH_URL` | dev 收据与 prod 门禁的 readiness 探活地址（如 `http://127.0.0.1:8080/actuator/health/readiness`）；必须能**从目标机访问**。强健康还要求全部已发现容器运行，且已配置的 HEALTHCHECK 为 healthy；未配置 HEALTHCHECK 的容器仍可通过。单个 URL 成功不证明各服务 readiness；仅声明单服务单副本且运行单容器时可记 strong；解析配置需要目标机 `python3`，缺失或解析失败时不能记 strong，多服务或多容器 dev 记 `readiness-partial`、不产生可晋级收据，prod 验证失败。未设置时部署最多记 `liveness-only`（HEALTHCHECK 通过）或 `running-only`，均不产生可晋级收据 |
| `FF_REQUIRE_DEV_PROOF` | dev/prod 部署与回滚当前由脚本拒绝，设置该变量不能解除限制；详见 [交付契约](deployment-contract.md) |
| `FF_READY_TIMEOUT` | 目标机就绪轮询上限秒数，默认 `50`；慢启动应用可调大，经 deploy.sh 透传到目标机 |

部署入口目前不会访问目标机，也不会写入发布历史或收据。已有历史文件不能证明当前实际运行状态；恢复交付前须重新验证安全性。

项目的 `.env.dev` / `.env.prod` 应包含 `APP_ENV`、`HOST_PORT`、`CONTAINER_PORT` 和应用必须的环境变量；真实密码不能入 Git。示例：

```dotenv
APP_ENV=dev
HOST_PORT=8080
CONTAINER_PORT=8080
SPRING_PROFILES_ACTIVE=dev
```

对生产可在本地受控环境使用 `FF_PROD_SSH` + SSH Agent，私钥文件权限收紧至仅当前用户可读（如 `chmod 600`）；不要把真实地址凭据写进 Skill 或自动生成配置。

## 项目可覆盖的模板

- `compose.delivery.yml` 是项目特定运行定义；默认模板只支持一个名为 `app` 的服务。项目文件必须引用镜像 `${FF_IMAGE}`，不要声明 `build` 导致目标机重新编译。
- Compose 在目标目录运行，默认数据存放在目标用户的 `~/.mv/delivery-standards/<app>` 下，而非需要 sudo 的 `/opt`。
- 由于 Compose 会同时用于服务变量替换及容器 env 注入，`APP_ENV` 与真实 env 文件保持一致。
- Node 静态前端在 env 文件中设置 `CONTAINER_PORT=80`。

## 环境一致性

必须在 dev / prod 使用相同镜像 Tag，并检查 Image ID。预先建立的 Docker Runtime image 不应编译进 dev/prod Secrets 或不同构建期 API Endpoint（构建期固化在出包阶段处理，见 [构建契约](build-contract.md)）。

## 限制

默认模板针对常规 Spring Boot uber-jar 和 Node 静态前端的单服务 Compose。多服务 Compose 的生产交付不受支持；`--service` 单服务回退被拒绝。镜像在构建点按其架构构建；跨 CPU 架构分发需镜像仓库侧多架构支持。
