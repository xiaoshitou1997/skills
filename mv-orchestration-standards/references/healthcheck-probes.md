# 探针判定与就绪语义

mv-orchestration-standards 关键规则 6 的展开：healthcheck 判定树、假绿清单、工具/端点核实与 start_period 估值。k8s probe 映射见 [k8s-mapping.md](k8s-mapping.md)。

## 原则

healthcheck 的意义是「服务在履职并就绪」，端口被绑定 ≠ 履职；探针必须验证服务真的在响应。优先级：专用健康端点 > 官方探针/脚本 > 不配。

## 判定树（逐服务自上而下，命中即停）

1. 一次性初始化任务 → 不配。
2. 镜像基于 `FROM scratch`、无 shell 或无探针工具（curl/wget/nc/bash 等）→ 无法定义有效探针，豁免。
3. 应用提供专用健康端点（`/health`、`/health/readiness`、`/livez`、`/ready` 等，返回应用主动判定的就绪/存活状态）→ 用端点。
4. 有官方探针命令/脚本 → 用之，按来源分级：官方随镜像提供 / 官方文档明载 > 官方工具/端点 + 社区惯例。常用对照（以各版本官方文档核实为准）：
   - mariadb：官方镜像自带 `healthcheck.sh`；postgres：`pg_isready`。
   - 对象存储类（如 RustFS）：官方文档明载的健康端点（如 `curl -sf http://127.0.0.1:9000/health`）。
   - mysql：`mysqladmin ping`；redis：`redis-cli ping`（开 requirepass 须带认证）。
   - 镜像无 HTTP 客户端时，官方 CLI 能验证 API 履职的即为探针（如 ollama `ollama list`）。
5. 以上皆无 → 不配。

## 禁止假绿

以下不算有效探针，不得使用：

- 纯 TCP 端口探测（`bash -c ': > /dev/tcp/...'`、`nc -z`）：只证明端口被绑定，不证明应用响应。
- 通用 Web 根路径探针（`curl -f http://localhost:{port}/`、`wget --spider /`）作为唯一手段：只证明 Web 进程存活，数据库等依赖挂掉时仍返回 200；有专用端点时不得退回根路径。

## 工具与端点核实（选探针前两项都须确认）

- 工具在目标镜像内实测存在：`docker run --rm --entrypoint sh <image> -c "command -v <tool>"`；alpine 用 busybox wget/nc；ubuntu/debian 的 `/bin/sh` 是 dash 不支持 `/dev/tcp`，须显式 `bash -c`；python 镜像用 urllib。
- 端点以官方文档或源码核实存在，不凭惯例猜路径（`/health` 与 `/healthz` 一字之差即假红）；拿不准就首启实测。
- 无法确认即豁免（按「不配」处理）：镜像不可得、工具无法实测、端点无法核实 → 禁止以「双回落/多工具猜测」上线未验证探针——假红探针比没有探针更糟。

## 参数

- 间隔 5-10s，超时 5s，retries 10 次；确因技术栈特征（慢启动、重资源）放宽时，在该服务 healthcheck 块行内注释写明原因，无注释偏离视为违规。
- start_period 按冷启动特征取初始值，首次部署后按 `docker inspect --format='{{.State.Health.Log}}' {容器名}` 实测回填：

| 技术栈 | 初始 start_period |
|---|---|
| Go / Node / 轻中间件（redis 类） | 10-30s |
| 数据库（mysql、postgres） | 30s |
| Python 应用（含 DB 迁移） | 60s |
| Java / Spring Boot（首启含 schema 初始化） | 60-90s |

拿不准取上限。

本文只判定探针配置；应用侧健康端点（readiness/liveness 双探针）的实现规范归 mv-backend-standards，部署健康验证与收据归 mv-container-deploy。
