# Spring Boot 框架条款

项目实际使用 Spring Boot 时并读本文件；通用条款见 [java-guide.md](java-guide.md)。与项目已确立基线冲突时以项目为准。

## 事务

- `@Transactional` 置于 Service 真实业务边界，明确事务的传播、隔离与 checked exception 回滚语义；`rollbackFor = Exception.class` 在业务需要时指定，不模板式声明。
- 理解 Spring 代理与自调用问题：同类内部调用不经代理，事务等注解不生效；不在长事务中执行远程 HTTP 请求或慢操作。

## Web 与校验

- 信任边界：浏览器、App、脚本、内部调用方、回调、消息和导入文件的输入均不可信；前端限制只用于交互体验，不能替代后端校验、认证或授权。各入口在解析与使用前独立检查来源、结构和约束；可信签名或认证只证明来源，不证明数据合法或已获业务授权。
- HTTP 入口按接口契约约束必填、类型、长度、范围、集合数量及允许值；请求体 DTO 用 Bean Validation，Controller 的 `@RequestBody` 参数加 `@Valid`，嵌套对象及容器元素按需加 `@Valid`，并分别声明非空和数量上限。路径、查询、表单与文件等入口也须生效；方法参数校验按项目 Spring 版本配置并用实际请求验证。请求体及上传大小在网关或服务器配置上限，具体值按项目契约确定。
- Service 层在真实事务边界检查跨字段关系、业务状态、资源归属及操作权限；从已认证安全上下文取得主体和租户，以服务端记录或可信配置确定价格、权限、状态等敏感事实，不以客户端提交值作最终依据。涉及并发的余额、库存、唯一性等不变量用数据库约束、条件更新或锁保证，不能只依赖先查后写。
- 校验失败按项目契约返回可定位字段及稳定错误码，不进入业务写入、不泄露堆栈或敏感输入；记录必要的拒绝信息，避免输出 Token 和完整请求体。第三方响应、MQ 消息与回调按各自协议验证来源及结构，并在执行副作用前检查业务约束；文件内容校验不能只依赖扩展名或客户端声明的 MIME。

示例（数值仅演示；已引入 Jakarta Bean Validation 实现，并按项目约定配置统一错误处理）：

```java
public record CreateOrderRequest(
    @NotNull @Positive Long productId,
    @NotNull @Min(1) @Max(100) Integer quantity,
    @NotEmpty @Size(max = 20) List<@NotNull @Valid OrderLine> lines
) {}

public record OrderLine(@NotBlank @Size(max = 64) String sku) {}

@PostMapping("/orders")
public OrderView create(@Valid @RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
```

示例中的 `quantity` 与 `lines` 上限须替换为实际业务契约；Service 仍须确认商品可售、库存、服务端价格和主体是否有权操作。DTO 注解不会自动保护 MQ 消费、内部方法调用等其他入口，须在对应入口显式触发等价校验。
- 用户可见文案统一维护在 `messages*.properties`，经 MessageSource 或 ErrorCode 关联的 messageKey 获取；国际化细则见下方「国际化」。
- 路由用绑定具体 HTTP 方法的注解（`@GetMapping`、`@PostMapping` 等），不用未指定方法的 `@RequestMapping`。
- 响应按统一包络返回（基线 `code`/`message`/`data`，项目既有包络优先）：成功路径 Controller 直接返回 VO，业务错误经全局异常处理器统一映射，不在每个 Controller 手工组装包络。

## 认证配置

- Spring Security 过滤器链按端分段（`/admin/**` 与 `/uc/**` 独立配置或独立 `SecurityFilterChain`）；JWT 基线下会话策略 STATELESS，CSRF 按 API 形态显式决策并记录理由。
- 令牌校验在过滤器层完成，业务代码从安全上下文取当前主体；认证异常统一映射为约定错误码，不向客户端泄漏堆栈。认证与会话的领域条款（双令牌、双端隔离、凭据传输）见 java-guide「认证与会话」。
- 密码编码器用 BCrypt（团队基线）；CORS 显式白名单来源，不放开 `*` 与凭据并用的组合；开发期跨域经前端 dev proxy 承担，不为此放宽生产 CORS。
- refresh token 经 HttpOnly Secure Cookie 或专用刷新端点传输，刷新做轮换与重放检测。

## 外部 HTTP 调用

