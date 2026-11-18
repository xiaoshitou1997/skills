---
name: mv-coding-standards
description: 编写、修改、重构或审查业务代码与软件测试时使用，覆盖后端、前端、测试三个子领域。后端：写或审 Java 代码，团队基线 Spring Boot + JDK 21（Spring Framework 7、JPA、PostgreSQL），覆盖分层、API、DTO/VO、错误码与国际化、枚举、异常、日志、事务、数据访问、认证与权限（RBAC）、集合并发。前端：写或审 React/TypeScript 代码，含 Vite SPA、shadcn-admin 后台管理类项目、Next.js、Taro H5/小程序端，覆盖组件分层、TypeScript 类型契约、数据获取与服务层、状态管理、路由、错误与国际化文案、构建环境变量、前端安全、页面交互体验基线、可访问性与性能预算。测试：规划、编写、审查或补齐软件测试，覆盖单测/集成/E2E 测试分层与各层范围、覆盖率口径、必测场景、性能与负载测试，及 JUnit/Testcontainers、Vitest/Testing Library、Playwright、Taro 端写法。需求、架构、系统设计与设计文档归 mv-design-standards；镜像构建与部署归 mv-delivery-standards。
---

# 编码规范：后端 Java、前端 React 与测试

这是**规范型 Skill**，面向 mv 团队全部项目的编码实现与测试资产，在 Agent 编码、审查、测试期间引用；后端 Java、前端 React 与测试三个子领域的条款合并在本文件，细则按文末参考清单下沉 references。不负责编排 Spec/Plan/Tasks，不直接启动、Commit 或部署，不负责构建出包与镜像，不负责搭建 CI 流水线，不写部署验证。

优先级：用户明确需求和项目已正式采纳的规范 / ADR → 本规范 → 框架默认约定。团队 Java 后端基线为 Spring Boot（见 mv-design-standards）：后端通用条款为 Java 通用工程条款，Spring Boot 与 JPA 专属条款按基线栈应用；前端通用条款对任意前端框架适用，React/Vite、shadcn-admin、Next.js 与 Taro 专属条款仅在使用对应技术栈时应用，不向其他框架强加不兼容约束；项目偏离基线时项目规范优先并记录理由。本规范只管编码实现层条款：系统边界、集成与一致性决策归 mv-design-standards；安全政策、数据分级与威胁建模归 mv-security-standards。

## 开始前确认

- 后端：确认本次业务范围、需求来源、版本及优先级，不默认原型、旧文档或现有代码永远权威。代码用于说明当前实现；与已确认需求不一致时记录差距，不反向改写需求。涉及表或接口设计先核对当前 DDL、迁移与契约基线，保留必要语义增量，避免并行修改覆盖彼此决策。业务规则、验收口径与业务术语按 mv-design-standards 读取或补齐，类与方法命名复用已确认业务术语，不另造同义词；规模、网络、部署等约束只在影响本次实现决策且尚未确认时补充确认，不阻塞无关的独立工作。本地开发或验证需要 dev 公共 infra 时，调用 mv-design-standards 并按其仓库布局参考的本机公共 infra 配置产物流程读取和维护固定配置，只询问本次缺项，不要求在对话中提供密钥。
- 前端：确认本次页面/组件范围、需求或设计稿来源、目标技术栈与脚手架（shadcn-admin 衍生项目、Vite SPA、Taro H5/小程序项目、Next.js 或其他），不默认原型、旧文档或现有代码永远权威。代码用于说明当前实现；与已确认设计不一致时记录差距，不反向改写设计。涉及前后端联调时，先按 [references/frontend-guide.md](references/frontend-guide.md) 读取或预填本 skill 的非敏感联调信息入口，核对接口契约、环境地址与认证来源；按目标端并读 Vite 或 Taro 条款。缺项向用户补问并写回已确认信息，冲突或无法确认时记录阻塞项。
- 测试：业务规则与验收标准取自 mv-design-standards 的当前项目确认结果，不由测试用例反向定义需求。确认变更范围与类型（新增功能、修缺陷、重构）、项目已有测试资产与既有覆盖口径、涉及端（后端、admin、user、H5/小程序）。修缺陷场景先确认可复现路径。

