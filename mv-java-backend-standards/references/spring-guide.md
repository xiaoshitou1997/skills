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

- 业务自定义配置用 `@ConfigurationProperties` 类型化绑定并按领域拆分，不合并为单一巨量配置类；key 用 kebab-case（如 `app.jwt.expire-minutes`）。
- 含连字符的 key 显式声明环境变量占位与默认值（如 `${APP_JWT_EXPIRE_MINUTES:30}`）：relaxed-binding 会把 expire-minutes 映射为 EXPIREMINUTES，显式占位规避环境变量命名歧义。
- 多环境用 `application-{profile}.yml` 加环境变量覆盖。

## 框架扩展点与运行时集成

- 修改拦截器、结果转换、重试器或自动配置时，检查当前依赖版本的实际执行链。确认结果转换影响的是最终类型绑定，而不只是响应对象的某个访问器。
- 用最小运行时集成覆盖真实客户端、序列化、Spring 注册与配置绑定；保留正常响应、业务失败包络、连接失败和重试耗尽场景。不要 mock 掉待验证的框架扩展点。
- 重试必须有明确上限、计数递增和终止路径；只有可安全重放的操作才重试。检查成功响应是否会误入重试，以及框架是否会重新执行请求前置钩子。
- token 失效重试时，确认刷新后的凭据已写入实际重放请求；仅驱逐缓存不保证旧请求头被替换。多实例共享 token 时，结合服务端失效语义设计刷新锁、缓存与并发测试。
- 配置含路径模式或特殊字符 Map 键时，通过真实 Spring 绑定检查最终键值；新增接口包后检查扫描注册、Bean 注入以及拦截器的作用范围。
- 保持模块依赖无环，必要时通过端口隔离技术实现与核心逻辑；装配根负责接线，不将业务决策藏入技术拦截器。