- Spring 应用统一用 RestClient（团队基线），复用项目 Jackson 转换器与既有拦截器；RestTemplate 已是维护模式，不用于新代码；WebClient 仅响应式栈。
- 外部 HTTP 调用优先声明式（Spring HTTP Interface）：接口方法标 `@HttpExchange` 系注解（`@GetExchange`、`@PostExchange` 等），`HttpServiceProxyFactory` 配 `RestClientAdapter` 生成实现，引擎仍是 RestClient；不引 OpenFeign、Retrofit。
- 仅当必须编程实现时用编程式 RestClient：动态 URL、运行时才能确定请求形态的调用（如通用网关转发）等固定接口签名覆盖不了的场景。
- 对接第三方平台按平台一接口；签名、公共头、错误码归一等公共逻辑放 RestClient 拦截器（`ClientHttpRequestInterceptor`）或 `ExchangeFilterFunction`，不写进业务方法。
- 非 Spring 场景用 JDK 原生 HttpClient（`java.net.http.HttpClient`）。

## 国际化

- 国际化是系统基本要求，不是可选项：任意系统最低支持双语——`zh-CN`（默认）与 `en-US`，从第一个对外接口起落地，不接受「先中文、后补英文」。
- 请求语言解析：按 `Accept-Language`（或项目既定的 locale 载体）解析目标 locale，用户手动切换语言时以项目定义的覆盖载体（自定义 header 或参数）优先，解析失败回落 `zh-CN`；locale 一经解析，本次请求的全部用户可见输出（响应文案、错误 reason、导出与通知内容）使用同一语言，不混排。
- 生成方判据：谁生成语义，谁负责翻译。前端界面文案由前端国际化；系统生成并在响应或载荷中输出的描述性文案（原因、备注、审批意见模板、通知、导出内容）由后端在生成时刻按目标 locale 输出译文，不以 messageKey 交前端二次翻译——这些文案会被持久化、异步消费或送出系统边界，生成时不翻译就没有可靠的翻译时机。
- 持久化形态：可能入库的系统生成文案（原因、备注、审计描述）落库存语义结构而非译文——`messageKey` + args；args 只装数据值（名称、单号、数量）与枚举型子原因（子原因同样 key 化），用户自由输入的原文属于数据，原样直存，不作为 i18n 对象。
- 渲染时机：库内存 key，出库必渲染——接口默认按请求 locale 渲染为译文返回（前端原样展示），导出、邮件、第三方推送在后端渲染成目标语言；项目声明需要客户端即时切换语言时，接口改返 `{key, args}` 由前端渲染。
- key 生命周期：key 只增不改语义，废弃 key 的译文长期保留，保证历史数据始终可渲染；仅审计强需求场景（要求留存「当时呈现的原话」）额外增加生成时快照字段并标注其 locale。
- 错误响应双层：`code` 是契约，前端可映射通用文案；系统判定的 `reason` 等描述由后端按 locale 给译文，前端原样展示。
- 载体：语言资源一律 `messages_zh_CN.properties` / `messages_en_US.properties`，与代码同源同审同回滚，不用数据库表存语言资源——表内改文案绕过审查与回滚、缺 key 无法静态发现。文案变更主语是运营的活动类内容属于内容数据，走内容管理方案，不冒充语言资源。
- 枚举与数据字典：枚举展示名是语言资源，走 key 化 properties（如 `status.order.pending`）随代码维护；数据字典表中运营维护的业务配置值属于数据，名称列需要多语言时用多语言列或关联语言资源，按内容管理处理，与「语言资源不进库」不冲突。
- 格式化与时区：日期、数字、货币按目标 locale 格式化（`DateTimeFormatter`/`NumberFormat` with locale），不硬编码格式模板；时间戳存储一律 UTC 或带时区，展示按目标受众 locale 与项目声明的展示时区换算，不存本地化字符串。复数等语法形态用 `MessageFormat`/ICU 机制表达，不靠拼接句子实现单复数。
- 完整性：新增 messageKey 必须双语文件同批补齐；错误码枚举关联的 messageKey 双语齐备纳入项目检查；前端文案硬编码可用 lint 规则（如 eslint-plugin-i18n 类）机器拦截，作为规范补充。

## 配置绑定与多环境

- 配置文件优先 YAML（`application.yml`、`application-{profile}.yml`）；每个新增配置项必须先在配置文件定义，不在代码里散落。
- 业务自定义配置用 `@ConfigurationProperties` 类型化绑定并按领域拆分，不合并为单一巨量配置类；key 用 kebab-case（如 `app.jwt.expire-minutes`）。
- 环境变量覆盖默认经宽松绑定生效，名称转换规则为点换下划线、去连字符、转大写（`app.jwt.secret` → `APP_JWT_SECRET`）；不含连字符的 key 无需单独定义环境变量。
- 含连字符的 key 在该转换中丢失词界（`expire-minutes` → `EXPIREMINUTES`），环境变量名与 key 分段不再对应：此类配置项在配置文件中用属性占位符显式声明环境变量与默认值（`expire-minutes: ${APP_JWT_EXPIRE_MINUTES:30}`）。属性占位符是独立于宽松绑定的核心 Spring 机制，默认值随占位符定义在配置文件，不进代码。
- 禁止 `@Value` 注入配置；代码（字段初始化、构造器默认参）不定义配置默认值。

