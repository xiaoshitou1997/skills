# 运维操作手册

mv-ops-standards 关键规则的落地做法：日志轮转、指标暴露、备份与恢复演练、巡检清单。命令样例按团队部署形态（服务器侧 Docker Compose、经 SSH 访问）书写。

## 日志轮转

- 应用侧落盘日志（logback 样例）按大小与时间双触发轮转并压缩，保留窗口按磁盘预算定：

```xml
<rollingPolicy class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
  <fileNamePattern>logs/app.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
  <maxFileSize>50MB</maxFileSize>
  <maxHistory>14</maxHistory>
  <totalSizeCap>2GB</totalSizeCap>
</rollingPolicy>
```

- 容器编排侧采集：日志走 stdout 时用 `docker compose logs --since` 回溯，不进容器内翻文件；排障动作经 SSH 执行，宿主不装 Docker。

## 指标暴露

- 依赖与端点：`spring-boot-starter-actuator` + `micrometer-registry-prometheus`，`management.endpoints.web.exposure.include` 最小化放开（health、prometheus）；`/actuator/prometheus` 不公网开放，经内网或网关侧采集。
- 最小指标集核对：JVM（内存、GC 暂停）、HTTP（`http.server.requests` 量与耗时分位）、连接池（HikariCP active/idle）、RabbitMQ 队列深度；业务关键计数（如支付回调量）按需补充自定义 Counter。

## 备份与恢复演练

- PostgreSQL 定时备份在目标机执行并通过 SSH 管理：`docker exec` 不分配 TTY，以 `pg_dump -Fc` 写入同目录临时文件；检查导出退出码，并用兼容版本的 `pg_restore --list` 检查归档目录。两步均成功后才原子重命名为正式备份，失败则保留失败记录并告警，不将临时文件视为有效备份。归档目录检查不能替代实际恢复演练。

- 留存策略：保留 ≥7 份日备 + ≥4 份周备；至少一份同步到目标机之外（对象存储或另一台机器），同步失败按备份失败告警。
- 恢复演练每季度至少一次：在隔离环境恢复最近一份备份，验证「库可启动、核心表行数、关键业务记录抽查」三步，演练记录归档。
- 对象存储（RustFS）桶与 `~/.mv/` 状态目录按同一策略纳入备份范围。

## 巡检清单

prod 固定周期巡检逐项核对并记录：

- [ ] readiness/liveness 健康（`FF_HEALTH_URL` 端点 UP）
- [ ] 容器状态与近期重启次数（`docker compose ps`，非预期重启按告警判据升级）
- [ ] 磁盘水位（数据卷与备份目录 <80%）
- [ ] 昨日备份文件存在且大小正常、异地副本同步成功
- [ ] error 日志速率与昨日基线对比无突增
- [ ] 证书与镜像老化：基础镜像有可用更新或新增 HIGH/CRITICAL 漏洞时登记升级窗口

本文是运维做法样例；部署动作与失败回滚归 mv-container-deploy，产品代码内的健康端点与日志配置规范归 mv-backend-standards。
