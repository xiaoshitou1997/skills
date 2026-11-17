# k3s/k8s 部署映射

compose 规则到 k3s/k8s 的原则映射与差异点。**本文件是最佳实践草案**：映射关系按行业实践整理，具体参数（probe 阈值、资源值）部署前按集群实际校准；团队有实机经验后回填修正。三铁律不变：一项目一 namespace、环境即 namespace（`{项目}-{环境}`）、不共享集群级共享依赖。

## 原则映射

| compose 概念 | k3s/k8s 对应 | 要点 |
|---|---|---|
| 栈（compose 项目） | namespace：`{项目}-{环境}` | 环境即栈 → 环境即 namespace；资源按 namespace 分组，网络和访问权限须另行配置并验证 |
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

以下清单在目标 namespace 中建立默认拒绝入口与出口；此时 DNS、入口控制器、监控及业务连接也会被拒绝，须按实际端点补充最小允许策略，再执行连通性验收：

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny
  namespace: example-prod
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
```

策略是叠加允许语义：同一 Pod 被多条策略选中时，任何策略允许的流量都会放行。上线前检查同 namespace 已有策略和实际 CNI 能力；对已上线系统先在测试环境演练放行清单与回退，避免直接中断流量。

## 差异与注意

- **环境隔离**：namespace 本身不是网络安全边界。各环境 namespace 默认配置 ingress 和 egress 双向拒绝的 NetworkPolicy，再按实际依赖放行同环境服务、DNS、入口及明确授权的外部依赖；跨环境访问默认拒绝，例外记录来源、目标、端口和责任人。先确认 CNI 实施 NetworkPolicy，否则不能宣称隔离生效。
- **验证隔离**：在 dev 与 prod 各部署受控测试 Pod；从 dev 访问 prod 业务与数据库端口应失败，从同环境访问明确放行的服务和 DNS 应成功。记录源/目标、端口、命令与结果；策略部署成功或 DNS 解析成功不等于网络隔离已生效。
- **凭据隔离**：生产与开发使用独立 Secret 和服务账号，RBAC 只授予目标 namespace 内所需操作，限制 list/watch/get Secret 权限；启用并验证集群 Secret 静态加密或使用外部 secrets manager。以授权和未授权身份分别执行访问验证，不输出真实 Secret 值。依赖随项目走，不建跨项目共享中间件。
- **探针语义分离**：k8s 区分 readiness（摘流量）与 liveness（重启进程），对应应用侧双探针端点；compose healthcheck 是单探针，迁移时按端点语义拆分，不把聚合依赖检查挂到 liveness。
- **资源上限不是全部**：k8s 还有 requests 调度语义与 LimitRange/ResourceQuota（namespace 级上限），namespace Quota 可承接「单项目不耗尽集群」的铁律意图。
- **镜像与版本**：固定具体版本规则不变；`imagePullPolicy` 随标签语义（非固定标签禁 `Always` 之外的假设）。
- **单机 k3s 与 compose 的选择**：单机自用、无编排需求 → compose；需要自愈、滚动升级、多实例或将来上多节点 → k3s。两者并存时同一项目只用一种形态，不双轨。

本文是 compose→k8s 映射草案；集群选型与安装归项目选型流程（mv-tech-stack-baseline），交付管线动作归 mv-container-deploy。
