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

## 团队基线（示例，待团队确认）

下表数值为**示例**，用于占位与演示格式；逐项经团队确认后固化，未确认前仅作新项目默认建议，不作为阻断依据。

| 类别 | 示例基线 | 说明 |
| --- | --- | --- |
| Java 版本 | 最新 LTS（示例：JDK 21） | 新项目取 LTS；存量项目按项目现值 |
| Java 框架 | Spring Boot 稳定版 | 框架条款见 mv-java-backend-standards |
| 持久层 | 按项目（MyBatis-Plus / JPA 均可） | 同一项目不混用方案 |
| 构建工具 | Gradle 或 Maven，按项目 | 优先 wrapper 锁版本 |
| 数据库 | MySQL / PostgreSQL | 版本随项目运行环境 |
| 中间件 | 按项目按需引入（缓存、MQ 等） | 引入前过「依赖引入」条款 |
| 前端 | 按项目（Node LTS + 团队选定框架） | 工具链安装见 mv-toolchain-manager |

## 输出

选型产出简版 ADR、盘点产出现状清单、升级产出迁移与回滚计划，均注明依赖来源与验证方式；基线偏离显式标注理由。不泛泛罗列技术对比。

## 边界

- 编码规范、分层与写法归 mv-java-backend-standards；本机工具链检测安装归 mv-toolchain-manager；构建出包与容器部署归 mv-wsl-build-deploy。
- 基线与项目实际冲突时项目优先；「示例」标注未去除的基线值不作为阻断依据。
