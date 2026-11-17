# MV 团队工程 Skills

MV 是按项目承接业务的研发团队。本集合沉淀团队共同使用的研发规则、技术默认值、工作方法与验证标准；凡随项目而变的——行业业务模型、法规与资质、客户约束、环境配置——由各项目维护。

面向团队 Git 发布、镜像构建与容器部署、容器编排规范、工具链管理、编码规范与测试规范、项目脚手架、稳态运维、技术栈约定、系统架构决策、应用安全与数据保护、工程文档写作（含工程制图与插图编排）的可独立安装 skills。每个目录包含自己的脚本与参考资料，通过 [skills CLI](https://github.com/vercel-labs/skills) 分发。

这是团队工程实践合集，不代表任何 Agent、框架或端点安全厂商的官方产品或认证。

## Skills 职责

| Skill | 阶段 | 范围 |
| --- | --- | --- |
| `mv-requirements-standards` | design | 需求分析：项目上下文、领域术语、业务流程与规则、状态流转、验收标准、需求评审与范围变更 |
| `mv-engineering-doc-writer` | design | 工程文档写作/评审与制图插图编排：PRD/HLD/LLD/RFC/API 文档与生产 MOP，架构图/组网图/时序图等可编辑图源与渲染成品，Markdown/Word/PPT 插图与图文核验 |
| `mv-tech-stack-baseline` | design | 技术栈选型、版本基线、依赖引入与升级决策 |
| `mv-architecture-standards` | design | 系统架构决策与评审：单体/按端/按域/微服务判据、模块与服务边界、同步/异步与一致性、多租户与数据隔离、集成模式、ADR 与架构评审 |
| `mv-backend-standards` | impl | Java 后端规范（基线 Spring Boot + JDK 21）：分层、API、DTO/VO、错误码与国际化、枚举、异常、日志、事务、数据访问、集合并发和测试；Spring Boot 与 JPA 条款按基线栈应用 |
| `mv-frontend-standards` | impl | React/TypeScript 前端规范（含 shadcn-admin 后台管理类项目）：组件分层、数据获取、状态管理、路由、构建环境变量、前端安全、页面交互体验基线、可访问性与性能预算；Vite SPA 与 shadcn-admin、Next.js 条款按项目实际栈应用 |
| `mv-test-standards` | impl | 测试分层与测试代码规范：单测/集成/E2E 各层范围与覆盖率口径、性能与负载测试，JUnit/Testcontainers、Vitest/Testing Library/Playwright 与 Taro 端写法 |
| `mv-project-scaffold` | impl | 新项目从零初始化：仓库布局与模块划分、Spring Boot 后端骨架、shadcn-admin 管理端、Vite SPA 用户端、Taro H5/小程序端，compose.dev/env 样例/Dockerfile.delivery/CI 样例落位 |
| `mv-image-builder` | build | 宿主出包、上传服务器构建瘦镜像：各栈模块内 `Dockerfile.delivery`，服务器侧 `docker build`，包与镜像同 Tag 可追溯。只构建不运行，镜像身份（IMAGE_ID）交部署侧（工具链配合 mv-toolchain-manager） |
| `mv-container-deploy` | delivery | 服务器构建产出的镜像交付 dev/prod、健康验证、同镜像晋级与回滚 |
| `mv-orchestration-standards` | delivery | 容器编排规范：一项目一 stack/ns、环境即栈、禁共享基础设施；compose 编写细则、探针判定树、凭证分级与资源日志限额，k3s/k8s 映射 |
| `mv-ops-standards` | operate | 交付后稳态运维：日志轮转、Actuator/Micrometer 指标、告警判据、数据库备份与恢复演练、镜像老化重扫、例行巡检与事故响应 |
| `mv-git-publisher` | 横切 | 按逻辑变更提交并推送、创建与检查 GitHub PR；纯起草/评审 commit 与 PR 短文本时只输出文稿 |
| `mv-toolchain-manager` | 横切 | JDK、Node.js、Python、Maven、Gradle、npm、pnpm、yarn、uv 的项目检测与便携准备，优先 wrapper 和项目内分发 |
| `mv-security-standards` | 横切 | 应用安全与数据保护基线：威胁建模、认证授权原则、数据分级与脱敏、凭据与供应链、安全评审与测试、漏洞响应 |

命名规范：统一采用 `mv-` + 对象 + 职责词——`mv-` 是本仓库的来源前缀（与 Maven 无关）；SDLC 阶段归属由受控词表承载（design 需求与方案设计、impl 编码实现、build 构建、delivery 交付部署、operate 交付后稳态运维、横切不限单一阶段），体现在上表阶段列与校验注册，不进名字。对象与职责词的选定走两步法与四条检查。具体规则见 [仓库结构规则](docs/structure-rules.md)。

## 组合场景

按项目实际裁剪，不为流程完整强行加载全部 skill：

| 场景 | 加载顺序 |
| --- | --- |
| 新项目从零 | `mv-requirements-standards` → `mv-tech-stack-baseline` → `mv-architecture-standards` → `mv-project-scaffold` → `mv-backend-standards` / `mv-frontend-standards` → `mv-test-standards` → `mv-image-builder` → `mv-container-deploy` → `mv-ops-standards` |
| 新功能或变更 | `mv-requirements-standards`（新增或改变业务规则、范围或验收时）→ `mv-architecture-standards`（涉及边界、集成或数据隔离时）→ `mv-backend-standards` / `mv-frontend-standards` → `mv-test-standards` → `mv-security-standards`（新入口、敏感数据或第三方集成时）→ `mv-git-publisher` |
| 存量项目接管 | `mv-requirements-standards`（项目上下文与需求/现状差异）→ `mv-architecture-standards`（现状与边界评估）→ `mv-security-standards`（安全评审）→ 对应端规范 → `mv-test-standards` → `mv-git-publisher` |
| 自托管第三方栈 | `mv-orchestration-standards` → `mv-ops-standards` |
| 生产事故 | `mv-ops-standards`（事故响应）→ `mv-container-deploy`（回滚）→ `mv-engineering-doc-writer`（复盘文档） |
| 文档与图件 | `mv-engineering-doc-writer`（写作、制图、插图编排） |

把 skills 安装到本机为可选项：需要时执行 `bash scripts/sync-installed.sh`（加 `--remote` 改从 GitHub 源安装），脚本安装全部并清理旧版本，避免重复触发；是否安装由使用者决定。

这里的“通用”指团队内跨项目复用，不是面向所有公司或团队的统一标准。Skills 以已确认的团队规范为默认基线，项目业务细节留在各项目中；团队 Git 规则中 commit 与 push 是可分开执行的两个动作，各自先 pull --rebase 并解决冲突，全程一颗 worktree（树脏时在主树原地用 plumbing 临时索引提交，不侧 worktree 提交后直推 SHA），保持线性历史、禁止 merge commit。

## 规则归属

| 层次 | 内容 | 维护位置 |
| --- | --- | --- |
| 团队共用 | 技术基线、编码规范、测试方法、构建交付纪律与安全要求 | 对应 skill 的 SKILL.md 与 references |
| 项目约定 | 行业术语、业务规则、验收、客户约束、技术偏离与 ADR | 当前项目的需求、README、契约与 ADR |
| 环境配置 | 连接目标、资源配额、部署参数与凭据引用 | 当前项目环境说明与配置；真实凭据不进 Git |

项目已有约定和用户明确需求优先于团队默认；冲突显式记录，不能把历史项目的业务或环境配置推广为团队要求。团队默认仍是新项目起点，不因项目业务不同而取消既有技术底座。读取与核对项目上下文的方法见 mv-requirements-standards 的 [项目上下文](mv-requirements-standards/references/project-context.md)。

每个 skill 只维护自己的判据：需求定义要实现和验收什么，架构与技术栈确定方案，脚手架落工程骨架，前后端规范约束实现，测试规范组织验证，构建/部署/运维分别负责产物、交付动作与持续运行；文档写作承接各阶段的正式文稿与图件。按任务触发，不把完整链路当作每次改动的固定手续。

## 维护原则

- 从实际经验提炼团队可复用的方法、规范和验证标准；团队规则可直接写入 skill，不因其他团队可能不同而弱化为可选项。不复制项目业务口径、固定路径或凭据。
- 主文件保留当前有效工作流，环境/框架细节按需放入 references；更新流程时同步描述、示例、执行入口与引用，避免旧操作指令残留。
- 编译、单测、mock 联调和真实系统联调分别记录证据；静态检查不能替代行为验证。反复出现的机械错误优先增加范围明确的机器检查，而非堆叠提醒。

## 安装

从本仓库安装：

```bash
npx skills@latest add xiaoshitou1997/skills --list
npx skills@latest add xiaoshitou1997/skills
npx skills@latest add xiaoshitou1997/skills --skill mv-git-publisher -g -a claude-code
# 本地仓库：只列出 skills，不安装
npx skills@latest add . --list
```

CLI 支持多个 agent，使用 `-a` 选择目标；技能加载方式取决于目标 agent。CLI 需要 Node.js；Python 脚本需要 Python 3，按环境使用 `python3`、`python` 或 `py -3`。Shell 脚本需要 Bash 及对应工具。

## 使用脚本

通过本次加载的 `SKILL.md` 定位实际安装目录。下文 `SKILL_ROOT` 需要明确赋值，不保证 agent 自动设置。项目命令应从用户应用仓库执行：

```bash
SKILL_ROOT="/实际绝对路径/mv-toolchain-manager"
python3 "$SKILL_ROOT/scripts/doctor.py" --project .

SKILL_ROOT="/实际绝对路径/mv-git-publisher"
python3 "$SKILL_ROOT/scripts/stage_audit.py"
bash "$SKILL_ROOT/scripts/pr.sh" view
```

提交语言与格式优先遵循用户和仓库约定；没有约定时可默认中文 Conventional Commits。已有暂存内容先识别、审查，不擅自清空。

## 容器构建与部署

当前交付脚本只为单服务单副本单容器、readiness 验证通过的配置签发可晋级收据。多组件完整栈、多副本和一次性任务未具备当前脚本的生产晋级支持；dev 诊断成功不代表可晋级，不通过拆 stack 或关闭门禁规避。

构建与交付按宿主/服务器职责二分（[构建与交付分工](docs/structure-rules.md#构建与交付分工)）：宿主只编译出二进制包并上传，镜像全部在服务器构建——单机部署为部署机自身，集群为镜像仓库所在节点，宿主不安装 Docker。把镜像跑起来属于部署，归 `mv-container-deploy`（dev 目标是开发服务器，经 `FF_DEV_SSH` 指定，验证健康后写收据；prod 需明确授权）。两者之间是 `mv-image-builder`：宿主出包后在服务器构建只含运行时的瘦镜像，只构建不运行，以镜像身份（`IMAGE=<repo>:<tag>` 与 `IMAGE_ID`）交接部署侧；晋级 prod 要求同一 Image ID 的 dev 健康收据。镜像定义与模块同源：各栈模块内自备 `Dockerfile.delivery`（Node 静态前端可用内置模板），其他产物布局用 `FF_ARTIFACT` 指定。准备 `.dockerignore` 与未跟踪的 `.env.dev`/`.env.prod`。出包上传统一经 SSH（`FF_BUILD_TARGET` 指向构建点），构建点核对 SHA-256，不匹配即删除损坏包中止构建。详见 [镜像构建契约](mv-image-builder/references/build-contract.md)、[交付契约](mv-container-deploy/references/deployment-contract.md) 与 [部署安全模型](mv-container-deploy/references/security-model.md)。

```bash
SKILL_ROOT="/实际绝对路径/mv-image-builder"
# 各栈模块：宿主产物 + 模块内 Dockerfile.delivery（或内置 Node 模板），服务器侧构建
FF_BUILD_TARGET=user@host bash "$SKILL_ROOT/scripts/image-build.sh" build dev myapp

SKILL_ROOT="/实际绝对路径/mv-container-deploy"
FF_DEV_SSH=devops@dev.example.com bash "$SKILL_ROOT/scripts/deploy.sh" deploy dev myapp 'myapp:TAG'
FF_DEV_SSH=devops@dev.example.com bash "$SKILL_ROOT/scripts/deploy.sh" status dev myapp
```

Docker/Compose 只在服务器侧，宿主不安装 Docker；部署目标一律经 SSH 交付。生产部署和回滚需要明确的用户请求与目标配置；`--approve-prod` 是脚本保护，不是授权证明。默认生产晋级要求同一镜像 ID 的 dev 健康验证收据。运行状态与发布历史保存在目标服务器侧 `~/.mv/` 下（包与构建记录 `~/.mv/image-builder/`；发布历史 `~/.mv/container-deploy/`），dev 健康验证收据保存在执行部署的本机 `~/.mv/container-deploy/receipts/`。应用回滚不回滚数据库迁移或外部副作用。

Gitleaks/Trivy 为可选集成；缺少工具应报告未执行，不能声称扫描通过。`FF_REQUIRE_SECURITY_SCAN=1` 要求对应扫描器。本仓库分发不自动安装命令 Hook。团队控制由 agent 权限、项目 Hook、仓库分支保护和 CI 落实，skill 指令本身不是强制执行机制。

## 验证

分发前运行 `python3 tests/validate_bundle.py`，检查已注册的 skill 集合、仓库支持的 frontmatter 标量子集、元数据长度与目录一致性、正文 ≤500 行（不含 frontmatter）、所有 Markdown 的显式本地链接目标（不验证锚点）、脚本/模板路径、复制脚本一致性及 Python/Bash 语法。使用脚本时按目标项目运行针对性验证。

description 路由用 `python3 tests/run_trigger_evals.py [skill]` 在临时 HOME/配置与仅含候选工作区 skills 的隔离环境评测，记录候选内容 SHA-256；不加载用户已安装 skills、Hook、MCP，仅允许 Skill 工具。合理的多 skill 协作按职责与用例判定，不因多个 skill 同时触发而告警。CLI 或隔离所需凭据缺失时明确 SKIP，人工核对不等于真实路由通过；详见 [触发契约评测](docs/structure-rules.md#触发契约评测)。技能发现与静态检查通过不代表部署成功或所有 agent 均已实测兼容。
