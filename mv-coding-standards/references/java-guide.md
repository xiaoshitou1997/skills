# Java 后端编码指南

框架中立主体，承载 Java 后端通用工程条款（团队 Java 后端基线为 Spring Boot，基线见 mv-design-standards）。使用 Spring Boot 时并读 [spring-guide.md](spring-guide.md)（含 JPA 数据访问条款）。

## 目录

- 包与模块分层
- 代码与命名
- 常量、控制语句与注释
- 集合与并发
- API 与错误
- 角色与权限
- 枚举与类型安全
- 接口契约与文档交付
- 异步任务与后台作业
- 外部调用与外部数据
- 数据库与事务
- 测试
- 配置与运行期约束
- 交付自查清单

## 包与模块分层

在已有项目约定不冲突时，模块命名与分层按本节规则。

### 模块命名

模块名 = `<项目>-[切片词]-<后缀>`，后缀取自固定闭集，不造集合外后缀：

| 后缀 | 语义 | 形态与拆分判据 |
|---|---|---|
| `-common` | 公共异常、常量、工具 | 库；必建——统一包络、错误码契约（`ErrorCode`、`ServiceException`、`CommonErrorCodeEnum`）等横切骨架与跨模块公共契约落点，全部后端模块依赖，不并入 service（`-entity` 的并入豁免不适用于此） |
| `-api` | 跨项目契约：服务接口 + DTO | 库；有外部集成方才拆 |
| `-sdk` | 客户端封装（重试、鉴权、序列化） | 库；对外发布才拆 |
| `-spring-boot-starter` | 技术组件自动装配 | 库；按 Spring 官方惯例命名 |
| `-entity` | 实体、仓储、业务用例 | 库；业务逻辑出现第二个可运行消费者才拆 |
| `-service` | 可运行后端入口，唯一含 main | 应用 |
| `-web` / `-mp` / `-mobile` | 浏览器前端 / 小程序 / App | 前端工程，不进后端聚合 pom；两端共用 Web 工程命名 `shop-web`，独立工程带端词（如 `shop-user-web`、`shop-admin-web`、`shop-user-mp`、`shop-user-mobile`） |

切片词 = 端词或域词。端词固定占用 `user`（用户端）、`admin`（管理端）；域词按业务划定（`order`、`member`、`product` 等），不得与端词重合（账号/会员域用 `member`，`user` 留给用户端）。同一层级不混用按端切与按域切；接入层端入口（`user`/`admin` 切片）与域服务（域词切片）属两个功能层级，微服务双端项目可同时存在，端入口聚合域服务对外。

**模块名与目录名逐字相同**：无论 Maven、Gradle 还是其他构建工具，工具侧定义的模块名必须与所在文件夹名完全一致，不允许工具层重命名——Maven 的 `artifactId` 与聚合 `<module>`、Gradle settings 的 project 名与 `rootProject.name`、npm 的 `package.json` `name`，都直接取目录名；根 POM、根 settings 的项目名与仓库根目录名同理。按本节公式命名的模块，目录同名（如 `shop-order-service/`）。

### 三种布局

任意后端聚合 POM 最少两个 Maven 模块：一个 `-common`（必建，判据见上表）加至少一个可运行 `-service`；其余模块按上表拆分判据增拆。

单入口——多数项目默认两端共用 `shop-service` 与 `shop-web`；两端按路径、布局和权限区分：

```text
shop-service/            唯一入口：controller/admin/（管理端）与 controller/uc/（用户端）分包
shop-entity/            共享业务核心（出现第二个可运行消费者前可并入 service 内分包）
shop-common/
```

两端共用进程时以路径前缀分段（如 `/admin/**`、`/uc/**`），安全配置按路径独立，权限点按 RBAC 集中在入口层校验。

按端切——面向 C 端消费者且同时有两端的产品默认分离；其他项目有独立伸缩、网络边界或发布节奏时采用：

```text
shop-user-service/       用户端入口
shop-admin-service/      管理端入口
shop-task-service/       定时任务与消息消费进程
shop-entity/  shop-common/
```

两个入口可调用同一实体模块，由该模块统一负责业务规则与数据写入；实体库不必然是独立运行的微服务。前端分别按需创建 `shop-user-web`、`shop-admin-web`，各入口和前端独立构建部署；仅有 H5/小程序时不强制创建用户 Web。

按域切——微服务化，每域一个可运行服务：

```text
shop-order-service/  shop-member-service/  shop-product-service/
shop-order-entity/      跨服务共享实现的域才拆；跨项目契约拆 shop-order-api
shop-common/
```