## SKILL_ROOT 与质量检查脚本

`SKILL_ROOT` 指向本 skill 目录，Agent 不保证自动提供，使用前显式赋值（如 `SKILL_ROOT="<本 skill 目录绝对路径>"`），从加载的 SKILL.md 定位；展开后的路径恒加引号；工作目录保持为用户项目，不切换到 skill 目录。项目级质量检查脚本用法：交付前执行 `"${SKILL_ROOT}/scripts/quality-check.sh" quick`，深入验证用 `full`。该脚本按项目类型执行项目级检查（package.json 走探测到的包管理器与既有脚本，pom.xml、build.gradle 走对应构建命令）；项目已有等价检查时优先项目检查并说明；需要模块或测试范围验证时直接使用项目已有命令，并报告验证范围与既有失败，不因脚本缺少范围参数扩大整改。静态规范和自动检查不能互相替代。

## 后端 Java（Spring Boot 基线）

### 分层与命名

1. `Controller` 处理路由、校验、协议映射，不编写核心业务逻辑，不直接操作数据访问层。
2. `Service` 处理业务/事务；`Mapper`/`Repository` 处理数据库持久化。
3. 分层以项目实际边界为准，不形式化地给所有简单逻辑强加接口与实现类。
4. 命名语义明确：类与方法 camelCase/PascalCase，数据库字段 snake_case。
5. 命名按英文习惯表达语义，不做中文直译：布尔判断用 `isNormal` 一类 is/has/can 命名，不写 `judgeIfNormal`。

### API 契约与错误

6. DTO/VO/API Contract 不直接泄露持久层 Entity。
7. 按项目既有 API 响应契约返回数据，不擅自把所有接口改为新的 `ApiResponse`。
8. 项目无既有响应契约时按基线统一包络（`code`/`message`/`data`，见 mv-design-standards），不临时发明新包络。
9. 每个独立业务失败场景对应唯一错误码枚举，不复用既有错误码扩展语义。
10. 结构化业务数据用强类型 POJO 承载，不用 Map/JsonNode 替代。
11. 项目已有错误码/文案体系优先。

### 输入校验、异常与外部数据

12. 所有外部输入均不可信：即使前端已限制，后端仍须独立校验并授权；HTTP 入口使用 Bean Validation 与业务校验，失败返回明确错误码且不暴露内部异常，具体做法见 spring-guide「Web 与校验」。
13. 捕获异常必须有实际处理意图，不吞异常，不用 `printStackTrace()`。
14. 异步任务、批处理和后台作业必须正确传播或记录失败状态，不把「请求已接受」或「没有异常抛出」当成执行成功。
15. 外部接口响应、MQ 消息、第三方回调与导入数据先校验结构、取值与来源再使用。
16. 校验不过按业务失败处理并记日志，不静默降级。
17. 外部返回的成功标志不替代本方执行结果的确认。
18. 外部传入的标识与取值不直接用作授权、资金等敏感决策依据。

### 日志

19. 日志采用 SLF4J 参数化占位符，不使用 System.out。
20. 不重复记录同一 stacktrace，不泄露 Token/密码/PII 或全量请求体。

### 数据访问与事务

21. 禁止无界全表列表，列表查询必须有分页或数量上限。
22. 消除循环单行查询（N+1），改用批量取数或关联查询。
23. SQL 使用参数绑定，不拼接 SQL 字符串。
24. 查询字段按需选取，不在生产代码里使用 `SELECT *` 作为默认查询模式。
25. 新增或修改查询时核对索引、事务、幂等与并发安全。
26. 事务置于真实业务边界，理解所用框架的事务代理与自调用行为。
27. 事务内不做网络 IO 或长时间等待。
28. `rollbackFor = Exception.class` 在业务需要时指定，不假设每个事务都必须模板式声明。
29. 枚举持久化用 `@Enumerated(EnumType.STRING)` 保证存储值可读；同一项目不混用映射方案；映射变更涉及历史数据与兼容性，作为独立迁移评估。
30. 查询按需取字段：列表与报表场景用投影（DTO projection）替代实体全字段查询，即 `SELECT *` 的同等约束。
31. 关联加载显式化：需要关联数据时用 fetch join 或 `@EntityGraph` 明确获取路径，默认保持懒加载，避免在事务外触发懒加载异常；此为默认行为，可按项目既有取数风格覆盖。

