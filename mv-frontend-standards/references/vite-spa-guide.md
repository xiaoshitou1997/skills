# Vite SPA 与 shadcn-admin 条款

项目实际使用 Vite + React SPA 时并读本文件；基于 shadcn-admin（https://github.com/satnaing/shadcn-admin）衍生的后台管理类项目额外适用「shadcn-admin 衍生基线」。通用条款见 [frontend-guide.md](frontend-guide.md)。与项目已确立基线冲突时以项目为准；脚手架升级（模板上游演进）是独立决策，按 mv-tech-stack-baseline 升级流程处理。

## 渲染模式与交付

- Vite 项目默认 SPA + 静态产物交付：`dist/` 走内置静态站点模板（nginx 托管，`CONTAINER_PORT=80`）；需要 SSR 的项目自备 `Dockerfile.delivery`，不混用两套交付方式。
- SPA 路由是前端路由，刷新直达与深链依赖部署侧 fallback（历史路径回退到 `index.html`）；交付确认 nginx 模板已覆盖，未覆盖按交付契约补配置，不在前端 hack 绕过。
- 需要服务端渲染、SEO 或首屏关键指标强约束的页面级需求，先回到技术选型评估（归 mv-tech-stack-baseline），不在 SPA 内堆砌变通方案。

## 路由（TanStack Router）

- 路由用文件式结构组织（脚手架 `routes/` 目录），路由层只做组装、守卫与数据编排；页面业务拆到 `features/<域>/`，路由文件不堆业务逻辑。
- 可公开分享的搜索参数（页码、非敏感筛选）用类型化 search params 承载并校验（zod schema 同源类型），不手写 `URLSearchParams` 拼串；敏感条件与不适合分享的选中状态放受控会话或组件状态，导航产生的临时状态（弹窗来源页）用 `router` 状态或 location state，不全局变量。
- 路由守卫（登录、权限）集中在路由定义层的 `beforeLoad` 一类钩子，不在页面组件内各自判断；无权限路径重定向到约定页面并记录目标页，登录后跳回。
- 类型安全路由导航：链接与跳转用路由实例的类型化 API（`Link`、`navigate`），不用裸字符串拼路径。

## 数据获取（TanStack Query）

- 服务端状态统一由 Query 管理：query key 按域分层设计（列表、详情、字典各自独立 key），失效（invalidate）范围取最小受影响集合，不整站失效。
- 变更（mutation）成功后的缓存更新显式声明：失效相关 query 或直接 setQueryData 二选一，同一域内口径一致。
- 请求执行统一走封装的服务层（统一 base URL、错误包络、超时与取消），Query 只管缓存与编排，不在 queryFn 里散落裸 `axios` 调用与硬编码地址。
- 分页、筛选参数进 query key，参数变化即新查询，由 Query 处理竞态（保留最后一次）；输入联想等高频请求启用防抖与 `cancelRefetch`，不做时序幸运假设。
- 枚举字典（下拉、筛选取值全集）走枚举字典端点并按请求 locale 缓存，用较长 staleTime 复用，不每次挂载重拉。
- 依赖身份或租户的数据在 query key 中包含主体 / 租户作用域；登出、账号或租户切换时先取消旧请求并清理对应 Query 缓存与敏感客户端状态，再加载新作用域。请求须消费取消信号，晚到的旧结果不能写入新作用域；测试切换后不展示上一主体的数据。

## 状态管理

- 服务端数据进 Query，不复制进全局 store；客户端 UI 状态（主题、侧栏折叠、当前租户）默认组件局部或 Context，跨页面共享且更新频繁的才进 zustand，一处创建、明确作用域。
- zustand store 按域拆分不建巨型单 store；store 内不缓存可从 Query 派生的服务端数据，避免双份真源。
- 表单状态归表单库（react-hook-form），不进全局 store；URL 可表达的状态不进任何 store。

## 表单与校验

- 表单用 react-hook-form + zod：schema 单一真源，`z.infer` 派生类型与提交载荷类型同源；提交前校验错误标在字段旁，服务端校验失败回填到对应字段。
- 高危操作（删除、批量变更）用确认对话（`AlertDialog`），对话文案写明对象与后果；确认后执行 mutation，失败不关对话并展示可操作错误。

## UI 体系（shadcn/ui + Tailwind）

- 组件经 shadcn CLI 增改（`npx shadcn@latest add <component>`），源码进项目 `components/ui/` 按项目定制，不引第三方二次封装包替代 CLI 通道。
- 主题走 CSS 变量令牌（`--primary`、`--destructive` 等语义色），深浅色模式经令牌切换（`dark` class），不硬编码色值绕开令牌；新增语义色先补令牌再用。
- 布局壳（侧栏、顶栏、命令面板）沿用脚手架结构，页面在壳内组装；全站命令面板（cmdk）提供快捷入口时把高频页面注册进去，不另造全局搜索。
- 图标统一 lucide-react，表格用 TanStack Table + 项目 `components/data-table` 封装（列定义类型化、排序筛选走列 API），不每页手写 `<table>`。
- 通知反馈统一 sonner（toast），加载进度用顶部进度条组件；同一动作不叠加多种反馈形态。

## shadcn-admin 衍生基线

- 衍生项目升级模板上游是独立决策：先盘点本地对脚手架的改动面（`components/ui/` 定制、布局、认证适配），评估合并成本再动，不静默跟进上游 major。
- 脚手架的演示数据（`@faker-js/faker` 假数据、示例 features）在真实业务接入时移除，不残留在生产构建；示例路由按需删除并清理路由树注册。
- 认证：模板默认 Clerk（SaaS 认证服务）；对接自建后端认证（JWT/session）时替换认证层实现（登录、令牌存储、守卫、登出），保留路由守卫结构，不双栈并存；后端认证与会话基线见 mv-backend-standards「认证与会话」。令牌存储与刷新按项目安全基线，不把长效凭据放 localStorage 除非项目显式决定并记录。
- API 对接对齐团队后端包络（`code`/`message`/data 三段）：错误码走前端文案资源映射，与 mv-backend-standards 的错误码/i18n 体系对齐，不沿用模板 mock 层的错误语义。
- 权限视图：按团队 RBAC 权限标识控制入口展示（见 mv-backend-standards 权限条款），脚手架自带的角色演示页不等于权限方案，对接时以后端权限点为准。

## 环境变量

- `VITE_*` 前缀变量会被打进产物，只放无环境差异的公开常量；分环境 API 地址与开关走运行时注入或相对路径，不靠多套构建产物区分环境（与交付侧「同一产物跨环境」约束一致）。
- 服务端专用变量不加 `VITE_` 前缀；Vite 项目无服务端运行时，凡不该公开的凭据不进前端工程，误引前缀等于泄露。
- 开发期跨域经 Vite dev proxy（`server.proxy`）转发到后端，不为开发环境在后端放开 CORS；生产走同域或网关路由，CORS 白名单条款见 mv-backend-standards。

## 测试

- 测试栈沿用脚手架（Vitest + 浏览器模式）或项目既有约定，不为统一而更换框架；路由与 Query 相关测试用内存路由与假服务层，不发真实请求。
- 关键交互（表单提交、权限守卫、错误态渲染）有对应测试；快照测试不替代行为断言；测试分层与覆盖口径按 mv-test-standards 执行。

本文只覆盖 Vite SPA 与 shadcn-admin 工程条款；渲染模式对应的镜像构建与部署契约归 mv-image-builder 与 mv-container-deploy，技术栈选型归 mv-tech-stack-baseline。
