# 各端初始化详单

mv-project-scaffold 初始化步骤的逐端展开；执行顺序按正文编号步骤。每端收尾以「本地可启动 + 关键验收项通过」为准。

## 后端

1. 聚合工程：Maven + mvnw，模块按布局判据划分，版本对齐基线（Spring Boot 4.0.x、JDK 21）。
2. 基础设施接线：PostgreSQL 连接、Flyway（`V1__init.sql`）、Redis/RabbitMQ/RustFS 按范围接入；保持惰性依赖——应用可独立于缓存/MQ 启动。
3. 横切骨架：统一包络（code/message/data）、全局异常处理器、错误码枚举包、双语资源文件（`messages_zh_CN`/`messages_en_US`）、SLF4J 日志配置、`@ConfigurationProperties` 配置类骨架。
4. 安全骨架：RBAC 权限点模型与入口层校验机制（声明式注解或集中拦截器）；认证方案按项目确认，团队默认自建 JWT access + refresh，条款见 mv-backend-standards。
5. 健康探测：`management.endpoint.health.probes.enabled: true`，readiness/liveness 双探针。
6. 交付文件：`Dockerfile.delivery`（基线镜像、非 root 10001、EXPOSE 8080）、`.dockerignore`（排除 `.git`、`.env*`）。
7. 验收：`mvnw spring-boot:run` 前台启动成功；readiness 返回 UP；Flyway V1 应用成功；包络与探针冒烟请求通过。

## admin 端

1. 以 shadcn-admin 为基线起步：Vite + React SPA + TypeScript strict + TanStack Router/Query/Table + Tailwind + shadcn/ui。
2. 衍生清理：移除 faker 演示数据与示例 features、Clerk 认证层替换为项目认证（守卫结构保留）、删除不用的示例路由并清理路由树。
3. 接入骨架：服务层封装（统一 base URL、包络解析、超时与取消）、双语文案骨架、错误码映射、RBAC 权限标识消费。
4. 验收：dev server 启动；登录流程可用（对接后端认证）；一个真实列表页跑通包络与权限点。

## user PC 端

1. Vite SPA 与 admin 同底座起步（无管理壳：侧栏、命令面板按用户端信息架构自建）。
2. SEO/SSR 需求先回 mv-tech-stack-baseline 评审；评得 Next.js 后按 mv-frontend-standards 的 Next.js 条款初始化，不在 SPA 内变通。
3. 服务层与类型接入按 repo-layout「共享契约与类型同步」条款。
4. 验收：dev server 启动；核心页面三态渲染正常。

## H5/小程序端（Taro）

1. `taro init`（React 语法 + TypeScript），编译目标 weapp + h5。
2. 工程条款按 mv-frontend-standards 的 Taro 条款：路由与 tabbar、样式 rpx 基准、平台差异 API 走适配层。
3. 请求层复用判断：与 user PC 端接口一致时共享服务层封装（抽共享包或初始化时复制并声明同步责任），不一致时独立封装并保持包络一致。
4. 验收：`npm run dev:h5` 启动；`dev:weapp` 构建产物可在微信开发者工具打开。

## 环境与交付配置

1. `compose.dev.yml` 与 `.env.example`：见 repo-layout 拓扑条款；env 样例只含占位值。
2. `.gitignore` 覆盖 `.env*`、`node_modules`、构建产物目录。
3. CI 样例入仓（见 repo-layout CI 条款）。
4. 全端收尾：宿主前台直启逐端验证并记录证据。

本文是初始化期的操作展开；初始化完成后的持续开发规范归 mv-backend-standards、mv-frontend-standards 与 mv-test-standards。