### 认证与权限（RBAC）

32. 角色与权限采用 RBAC 模型。
33. 功能权限点在入口层统一校验（声明式注解或集中拦截器）；资源归属、数据范围和状态相关授权在 Service 业务边界校验，不以入口权限替代对象级授权。
34. 权限点按业务操作定义且前后端共用同一权限标识：前端列表页面与后端列表接口是同一个权限，前端删除按钮与后端删除接口是同一个权限，不拆开设计。
35. 权限点与菜单等结构定义是版本化种子数据，不设运行时管理入口，运行时只管理角色及其授予关系。

### 枚举与国际化

36. 状态、类型、角色等枚举型字段用 Java 枚举全链路承载（存储、入参、返回值、判断），不以 String 中转。
37. 枚举落库映射按项目持久层框架确立，同一项目不混用。
38. 用户可见文案走国际化资源，不在业务代码硬编码。
39. 国际化最低支持双语 `zh-CN`（默认）与 `en-US`，从首个接口起落地，不接受「先中文后补英文」。
40. 系统生成的描述性文案（原因、备注、通知、导出内容）由后端在生成时按目标 locale 输出译文，不以 messageKey 交前端二次翻译，载体与判据见 spring-guide「国际化」。

### 配置

41. 配置与 Secret 分离：敏感信息经运行时环境变量或 Secret Store 注入，不硬编码密钥。
42. `.env.prod` 等生产配置不提交 Git。
43. 配置支持按 profile 环境差异化。
44. 每个新增配置项必须先在配置文件定义（格式优先 YAML，如 `application.yml`），不在代码中定义默认值。
45. 环境变量覆盖默认走宽松绑定：点换下划线、去连字符、转大写（`app.jwt.secret` → `APP_JWT_SECRET`）。
46. 含连字符的 key 转换后丢失词界（`expire-minutes` → `EXPIREMINUTES`），此类配置项须在配置文件用属性占位符显式声明环境变量与默认值（`expire-minutes: ${APP_JWT_EXPIRE_MINUTES:30}`）。
47. 注入用 `@ConfigurationProperties` 类型化绑定，禁止 `@Value` 注入。

### 集合与并发

48. 线程池用 `ThreadPoolExecutor` 显式建池。
49. `ThreadLocal` 用后 remove。
50. foreach 中不增删元素。
51. 遍历 Map 用 entrySet。
52. 返回集合不返回 null。
53. 判空统一走标准工具类。

### 集成组件边界

54. 集成组件封装鉴权、协议包络、超时等技术机制，业务侧保留业务接口与决策。
55. 优先使用现有客户端的声明能力，不为复用另造通用路径调用门面或代理栈。
56. 只实现组件的任务，不自动扩展成服务接线与业务编排。

### 变更纪律与测试衔接

57. 改动现有系统时保持最小必要变更，优先遵从项目已有模块、依赖版本与兼容性约束。
58. 不引入未使用的 import，新产生的多余 import、代码块与类一律删除。
59. 涉及契约、数据库、升级或不兼容 API 时更新对应文档和迁移建议。
60. 业务逻辑与行为改动必须写单元测试，涉及金额计算、授权、状态机或并发的逻辑另加集成测试；测试分层与覆盖率口径按「测试」分节执行。
61. 测试覆盖正常路径、边界条件、异常和并发/事务场景；测试代码写法与替身规则见 [references/backend-testing.md](references/backend-testing.md)。
62. 使用项目现有 JUnit/Mockito/Testcontainers 等工具，不为规范而更换框架。

