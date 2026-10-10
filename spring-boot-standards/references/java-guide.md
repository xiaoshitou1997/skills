# Java Spring Boot / MyBatis-Plus 编码指南

## 包与模块分层

在已有项目约定不冲突时，可选择以下布局：

```text
module-common/        通用异常、常量、工具
module-api/           DTO/契约、服务接口（需要跨模块调用时）
module-service/       Controller、Service、Repository/Mapper
module-task/          消息消费/任务（存在时）
```

单模块常见目录：`controller/`、`service/`、`mapper/`、`model/entity/`、`model/dto/`、`model/vo/`、`model/query/`、`config/`、`handler/`。

## 代码与命名

- Controller `UserController`; Service `UserService`; Mapper `UserMapper`; DTO `CreateUserRequest` 或遵循项目既有 `CreateUserDTO`; VO `UserVO`。
- 参数数量过多时封装对象；避免含混的 `deal`, `handleData` 与不必要缩写；注释解释为何而非复述代码。
- Java 代码缩进一般 4 空格，行宽参考项目 Checkstyle/Spotless，不强制与既有格式化配置冲突；避免注释掉的旧实现。
- DTO/Entity/VO 转换优先显式代码或项目既有 MapStruct；避免未受控的反射拷贝造成字段漏填/泄露。
- 有状态组件按职责命名，避免伪装成工具类。使用 Lombok 等注解时检查嵌套类型是否遮蔽注解名。重复出现的拼写错误使用限定范围的扫描或重命名工具校验，并以编译结果确认引用完整。

## 常量、控制语句与注释

- 不散落魔法值；字面量收敛为具名常量并按功能归类，不维护单一巨型 Constants 杂糅类。可变状态取值优先用枚举承载。`long` 赋值用大写 `L`。
- if/for/while/switch 即使单行也加花括号；switch 必须有 default，case 以 break/return 结束或显式注释 fall-through。
- 嵌套超过 3 层用卫语句（early return）、策略或状态模式重构；少用取反逻辑；`Boolean` 对象用于条件前注意 null 语义（仅 getXxx/isXxx 场景可直接判断）。
- 覆盖 `equals` 必须同时覆盖 `hashCode`；浮点数等值判断用 `BigDecimal` 或精度阈值，不用 `==`。
- 类、类属性、类方法用 Javadoc 说明功能、参数、返回值与异常；枚举每个元素注释含义；注释解释"为什么"，不留废弃代码，历史追溯交给版本管理。

## 集合与并发

- 集合转数组用 `toArray(T[] array)` 传同类型空数组；不在 foreach 中 remove/add，删除用 Iterator；遍历 Map 用 entrySet，不 keySet 后逐个 get。
- `Arrays.asList` 与 `subList` 结果不可强转 ArrayList；原集合结构性修改会使 subList 抛 `ConcurrentModificationException`。
- 集合初始化指定预期容量；`ConcurrentHashMap` 键值均不支持 null，并发场景不依赖 HashMap 的线程安全。
- 线程池用 `ThreadPoolExecutor` 显式声明参数，不用 Executors 工厂直接创建，规避无界队列 OOM 与线程数失控。
- `SimpleDateFormat` 不定义为 static 共享，用 `DateTimeFormatter` 或 ThreadLocal（用后 remove）；volatile 不保证原子性，计数累加用原子类。
- 加锁顺序一致、锁范围仅覆盖临界区；并发修改同一条记录用行级锁、乐观锁或分布式锁。

## API 与错误

- 约定统一的错误编码、HTTP 状态、参数校验和 requestId/traceId。
- 使用 `@Valid`/`@Validated`，业务规则同时在 Service 层确认；避免直接相信 Controller 层入参。
- 生产错误仅给必要的错误信息，不返回堆栈；在合适层统一记录错误，不制造日志风暴。
- API 改动考虑兼容老客户端、分页约定、幂等请求、限流与鉴权权限边界。
- 区分 HTTP 状态、平台包络码和内层业务码；HTTP 200 不保证业务成功。确认码的字符串/数值类型和真实响应结构，不凭字段名推断契约。
- 每个独立业务失败场景对应唯一错误码枚举常量，一个 code 唯一映射一个业务语义；不复用既有错误码扩展语义，新增失败场景同步新增枚举。前端按 code 分支，前后端语义严格对齐。
- 用户可见文案（异常提示、响应信息）不在业务代码中硬编码中英文字符串；统一维护在 `messages*.properties`，经 MessageSource 或 ErrorCode 关联的 messageKey 获取。
- RESTful 动词语义清晰：查询 GET、新增 POST、更新 PUT、删除 DELETE，不用未指定方法的 `@RequestMapping`；URL 小写名词复数、不含动词，可带版本前缀（`/api/v1/users`）。项目已有路由风格优先。
- 手机号、证件号等隐私数据在 VO 层脱敏后返回，不暴露原始敏感数据。