单模块常见目录：`controller/`、`service/`、`mapper/` 或 `repository/`、`model/entity/`、`model/request/`、`model/response/`、`model/query/`、`config/`、`handler/`。

`-common` 包结构固定：`web/` 承载 `Result`、`Page`、`GlobalExceptionHandler` 与包络装配；`error/` 承载错误码契约三件（`ErrorCode`、`CommonErrorCodeEnum`、`ServiceException`）；`i18n/` 承载 locale 解析与 MessageSource 装配；`config/` 承载 `XxxProperties` 类型化配置骨架；`util/` 承载 Jackson 静态封装等纯工具，首个纯工具类出现时建，无工具类不建空目录。`-common` 的 Java 包根为 `{项目根包}.common`；启动类置于 `{项目根包}`（`-service` 模块内），默认组件扫描覆盖 common 组件，不另配扫描路径。

## 代码与命名

- Controller `UserController`; Service `UserService`; Mapper `UserMapper`; 载体 `CreateUserRequest`/`CreateUserResponse`、`ListUserRequest`/`ListUserResponse`。
- 载体命名 `${Action}${Entity}Request`/`${Action}${Entity}Response`，按端点成对出现（`CreateUserRequest`/`CreateUserResponse`、`ListUserRequest`/`ListUserResponse`、`GetUserRequest`/`GetUserResponse`）；裸 `UserRequest`/`UserResponse`（顶层实体名 + 后缀）禁止——名字须能回答「服务于哪个行为」。Model/DTO/VO/View 一律不作载体后缀，裸 `XxxRow`（实体名 + Row、不带动作）同样禁止；方向与行为由 Action 前缀加 Request/Response 后缀表达，既有项目沿用旧后缀的按「用户明确需求 → 本规范」偏离链记录理由；不用 `UpdatingXxx`/`UpdatedXxx` 一类时态对命名。
- Request 与 Response 必须是对象，不作裸 List/Map 进出：单对象响应用字段承载（`GetUserResponse` 内 `user` 字段），批量入参同样以字段承载（`DeleteUsersRequest` 内 `ids` 字段）；列表端点响应载体为固定分页结构 `Page<...Row>`（见下方分页条款）；形态相同的端点可复用同一载体类。
- 分页机制分层各归其位：分页参数（`page`/`size`/`sort` 一类）作为普通字段进 `ListXxxRequest`，入口可用 `@PageableDefault` 绑定；`Pageable`/`PageRequest` 与 Spring 的 `Page<T>` 止步 Service 内部——仓库返回的 `Page<T>` 在 Service 消费并转成本方分页结构，`PageImpl` 不出 Service（序列化形态随版本漂移、等价性只按 content 与 total 判定）。列表端点响应载体用固定分页结构 `Page<T>`（与 `Result` 同级的固定通用结构，落 `-common` `web/` 包，字段固定为 `rows`/`total`，行元素 `${Action}${Entity}Row`，包络 `data` 直接为 `Page<ListUserRow>`）；列表端点不另造 `ListXxxResponse` 类，其余端点仍按 `XxxRequest`/`XxxResponse` 成对。
- 参数数量过多时封装对象；不含业务语义的万能词不作方法名（`deal`、`handleData`、`processData`、`manage`），判定标准：看名字与所在类说不出它处理什么、产出什么即换业务动词；非行业通用缩写不用；注释解释为何而非复述代码。
- 命名按英文习惯表达语义，不做中文大白话直译：先定语义再选词，不以中文语序拼英文；布尔判断用 is/has/can + 形容词（如 `isNormal`），不写 `judgeIfNormal`、`checkIsNormal` 这类逐字翻译。
- 实现需求时禁止 import 未使用的类；新产生的多余 import、代码块与类一律删除，不依赖 IDE 自动清理兜底；存量冗余按最小变更原则不扩散、不随本次变更重写。
- 项目无格式化配置时 Java 代码缩进 4 空格；行宽上限取项目 Checkstyle/Spotless 配置，有配置以配置为准；避免注释掉的旧实现。
- Request/Response 载体与 Entity 转换优先显式代码或项目既有 MapStruct；避免未受控的反射拷贝造成字段漏填/泄露。
- JSON 序列化统一 Jackson（团队基线），不引入 fastjson、gson；ObjectMapper 统一使用 Spring Boot 自动配置的 bean，定制经 `spring.jackson.*` 配置属性集中调整，不在业务代码散落自建实例；需要静态工具入口时经构造注入把该 bean 装进封装类，封装内部不自建 mapper；第三方库内部自建的 mapper 不受此限。Jackson 3 下未知属性处理与日期序列化格式按项目契约显式验证，不依赖版本默认值。
- 工具方法优先 JDK 标准库、Spring 自带工具类与 Apache Commons（判空、集合、断言、IO 等）；不引入 Hutool（团队基线）。
- 有状态组件按职责命名，避免伪装成工具类。使用 Lombok 等注解时检查嵌套类型是否遮蔽注解名。重复出现的拼写错误使用限定范围的扫描或重命名工具校验，并以编译结果确认引用完整。
- 禁止通配符导入（`import xxx.*`），按类显式列出依赖；禁止在代码正文中使用全限定名（如 `java.util.List`），统一通过 `import` 语句引用，避免与同包同名类混淆并保持 import 顺序稳定。
- 命名角色后缀取固定词表，一词一义：`Resolver` 策略式转换裁决、`Handler` 输入处置组件、`Processor` 流水线钩子、`Adapter` 接口桥接、`Registry` 可注册容器、`Holder` 对象载体、`Template` 操作模板、`Configurer` 配置定制装配（`WebMvcConfigurer`）、`Listener` 事件监听（`ApplicationListener`）、`Interceptor` 拦截横切（`HandlerInterceptor`）、`Properties` 类型化配置载体（`@ConfigurationProperties` 的 `XxxProperties`）、`Utils` 纯静态工具类（`StringUtils`，配 private 构造器防实例化）。新增类名从词表选词；表外职责词先给出仓外既定用法证据再使用，同一职责不另造同义词。
- 查询动词分级编码返回契约，同一接口对同一数据只用其一：`getXxx` 必得，缺失抛业务异常；`findXxx` 可空，缺失返回 null 或 Optional；`resolveXxx` 经策略把输入规范化为目标值（占位符、locale、视图名一类）；`loadXxx` 装载或刷新可缓存状态；`obtainXxx` 内部获取必然就绪的实例，未就绪即失败。调用点不查实现即可判定缺失行为。
- 成对操作动词对称且全库唯一：register/remove、before/after、pre/post；同一概念不出现第二套动词（如 register 与 unregister 并存）。
- 近邻概念用复合名词写全作用对象消歧（如 `BeanFactoryPostProcessor` 与 `BeanPostProcessor` 各自作用于工厂与实例），不用未加说明的缩写。
- 接口的实现类以策略命名，不用 `Impl` 后缀：类名说明选择的路线（`JpaOrderRepository`、`InMemoryOrderRepository`、`DefaultUserService` 一类），`OrderServiceImpl` 式命名只说明"它是实现"，不说明是什么实现；策略不分化时不为命名造形式化接口+实现两件套（主规范「分层与命名」既有条款）。
- `Manager` 仅限拥有某资源族生命周期的所有者角色（`TransactionManager`、`CacheManager` 一类），不作模糊职责词；说不出"拥有什么资源的生命周期"的类按角色词表另选词。
- 对外方法薄封装，真实逻辑下沉到 `do` 前缀的内部工作方法（`AbstractBeanFactory.doGetBean`、`doResolveDependency` 一类），`do` 方法不直接对外暴露；静态工厂动词按语义从 `of`/`from`/`valueOf`/`for`/`parse` 选词——聚合组件用 `of`、转换既有值用 `from`/`valueOf`（`HttpStatus.valueOf`）、按已知上下文定位用 `for`（`ResolvableType.forClass`）、解析文本用 `parse`（`MediaType.parseMediaType`）；事件与回调方法用 `on` + 事件名（`onApplicationEvent` 式，业务侧如 `onOrderCreated`）；组件生命周期收口到框架注解或接口（`@PostConstruct`/`@PreDestroy`/`InitializingBean.afterPropertiesSet`），自定义生命周期对沿用成对动词条款。
- 接口小而单一，接口名即能力名（`Ordered`、`InitializingBean`、`BeanNameAware` 一类，一句话说不出能力的不建接口）；能力通过组合与接口注入装配，不靠继承层级堆叠；常量定义在所属类上（`HttpStatus.OK`、`MediaType.APPLICATION_JSON`），随类组织不建 `XxxConstants` 收容类（衔接「不维护巨型 Constants」条款）。

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
- 使用 Bean Validation（如 `@Valid`/`@Validated`）做入口校验，基础校验一律约束注解声明，且每个注解必须声明 `messageKey`（格式 `validation.{entity}.{field}.{constraint}`，禁 `param.invalid` 一类笼统键）引用语言资源，不手写等价判断，Service 不重复基础校验；业务规则同时在 Service 层确认，避免直接相信入参。
- 生产错误仅返回错误码、message 与 requestId，不返回堆栈；错误经全局异常处理器统一记录，不制造日志风暴。
- API 改动考虑兼容老客户端、分页约定、幂等请求、限流与鉴权权限边界。
- 区分 HTTP 状态、平台包络码和内层业务码；HTTP 200 不保证业务成功。确认码的字符串/数值类型和真实响应结构，不凭字段名推断契约。
- 每个独立业务失败场景对应唯一错误码枚举常量，一个 code 唯一映射一个业务语义；不复用既有错误码扩展语义，新增失败场景同步新增枚举。常量名与语义必须落到具体失败场景（`ORDER_NOT_FOUND`、`INSUFFICIENT_STOCK` 一类），`OPERATION_FAILED`、`REQUEST_FAILED`、`BIZ_ERROR` 一类不指向具体场景的笼统常量禁止——它们天然一码多场景，直接违反唯一映射；系统级兜底由 `-common` 的公共枚举承担（`COMMON_INTERNAL_ERROR` 语义即「未捕获异常」），业务枚举内不自造同类兜底。前端按 code 分支，前后端语义严格对齐。
- 用户可见文案（异常提示、响应信息）不在业务代码中硬编码中英文字符串；统一维护在 i18n 资源文件，经项目国际化机制或 `ErrorCode` 关联的 messageKey 获取。
- 错误码载体定型：每模块一个错误码枚举，类名 `XxxErrorCodeEnum`（模块语义名），统一实现公共 `ErrorCode` 接口；接口声明三个成员——HTTP 状态、`code`、`messageKey`，是 `ServiceException`、全局异常处理器与文案解析共同依赖的唯一类型，处理器与框架接线不耦合具体模块枚举。
- `code` 为字符串契约标识：等于枚举常量名，常量名以模块语义前缀开头（如 `ORDER_NOT_FOUND`、`USER_NOT_FOUND`），全集唯一；唯一性与「`code` 等于常量名」由单元测试扫描全部错误码枚举校验，不设人工维护的号段分配表，不以数字作 `code`。
- `messageKey` 不作为枚举存储字段，由 `ErrorCode` 接口按固定规则派生：`error.` + `code`（如 `error.ORDER_NOT_FOUND`）；派生规则一处实现，文案键双语同批补齐按 spring-guide「国际化」完整性条款纳入项目检查。
- 业务失败统一抛 `ServiceException`（`RuntimeException` 子类，落 `-common` 模块）：构造只接受 `ErrorCode` 与占位符 args，args 只装数据值（名称、单号、数量一类，同 spring-guide「国际化」持久化形态口径）；不提供裸文案构造——文案在输出时刻按 locale 渲染，异常携带成品文案即绕过国际化。
- RESTful 动词语义清晰：查询 GET、新增 POST、更新 PUT、删除 DELETE，路由声明绑定具体 HTTP 方法；URL 小写名词复数、不含动词，可带版本前缀（`/api/v1/users`）。存量路由不批量改写，新端点按本条执行；确需偏离时显式记录。
- 手机号、证件号等隐私数据在响应载体（Response/Row）层脱敏后返回，不暴露原始敏感数据。