后端参考：框架中立主体见 [references/java-guide.md](references/java-guide.md)；使用 Spring Boot 时并读 [references/spring-guide.md](references/spring-guide.md)（含 JPA 数据访问条款）；schema 迁移与大表 DDL 执行策略见 [references/schema-migrations.md](references/schema-migrations.md)。编写或审查设计、接口文档时读取 java-guide 中的文档条款。这些文件仅为工程规则，不是独立 Reviewer/Quality Gate Skill。安全政策与安全评审清单见 mv-security-standards，系统架构与集成决策见 mv-design-standards。规范中的举例和阈值（如覆盖率门槛、主键策略）不应覆盖项目实际库版本、性能特征或已确立基线。

## 前端 React（Vite SPA / shadcn-admin / Next.js / Taro）

1. 组件分层：页面（路由层）只做组装与数据编排；可复用 UI 组件无业务副作用；业务逻辑进 hooks/services，不在组件体内堆叠。一个文件一个组件，命名与职责一致。
2. 类型契约：组件 props、API 响应、全局状态一律显式 TypeScript 类型；API 响应类型与后端契约字段一一对应，不随手 `any`；不把后端 VO 原样透传到展示层，按页面需要挑选与映射；枚举型字段按消费建模，前端区分取值（按值分支、逐值样式）时才定义与后端契约一致的字面量联合类型，纯展示与回传场景用 `string`。
3. 数据获取：请求统一走封装的服务层（统一 base URL、错误包络、超时与取消），不在组件里散落裸 `fetch`/`axios` 调用；加载、错误、空三态显式建模；列表与表单处理竞态（去重、取消上次请求），不做「看起来能跑」的时序假设。
4. 路由与状态：可安全公开的路由状态（页码、非敏感筛选、抽屉弹窗回退）进 URL，刷新与分享不丢；敏感条件及不适合分享的选中状态放受控会话或组件状态；服务端数据由请求层缓存管理，客户端 UI 状态能靠 props、URL 或组件局部解决的不引入全局 store；引入状态库须说明理由并只在一处定义。
5. 表单与校验：表单用受控校验库承载（react-hook-form + zod 等按项目脚手架），schema 与类型契约同源，字段规则（必填、长度、格式、取值域）与后端契约对齐，不一致以后端契约为准并反馈修正；前置校验错误标在字段旁，高危操作确认并设计恢复或审计，细则见交互基线。前端校验只改善交互，不替代后端对所有外部输入的独立校验和授权。
6. 错误与文案：国际化是系统基本要求——文案资源最低双语 `zh-CN`（默认）与 `en-US`，项目初始化即引入双语骨架，不在组件里硬编码任何语言的句子；前端只翻译自己生成的界面文案，响应中系统生成的描述性文案与枚举展示名由后端按 locale 给出译文、前端默认原样展示；项目显式采用 `{key, args}` 即时切换语言契约时按约定渲染（生成方判据与 key 生命周期以本 skill spring-guide「国际化」为唯一全文源）；枚举取值全集（筛选、下拉）走枚举字典端点取得，不维护「取值 → 展示名」映射表；`code` 走前端文案资源映射通用描述；错误边界兜底，不白屏、不吞错。
7. 构建与环境变量：区分编译期固化与运行时注入——`VITE_*`、`TARO_APP_*` 等前端前缀变量会被打进产物，不放环境差异配置、密钥或分环境 API 地址；跨环境配置走运行时注入或相对路径（与 mv-delivery-standards 的构建期固化条款同源）。
8. 安全基线：不将未消毒内容注入 `dangerouslySetInnerHTML` 等等价通道；不把密钥、内网地址、调试开关打进前端包；新依赖先过 mv-design-standards 的依赖引入评估再进。跨栈安全政策、数据分级与安全评审见 mv-security-standards，本节只保留前端实现边界。
9. 样式与设计系统：样式方案同一项目不混用多套；shadcn/ui 项目经 CLI 增改组件、走 CSS 变量主题令牌（语义色、间距），不硬编码色值绕开令牌；间距、色彩走项目设计令牌，不散落魔法数值；视觉还原以设计稿为准，本规范不定义视觉风格。
10. 交互与体验基线：页面布局范式稳定、信息层级清晰；交互元素状态完整、操作即时反馈；空/错/加载异常页面完备；用词全站统一；色彩用于区分状态而非装饰；键盘可达并按项目约定适配多分辨率。页面级条款见 [references/ux-interaction-guide.md](references/ux-interaction-guide.md)。
11. 最小变更与测试：改动现有系统保持最小必要变更，新产生的死代码、未用 import 一律删除；业务逻辑与行为改动写或更新对应测试（组件渲染/工具函数单测），使用项目现有测试框架，不为规范而更换框架；测试分层策略与覆盖口径按「测试」分节执行，组件与交互测试写法见 [references/frontend-testing.md](references/frontend-testing.md)。

