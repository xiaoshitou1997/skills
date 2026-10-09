# 本机实测与可用路径

来源：本机项目记忆中的 2026-09-28 至 2026-10-09 实测。以下是本机观察，不是厂商保证；策略、进程来源、扩展名和目录变化后应做最小复验。不要保存账号密码或将历史项目路径当成当前路径。

## 读取与编辑

- 直接 Read/Grep 可能取得 `%TSD-Header` 密文；部分 Java/SQL 可经搜索工具取得明文，前端源码则可能仍是密文。先看实际结果，不反复对密文做文本操作。
- `git show HEAD:<path>` 可取得提交版本，但会漏掉未提交修改。读取当前工作区时，本机已验证 Git 的 `hash-object -w -- <path>` → `cat-file blob <hash>` 通道可取得明文，文本与 PNG 均曾成功；先用已知样本复验，并使用允许且可清理的临时对象库。
- 早期 node 能读源码的观察，不足以说明它能读所有产物。Java/Python 的成功也可能仅发生于写入窗口或缓存，不能当作稳定通道。
- 修改前取得完整明文和可恢复副本。本机 `sed -i` 的临时文件替换曾导致文件无法再读取；优先使用已验证的整文件写入方式或在可读临时文件中修改，再写回并回读。具体工具仍须符合当前 harness 的编辑要求。
- 编辑完成后检查实际编译器和下游读取视图；只看编辑工具显示的内容，可能漏掉端点回滚、文件复活或进程间视图差异。

## 写入与 WSL 暂存

- 2026-10-08/09 观察：Gradle/Java/IDE 写出的部分产物保持明文；cp、node、tar、Python 或 WSL 经 Windows 挂载盘写入时，受策略覆盖的文件可能重新加密。曾涉及 YAML、JS、HTML、JAR 等，不能据此认定所有扩展名的行为。
- 已解码内容优先流式送入允许使用的 WSL ext4 暂存目录，避免先落回受加密策略影响的 Windows 盘。二进制传输验证格式和摘要，分别检查生产者、WSL 与消费者退出码。
- Compose 直读 Windows 挂载盘上的密文曾报 YAML `invalid UTF-8 octet`；复制出的 JAR 被再加密后曾报 `Invalid or corrupt jarfile`。遇到这些错误先比较源文件、暂存文件与容器内文件视图。
- 2026-10-09 本仓复验：Windows 静态检查可读脚本，WSL 直读同一目录的部分 `.py`、`.sh` 却取得密文，分别报非 UTF-8 与 cannot execute binary file。早期“.sh 不加密”的记录不适用于这些文件；切换 shell 不等于完成文件解码。
- 当前工作区同步：先解包 HEAD 基线，再覆盖必要的 staged/unstaged/untracked 文件并处理删除；不能反过来用 archive 覆盖当前文件。排除秘密和缓存，确认最终树与预期一致。
- 本机曾遇到 CRLF/LF 不一致导致 `git apply` 失败，也出现过 check 与实际 apply 结果不一致。先定位换行与 Git 版本；必要时改为逐文件同步，不将“补丁永远不可用”写成规律。

## 构建通道与验证等级

- agent 派生 JVM 曾在 `Selector.open()` 最小探针失败，Gradle 报 `Unable to establish loopback connection`；`--no-daemon`、IPv4 参数等未解决。用户终端/IDE 与 WSL 容器构建曾可用，需分别验证进程来源。
- 证实上述阻塞后选择已验证的用户终端或容器通道，不继续堆叠同类 JVM 参数。`docker-delivery` 仍要求容器内编译，宿主出包属于另一条项目流程。
- `javac` 加缓存依赖、必要签名桩可作限定范围编译检查；JUnit console standalone 可执行目标测试。桩不能验证真实依赖行为，手工编译也不覆盖完整构建与 Checkstyle。
- classpath 需配套版本及传递依赖；不要简单取缓存里版本号最大的 JAR。Mockito inline 还需匹配的 byte-buddy 支持和被 mock 类型层级的依赖。
- TEMP argfile 在不同日期出现过失败与成功，不能固定断言 TEMP 可用或不可用；先验证当前解释器能读取，再使用允许的其他暂存目录。

## Shell 与 WSL 服务

- Git Bash 调用 `wsl.exe` 时只对该调用关闭 MSYS 路径转换；Windows 原生程序使用其可识别路径，WSL 使用 Linux 路径。显式设置命令工作目录。
- 本机外层 shell 曾提前展开内联 `$var`。复杂逻辑放脚本内，再从 WSL 执行；根据外层 shell 引用规则传参，而不认为所有变量都会被吞。
- WSL 服务集体停止时先查 `journalctl --list-boots` 与发行版生命周期，再查应用。曾观察到 systemd 服务不足以维持发行版活动，后台 `wsl -d <distro> -- sleep infinity` 可保活；使用时记录并清理该进程。
- mirrored 模式先查 Windows/WSL 共享端口占用、路由与 Hyper-V 防火墙；不自动杀掉已有开发进程或修改全局防火墙。k3s 重启后曾有 flannel 初始化延迟，应先看事件再重建 Pod。
- DNS/转发问题验证容器内解析和实际路由；本机 Kafka KRaft 在使用完整服务 FQDN 后解决过解析问题，不能推导所有部署必须同一命名方式。stdout 缺错误时检查应用自身日志。

## 更新这些观察

新结果记录日期、进程来源、目录/文件类型、最小复现和验证结果。新旧冲突时标出被覆盖的条件；参考文件只保留当前可执行路径和必要解释，不累积互相矛盾的操作指令。