## 角色与权限

- 角色与权限采用 RBAC 模型：用户经角色关联权限，授权判定只认权限点，不做用户与权限的直接绑定。
- 功能权限点在入口层用声明式注解或集中拦截器统一校验，不散落手写 `if (!hasPerm(...))`；资源归属、数据范围及状态相关授权在 Service 真实业务边界校验，使用当前可信主体与服务端数据。统一功能授权不能替代对象级授权。
- 权限点按业务操作定义且前后端共用同一权限标识：前端列表页面与后端列表接口是同一个权限点，前端删除按钮与后端删除接口是同一个权限点；页面可见性与接口授权不拆成两个权限分别设计。
- 权限标识是稳定契约：统一定义、纳入接口文档交付，前端按标识控制入口可见性，后端按标识做接口授权；权限标识变更按契约变更管理，不前后端各自改名。
- 权限粒度判据：写操作一接口一点——POST/PUT/DELETE 及带副作用的动作接口各对应一个权限点（`order:create` 与 `order:export` 分开），写操作是审计与追责的最小单位；读操作一页面一点——列表、详情、下拉等查询合并为页面查询权限点，导出与敏感字段查看单独成点；页面受控入口（按钮、菜单项）必须绑定权限标识，某入口找不到应绑权限点即粒度拆分有误——要么并入页面级，要么对应写接口缺权限点。层级基线三级：域/目录、页面、操作，页面内出现操作分组时到四级，不再深。评审试金石：撤销一个权限点只影响一个操作、新增接口只需种子新增一个叶子，两条同时成立即粒度合适。
- 权限点组织为一棵树（节点即权限点，根为域/目录，父标识承载层级），树承载菜单渲染、角色授予勾选（父子联动展示）与种子归组；菜单不另立一棵树——菜单节点即权限树中的目录与页面节点，管理端按当前用户授予集渲染菜单与勾选授予。授权判定 exact-match 功能权限标识、不递归祖先节点，授予集合即勾选集合（含目录与页面节点）；数据权限不入树——「能做什么操作」属功能权限入树，「能操作哪些数据」走 Service 真实业务边界的对象级授权，树内不出现「只看本部门」一类数据范围节点。
- 权限点、菜单等结构定义没有运行时管理入口，作为版本化种子数据随代码发布（迁移脚本幂等 upsert，空库一键拉起，权限标识变更与代码同版本生效）；运行时只管理角色、角色-权限授予与用户-角色关系，授权调整是数据操作，不增删权限定义。

