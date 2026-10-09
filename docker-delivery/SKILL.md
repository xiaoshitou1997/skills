---
name: docker-delivery
description: 构建 Docker 应用镜像、通过 Docker Compose 部署开发或生产环境、检查容器健康、晋级同一镜像或回滚应用时使用。自带模板支持 Maven/Gradle Java 可执行 JAR 和 Node 静态前端；多服务及其他技术栈使用项目自备 Dockerfile/Compose。普通本地启动调试使用 local-development。
---

# Docker Delivery

## 职责

将代码通过**容器内编译**生成可追溯、跨环境复用的版本镜像，再沿相同流程交付至 dev 或 prod：`detect → build → package image → transfer/load → compose up → verify → record/recover`。

- `local-development` 负责本地 Debug；这里不使用 `mvn`、`gradle`、`npm` 等宿主编译命令。
- 与 Spec Kit `implement` 兼容，但不重写需求规划、测试编排或版本管理；与 Git 独立，不暗中 commit。
- dev 默认本地 Docker（Windows 可以在 WSL 环境运行），设置 `FF_DEV_SSH` 后为开发服务器；prod 只能明确指定 SSH 目标。
- 默认使用 Docker save/load 复用同一镜像，后续可替换 Registry；切换环境绝不重新生成不同编译结果。

## 交付前检查

1. 判断用户意图："本地调试"转 `local-development`；"部署 dev" 用 dev；"上生产"只在用户明确授权后选择 prod。不因含糊的“跑起来”自动操作 prod。
2. 查看项目 `Dockerfile.delivery`、Maven/Gradle Wrapper、Node lockfile、`.dockerignore`、`compose.delivery.yml`、`.env.<env>`。如果用户自有规范优先，其次使用 `templates/` 中适配技术栈的多阶段模板。
3. 构建必须在 Docker 完成，不允许把 `.env.prod`、私钥、`.git` 纳入构建上下文。提交前需确保 env 不在 Git 跟踪之下；注意 `.dockerignore` 的排除规则和取反规则。
4. 检查 Java/Node 版本、前端环境变量是否在编译期固化。若前端 Vite 构建期嵌入不同 API 地址，不能宣称跨环境同一镜像，必须改为相对路径或运行时配置注入，或明确例外。
5. 构建验证失败则不进入部署步骤；生产还需要确认 dev 已验证的镜像 ID/Tag、备份/回滚预案及业务变更影响。数据库迁移必须单独审批，不随 Docker 回滚自动执行。
6. 构建当前工作区时，明确 staged、unstaged、untracked 和删除项的范围；`git archive HEAD` 只代表提交快照。需要叠加变更时先解包基线，再应用当前文件及删除项，避免后续基线覆盖新内容。检查忽略规则、凭据和依赖文件，并如实记录输入不是纯 Git SHA。

## 工具入口

从本次加载的 `SKILL.md` 路径确定 skill 目录，将其实际绝对路径赋给 `SKILL_ROOT`。这只是文档中的路径变量，agent 不一定自动提供它。路径始终加引号；工作目录保持为用户应用仓库。

```bash
# 用户的应用仓库根目录
bash "${SKILL_ROOT}/scripts/deliver.sh" build dev app-name
# build 输出唯一镜像 TAG；保存它并在后续部署复用
bash "${SKILL_ROOT}/scripts/deliver.sh" deploy dev app-name app-name:TAG
bash "${SKILL_ROOT}/scripts/deliver.sh" status dev app-name
# 必须先获得用户明确生产授权，验证同一镜像可用后才执行
bash "${SKILL_ROOT}/scripts/deliver.sh" deploy prod app-name app-name:TAG --approve-prod
bash "${SKILL_ROOT}/scripts/deliver.sh" rollback prod app-name --approve-prod
```

- 如果 Dockerfile 与 Compose 过于复杂，可选择严格遵循同一环境契约的项目内自有 CI/CD 工具；但不得偷偷换成宿主编译。
- `status` 只读。`rollback` 仅还原上一已验证镜像，**不**触碰数据库及外部状态。
- `--approve-prod` 只是额外的脚本保护，不能代替用户对真实生产操作的授权。脚本不自动持有服务器凭证。

## 环境契约

读取 [references/configuration.md](references/configuration.md)；准备 `.env.dev` 或 `.env.prod`、SSH 和 Compose 项目描述。项目自行管理环境端点与 Secrets。

## 验收报告

输出 Git SHA/构建输入状态、完整镜像 Tag 与 Image ID、目标环境、部署位置、Compose 状态、探活方式与结果、回滚到的上个版本、未验证的风险。没有真实构建/SSH 时要明确写出未执行，不可虚构成功。

将镜像构建、容器健康、经网关访问和业务联调分别报告。入口验证应按真实鉴权、Origin 和响应契约执行，并确认目标实例与依赖；共享服务注册中心可能将请求路由到其他实例，不能仅凭成功响应断言本次部署已验证。仅 mock 联调通过时明确外部系统尚未验证。

## 发布门禁与工程工具

- 本地预检：`bash "${SKILL_ROOT}/scripts/deploy-preflight.sh" dev APP` 或 `prod APP`。检查 Docker、env 跟踪和构建上下文。
- 自检：`python3 "${SKILL_ROOT}/scripts/doctor.py" --project .`，使用本机可用的 Python 3 命令；这是信息诊断，不构成发布门禁。
- 安全扫描：`bash "${SKILL_ROOT}/scripts/security-scan.sh" source .` 用已有 Gitleaks；`FF_REQUIRE_SECURITY_SCAN=1` 后镜像构建要求已有 Trivy，缺失则失败。缺扫描器不能宣称扫描通过。
- dev 交付成功后记录当前 Image ID 的验证收据；默认 prod 只能晋级已有 dev 收据的**同一** Image ID，不能仅凭相同 Git SHA 推断镜像一致。
- prod 必须具有 Docker HEALTHCHECK 或可从目标机访问的 `FF_HEALTH_URL`。仅 `running` 对 prod 不算健康。
- 目标机保存当前与上一个成功镜像，并在验证失败时尝试应用级回滚；发布历史写在受控用户目录的 `releases.tsv`。数据库 Schema / 数据回滚完全独立，需单独审批。
- 镜像/Host 授权属于组织安全边界，`--approve-prod` 仅是避免误触发的执行保护，不是用户批准证明，也不是 RBAC。

详细契约：读取本 skill 的 [交付契约](references/deployment-contract.md) 和 [安全模型](references/security-model.md)。
