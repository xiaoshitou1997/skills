# k3s/k8s 部署映射

compose 规则到 k3s/k8s 的原则映射与差异点。**本文件是最佳实践草案**：映射关系按行业实践整理，具体参数（probe 阈值、资源值）部署前按集群实际校准；团队有实机经验后回填修正。三铁律不变：一项目一 namespace、环境即 namespace（`{项目}-{环境}`）、不共享集群级共享依赖。

## 原则映射

| compose 概念 | k3s/k8s 对应 | 要点 |
|---|---|---|
| 栈（compose 项目） | namespace：`{项目}-{环境}` | 环境即栈 → 环境即 namespace；资源（卷、Secret、Service）都在 namespace 内隔离 |
| `docker-compose.yaml` | Deployment/StatefulSet + Service 清单（Kustomize/Helm 组织） | 一个项目一个 overlay/values 文件组，目录 = 项目名 |
| service 名直连（同 compose） | 同 namespace 内 Service DNS（`{service}.{ns}.svc`） | 跨 namespace 调用须显式全名 + NetworkPolicy 控制面，等价 external 网络判定 |
| healthcheck | `readinessProbe` + `livenessProbe` | 探针判定树与假绿清单同样适用（见 [healthcheck-probes.md](healthcheck-probes.md)）；专用健康端点优先、TCP 探测禁作履职证明；Spring Boot 应用对接 `/actuator/health/readiness` 与 `/liveness`（实现归 mv-backend-standards） |
| `restart: unless-stopped` | Deployment 自愈（默认语义）；`restartPolicy: Never` 仅一次性任务 | 初始化容器改用 initContainers + 成功退出判定 |
| `depends_on: service_healthy` | initContainers 探针等待或应用重试逻辑 | k8s 无编排级依赖等待，启动顺序靠就绪探针 + 应用侧重试 |
| `deploy.resources.limits` | `resources.limits` + `requests` | 限额表同源（见 [resources-logging.md](resources-logging.md)）；requests 按实测稳态值设，不用上限值 |
| `.env` 插值 | Secret（敏感）/ ConfigMap（非敏感配置） | 生成规则与轮换周期同 [credentials.md](credentials.md)；k3s 支持 seeded Secret，生产仍走 secrets manager 下发 |
| logging max-size/max-file | 节点级轮转采集（容器 stdout 由集群日志栈采集） | 应用仍只写 stdout；不在容器内自建轮转文件 |
| 命名卷 `-data` | PVC（StorageClass 动态供给） | `-data`/`-home` 后缀语义延续到 PVC 命名；备份以数据类 PVC 为准 |
| host 端口判定 | Service type：ClusterIP 默认；对外暴露走 Ingress（TLS 终结）或 LoadBalancer | 栈内数据库/中间件一律 ClusterIP 不暴露；Ingress 终结 TLS 等价「反代终结 TLS」判定分支 |

## 差异与注意

- **环境隔离更强**：namespace 隔离默认不带网络策略，跨 namespace 流量默认可达——需要真隔离时配 NetworkPolicy 默认拒绝跨 ns；依赖随项目走（namespace 内自建数据库 StatefulSet 或用外部可寻址实例），不建集群级共享中间件。
- **探针语义分离**：k8s 区分 readiness（摘流量）与 liveness（重启进程），对应应用侧双探针端点；compose healthcheck 是单探针，迁移时按端点语义拆分，不把聚合依赖检查挂到 liveness。
- **资源上限不是全部**：k8s 还有 requests 调度语义与 LimitRange/ResourceQuota（namespace 级上限），namespace Quota 可承接「单项目不耗尽集群」的铁律意图。
- **镜像与版本**：固定具体版本规则不变；`imagePullPolicy` 随标签语义（非固定标签禁 `Always` 之外的假设）。
- **单机 k3s 与 compose 的选择**：单机自用、无编排需求 → compose；需要自愈、滚动升级、多实例或将来上多节点 → k3s。两者并存时同一项目只用一种形态，不双轨。

本文是 compose→k8s 映射草案；集群选型与安装归项目选型流程（mv-tech-stack-baseline），交付管线动作归 mv-container-deploy。
