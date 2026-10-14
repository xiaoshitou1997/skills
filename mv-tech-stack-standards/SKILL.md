---
name: mv-tech-stack-standards
description: 新建项目技术选型、确定或调整项目技术栈基线、评估依赖引入与版本升级、盘点项目现有技术栈时使用；存量项目沿用现状优先，基线仅约束新项目与新增依赖。编写业务代码的规范归 mv-java-backend-standards，本机 JDK/Node 等工具链安装切换归 mv-toolchain-manager，构建出包与部署归 mv-wsl-build-deploy。
---

# Tech Stack Standards

## 作用与优先级

这是**规范型 Skill**，约束技术栈选型、基线维护与依赖演进决策；不负责编码规范、工具链安装、构建部署。优先级：用户明确需求和项目已正式采纳的规范 / ADR → 本规范 → 生态默认推荐。

存量项目友好核心原则：**基线只约束新项目与新增依赖**。存量项目沿用现状栈与版本，不因基线更新强制升级；盘点先于判断，先记录现状再谈改进；升级是独立决策，先评估影响面再列迁移计划，不搭车业务变更。

## 任务

1. 新项目选型：明确约束（团队熟悉度、运维能力、社区活跃度、License、性能要求）→ 从团队基线默认选起 → 偏离基线时记录理由 → 产出简版 ADR（模板见 [references/baseline-template.md](references/baseline-template.md)）。不为选新而选新；基线未覆盖的类别按同一决策流程补齐并与团队确认。
2. 存量项目盘点：从构建文件识别栈与版本锁定方式（Maven parent/BOM、Gradle version catalog/platform、package.json engines、.java-version、Dockerfile 基镜像等），记录现状；只盘点不评判，改判留待独立决策。
3. 依赖引入：版本对齐项目基线与既有依赖管理（BOM/version catalog），不在构建文件散落单点版本号；优先复用项目已用库的既有能力，引入新库说明理由、维护状态与退出成本；License 与安全基线核对后再进。
4. 版本升级：安全补丁与 LTS 优先；破坏性升级独立分支，先评估 API、依赖与数据迁移影响并列迁移与回滚计划；一次升级一件事，不与业务变更搭车；升级后按项目管线验证（出包、部署、回归）。

## 团队基线（2026-10 团队确认）

| 类别 | 基线 | 状态 | 说明 |
| --- | --- | --- | --- |
| Java 版本 | JDK 21（LTS） | 已确认 | 新项目默认；存量项目按现值 |
| 持久层 | 优先 JPA，其次原生 MyBatis | 已确认 | 禁止 MyBatis-Plus、tk-mapper；存量项目沿用维护，新项目与新模块不引入 |
| JSON 序列化 | Jackson | 已确认 | 禁止 fastjson、gson |
| 数据库（本地开发） | SQLite | 已确认 | 与远程方言不同，SQL 与迁移按环境区分 |
| 数据库（远程） | PostgreSQL | 已确认 | dev/prod 环境统一 |
| 缓存 | Redis | 已确认 |  |
| 分布式锁 | Redis | 已确认 | 与缓存共用设施 |
| 对象存储 | MinIO（S3 兼容 API） | 已确认 | 统一用 S3 兼容客户端接入 |
| 文件传输 | SFTPGo（SFTP） | 已确认 | 不使用明文 FTP |
| Java 框架 | Spring Boot 稳定版 | 待确认 | 框架条款见 mv-java-backend-standards |
| 构建工具 | Maven | 已确认 | 新项目默认 Maven，优先 wrapper（mvnw）锁版本；存量 Gradle 项目沿用 |
| 消息队列（MQ） | RabbitMQ | 已确认 | 其他中间件按需引入，先过「依赖引入」条款 |
| 前端 | Next.js（Node LTS） | 已确认 | 工具链安装见 mv-toolchain-manager |

## 输出

选型产出简版 ADR、盘点产出现状清单、升级产出迁移与回滚计划，均注明依赖来源与验证方式；基线偏离显式标注理由。不泛泛罗列技术对比。

## 边界

- 编码规范、分层与写法归 mv-java-backend-standards；本机工具链检测安装归 mv-toolchain-manager；构建出包与容器部署归 mv-wsl-build-deploy。
- 基线与项目实际冲突时项目优先；状态为「待确认」的行仅作占位建议，不作为阻断依据。