前端参考：框架中立主体见 [references/frontend-guide.md](references/frontend-guide.md)；Vite SPA 与 shadcn-admin 衍生项目并读 [references/vite-spa-guide.md](references/vite-spa-guide.md)；Taro H5/小程序项目并读 [references/taro-guide.md](references/taro-guide.md)；使用 Next.js 时并读 [references/nextjs-guide.md](references/nextjs-guide.md)；涉及页面布局、交互流程、表单容错、异常态与可访问性时并读 [references/ux-interaction-guide.md](references/ux-interaction-guide.md)；涉及可访问性验收与性能预算时并读 [references/accessibility-performance.md](references/accessibility-performance.md)。规范中的举例和阈值不应覆盖项目实际框架版本、性能特征或已确立基线。

## 测试

定「哪层测什么、测到什么程度」，并给出各端测试代码写法；产品代码规范与测试的构建期执行通道不归本分节裁决。

### 关键规则

1. 分层默认口径：**单测覆盖纯逻辑（工具、计算、状态转换、边界条件），集成测试覆盖持久化与事务（真实隔离数据库），业务 E2E 按业务风险覆盖完整用户旅程**；受控测试服务器或 CI 可用 Testcontainers，宿主不运行 Docker，替代环境与隔离要求见后端测试参考；不用全量 E2E 追求覆盖率。
2. 后端每个新增或修改的 Service 公有方法至少有一条失败路径用例；Controller 层不重复测 Service 已覆盖逻辑，经 Web 层切片测试只测参数校验、错误码映射与鉴权。
3. 前端组件测试断言行为不断言渲染快照：加载、错误、空三态、表单校验分支、权限分支有交互断言；纯展示组件不强制建测试文件。
4. 业务 E2E 按业务风险选择完整用户旅程并验收到业务结果；带认证的 CRUD 项目默认覆盖登录、核心列表、一条核心写操作、登出，公开站点、API 服务与批处理按实际入口裁剪。按业务适用性与风险覆盖替代和异常流程、失败恢复、状态转换、跨系统一致性、重复与并发操作、金额计算及外部副作用；记录选择和裁剪依据。发布前执行适用场景，PR 与提交阶段按项目管线及变更风险确定。
5. 覆盖率基线：后端核心包行覆盖 ≥70%、分支 ≥50%（项目可上调，下调须项目 ADR 记录）；统计范围排除生成代码与纯 DTO/VO。项目未配置覆盖率门槛时不擅自引入，先与团队确立。
6. 外部依赖替身：纯业务单测可替身 Repository 等直接协作者；验证查询、映射、约束、事务与并发语义时必须用真实隔离数据库，不以 mock 结果代替。HTTP 外部依赖用 WireMock 一类桩；时间用注入时钟，不在测试内 sleep 等待。
7. 测试数据：集成测试经版本化迁移脚本建 schema，用例内自建自清数据，用例间不依赖执行顺序。
8. 缺陷修复先补一条复现该缺陷的失败用例再修复，修复后该用例转绿；不补用例的修复在交付说明说明原因。
9. 测试代码与产品代码同一分层纪律：一个测试类/文件对应一个被测单元，命名 `<被测单元>Test`（Java）或 `<被测单元>.test.tsx`（前端），不建跨单元共享的巨型测试类。
10. 涉及认证上下文的集成测试设置真实主体对象，不用静态 mock 框架替代认证链路。
11. 性能与负载测试按项目风险安排：有明确吞吐/延迟目标、高并发或大促场景时，先定负载模型与阈值，再选工具与场景；压测结论写明环境、数据量、并发与瓶颈，不以一次压测代替容量规划。
12. API 测试直接调用 HTTP/API，按接口适用性验证请求参数、响应契约、状态码、业务规则、认证授权、边界、错误处理和数据影响；可使用受控依赖，不能将其结果当作真实业务 E2E。
13. 真实业务 E2E 必须连接测试环境中的实际后端服务，验证业务结果及适用的跨系统状态与副作用；全 Mock 不算真实 E2E。测试环境或依赖缺失时继续不依赖该环境的工作，记录真实联调和 E2E 未执行、阻塞原因及待补验证，不以替身结果冒充。

