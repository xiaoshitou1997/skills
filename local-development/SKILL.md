---
name: local-development
description: 用户要求在本地启动、停止、复现或调试 Java/Spring Boot、Node/Vue/React 应用，以及排查启动失败、端口冲突、热更新和接口联调问题时使用。可运行与调试目标相关的测试；单纯执行已有单元测试不需要完整启动流程。远程部署使用 docker-delivery。
---

# Local Development

## 适用意图与边界

“本地跑一下 / debug / 断点 / 热更新 / 本机联调”属于本 Skill；“部署到 dev/prod / 上线 / 发布服务器”属于 `docker-delivery`。允许使用 `mvn spring-boot:run` / `./gradlew bootRun` / `npm run dev` / `pnpm dev` 或 IDE Run/Attach。

## 工作流

1. 检查项目、README、wrapper、包管理器、运行参数和现有占用端口；默认只启动用户目标组件，不改变仓库或系统配置。
2. 版本不满足时使用 `toolchain-manager`；用户可能希望 Docker Compose 启动 DB/Redis 等本地依赖，但**绝不**默认连生产数据库或对生产数据做写操作。
3. 只加载 `.env.local` 或项目已允许的开发环境设置；不自动复用 `.env.prod`、密钥或服务器配置。若需新增 local 配置，先检查 `.gitignore`。
4. Java 优先现有 Maven/Gradle Wrapper；如果 IDE 调试，以项目 JDK 和启动配置为准。输出可复制的 JDWP/IDE attach 配置时，仅绑定 `127.0.0.1` 或通过安全隧道访问；不暴露对公网的 Debug 端口。
5. Node 前端按 lockfile / `packageManager` 选择 npm/pnpm/yarn；优先项目定义的 `dev` 脚本。确认 API 请求目标为本地/dev，不应误发到 prod。
6. 启动后确认进程、监听端口、可用的 health endpoint；调试失败先复现、缩小范围、保留关键日志并建议最小修改。
7. 单元测试与本地集成测试按变更影响范围运行，记录实际执行命令与结果；**不**暗示完整 CI 已通过。
8. 记录本次启动的进程/容器标识、命令、工作目录与日志路径；停止前重新核对标识，优先正常停止，只清理本次创建的资源。端口占用者不是本次启动的进程时，报告冲突并选择其他端口或征求用户决定。

## 与项目流程配合

遵循项目已有任务、测试与调试流程；本 skill 只提供运行、调试与验证指导，不另建计划系统或持久化工作流。

## 排障证据与验证边界

- 对机制问题沿“配置读取 → 业务传递 → 框架/依赖消费 → 实际副作用”追踪。结论附关键文件与行号；依赖行为优先查当前版本源码，必要时检查本地 JAR 字节码，不用通用知识补成已证实结论。
- 使用同一请求的 requestId/traceId 串联入口、业务日志和下游调用。没有 SQL 日志只能作为排查线索，需结合日志配置与代码确认是否在校验层失败。
- 区分编译、单元测试、mock 运行时联调和真实依赖联调；每项记录实际输入、命令及结果。使用签名桩或手工 classpath 的验证只覆盖该范围，不等同于项目完整构建、依赖解析或 CI。
- 验证业务功能时检查入口、权限、状态变更、持久化、下游动作和查询展示；有表、字段、按钮或成功响应不等于闭环完成。已有数据上的验证采用“操作前基线 + 本次增量”断言，并确认重复执行的影响。
- 先核对真实请求契约，包括认证处理、Origin、响应码类型、分页字段和模式限制；不要因测试客户端假设错误而判定服务故障。
- 已用最小复现确认环境阻塞后，切换已验证的可用通道，避免反复试同类参数；有 DLP/EDR 证据时使用 `windows-dlp-environment`。

## 安全要点

- 禁止以开发命令冒充 dev/prod 部署成功。
- 禁止生产 Debug Agent、明文输出 secret、无确认修改数据库 schema。
- 不需要安装工具时不触发 `toolchain-manager`，避免无谓的工具链准备。

## 结束报告

输出启动命令、运行地址、进程或容器标识、日志位置、测试执行结果、已知问题和清理方式。

## 可复用的验证工具

从加载的 SKILL.md 定位实际 skill 目录并赋给 `SKILL_ROOT`，此变量不会保证自动设置。工作目录保持为用户项目，Python 3 命令按环境选择 `python3`、`python` 或 `py -3`。可运行 `python3 "${SKILL_ROOT}/scripts/doctor.py" --project .` 检查环境；代码就绪后运行 `bash "${SKILL_ROOT}/scripts/quality-check.sh" quick` 或 `full`。优先遵循项目已有命令，记录实际执行结果，不替代 CI。
