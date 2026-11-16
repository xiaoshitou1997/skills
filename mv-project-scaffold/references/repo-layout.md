# 仓库布局与基础设施拓扑

mv 团队项目仓库布局默认形态与共享契约约定；配合 mv-project-scaffold 正文判据使用。既有项目以实际布局为准。

## 单仓多模块布局

默认目录形态（端按项目需要裁剪）：

```text
<project>/
├── server/                  后端聚合工程（Maven 多模块）
│   ├── <project>-common/
│   ├── <project>-api/       跨端契约：服务接口 + DTO（有外部集成方才拆）
│   ├── <project>-domain/    实体、仓储、业务用例（第二个可运行消费者出现前可并入 service）
│   └── <project>-service/   可运行入口（单入口时 controller/admin/ 与 controller/uc/ 分包）
├── admin/                   管理端（shadcn-admin 衍生，Vite SPA）
├── user-web/                用户 PC 端（Vite SPA；SSR 需求按选型评 Next.js）
├── mobile/                  Taro H5/小程序端（按需）
├── compose.dev.yml          本地/联调基础设施编排
├── .env.example             环境变量样例（占位值）
└── .github/workflows/       CI 样例
```

- 目录名即模块名逐字相同（Maven artifactId、npm name 均取目录名），命名闭集细节见 mv-backend-standards 模块命名条款。
- 前端工程不进后端聚合 pom；后端模块不引用前端目录。
- 多仓拆分判据见正文「仓库布局判据」；多仓时契约经 `-api` 模块发包共享，不复制 DTO 源码。

## 共享契约与类型同步

- 契约真源是后端：接口经 springdoc/OpenAPI 暴露（`springdoc-openapi` starter，`/v3/api-docs`），接口文档与契约同源生成，不手写第二份。
- 前端类型来源二选一并全项目一致：经 OpenAPI 生成器从 `/v3/api-docs` 生成 TS 类型，或从 `-api` 模块 DTO 集中映射（`types/api` 集中定义）；不散落各页面重复声明。
- 后端字段变更同步前端类型的责任在变更方：契约变更提交说明列出受影响端，前端类型与映射层在同一变更内更新。

## compose.dev 拓扑

- 基础设施固定版本 Tag（不用 `latest`）：PostgreSQL 必选；Redis、RabbitMQ、RustFS 按项目确认范围启停；数据卷命名带项目前缀防串。
- 端口约定：同一开发服务器多项目共存时，宿主映射端口按项目分配区间并记录在项目 README，避免冲突；容器内端口用各组件默认值。
- `compose.dev.yml` 只含基础设施与联调依赖；业务服务本地经 mv-local-debug 宿主直启，不进 dev 编排（项目文档化开发拓扑为容器时除外，归 mv-container-deploy 的 dev 交付）。

## CI 样例

- 最小门禁：PR 触发「后端编译 + 单测」「各端 lint + typecheck + 单测」两条 job，样例用 GitHub Actions；跑不通的流水线不入主干。
- 交付类检查（镜像构建、部署）不在 CI 样例内，归 mv-image-builder 与 mv-container-deploy 的交付流程。

本文只定仓库布局与本地拓扑；后端模块命名细则归 mv-backend-standards，交付编排与部署归 mv-image-builder 与 mv-container-deploy。