### 用例设计与执行

1. 读取本次需求、验收标准、设计及受影响代码和现有测试；按需求或缺陷编号列出要验证的行为，资料冲突或预期结果未确认时标记待确认，不按当前代码猜测业务结果。
2. 每个场景写明前置条件与数据、执行动作、可观察预期和测试层次；按适用范围覆盖正常、边界、失败，以及权限、重复与并发等分支。已有用例已覆盖时引用并运行，不重复创建等价用例。
3. 根据被验证的行为选择单测、组件、API、集成测试或业务 E2E；需验证真实依赖语义时先确认隔离目标及权限，测试资源缺失则记录该层未执行，继续运行不依赖该资源的用例。
4. 默认依次执行适用的单测/组件、API、集成和业务 E2E；不适用的层记录裁剪依据。执行后逐层记录命令、目标环境、通过与失败结果；失败保留复现步骤和证据，区分产品缺陷、环境阻塞和尚未定位的问题。未运行的场景记录原因，不把测试计划当作执行结果。

测试参考：后端测试写法见 [references/backend-testing.md](references/backend-testing.md)；前端测试写法见 [references/frontend-testing.md](references/frontend-testing.md)；性能与负载测试见 [references/performance-testing.md](references/performance-testing.md)。

## 硬约束

- **所有外部输入均不可信：即使前端已限制，后端仍须独立校验并授权；前端校验只改善交互，不替代后端校验。**
- **捕获异常必须有实际处理意图，不吞异常，不用 `printStackTrace()`。**
- **禁止无界全表列表，列表查询必须有分页或数量上限；SQL 使用参数绑定，不拼接 SQL 字符串。**
- **敏感信息经运行时环境变量或 Secret Store 注入，不硬编码密钥；`.env.prod` 等生产配置不提交 Git。**
- **外部接口响应、MQ 消息、第三方回调与导入数据先校验结构、取值与来源再使用；校验不过按业务失败处理并记日志，不静默降级。**
- **外部返回的成功标志不替代本方执行结果的确认；外部传入的标识与取值不直接用作授权、资金等敏感决策依据。**
- **DTO/VO/API Contract 不直接泄露持久层 Entity。**
- **不将未消毒内容注入 `dangerouslySetInnerHTML` 等等价通道；不把密钥、内网地址、调试开关打进前端包。**
- **`VITE_*`、`TARO_APP_*`、`NEXT_PUBLIC_*` 等前端前缀变量会被打进产物，不放环境差异配置、密钥或分环境 API 地址。**
- **验证查询、映射、约束、事务与并发语义时必须用真实隔离数据库，不以 mock 结果代替。**
- **真实业务 E2E 必须连接测试环境中的实际后端服务，全 Mock 不算真实 E2E；不以替身结果冒充执行结果。**
- **未实际运行的检查与测试明确写「未执行」，不虚构通过。**

## 输出