## 认证与会话

- 多用户系统（有用户表、多个可登录账号）用户认证只走 OIDC 联邦登录，不建本地密码账号体系，对接项目已确认的 IdP；IdP 选型是多用户系统的设计前置（见 mv-design-standards），未确认不开建用户认证。单管理员工具端（无用户表）不受此限。OIDC 接入必须完整形态，四项缺一按未完成处理：授权码登录并校验 ID Token（签名、`iss`、`aud`、`exp`、`nonce`）；RP 发起登出跳 IdP `end_session_endpoint` 并同步失效本地会话，不以清本地会话冒充联邦登出；令牌生命周期闭环（过期刷新或重新授权，失效与过期令牌按未认证处理）；身份映射衔接（claims 映射本地用户与角色，审计操作人从 OIDC 主体解析）。不交付只含登录的半截接入；偏离基线（如客户强制要求本地登录）按「用户明确需求 → 本规范」优先级链记录理由；Spring 承载写法见 spring-guide「认证配置」。
- 认证与授权分离：入口层校验令牌并建立可信主体，按 RBAC 统一校验功能权限点；Service 从安全上下文取主体，按「角色与权限」检查对象级授权，不自行解析令牌。
- admin 端与 user 端会话相互独立：两端在 IdP 注册独立客户端（scope 区分授权边界），本地服务端会话各自建立互不互认；单端登出失效本端本地会话，IdP 统一会话注销后两端均需重新认证。
- 管理员口令哈希用 BCrypt/Argon2 一类自适应慢散列，经环境变量注入哈希值（见「初始管理员」条款）；登录失败统一返回 `COMMON_LOGIN_FAILED`，不区分「用户不存在」与「密码错误」，防账号枚举。
- 会话过期返回 `COMMON_SESSION_EXPIRED`，前端据此引导重新认证；Spring 侧过滤器链配置见 spring-guide「认证配置」。
- 初始管理员凭据不进迁移脚本与代码默认值，经环境变量注入：变量名如实承载形态（`*_ADMIN_USERNAME`、`*_ADMIN_PASSWORD_HASH` 存 BCrypt 哈希，生成命令见 mv-delivery-standards credentials 分级表）。无后台工具端用内存用户认证，不建用户表；有后台项目由启动期初始化器按 env 为准幂等 upsert 管理员账号及角色授予，该账户不提供 UI 改密入口，改密=改 env 重启；账号缺失且 env 未配置时拒绝启动并明确报错，日志记 created/updated/skipped 不记凭据值。适用范围与毕业判据见 mv-security-standards「认证」；Spring 接线见 [spring-guide.md](spring-guide.md)「认证配置」。

