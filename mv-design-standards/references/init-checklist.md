# 各端初始化详单

本 skill「新项目初始化」初始化步骤的逐端展开；执行顺序按正文编号步骤。只执行当前项目已确认端与组件的条目；无后端或数据库时跳过对应章节。每端收尾以「本地可启动 + 关键验收项通过」为准。

## 后端

1. 聚合工程：Maven + mvnw，模块按布局判据划分，版本对齐基线（Spring Boot 4.0.x、JDK 21）。
2. 基础设施接线：按项目范围接入开发服务器公共 infra 的 PostgreSQL、Redis、RabbitMQ、RustFS 或 SFTPGo，申请项目专用资源及凭据；数据库使用 Flyway（`V1__init.sql`）。仅在业务允许且实现安全降级时，允许缓存、消息或文件依赖缺失启动，并明确受影响功能。
3. 横切骨架：统一包络（code/message/data）、全局异常处理器、错误码枚举包、双语资源文件（`messages_zh_CN`/`messages_en_US`）、SLF4J 日志配置、`@ConfigurationProperties` 配置类骨架。
4. 安全骨架：RBAC 权限点模型与入口层校验机制（声明式注解或集中拦截器）；认证方案按项目确认，团队默认自建 JWT access + refresh，条款见 mv-coding-standards。
5. 健康探测：`management.endpoint.health.probes.enabled: true`，readiness/liveness 双探针。
6. 交付文件：每个后端入口各自定义构建目标、配置、端口、探针与 `Dockerfile.delivery`（基线镜像、非 root 10001、EXPOSE 8080）；`.dockerignore` 排除 `.git`、`.env*`。
7. 验收：逐入口以前台命令启动成功；各自 readiness 返回 UP；Flyway V1 应用成功；对应端的包络与探针冒烟请求通过，记录命令与结果。

## 运营管理后台

1. 以 shadcn-admin 为基线起步：Vite + React SPA + TypeScript strict + TanStack Router/Query/Table + Tailwind + shadcn/ui。
2. 衍生清理：移除 faker 演示数据与示例 features、Clerk 认证层替换为项目认证（守卫结构保留）、删除不用的示例路由并清理路由树。
3. 接入骨架：服务层封装（统一 base URL、包络解析、超时与取消）、双语文案骨架、错误码映射、RBAC 权限标识消费。
4. 验收：dev server 启动；已确认认证范围时验证对接后端的真实登录，已确认真实列表及权限范围时验证列表包络与权限点。未确认的认证或列表不构造业务功能；记录对应验收未执行及原因，不声称通过。

## 用户端网页

1. 确认公开网站与用户后台（Portal）范围；网站和 Portal 均以 shadcn-admin + Vite + React + TypeScript 为基线，共用工程时建立用户路由与布局，独立时新建工程，界面按用户任务设计；小型项目同样采用该基线。
2. 公开网站与 Portal 可共用工程或根据独立发布、技术需求拆分；分别按访问范围设置路由、布局和权限。
3. 服务层与类型接入按 repo-layout「共享契约与类型同步」条款。
4. 验收：dev server 启动；核心页面三态渲染正常。

## 用户端 H5/小程序（Taro）

1. `taro init`（React 语法 + TypeScript），编译目标 weapp + h5。
2. 工程条款按 mv-coding-standards 的 Taro 条款：路由与 tabbar、样式 rpx 基准、平台差异 API 走适配层。
3. 请求层复用判断：与用户端网页接口一致时共享服务层封装（抽共享包或初始化时复制并声明同步责任），不一致时独立封装并保持包络一致。
4. 验收：`npm run dev:h5` 启动；`dev:weapp` 构建产物可在微信开发者工具打开。

## 环境与交付配置

1. 公共 infra 接入说明与 `.env.example`：按 repo-layout 的本机公共 infra 配置产物流程读取和维护已确认信息；env 样例只含占位值。
2. `.gitignore` 忽略 `.env*`、`node_modules`、构建产物目录，并以 `!.env.example` 放行不含真实密钥的样例；确认各模块样例可被 Git 跟踪、真实 env 文件仍被忽略。
3. CI 样例入仓（见 repo-layout CI 条款）。
4. 全端收尾：宿主前台直启逐端验证并记录证据。

本文是初始化期的操作展开；初始化完成后的持续开发规范归 mv-coding-standards。
