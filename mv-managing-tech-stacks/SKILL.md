---
name: mv-managing-tech-stacks
description: 新建项目技术选型、确定或调整项目技术栈基线、评估依赖引入与版本升级、盘点项目现有技术栈时使用；存量项目沿用现状优先，基线仅约束新项目与新增依赖。编写业务代码的规范归 mv-writing-java-backends，本机 JDK/Node 等工具链安装切换归 mv-managing-toolchains，构建出包与部署归 mv-delivering-containers。
---

# Managing Tech Stacks

## 作用与优先级

这是**规范型 Skill**，约束技术栈选型、基线维护与依赖演进决策。优先级：用户明确需求和项目已采纳的规范 / ADR → 本规范 → 生态默认推荐。

基线只约束新项目与新增依赖：存量项目沿用现状栈与版本，不因基线强制升级；升级是独立决策，先评估影响面再列迁移计划，不搭车业务变更。

## 团队基线

| 类别 | 基线 | 说明 |
| --- | --- | --- |
| Java 版本 | JDK 21（LTS） | 存量项目按现值 |
| Java 框架 | Spring Boot 3.5.x | 框架条款见 mv-writing-java-backends |
| 构建工具 | Maven | 优先 mvnw 锁版本；存量 Gradle 项目沿用 |
| 持久层 | JPA 优先，其次原生 MyBatis | 禁止 MyBatis-Plus、tk-mapper；存量项目沿用维护，新项目与新模块不引入 |
| JSON 序列化 | Jackson | 禁止 fastjson、gson |
| 数据库 | PostgreSQL | dev/prod 统一，开发联调直连远程 |
| SQLite | 仅限单测、临时验证 | 不作开发联调库，无双方言兼容要求 |
| 缓存与分布式锁 | Redis | 共用设施 |
| 消息队列 | RabbitMQ | 其他中间件按需引入，先过「依赖引入」 |
| 对象存储 | MinIO（S3 兼容） | 统一用 S3 兼容客户端接入 |
| 文件传输 | SFTPGo（SFTP） | 不使用明文 FTP |
| 前端 | Next.js（Node LTS） | 工具链安装见 mv-managing-toolchains |

新项目从基线默认选起，偏离基线记录理由并产出简版 ADR；选型决策要点与 ADR 模板见 [references/baseline-template.md](references/baseline-template.md)，基线未覆盖的类别按同一流程补齐。

## 依赖引入与升级

- 新增依赖版本对齐项目既有依赖管理（BOM / version catalog），不在构建文件散落单点版本号；优先复用已用库的既有能力，引入新库说明理由、维护状态与退出成本，License 与安全核对后再进。
- 升级安全补丁与 LTS 优先；破坏性升级独立分支，先评估 API、依赖与数据迁移影响并列迁移与回滚计划；升级后按项目管线验证（出包、部署、回归）。

## 输出

选型产出简版 ADR，盘点产出现状清单，升级产出迁移与回滚计划；基线偏离显式标注理由。

## 边界

编码规范、分层与写法归 mv-writing-java-backends；本机工具链检测安装归 mv-managing-toolchains；构建出包与容器部署归 mv-delivering-containers；基线与项目实际冲突时项目优先。