## 枚举与类型安全

- 实体中的状态、类型、角色、协议等枚举型字段用 Java 枚举承载，并全链路使用（存储、方法入参、返回值、查询条件、业务判断），不以 String 中转。
- 数据库存储的枚举值必须用可读语义字面量（如 `STARTING`/`STOPPED`/`PAUSED`），禁止用数字（1/2/3 等）作为状态值；落库映射遵循所选持久层框架（JPA 见 [spring-guide.md](spring-guide.md)「JPA 数据访问」）的既定方案，同一项目不混用。
- 值域封闭/开放判定与三种落库形态（枚举加 CHECK、版本化种子表、真表加真外键）按 mv-design-standards「关键规则」值域条款判定；本节定封闭值域在代码中的承载。封闭值域列带 CHECK 约束兜住封闭性，新增值随发版走 CHECK 迁移；只插数据行、无代码配合的「死值」不允许出现。封闭值域全链路标识用 code 不用自增 id：出入参、存储值、日志与对接报文一律携带 code；id 是存储实现细节（跨环境不可复现、重建即漂移），不进契约与日志。种子表以 code 作唯一键，暴露给运行时行真外键引用。
- 枚举承载完整类型：属性挂构造字段（展示名走 i18n messageKey，不硬编码文案），行为挂枚举方法或常量级覆写；按值分支的 switch/if 散落在多个 Service 中是行为未归位信号，分支收敛到枚举本体。
- 复杂流程策略化：行为需要依赖注入（Repository、RestClient 等容器 bean）或流程超出枚举方法承载时，升级为策略接口加每值一个 Handler/Adapter bean；枚举拿不到容器 bean，索引由 Spring 注入全部策略实现按 code 组装，枚举只作 key，不在枚举内持有 bean 或静态单例。新增封闭值 = 新枚举常量加新策略（如有）加 CHECK 迁移，一次发版完成。
- 开放值域（真表承载）的取值与展示名经该值域的列表或字典接口按请求 locale 返回，供给形态与实体 list 接口一致；前端消费约束见 [frontend-guide.md](frontend-guide.md)「数据获取与服务层」。
- 前端需要枚举取值全集的场景（筛选、下拉等）提供枚举字典端点，按请求 locale 返回取值与展示名（展示名渲染见 [spring-guide.md](spring-guide.md) 国际化条款）；取值全集以该端点为唯一来源，不在多个接口各自重复定义。
- 结构化业务数据用强类型载体（Request/Response/Row）承载，不用 Map、JsonNode 替代真实类型；仅无固定 Schema 的三方协议载荷、JSON 转换字段允许动态结构。
- 具备独立业务语义的类定义为顶层类，不以嵌套类、静态内部类形式存在；一次性匿名实现不受限。
- 字符串、对象、集合判空用 StringUtils/ObjectUtils/CollectionUtils 等标准工具类，不手写空值判断，不保留冗余判空；返回集合时返回空集合，不返回 null。

