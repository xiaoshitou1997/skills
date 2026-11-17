---
name: mv-orchestration-standards
description: 编写、审查或整改容器编排文件时使用：写 Docker Compose 项目（应用加自带数据库的完整栈）、定 healthcheck 探针、定资源限额与日志轮转、管 compose 凭证与环境变量注入、规划 k3s/k8s 部署映射（namespace、probe、Secret），或排查编排配置问题。自研应用的交付管线动作（出包、镜像构建、dev/prod 收据晋级）归 mv-container-deploy；交付后稳态运维归 mv-ops-standards。
---

# 容器编排规范

面向 mv 团队自托管与自研应用共用的编排编写规范：一项目一栈、环境即栈、栈内自闭环。交付管线动作与稳态运维不归本 skill。

## 作用与优先级

这是**规范型 Skill**，在编写、审查、整改 compose 与 k8s 编排时引用；不执行部署动作，不写部署收据，不做交付后巡检。优先级：用户明确需求和项目已采纳的规范 / ADR → 本规范 → 官方默认。规范中的数值（探针间隔、限额表、轮转参数）为默认基线，项目按实际负载调整并记录。

## 三条铁律

1. **一项目一 stack/ns**：一个产品一个 compose 项目 / 一个 namespace，数据库与中间件随项目栈走，栈内自闭环；不做跨项目共享实例。
2. **环境即栈**：同一项目不同环境是两个独立 stack/ns（如 `halo-dev` / `halo-prod`），数据卷、数据库、网络、凭据互不共享；不存在「同一 stack 切换环境」的形态。
3. **禁止共享基础设施**：不设 infra 类跨项目共享基建栈；跨栈只允许应用级调用（external 网络或可路由地址），不允许共享数据库、缓存、消息中间件实例。

## 关键规则

1. 栈名全小写 DNS-1123 label（小写字母数字、连字符分段，形如 `halo-dev`），取官方产品名小写、连字符保留（`open-webui`），跨产品聚合类用语义词；目录名 = 栈名 = compose 项目名，不设顶层 `name:`，不设 `container_name`。k8s 侧 namespace 同规则。
2. 一个项目一个目录：`{栈名}/docker-compose.yaml` 与项目配置文件同目录；部署命令 `cd {栈名} && docker compose up -d`。
3. 显式声明网络 `networks.default.name: {栈名}-net`，随栈名同步；跨栈通信走共享 external 网络，禁止经宿主机发布端口或 `localhost` 绕行；目标是宿主机原生进程时才允许 `host.docker.internal` 并声明 `extra_hosts`，不为「将来可能用」保留投机映射。
4. 端口判定逐服务自上而下：反代终结 TLS → 后端只发布 HTTP 端口；栈内数据库/中间件 → 不发布端口，映射以注释声明；官方文档有 host 端口示例 → 取示例值；无示例 → host 端口 = 容器内官方监听端口；同一 compose 内多服务端口冲突 → 后者 +1 递增；跨栈重复不处理，按需启停。偏离必须行内注释写明原因，无注释偏离即违规。
5. 镜像固定具体版本，禁 `latest`/`main`/无标签；有 Alpine 变体一律用 Alpine（glibc 依赖或 C 扩展本地编译不兼容时退 `-slim`/官方变体并注释）；晋级使用已验证的同一镜像身份，验证、发布和回滚期间环境可暂时运行不同版本；上游仅维护 latest 的镜像允许 latest，EOL 镜像继续使用须行内注释登记理由与评估日期。
6. healthcheck 必须证明「服务在履职」：专用健康端点 > 官方探针/脚本 > 不配；纯 TCP 探测与根路径探针是假绿，禁止作为手段；探针工具与端点都须实测核实，无法确认即按「不配」处理——假红探针比没有探针更糟。判定树与 start_period 初始值见 [references/healthcheck-probes.md](references/healthcheck-probes.md)。
7. 启动顺序用 `depends_on` + `condition: service_healthy`；被依赖方无探针时退 `service_started`；一次性初始化容器不配探针、restart 省略，依赖方用 `service_completed_successfully` fail-closed；每服务 `restart: unless-stopped`（初始化容器除外）。
8. YAML 写法：`command` 内联列表、`environment` map、`volumes`/`ports` 列表；service 键按 image→privileged→command→environment→volumes→ports→networks→extra_hosts→init→shm_size→stop_grace_period→secrets→healthcheck→depends_on→logging→restart→deploy 排列，顶层键 volumes→networks→secrets→services；删除注释掉的配置行，偏离注释与分块标题保留。
9. 数据卷默认命名卷（`{用途}-data`/`{用途}-home`，判定见 [references/compose-rules.md](references/compose-rules.md)）；仅预置仓库配置与挂载宿主机资源两类例外用 bind，bind 源路径用 `./` 或绝对路径，禁 `~`。
10. 凭证分级生成与注入：按 §凭证分级表选强度与命令生成，统一 `.env` 插值注入；**凭据不进 Git**（真实值不入版本控制，生产/CI 环境用 secrets manager），分类型生成命令与轮换周期见 [references/credentials.md](references/credentials.md)。
11. Spring Boot 项目经环境变量宽松绑定注入（`spring.datasource.url` → `SPRING_DATASOURCE_URL`），不走 PARAMS 转发或启动包装；禁止自定义 entrypoint 包装脚本改配置，配置走组件官方渠道，发现自建包装脚本即回归官方方式并删除脚本。
12. 所有服务配 `deploy.resources.limits`（防止单服务耗尽宿主机）与 logging 限额（`max-size`/`max-file`）；参数按服务类型取值表执行，见 [references/resources-logging.md](references/resources-logging.md)。
13. 检测到透明加密软件时，按当前宿主已验证的透明通道读写 `.env`、SQL 等文件，不预设所有命令行或编辑器具有相同行为；传输与部署仍经 SSH，在目标服务器验证文件可读、配置可解析，不以宿主读取正常代替目标侧验证。
14. 新增栈按 SOP 执行，部署后过校验清单；两份清单见 [references/sop-checklist.md](references/sop-checklist.md)。
15. k3s/k8s 部署映射（namespace、probe、Secret、requests/limits）见 [references/k8s-mapping.md](references/k8s-mapping.md)；compose 规则到 k8s 的对应关系与差异点以该文件为准。

## 输出

交付说明列出：栈名与目录、逐服务判定记录（端口、探针、卷形态、限额）、偏离项及行内注释位置、凭证生成与落点（不含值）、部署后校验结果；未执行的检查如实写「未执行」。

## 边界

自研应用的交付管线动作（出包、镜像构建、dev/prod 收据晋级、回滚）归 mv-container-deploy，其落到目标机的 compose 文件同样遵守本规范；交付后稳态运维（日志聚合、备份演练、巡检）归 mv-ops-standards；镜像构建期扫描与包版本管理归 mv-image-builder；跨栈凭据生命周期、数据保护与安全评审归 mv-security-standards。运行期故障排查时探针语义与健康日志核验归本规范，容器操作本身归 mv-container-deploy。

## 参考

- references/compose-rules.md — 命名、网络、端口、镜像、YAML 键序、数据卷形态与卷名后缀判定
- references/healthcheck-probes.md — 探针判定树、假绿清单、start_period 初始值表与实测回填
- references/credentials.md — 凭证分级生成表、.env 注入机制、轮换周期与透明加密环境注意
- references/resources-logging.md — 资源限额表与日志轮转参数
- references/k8s-mapping.md — compose 规则到 k3s/k8s 的映射与差异点
- references/sop-checklist.md — 新增栈 SOP 与部署后校验清单
