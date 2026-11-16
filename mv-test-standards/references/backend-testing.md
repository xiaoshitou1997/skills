# 后端测试写法

后端测试代码条款，配合 mv-test-standards「关键规则」使用；团队基线 Spring Boot + JDK 21，Spring 与 JPA 专属条款见 mv-backend-standards 的 spring-guide。与项目已确立测试基线冲突时以项目为准。

## 单元测试

- 测试框架用项目既有栈（基线 JUnit 5 + Mockito + AssertJ 断言），不为统一而更换。
- 一个测试类对应一个被测单元，命名 `<被测单元>Test`；测试方法名表达场景与预期（`createUser_duplicateEmail_throwsException` 一类），或用 `@DisplayName` 中文描述场景。
- 断言用 AssertJ 链式断言，异常路径用 `assertThatThrownBy` 断言异常类型与业务语义，不用 JUnit4 时代断言风格。
- 参数化场景（同一逻辑多组输入）用 `@ParameterizedTest`，不在一个测试方法里循环多组断言。
- 只测被测单元的对外行为，不锁内部实现细节（私有方法调用次数一类）；mock 只用于被测单元的直接协作者。

## Web 层切片测试

- Controller 用 `@WebMvcTest` 切片：只测参数校验、错误码映射、鉴权与序列化，Service 经替身注入；不通过 Web 层重复验证 Service 内部逻辑。
- Bean 注入替身用 `@MockitoBean`（Spring Boot 3.4+ 基线），不用已移除的 `@MockBean`。
- 响应断言落到包络结构（`code`/`message`/`data`）与错误码枚举值，不只断言 HTTP 200。

## 集成测试（Testcontainers）

- 持久层与事务链路用真实数据库验证：Testcontainers 起 PostgreSQL 容器（团队基线库），容器随测试会话复用，不为每个用例重启容器。
- schema 经版本化迁移脚本建立（Flyway/Liquibase 随应用启动执行），集成测试不手工建表、不用 `ddl-auto` 生成生产 schema。
- 集成测试入口按范围选切片：持久层 `@DataJpaTest` + Testcontainers；跨层业务回环用 `@SpringBootTest` + 随机端口（`WebEnvironment.RANDOM_PORT`），经真实 HTTP 客户端从入口请求到数据库回环验证。
- 用例内自建自清数据：前置数据经被测 API 或仓储构造，清理按用例隔离（事务回滚或显式删除），用例间不依赖执行顺序；不共享可变夹具实例。
- 涉及认证上下文的集成测试设置真实主体对象，不用静态 mock 替代认证链路。
- 中间件集成（Redis、RabbitMQ）同样经 Testcontainers 起真实实例；网络协议与外部交互用真实客户端做回环验证，端口动态分配避免冲突。

## 外部依赖替身

- HTTP 外部依赖用 WireMock 一类 HTTP 桩：按契约模拟响应结构与超时、失败路径，不 mock 项目内部的 HTTP 客户端封装类。
- 时间敏感逻辑注入 `Clock`，测试构造固定时刻；轮询场景在测试内断言状态而非 sleep 等待。
- 测试专属配置经测试 profile 注入，不修改生产配置文件。

## 覆盖率与执行

- 覆盖率统计经构建工具覆盖率插件（Maven 常用 JaCoCo）产出，口径与门槛按 mv-test-standards 关键规则第 5 条；门槛以项目 CI 实际配置为准，项目未配置时先与团队确立。
- 异步任务验证最终状态、失败记录与重试行为：覆盖处理器抛异常、部分完成场景，不只断言任务被接受。
- 变更回归范围依风险确定；未实际运行的测试不声称通过，执行命令与结果如实记录。

本文只管后端测试代码写法；产品代码写法归 mv-backend-standards，测试分层范围与覆盖率口径的裁决见 mv-test-standards 正文。