## 接口契约与文档交付

- 团队基线经 springdoc/OpenAPI 暴露机器可读契约（`springdoc-openapi` starter，`/v3/api-docs`），接口文档与代码同源生成；手工文档与生成契约不一致时先核实代码现状再改。前端类型来源与同步责任见 mv-design-standards「共享契约与类型同步」。
- 接口文档明确方法、路径、请求与响应字段的类型、必填条件、枚举值以及成功/失败示例；示例须与契约一致，足以让调用方直接准备联调请求。
- 公共鉴权、签名、幂等与重试约定集中说明，区分公共错误和接口特有错误；字段命名与真实提供方契约一致，不把调用方字段名直接替换进去。
- 密钥、密码等凭据不作为普通业务接口响应字段返回；凭据交付或专用认证接口遵循团队安全契约，示例使用占位值。外部尚未确认的字段、参数或行为显式标为待确认，不写成已验证事实。
- 用户指定目录、编号或文档结构时按约束编写，不自行增删、重编号或重组；发现缺项先说明。交付前检查跨文件链接、示例与正文一致性，以及变更是否同步到关联文档。

## 异步任务与后台作业

- 检查调度器、任务基类、异步执行器和异常处理器是否会捕获异常并误报成功；按框架机制明确返回失败、标记失败状态或传播异常，日志不是失败状态的替代品。
- 区分已接收、执行中、成功、失败，确保调用方或运维能关联任务标识并查询最终结果。重试考虑幂等、部分成功、次数上限及耗尽后的处理，避免只重跑整批造成重复副作用。

## 外部调用与外部数据

- 第三方平台联调先采用用户提供的测试环境信息，再查项目集成文档和已有测试配置，确认测试端点、应用身份、签名凭据配置方式及回调地址；缺项向用户询问，不在对话中索取密钥。凭据从项目密钥管理或未跟踪配置注入，不输出到日志；测试环境或凭据不可用时记录未验证的接口和阻塞项，不将单测冒充真实验签通过。
- 不默认信任外部系统：外部接口响应、MQ 消息、第三方回调与导入数据先校验结构、取值与来源（验签、来源标识）再使用；反序列化与校验失败按业务失败处理并记日志，不静默降级、不用兜底默认值掩盖失败。
- 外部返回的成功标志不替代本方执行结果的确认，以本地事务状态或幂等记录为准；外部传入的标识与取值不直接用作授权、资金等敏感决策依据，先按本方规则校验归属与合法性。
- 调用外部系统显式设置连接与读取超时，失败路径明确：重试考虑幂等与次数上限，熔断与降级是显式设计而非隐式吞错；解析容忍未知字段、不放过缺失必填字段，外部契约变更按「接口契约与文档交付」条款管理。

