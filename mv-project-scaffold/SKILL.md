---
name: mv-project-scaffold
description: 新项目从零初始化，或既有项目新增端/新增模块时使用：初始化 Git 仓库、确定仓库布局与模块划分、搭后端 Spring Boot 骨架、起 shadcn-admin 管理端、起 Vite SPA 用户端、起 Taro H5/小程序端、配置 compose.dev 与环境变量样例、落位 Dockerfile.delivery、建立首次数据库迁移与 CI 样例。技术栈选型与版本基线归 mv-tech-stack-baseline；业务功能编码归 mv-backend-standards 与 mv-frontend-standards。
---

# 项目脚手架

面向 mv 团队新项目的从零到可运行骨架：仓库布局、三端初始化、交付与环境配置一次落位。技术栈定版之后的业务编码、既有项目的常规功能开发不归本 skill。

## 作用与优先级

这是**过程型 Skill**，在新项目初始化与新增端/模块时执行；优先级：用户明确需求和项目已采纳的规范 / ADR → mv-tech-stack-baseline 基线 → 生态默认。初始化产出的骨架持续遵守 mv-backend-standards 与 mv-frontend-standards，本 skill 不重复其条款。

## 开始前确认

先按 mv-requirements-standards 读取已有项目上下文，复用已确认的范围与业务约定；脚手架不重新定义业务模型。开始前确认：项目名与应用名（APP 名，部署侧同用）、需要的端（后端、admin、user PC、H5/小程序按需）、仓库形态（单仓多模块或多仓）、基础设施范围（是否需要 PostgreSQL、Redis、RabbitMQ、RustFS）。只对会影响本次初始化且资料中缺失的决策补充确认，不默认全量端全量设施。纯前端、无数据库或已有后端的任务只初始化所需部分，不附带新增 Spring Boot、数据库或认证系统。

## 仓库布局判据

系统形态（单体、按端切、按域切、微服务）按 mv-architecture-standards 判定；本节只负责把选定形态落成目录与模块。

1. 单仓多模块为默认：后端与各端模块目录同仓平铺（后端 `-common`/`-service` 与按端契约 `-user-api`/`-admin-api`，前端 `-admin-web`/`-user-web`/`-user-mp` 按需），小团队同迭代发布优先。
2. 出现独立团队、独立发布节奏或独立访问控制的模块才拆多仓，不为「看起来干净」拆仓。
3. 模块与目录命名按 mv-backend-standards 模块命名闭集执行：目录名即模块名，端词固定占用 `admin`（管理端）、`user`（用户端），不与域词混用。
4. 契约在后端 api 模块承载（服务接口 + DTO）并按端拆分（`-user-api`/`-admin-api`），前端类型从契约生成或集中映射，不在各端重复手写后端字段。

## 初始化步骤

只执行已确认范围对应的步骤；后端、各前端、数据库与基础设施均按实际需要落位，不把完整示例当作每个项目的必建清单。

1. 建仓库与首次提交：`git init` 后首次提交为空提交（`git commit --allow-empty`），README、骨架代码从第二个提交开始；分支模型按团队约定（默认 `main`）。
2. 后端骨架：Spring Boot 4 + JPA + PostgreSQL + Flyway 首迁（V1 建表与种子数据）、统一包络、readiness/liveness 双探针、错误码枚举与双语资源骨架、`.dockerignore` 与 `Dockerfile.delivery`（基线镜像 eclipse-temurin:21-jre、非 root 10001、端口 8080）；模块划分按「仓库布局判据」。
3. admin 端：以 shadcn-admin 为基线起步（Vite + React SPA + TanStack + Tailwind），衍生清理（faker 演示数据、Clerk 认证替换、示例路由）按 mv-frontend-standards 的 Vite SPA 条款执行；对接后端包络与 RBAC 权限点。
4. user PC 端（按需）：Vite SPA 与 admin 同底座起步；页面级 SEO/SSR 需求先回 mv-tech-stack-baseline 评 Next.js，不在 SPA 内变通。
5. H5/小程序端（按需）：Taro（React 语法）初始化，编译目标 weapp + h5；工程条款见 mv-frontend-standards 的 Taro 条款。
6. 环境配置：`compose.dev.yml` 描述开发服务器上的联调基础设施（需要关系型持久化时默认 PostgreSQL，Redis/RabbitMQ/RustFS 按确认范围，固定版本 Tag），服务器经 SSH 访问；无联调基础设施时不生成空编排。`.env.example` 使用占位值并纳入版本控制，真实 env 文件保持未跟踪。`.gitignore` 忽略 `.env*` 并以 `!.env.example` 放行样例。
7. 首次迁移与种子数据：需要数据库的项目建立 V1；已确认的 RBAC 权限点、菜单及字典按实际范围加入种子数据（幂等 upsert），与代码同版本发布。不预置订单、会员、支付等未确认业务表，也不为无管理端的项目创建演示菜单。
8. CI 样例：PR 触发「编译 + lint + 单测」工作流样例（GitHub Actions），作为项目最小门禁起点，按项目演进调整。
9. 本地验证：宿主前台直启跑通后端与各端（前台可见窗口运行、Ctrl-C 可停），记录「编译/启动/首屏」证据后收尾。

## 硬约束

- **版本与依赖一律取自 mv-tech-stack-baseline 基线**，不引入基线外依赖；确需偏离先走选型流程产出简版 ADR。
- **环境变量样例不含真实密钥**，占位值即可；真实凭据经运行时注入，不进仓库；数据分级与凭据要求按 mv-security-standards 落位。
- **初始化不连生产**：全流程只接触本地与开发环境。
- 首次提交为空提交，不夹带文件。

## 输出

产出可运行的骨架仓库（端按需）、env 样例与 CI 样例；有联调基础设施时产出 `compose.dev.yml`，有数据库时产出首次迁移；交付说明记录：布局形态与理由、偏离基线项及对应 ADR、各端本地验证证据、未初始化的端与原因。

## 边界

技术栈选型与版本基线归 mv-tech-stack-baseline；系统形态、服务边界与集成方式归 mv-architecture-standards；安全政策、数据分级与凭据治理归 mv-security-standards；初始化后的业务编码规范归 mv-backend-standards 与 mv-frontend-standards；镜像构建归 mv-image-builder，容器部署归 mv-container-deploy；测试分层与写法归 mv-test-standards。

## 参考

- references/repo-layout.md — 单仓多模块布局、目录树样例、共享契约与类型同步、compose.dev 拓扑与 CI 样例
- references/init-checklist.md — 各端初始化步骤详单与逐端验收清单
