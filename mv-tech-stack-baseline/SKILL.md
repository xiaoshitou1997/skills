---
name: mv-tech-stack-baseline
description: 新建项目技术选型、确定或调整项目技术栈基线、评估依赖引入与版本升级、盘点项目现有技术栈时使用。编写业务代码的规范归 mv-java-backend-standards，版本对应的本机安装切换归 mv-toolchain-manager。
---

# 技术栈基线

## 作用与优先级

这是**基线型 Skill**，约束技术栈选型、基线维护与依赖演进决策。优先级：用户明确需求和项目已采纳的规范 / ADR → 本基线 → 生态默认推荐。

升级是独立决策，先评估影响面再列迁移计划，不搭车业务变更。

## 团队基线

| 类别 | 基线 | 说明 |
| --- | --- | --- |
| Java 版本 | JDK 21（LTS） |  |
| Java 框架 | Spring Boot 3.5.x | 框架条款见 mv-java-backend-standards |
| 构建工具 | Maven | 优先 mvnw 锁版本 |
| 镜像基线 | 基镜像 eclipse-temurin:21-jre、非 root 用户 10001、端口 8080 | 各栈 Dockerfile.delivery 基线，镜像定义随模块，编排见 mv-image-builder |
| 持久层 | JPA | 禁止 MyBatis/MyBatis-Plus、tk-mapper |
| JSON 序列化 | Jackson | 禁止 fastjson、gson |
| 统一响应包络 | code/message/data 三段：code 为业务错误码枚举（一场景一码）；message 走 i18n messageKey；data 为强类型 VO | 新项目默认；项目既有包络优先；存量接口不擅自改造；HTTP 状态码保持语义，不一律 200 |
| 工具类库 | JDK 标准库、Spring 自带工具类与 Apache Commons | 禁止 Hutool |
| HTTP 客户端 | Spring 应用用 RestClient：优先声明式调用（Spring HTTP Interface，引擎仍是 RestClient），必须编程实现时才用编程式 RestClient；非 Spring 场景用 JDK 原生 HttpClient | 不用 RestTemplate（维护模式）；WebClient 仅响应式栈；不引 OpenFeign、Retrofit |
| 第三方平台 SDK | 平台专属 SDK 默认不引：RestClient 直连 + 签名/验签自封装；行业标准协议的事实标准客户端放行（S3、SFTP、SMTP 等） | 试金石：换同类供应商客户端要不要跟着换；自封装签名配单测，平台测试环境联调验签通过为完成门；真引入才写 ADR 并加防腐层 |
| 数据库 | PostgreSQL | dev/prod 统一，开发联调直连远程 |
| SQLite | 仅限单测、临时验证 | 不作开发联调库，无双方言兼容要求 |
| 缓存与分布式锁 | Redis | 共用设施 |
| 消息队列 | RabbitMQ | 其他中间件按需引入，先过「依赖引入」 |
| 对象存储 | RustFS（S3 兼容） | 统一用 S3 兼容客户端接入 |
| 文件传输 | SFTPGo（SFTP） | 不使用明文 FTP |
| AI 能力接入 | magpie 网关 | `baseUrl` `http://127.0.0.1:3425/v1`、`apiKey` `magpie`，不向用户另行索取；用户或项目文档明确给出其他连接信息时以所给为准 |
| LLM 应用框架 | Spring AI | 不引入 Spring AI Alibaba；模型接线统一用 OpenAI 兼容 starter（`spring-ai-starter-model-openai`），不引入 provider 专属 starter/SDK，不自研 HTTP 客户端直连模型 API；换模型只改配置 |
| 前端 | Next.js（Node LTS） | 工具链安装见 mv-toolchain-manager，编码规范见 mv-nextjs-frontend-standards |

新项目从基线默认选起，偏离基线记录理由并产出简版 ADR；选型决策要点与 ADR 模板见 [references/baseline-template.md](references/baseline-template.md)，基线未覆盖的类别按同一流程补齐。

## 依赖引入与升级

- 新增依赖版本对齐项目既有依赖管理（BOM / version catalog），不在构建文件散落单点版本号；优先复用已用库的既有能力，引入新库说明理由、维护状态与退出成本，License 与安全核对后再进。
- 升级安全补丁与 LTS 优先；破坏性升级独立分支，先评估 API、依赖与数据迁移影响并列迁移与回滚计划；升级后按项目管线验证（出包、部署、回归）。

## 输出

选型产出简版 ADR，盘点产出现状清单，升级产出迁移与回滚计划；基线偏离显式标注理由。

## 边界

编码规范、分层与写法归 mv-java-backend-standards（后端）与 mv-nextjs-frontend-standards（前端）；本机工具链检测安装归 mv-toolchain-manager；构建出包与镜像归 mv-image-builder，容器部署归 mv-container-deploy；基线与项目实际冲突时项目优先。