## 数据库与事务

- 查询按本次所需指定列，不取全列；分页大集合，限制最大 page size；避免 N+1 查询，考虑批量查询/缓存权衡。
- 库层约束逐字段落位作为最后防线：必填列 `NOT NULL`，长度定类型上限并与后端校验同口径，取值域用 CHECK、字典表外键或受控枚举列，业务唯一性用 UNIQUE；迁移、脚本、并发与缺陷都可能绕过应用写入，不以「应用已校验」为由省略库层约束；确需免约束的列（如 JSON 内部结构、条件生效约束）在迁移说明记录理由。
- DDL / migration 用项目已有 Flyway/Liquibase/SQL 流程，默认不得随应用镜像回滚反向执行；schema 迁移与大表 DDL 执行策略见 [schema-migrations.md](schema-migrations.md)。
- schema 全量版本化：建表、索引、约束、种子/字典数据一律进版本化迁移脚本，与代码同仓库同版本发布，空库一键拉起，部署与回滚不做手工 SQL。
- 脚本一经任一环境应用不可修改、只追加新脚本，全环境共用一份，方言差异按方言目录（如 `db/migration/{vendor}`）承载；migrate 由流水线自动执行（开发/测试随应用启动，生产与应用启动解耦），人工只审批不执行。
- 结构演进走 expand–contract，应用对上一版 schema 兼容：新增列先可空/带默认，回填或双写后切读，旧列延迟删除；回填按主键游标分批限速，收紧 `NOT NULL`/`UNIQUE` 前先回填查重。
- 事务置于 Service 真实业务边界：不在长事务中执行远程 HTTP 或慢操作；分布式事务优先讨论 Outbox 等替代方案并与团队确认。事务代理、传播与自调用语义按所用框架理解（Spring 见 spring-guide.md）。
- 避免日志打印账户机密、令牌或用户私密资料；敏感字段标记/脱敏。
- 业务表统一审计字段 `created_at`、`updated_at`、`created_by`、`updated_by`（及逻辑删除标记）并实现自动填充；逻辑删除统一实体级 Hibernate `@SoftDelete`（默认 `deleted` 布尔列），不自写 `@SQLDelete` 加 `@SQLRestriction` 组合；时间按语义选型：绝对时刻用 `Instant` / `OffsetDateTime`（PostgreSQL `timestamptz`），业务日期用 `LocalDate`（`date`），不带时区的业务本地时间才用 `LocalDateTime`（`timestamp without time zone`）并明确所属业务时区；`timestamptz` 不保留原始时区标识，业务需要重现用户原始时区（如按用户本地时区展示）时另存 zone ID 列。不混用 `Date`；数据库列名一律 snake_case 命名，Java camelCase 字段通过 `@Column` 或等价注解显式映射，禁止依赖隐式命名策略。
- 同一组审计字段只在公共基类声明一次：多个类重复声明同一审计字段时抽取公共基类，业务类继承取得，不在各类重复声明；JPA 承载写法见 spring-guide「JPA 数据访问」。
- 主键策略（如雪花 ID）由项目/采用方统一后不混用其他方案；新项目未确立时先与团队确认，不擅自定方案。
- 列表查询必须分页，不执行无边界全量查询；SQL 参数一律预编译占位符，不拼接。

## 缓存与 Redis

- 任意 Redis key 写入必须带过期时间：字符串写入带 EX/PX，集合与结构类写入后补 expire 约定 TTL；清理一律靠过期，不做人工清理任务。分布式锁持有租约 TTL 与续期机制显式设计，不出现永不过期的 key；确需长期驻留的键先确认其属于可再生成数据并记录理由。
- Redis 是可丢弃的缓存与临时状态承载，不是数据真相：业务真相在 PostgreSQL，缓存不可用或缺失时回源数据库即恢复正确；需要持久保存的数据落库。
- Redis 实例不开启持久化（RDB/AOF 均关闭），代码不得依赖重启后仍存在的数据；实例或进程重启后的数据丢失不构成业务影响。
- 业务不强依赖 Redis：应用可独立于 Redis 启动（惰性连接）；运行中 Redis 不可用时，缓存类功能降级回源继续服务，借 Redis 表达的互斥、幂等等语义按安全侧失败（拒绝执行或显式排队，不放行并发），不出现数据错误；降级路径与受影响功能在设计阶段写明。调度防重等强协调优先用 PostgreSQL 或任务框架自带机制，不依赖 Redis 状态。

