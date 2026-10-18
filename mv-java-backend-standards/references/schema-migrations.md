# Schema 迁移与大表 DDL

适用于 Java 后端项目的 SQL 迁移管理与 schema 变更执行策略（Flyway/Liquibase 及等效 SQL 流程），与 [java-guide.md](java-guide.md)「数据库与事务」配套使用；执行通道与工具按项目实际设施选择，项目已采纳的流程优先。

## 执行通道

migrate 由流水线自动执行，人工只参与审批，不手工逐库执行 SQL；发布窗口不承担长 DDL。

| 环境 | migrate 执行方式 | 应用启动行为 |
|---|---|---|
| 开发/测试 | 随应用启动自动执行 | 正常启动 |
| 生产 | 发布流水线步骤或 init job 执行 | 仅 validate，不 migrate |
| 工单治理团队 | 变更平台（Bytebase/Archery 等）审批通过后自动执行 | 仅 validate |

## 脚本管理纪律

- 版本号按项目约定全局递增；同一版本脚本全环境只提交一份。
- 脚本一经任一环境应用即不可修改，修正以追加新脚本实现；改动已应用脚本会因校验和不一致使 validate 失败。
- 多库项目迁移按方言分目录（如 `db/migration/{vendor}`），方言专属 SQL 不进公共目录；种子/字典数据同样版本化，不靠手工导 dump 打底。

## 大表 DDL 判定

千万行级或预计执行超分钟级，先判定执行路径，再决定能否直接进迁移脚本：

1. 能走秒级/在线算法的显式声明算法，不兼容时快速失败，防静默降级成阻塞重建。
2. 执行前排查长事务，设小锁等待超时（MySQL `lock_wait_timeout`、PG `lock_timeout`），拿不到锁即失败重试，防锁排队堵死全表。
3. 预检（`EXPLAIN ALTER TABLE`、squawk 等 lint）只证明算法，不证明执行瞬间锁队列状态，第 2 步不可省。

### 方言等价写法

| 操作 | MySQL 8 | PostgreSQL | Oracle | SQL Server |
|---|---|---|---|---|
| 秒级加列 | `ALGORITHM=INSTANT` | 常量默认值即秒级（11+） | 天然元数据级 | 天然元数据级（2014+） |
| 在线建索引 | `ALGORITHM=INPLACE, LOCK=NONE` | `CREATE INDEX CONCURRENTLY`（迁移须关闭事务） | `CREATE INDEX ... ONLINE` | `WITH (ONLINE = ON)`（仅企业版） |
| 收紧约束 | 先回填再变更 | `NOT VALID` + `VALIDATE` 两步 | `NOVALIDATE` + `VALIDATE` | 新列+回填+切换 |
| 重建类兜底 | gh-ost / pt-osc | pg_repack / reshape | `DBMS_REDEFINITION` | expand–contract |

TiDB/OceanBase 原生在线 DDL，无需此类声明；MariaDB 兼容 `ALGORITHM` 语法但支持矩阵与 MySQL 有差异、且无 `EXPLAIN ALTER`，不照抄。

## 重建类变更

改列类型、加唯一约束、删列、字符集转换属重建类：用 gh-ost、pt-osc 等在线变更工具执行（可限速暂停、控主从延迟），migration 记 marker 标注版本；无在线工具条件时安排维护窗口，不在业务高峰直接执行。

## 回填与 expand–contract

- 回填按主键游标分批限速，不放单条大 UPDATE；加 `NOT NULL`/`UNIQUE` 前先回填并核实无冲突。
- expand–contract：新增列先可空/带默认（与在用版本兼容），回填或双写后切读，旧列延迟到后续版本删除；每步可与在用版本共存，schema 不依赖反向 DDL 回滚。

本页为执行策略参考，不替代项目既有变更流程与工单规范；工具选型（gh-ost/pt-osc/变更平台）以团队实际设施为准。