## 枚举与类型安全

- 实体中的状态、类型、角色、协议等枚举型字段用 Java 枚举承载，并全链路使用（存储、方法入参、返回值、查询条件、业务判断），不以 String 中转。
- JPA 持久化用 `@Enumerated(EnumType.STRING)` 保证存储值可读；MyBatis-Plus 用 `@EnumValue`/`IEnum` 或项目既有 TypeHandler，遵循项目已确立的映射方式，不混用方案。
- 结构化业务数据用 POJO/DTO/VO 强类型承载，不用 Map、JsonNode 替代真实类型；仅无固定 Schema 的三方协议载荷、JSON 转换字段允许动态结构。
- 具备独立业务语义的类定义为顶层类，不以嵌套类、静态内部类形式存在；一次性匿名实现不受限。
- 字符串、对象、集合判空用 StringUtils/ObjectUtils/CollectionUtils 等标准工具类，不手写空值判断，不保留冗余判空；返回集合时返回空集合，不返回 null。

## 接口契约与文档交付

- 接口文档明确方法、路径、请求与响应字段的类型、必填条件、枚举值以及成功/失败示例；示例须与契约一致，足以让调用方直接准备联调请求。
- 公共鉴权、签名、幂等与重试约定集中说明，区分公共错误和接口特有错误；字段命名与真实提供方契约一致，不把调用方字段名直接替换进去。
- 密钥、密码等凭据不作为普通业务接口响应字段返回；凭据交付或专用认证接口遵循团队安全契约，示例使用占位值。外部尚未确认的字段、参数或行为显式标为待确认，不写成已验证事实。
- 用户指定目录、编号或文档结构时按约束编写，不自行增删、重编号或重组；发现缺项先说明。交付前检查跨文件链接、示例与正文一致性，以及变更是否同步到关联文档。

## 异步任务与后台作业

- 检查调度器、任务基类、异步执行器和异常处理器是否会捕获异常并误报成功；按框架机制明确返回失败、标记失败状态或传播异常，日志不是失败状态的替代品。
- 区分已接收、执行中、成功、失败，确保调用方或运维能关联任务标识并查询最终结果。重试考虑幂等、部分成功、次数上限及耗尽后的处理，避免只重跑整批造成重复副作用。

## 数据库与事务

- 查询指定必要字段；分页大集合，限制最大 page size；避免 N+1 查询，考虑批量查询/缓存权衡。
- DDL / migration 用项目已有 Flyway/Liquibase/SQL 流程，默认不得随应用镜像回滚反向执行。
- 合适的 `@Transactional` 仅在 Service 业务边界上，明确事务的传播、隔离与 checked exception 回滚语义。
- 不在长事务中远程 HTTP 请求或慢操作；避免自调用导致代理失效；讨论分布式事务和 Outbox 等替代方案。
- 避免日志打印账户机密、令牌或用户私密资料；敏感字段标记/脱敏。
- 使用 MyBatis-Plus 时，含数字或特殊分隔的属性名要核对实际列映射，必要时显式 `@TableField`；软删除、枚举和唯一键形状遵循项目基线，不将单个项目约定推广为通用 DDL 规则。
- 业务表统一审计字段（创建时间、更新时间、逻辑删除标记）并实现自动填充；时间用 `LocalDateTime` 对应 datetime 列，不混用 `Date`。JPA 用投影查询替代 `select *` 的同等约束。
- 主键策略（如雪花 ID）由项目/采用方统一后不混用其他方案；新项目未确立时先与团队确认，不擅自定方案。
- 列表查询必须分页，不执行无边界全量查询；SQL 参数一律预编译占位符，不拼接。

## 框架扩展点与运行时集成