## JPA 数据访问

JPA 为团队持久层基线，新项目与新模块默认采用；通用数据访问条款见 java-guide「数据库与事务」。

- 枚举持久化用 `@Enumerated(EnumType.STRING)` 保证存储值可读；同一项目不混用映射方案；映射变更涉及历史数据与兼容性，作为独立迁移评估。
- 查询按需取字段：列表与报表场景用投影（DTO projection）替代实体全字段查询，即 `SELECT *` 的同等约束。
- 关联加载显式化：需要关联数据时用 fetch join 或 `@EntityGraph` 明确获取路径，默认保持懒加载，避免在事务外触发懒加载异常；此为默认行为，可按项目既有取数风格覆盖。

## 健康探测

- 可运行服务暴露 readiness 与 liveness 双探针端点：`application.yml` 显式设置 `management.endpoint.health.probes.enabled: true`（部署到 k8s 时自动启用，Compose 等环境必须显式开启），端点为 `/actuator/health/readiness` 与 `/actuator/health/liveness`；`management.endpoints.web.exposure.include` 最小化放开（health 必开，其余按需）。
- 两个端点检查内容分离：liveness 只反映进程内状态（死锁、关键线程停摆），不聚合任何外部依赖——基础设施抖动若进入 liveness 会放大成容器重启风暴；readiness 反映可接流状态，聚合关键依赖（连接池等）检查，失败时摘除流量、恢复后自动回归，不重启进程。
- 自定义 `HealthIndicator` 只做组件可用性判定，不在健康检查里跑慢查询或重逻辑；镜像 HEALTHCHECK 用 `start_period` 覆盖启动期，防止启动中被判死。
- readiness 端点同时是交付门禁探活地址：容器部署 `FF_HEALTH_URL` 指向它，语义与编排映射见 `mv-container-deploy` 交付契约「双探针」。

## LLM 集成

- LLM 集成统一使用 Spring AI（团队基线）：对话补全、流式输出、结构化输出（`.entity()` 类型化映射）、Function/Tool Calling、RAG（Embedding、VectorStore、Advisor）等一切模型调用都从 `ChatClient` 起步，不自研 HTTP 客户端直连模型 API，不重复实现其已有的鉴权包络、重试与流式解析。
- 不引入 Spring AI Alibaba（团队基线）；多步编排优先用 Spring AI 自身能力（`ChatClient` 链、Advisor 链、工具调用组合）实现，编排逻辑随业务代码维护，不引入平行编排栈。
- 模型接线统一用 OpenAI 兼容 starter（`spring-ai-starter-model-openai`）指向网关或各家 OpenAI 兼容端点，不引入 provider 专属 starter 或 SDK（如 ollama、dashscope）；换模型只改配置（base-url、model、api-key），不改代码。
- 连接信息（baseUrl、apiKey 等）按「配置绑定与多环境」经配置文件注入，不硬编码；模型与参数随配置切换，不写死在代码。
- 模型响应按外部系统对待：结构校验不过按业务失败处理并记日志，不静默降级。

## 框架扩展点与运行时集成

- 修改拦截器、结果转换、重试器或自动配置时，检查当前依赖版本的实际执行链。确认结果转换影响的是最终类型绑定，而不只是响应对象的某个访问器。
- 用最小运行时集成覆盖真实客户端、序列化、Spring 注册与配置绑定；保留正常响应、业务失败包络、连接失败和重试耗尽场景。不要 mock 掉待验证的框架扩展点。
- 重试必须有明确上限、计数递增和终止路径；只有可安全重放的操作才重试。检查成功响应是否会误入重试，以及框架是否会重新执行请求前置钩子。
- token 失效重试时，确认刷新后的凭据已写入实际重放请求；仅驱逐缓存不保证旧请求头被替换。多实例共享 token 时，结合服务端失效语义设计刷新锁、缓存与并发测试。
- 配置含路径模式或特殊字符 Map 键时，通过真实 Spring 绑定检查最终键值；新增接口包后检查扫描注册、Bean 注入以及拦截器的作用范围。
- 保持模块依赖无环，必要时通过端口隔离技术实现与核心逻辑；装配根负责接线，不将业务决策藏入技术拦截器。
