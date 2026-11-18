# 资源限额与日志轮转

SKILL.md「Compose 编排」关键规则 12 的展开：资源上限表与 logging 参数。所有服务必须配置，不区分开发/生产。

## 资源限额

防止单服务耗尽宿主机 CPU / 内存，影响同机其他服务。参数按服务类型取值（同类型服务全站一致）：

| 服务类型 | 内存上限 | CPU 上限 |
|---|---|---|
| 轻量中间件（redis 类） | 256m | 0.5 |
| 轻量中间件（对象存储、sftpgo、portainer、nginx 类） | 512m | 0.5-1.0 |
| 数据库（mysql、mariadb、postgres 类） | 1g | 1.0 |
| Go / Node / Python 应用 | 1g | 1.0-2.0 |
| Java 应用（Spring Boot） | 1g-4g | 1.0-2.0 |
| LLM 推理 | 8g+（按模型调） | 2.0 |
| Agent 运行时（含浏览器自动化） | 4g | 2.0 |

```yaml
deploy:
  resources:
    limits:
      cpus: "1.0"
      memory: 1G
```

实际负载偏离表值时在该服务 deploy 块行内注释写明原因，无注释偏离视为违规。

## 日志轮转

compose 默认 json-file 驱动无上限，容器日志会无限增长直至占满磁盘。每个服务统一配置：

```yaml
logging:
  driver: json-file
  options:
    max-size: "10m"
    max-file: "3"
```

- 单服务日志上限 = `max-size` × `max-file` = 30m。
- 排障需要更多历史时临时调大该服务的 `max-file`，不全局放宽。

本文只管编排侧限额与轮转；应用内日志规范（SLF4J、落盘轮转）归 mv-coding-standards，运行期巡检含日志速率核查归 mv-ops-standards。
