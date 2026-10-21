# Spring Boot 框架条款

项目实际使用 Spring Boot 时并读本文件；通用条款见 [java-guide.md](java-guide.md)。与项目已确立基线冲突时以项目为准。

## 事务

- `@Transactional` 置于 Service 真实业务边界，明确事务的传播、隔离与 checked exception 回滚语义；`rollbackFor = Exception.class` 在业务需要时指定，不模板式声明。
- 理解 Spring 代理与自调用问题：同类内部调用不经代理，事务等注解不生效；不在长事务中执行远程 HTTP 请求或慢操作。

## Web 与校验

- 输入校验用 Bean Validation（`@Valid`/`@Validated`），业务规则同时在 Service 层确认；避免直接相信 Controller 层入参。
- 用户可见文案统一维护在 `messages*.properties`，经 MessageSource 或 ErrorCode 关联的 messageKey 获取。
- 路由用绑定具体 HTTP 方法的注解（`@GetMapping`、`@PostMapping` 等），不用未指定方法的 `@RequestMapping`。

## 配置绑定与多环境

- 配置文件优先 YAML（`application.yml`、`application-{profile}.yml`）；每个新增配置项必须先在配置文件定义，不在代码里散落。
- 业务自定义配置用 `@ConfigurationProperties` 类型化绑定并按领域拆分，不合并为单一巨量配置类；key 用 kebab-case（如 `app.jwt.expire-minutes`）。
- 环境变量覆盖默认经宽松绑定生效，名称转换规则为点换下划线、去连字符、转大写（`app.jwt.secret` → `APP_JWT_SECRET`）；不含连字符的 key 无需单独定义环境变量。
- 含连字符的 key 在该转换中丢失词界（`expire-minutes` → `EXPIREMINUTES`），环境变量名与 key 分段不再对应：此类配置项在配置文件中用属性占位符显式声明环境变量与默认值（`expire-minutes: ${APP_JWT_EXPIRE_MINUTES:30}`）。属性占位符是独立于宽松绑定的核心 Spring 机制，默认值随占位符定义在配置文件，不进代码。
- 禁止 `@Value` 注入配置；代码（字段初始化、构造器默认参）不定义配置默认值。

## 健康探测

- 可运行服务暴露 readiness 与 liveness 双探针端点：`application.yml` 显式设置 `management.endpoint.health.probes.enabled: true`（部署到 k8s 时自动启用，Compose 等环境必须显式开启），端点为 `/actuator/health/readiness` 与 `/actuator/health/liveness`；`management.endpoints.web.exposure.include` 最小化放开（health 必开，其余按需）。
- 两个端点检查内容分离：liveness 只反映进程内状态（死锁、关键线程停摆），不聚合任何外部依赖——基础设施抖动若进入 liveness 会放大成容器重启风暴；readiness 反映可接流状态，聚合关键依赖（连接池等）检查，失败时摘除流量、恢复后自动回归，不重启进程。
- 自定义 `HealthIndicator` 只做组件可用性判定，不在健康检查里跑慢查询或重逻辑；镜像 HEALTHCHECK 用 `start_period` 覆盖启动期，防止启动中被判死。
- readiness 端点同时是交付门禁探活地址：容器部署 `FF_HEALTH_URL` 指向它，语义与编排映射见 `mv-container-deploy` 交付契约「双探针」。

## 框架扩展点与运行时集成

- 修改拦截器、结果转换、重试器或自动配置时，检查当前依赖版本的实际执行链。确认结果转换影响的是最终类型绑定，而不只是响应对象的某个访问器。
- 用最小运行时集成覆盖真实客户端、序列化、Spring 注册与配置绑定；保留正常响应、业务失败包络、连接失败和重试耗尽场景。不要 mock 掉待验证的框架扩展点。
- 重试必须有明确上限、计数递增和终止路径；只有可安全重放的操作才重试。检查成功响应是否会误入重试，以及框架是否会重新执行请求前置钩子。
- token 失效重试时，确认刷新后的凭据已写入实际重放请求；仅驱逐缓存不保证旧请求头被替换。多实例共享 token 时，结合服务端失效语义设计刷新锁、缓存与并发测试。
- 配置含路径模式或特殊字符 Map 键时，通过真实 Spring 绑定检查最终键值；新增接口包后检查扫描注册、Bean 注入以及拦截器的作用范围。
- 保持模块依赖无环，必要时通过端口隔离技术实现与核心逻辑；装配根负责接线，不将业务决策藏入技术拦截器。