- 修改拦截器、结果转换、重试器或自动配置时，检查当前依赖版本的实际执行链。确认结果转换影响的是最终类型绑定，而不只是响应对象的某个访问器。
- 用最小运行时集成覆盖真实客户端、序列化、Spring 注册与配置绑定；保留正常响应、业务失败包络、连接失败和重试耗尽场景。不要 mock 掉待验证的框架扩展点。
- 重试必须有明确上限、计数递增和终止路径；只有可安全重放的操作才重试。检查成功响应是否会误入重试，以及框架是否会重新执行请求前置钩子。
- token 失效重试时，确认刷新后的凭据已写入实际重放请求；仅驱逐缓存不保证旧请求头被替换。多实例共享 token 时，结合服务端失效语义设计刷新锁、缓存与并发测试。
- 配置含路径模式或特殊字符 Map 键时，通过真实 Spring 绑定检查最终键值；新增接口包后检查扫描注册、Bean 注入以及拦截器的作用范围。
- 保持模块依赖无环，必要时通过端口隔离技术实现与核心逻辑；装配根负责接线，不将业务决策藏入技术拦截器。

## 测试

- 核心业务 Service 单元测试覆盖成功、失败、边界和异常；测试方法采用项目约定，`createUser_DuplicateEmail_ThrowsException` 是示例。
- Mapper/SQL 结合真实数据库方言做集成测试；不要将 mock 成功当成 SQL 已验证。
- 涉及网络协议、中间件等外部交互的能力用真实客户端做回环集成测试；集成测试端口动态分配（`new ServerSocket(0)` 获取空闲端口），避免冲突。
- 涉及认证上下文的集成测试设置真实主体对象，不使用静态 mock。
- 覆盖率门槛（如核心包行覆盖 ≥70%、分支 ≥50%，其他受控包 ≥65%/≥40%）以项目 CI 实际配置为准，作为合并前阻断执行；项目未配置时不擅自引入新门槛，先与团队确立。
- 变更回归范围依风险而定，未实际运行测试不能声称通过。
- 对异步任务验证最终状态、失败记录和重试行为；覆盖处理器抛异常、基类捕获异常及部分完成的情况，不能只断言接口接受请求或执行过程没有向调用方抛异常。

## 配置、CI 与运行期约束

- 业务自定义配置用 `@ConfigurationProperties` 类型化绑定并按领域拆分，不合并为单一巨量配置类；key 用 kebab-case（如 `app.jwt.expire-minutes`）。
- 含连字符的 key 显式声明环境变量占位与默认值（如 `${APP_JWT_EXPIRE_MINUTES:30}`）：relaxed-binding 会把 expire-minutes 映射为 EXPIREMINUTES，显式占位规避环境变量命名歧义。
- 敏感配置（密钥、令牌、连接串）统一走环境变量或配置中心，不提交仓库、不硬编码；多环境用 `application-{profile}.yml` 加环境变量覆盖。
- CI 合并前检查点（编译、lint、单测、覆盖率、依赖安全扫描如 OWASP dependency-check）全绿后合并；静态分析用 SpotBugs/SonarQube，以项目既有流水线为准，不为规范而重建流水线。
- 发布版本遵循语义化版本 `vMAJOR.MINOR.PATCH`，产物含 commit 溯源信息；分支模型与主分支保护按项目约定。
- 运行期行为必须明确并文档化：schema 策略（如 create-drop 仅限临时环境，生产禁止自动重建）、惰性依赖（应用可独立于缓存/MQ 启动，依赖宕机时的失败范围）、调度任务周期与数据保留策略、重启后恢复运行态资源。

## 交付自查清单

变更交付前逐项确认；与项目实际基线冲突时以项目为准：

- [ ] 无魔法值，命名规范，equals/hashCode 成对覆盖，Javadoc 完整
- [ ] 集合与并发合规：toArray、Iterator 删除、entrySet、ThreadPoolExecutor 显式建池、ThreadLocal 用后 remove
- [ ] 异常未用于流程控制，finally 无 return，无空 catch；日志 SLF4J 占位符，无敏感信息与 System.out
- [ ] 分层单向依赖，无跨层调用与循环依赖；业务数据 POJO 化，无 Map/JsonNode 替代，无承载业务语义的内部类
- [ ] 枚举字段全链路枚举类型；错误码一场景一码；用户可见文案走国际化资源
- [ ] 配置类型化绑定、kebab-case，敏感配置外置
- [ ] 审计字段、时间类型、分页、SQL 参数化符合项目基线；REST 动词/URL/DTO 校验/统一响应/VO 脱敏合规
- [ ] 测试覆盖正常/边界/异常路径，覆盖率达标，CI 全绿
- [ ] 运行期约束（schema 策略、惰性依赖、调度、启动恢复）已文档化