## 测试

- 业务逻辑与行为改动必须写测试；测试分层、覆盖率口径、必测场景、测试代码写法与替身规则统一按本 skill SKILL.md「测试」分节（后端条款见 [backend-testing.md](backend-testing.md)）执行，本文不重复展开。
- 使用项目现有测试工具栈，不为规范而更换框架；测试随产品代码同一变更提交，未实际运行不声称通过。

## 配置与运行期约束

- 敏感配置（密钥、令牌、连接串）统一走环境变量或配置中心，不提交仓库、不硬编码；多环境差异用框架 profile 机制管理（Spring 见 spring-guide.md）。
- CI 合并前检查点（编译、lint、单测、覆盖率、依赖安全扫描如 OWASP dependency-check）全绿后合并；静态分析用 SpotBugs/SonarQube，以项目既有流水线为准，不为规范而重建流水线。
- 发布版本遵循语义化版本 `vMAJOR.MINOR.PATCH`，产物含 commit 溯源信息；分支模型与主分支保护按 mv-git-publisher 团队 Git 基线执行：默认分支 `main`、日常开发在 `dev` 分支（开发提交不直接落 `main`）、线性提交历史、禁止 merge commit 与强制推送。
- 运行期行为必须明确并文档化：schema 策略（如 create-drop 仅限临时环境，生产禁止自动重建）、惰性依赖（应用可独立于缓存/MQ 启动，依赖宕机时的失败范围）、调度任务周期与数据保留策略、重启后恢复运行态资源。

## 交付自查清单

变更交付前按任务及其直接影响范围逐项确认；与项目实际基线冲突时以项目为准。清单不要求未修改的代码追溯达标，兼容性导致未应用的条款说明原因；历史问题与本次新增问题分别报告：

- [ ] 无魔法值，命名合规（角色后缀词表、查询动词分级），equals/hashCode 成对覆盖，Javadoc 完整
- [ ] 本次变更按 [readability-refactoring.md](readability-refactoring.md) 修剪：结构信号逐条判定，修剪点与未修剪原因已记录
- [ ] 无未使用的 import、无本次新增的多余代码块/类、无注释掉的旧实现
- [ ] 集合与并发合规：toArray、Iterator 删除、entrySet、ThreadPoolExecutor 显式建池、ThreadLocal 用后 remove
- [ ] 异常未用于流程控制，finally 无 return，无空 catch；日志 SLF4J 占位符，无敏感信息与 System.out
- [ ] 分层单向依赖，无跨层调用与循环依赖；业务数据 POJO 化，无 Map/JsonNode 替代，无承载业务语义的内部类
- [ ] 枚举字段全链路枚举类型；错误码一场景一码，`code` 等于枚举常量名、全集唯一且有扫描校验；用户可见文案走国际化资源
- [ ] 角色权限走 RBAC：功能权限点在入口层统一校验，Service 校验资源归属与数据范围；前后端共用权限点标识，权限点/菜单为种子数据、无运行时管理入口
- [ ] 配置类型化绑定、kebab-case，配置项全部定义在配置文件（优先 YAML），含连字符 key 的环境变量用属性占位符显式声明、默认值不进代码、无 `@Value`，敏感配置外置
- [ ] 审计字段、时间类型、分页、SQL 参数化符合项目基线；REST 动词/URL/载体校验/统一响应/响应载体脱敏合规
- [ ] 新增或改口径的字段：库层约束、后端校验、前端校验三处同口径落地，变换字段有映射记录，各层校验测试已补
- [ ] 可运行服务暴露 readiness/liveness 双探针：liveness 不聚合外部依赖，readiness 聚合关键依赖并作为部署门禁探活地址
- [ ] schema 全量版本化（空库一键拉起、脚本只追加、生产 migrate 与启动解耦），大表 DDL 走在线路径并设锁等待超时，应用与上一版 schema 兼容
- [ ] 按项目框架并读对应指南（Spring Boot、持久层）条款后自查
- [ ] 外部调用与外部数据：响应/回调/消息先校验再用，超时与重试幂等明确，未用外部成功标志替代本方确认
- [ ] 业务逻辑与行为改动有对应单元测试，覆盖正常/边界/异常路径，覆盖率达标，CI 全绿
- [ ] 运行期约束（schema 策略、惰性依赖、调度、启动恢复）已文档化