- 后端交付前按 java-guide「交付自查清单」逐项核对本次变更直接影响范围；未修改代码不追溯达标，兼容性未应用条款与历史问题分别如实报告。
- 交付前对本次变更范围执行 [references/readability-refactoring.md](references/readability-refactoring.md) 的可读性修剪：结构信号逐条判定，记录修剪点与未修剪原因；修剪保持行为等价并复跑受影响检查。
- 交付说明列出关键规范决策、针对本次变更的遵循/偏离原因、实际应用的框架条款与执行的验证结果；未执行的检查明确写「未执行」，不虚构通过。
- 前端交付结合实际页面逐项标注发现或无法排除的风险点、影响及对应优化方案，区分已完成与待验证，不泛泛输出整本规范。
- 测试证据分别记录编译、单测/组件、API、集成测试和业务 E2E；每项记录执行命令、时间、目标环境、结果或退出码及报告位置，区分通过、失败、跳过与未执行并说明原因。记录提交 SHA、工作区是否有未提交改动，并对验证范围内的文件记录内容指纹或其他足以识别内容的依据；不记录秘密。需求、设计、代码、配置或环境变化后检查证据受影响范围；无法判定影响时执行覆盖变更范围的完整检查，无法确认原证据对应当前内容时重新验证。按项目风险关联需求或变更编号、验收标准、测试或人工验收证据、未关闭缺陷及风险，交由项目责任人作发布判断；健康检查不等于业务验收。执行性能测试时另记负载模型、环境、数据量、阈值与结果。
- 测试交付说明列出新增用例清单、覆盖率数字（配置了门槛时）与豁免偏离项。

## 边界

本规范是项目规范的补充，供支持 Agent Skills 的编码助手编码、自检与审查时引用；静态规范和自动检查不能互相替代。项目已有覆盖口径与本规范冲突时项目优先，偏离记录进交付说明。

- 技术栈选型与版本基线、需求、系统架构与集成决策、工程文档与图件归 mv-design-standards；出包与镜像构建、部署归 mv-delivery-standards；安全政策与安全评审归 mv-security-standards。
- 产品代码分层、DTO、事务写法见「后端 Java」分节；组件与服务层写法见「前端 React」分节。
- 测试的构建期执行通道（CI 步骤、流水线）由项目承担，本规范只定测试内容与底线；安全测试的评审清单与必测项见 mv-security-standards，架构与集成方式对测试范围的影响见 mv-design-standards。

## 参考清单

- [references/java-guide.md](references/java-guide.md) — Java 后端通用工程条款：模块分层与命名、集合并发、API 错误码、RBAC、认证会话、外部调用、数据库事务与交付自查清单
- [references/spring-guide.md](references/spring-guide.md) — Spring Boot 专属条款：事务、Web 校验、认证配置、国际化、配置绑定、JPA 数据访问、健康探测、LLM 集成
- [references/schema-migrations.md](references/schema-migrations.md) — schema 迁移与大表 DDL：执行通道、脚本纪律、在线 DDL 方言写法、expand–contract
- [references/readability-refactoring.md](references/readability-refactoring.md) — 交付前可读性修剪：结构信号判定标准、修剪流程与反目标
- [references/frontend-guide.md](references/frontend-guide.md) — 前端框架中立条款：目录命名、类型契约、服务层、前后端联调信息固定入口、状态管理、安全与性能基线
- [references/vite-spa-guide.md](references/vite-spa-guide.md) — Vite SPA 与 shadcn-admin 衍生项目条款：路由、TanStack Query、表单、UI 体系、环境变量、开发代理
- [references/taro-guide.md](references/taro-guide.md) — Taro H5/小程序条款：渲染目标、请求层、各端联调、平台差异、分包
- [references/nextjs-guide.md](references/nextjs-guide.md) — Next.js 条款：渲染模式、服务端/客户端组件边界、Route Handlers、环境变量
- [references/ux-interaction-guide.md](references/ux-interaction-guide.md) — 交互与体验基线：布局层级、即时反馈、表单容错、用词一致性、异常页面、多分辨率适配
- [references/accessibility-performance.md](references/accessibility-performance.md) — 可访问性基线与性能预算：WCAG 2.1 AA 核心要求、预算指标与验证方式
- [references/backend-testing.md](references/backend-testing.md) — 后端测试写法：JUnit 5、Web 层切片、Testcontainers 集成与覆盖率执行
- [references/frontend-testing.md](references/frontend-testing.md) — 前端测试写法：Vitest、Testing Library、Playwright 冒烟与 Taro 端
- [references/performance-testing.md](references/performance-testing.md) — 性能与负载测试：负载模型、阈值、环境、场景与证据记录
