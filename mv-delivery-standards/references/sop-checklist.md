# 新增栈 SOP 与部署后校验

SKILL.md「Compose 编排」关键规则 14 的展开：新增栈按序执行的操作步骤与部署后校验清单。

## 新增栈 SOP

按序执行，每步引用对应规则：

1. 建目录：`{栈名}/`，栈名按命名规则（小写 DNS-1123、官方连字符保留、环境后缀入栈名）。
2. 套模板：以 SKILL.md 关键规则 8 的键序为骨架整理。
3. 定网络：声明 `networks.default.name: {栈名}-net`；跨栈通信逐连接走网络判定，仅访问宿主机进程才加 `extra_hosts`。
4. 定端口：逐服务走端口判定步骤。
5. 定镜像：固定具体版本；过 Alpine 兼容性判定；晋级时核对已验证镜像身份，记录环境间暂时的版本差异。
6. 生成凭证：按凭证分级表选类型与命令生成，写入 `{栈名}/.env`；`db_user = db_name` 取栈名去连字符形式；确认 `.env` 已被 .gitignore 排除。
7. 定数据卷：判定 `-data`/`-home` 与命名卷/bind。
8. 定 healthcheck：走探针判定树；被依赖服务无探针时依赖方用 `service_started`。
9. 定依赖与重启：`depends_on` + condition；每服务 `restart: unless-stopped`（初始化容器除外）。
10. 资源与日志：按限额表配 `deploy.resources`；套 logging 限额。
11. 整理 YAML：键序、environment map、按需声明与分块、删除多余注释；逐 service 复核。
12. 部署：`cd {栈名} && docker compose up -d`。
13. 首启回填：观察 `docker inspect --format='{{.State.Health.Log}}' {容器名}`，按实测回填 start_period。
14. 写栈级 README：「定位」与「官方资料」（官方文档入口 + 镜像）两节必写；config 说明列出实际启用的环境变量及注入来源；排障要点至少覆盖启动失败、健康检查不过、凭据缺失三类通用项与本栈特有坑。

## 部署后校验清单

| 检查项 | 验证方式 |
|---|---|
| 栈名形态合规 | `ls -d */ \| grep -vE '^[a-z0-9]+(-[a-z0-9]+)*/$'` 应无输出 |
| 无 latest / main / 无标签镜像 | `grep -rnE 'image:.*(latest\|main)\s*$' */docker-compose.yaml` 无输出；无标签镜像输出人工复核 |
| restart / logging / resources 三件套 | `grep -rL 'restart:'`、`grep -rL 'max-size'`、`grep -rL 'cpus'` 均无输出 |
| 无 TCP / 根路径探针 | `grep -rn '/dev/tcp\|nc -z' */docker-compose.yaml` 无输出；根路径探针作唯一手段的人工复核 |
| compose 无明文凭据 | `grep -rnE '(PASSWORD\|SECRET\|_KEY\|TOKEN):' */docker-compose.yaml \| grep -v '\${'` 输出仅允许空值/占位符 |
| env 文件未入库 | `git ls-files` 无 `.env`、secrets 目录条目 |
| start_period 已实测回填 | `docker inspect --format='{{.State.Health.Log}}' {容器名}` 与配置值比对 |
| 键序与写法 | 人工比对 YAML 写法节（service 键序、顶层键序、environment map） |
| 端口符合判定步骤 | 逐服务对照端口判定复核，偏离项有行内注释 |
| 环境变量按需声明且分块 | 人工复核：无未使用的默认值变量、跨关注点 env 按功能分块、变量后无行内注释 |
| 数据卷形态合规 | bind 挂载逐条对照两类例外，其余应为命名卷 |

本文是操作展开；自研应用交付的部署入口见 SKILL.md 容器交付节（当前关闭），部署后巡检与备份演练归 mv-ops-standards。
