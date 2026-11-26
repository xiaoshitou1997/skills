# MV 软件研发 Skills

MV 以一组 Skills 提供软件研发生命周期的流程与工程标准；按任务触发，凡随项目而变的业务模型、法规与资质、客户约束和环境配置由各项目维护。

面向团队需求与设计、编码与测试、构建交付、稳态运维、Git 发布、工具链管理、应用安全的可独立安装 skills。每个目录包含自己的脚本与参考资料，通过 [skills CLI](https://github.com/vercel-labs/skills) 分发。

这是团队工程实践合集，不代表任何 Agent、框架或端点安全厂商的官方产品或认证。

## Skills 职责

| Skill | 阶段 | 范围 |
| --- | --- | --- |
| `mv-design-standards` | design | 需求与方案设计：业务规则与验收建模、架构决策与评审、技术栈选型与版本基线、PRD/HLD/LLD/RFC/API/MOP 工程文档、工程制图与插图编排、新项目从零初始化骨架 |
| `mv-coding-standards` | impl | 编码与测试规范：Java 后端（基线 Spring Boot + JDK 21）、React/TypeScript 前端（Vite SPA/shadcn-admin/Next.js/Taro）、测试分层与各端测试写法 |
| `mv-delivery-standards` | delivery | 镜像构建与容器交付：宿主出包、服务器构建瘦镜像、交付契约与部署诊断（部署/晋级/回滚入口当前关闭）、Compose 编排规范、探针与凭证分级 |
| `mv-git-publisher` | 横切 | 按逻辑变更提交并推送、创建与检查 GitHub PR；纯起草/评审 commit 与 PR 短文本时只输出文稿 |
| `mv-ops-standards` | operate | 交付后稳态运维：日志轮转、Actuator/Micrometer 指标、告警判据、数据库备份与恢复演练、镜像老化重扫、例行巡检与事故响应 |
| `mv-security-standards` | 横切 | 应用安全与数据保护基线：威胁建模、认证授权原则、数据分级与脱敏、凭据与供应链、安全评审与测试、漏洞响应 |
| `mv-toolchain-manager` | 横切 | JDK、Node.js、Python、Maven、Gradle、npm、pnpm、yarn、uv 的项目检测与便携准备，优先 wrapper 和项目内分发 |

命名规范：统一采用 `mv-` + 对象 + 职责词——`mv-` 是本仓库的来源前缀（与 Maven 无关）；SDLC 阶段归属由受控词表承载（design 需求与方案设计、impl 编码实现、build 构建、delivery 交付部署、operate 交付后稳态运维、横切不限单一阶段），体现在上表阶段列与校验注册，不进名字。具体规则见 [仓库结构规则](docs/structure-rules.md)。

## 组合场景

skills 按 description 触发，按任务需要协作加载，不为流程完整强行加载全部 skill；普通问答不启动研发流程。

| 场景 | 加载顺序 |
| --- | --- |
| 新项目从零 | `mv-design-standards`（选型与骨架）→ `mv-coding-standards` → `mv-delivery-standards`（构建）→ `mv-ops-standards` |
| 新功能或变更 | `mv-design-standards`（新增或改变业务规则、架构或技术选型时）→ `mv-security-standards`（新入口、数据流、第三方集成、多租户或高敏数据变更时先行）→ `mv-coding-standards` → `mv-git-publisher`（仅按授权） |
| 存量项目接管 | `mv-design-standards`（项目上下文与现状评估）→ `mv-security-standards`（安全评审）→ `mv-coding-standards` → `mv-git-publisher` |
| 自托管第三方栈 | `mv-delivery-standards`（Compose 编排）→ `mv-ops-standards` |
| 生产事故 | `mv-ops-standards`（事故响应）→ `mv-delivery-standards`（回滚契约，脚本当前关闭）→ `mv-design-standards`（复盘文档） |
| 文档与图件 | `mv-design-standards`（写作、制图、插图编排） |

把 skills 安装到本机为可选项：需要时执行 `bash scripts/sync-installed.sh`（加 `--remote` 改从 GitHub 源安装），脚本安装全部并清理合并前旧版本，避免重复触发；是否安装由使用者决定。

Skills 以内置团队基线为默认，适用于不同项目；用户明确要求优先，项目偏离基线须显式确认并记录，已有项目不因偏离默认而擅自改造。项目业务细节留在各项目中；团队 Git 规则中 commit 与 push 是可分开执行的两个动作，各自先 pull --rebase 并解决冲突，全程一颗 worktree（树脏导致同步失败时停止，不通过本地提交绕过同步），保持线性历史、禁止 merge commit。

## 规则归属

| 层次 | 内容 | 维护位置 |
| --- | --- | --- |
| 团队共用 | 技术基线、编码规范、测试方法、构建交付纪律与安全要求 | 对应 skill 的 SKILL.md 与 references |
| 项目约定 | 行业术语、业务规则、验收、客户约束、技术偏离与 ADR | 当前项目的需求、README、契约与 ADR |
| 环境配置 | 连接目标、资源配额、部署参数与凭据引用 | 当前项目环境说明与配置；真实凭据不进 Git |

项目已有约定和用户明确需求优先于团队默认；冲突显式记录，不能把历史项目的业务或环境配置推广为团队要求。团队默认仍是新项目起点，不因项目业务不同而取消既有技术底座。读取与核对项目上下文的方法见 mv-design-standards 的 references/project-context.md。

每个 skill 只维护自己的判据：需求定义要实现和验收什么，设计确定方案与文档，编码规范约束实现与测试，构建/交付负责产物与交付动作，运维负责持续运行；按任务触发，不把完整链路当作每次改动的固定手续。

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

提交信息统一用中文 Conventional Commits 格式，用户明确指定语言或格式时按用户执行。已有暂存内容先识别、审查，不擅自清空。

## 容器构建与部署

当前 mv-delivery-standards 的 deploy.sh 与 target-runner.sh 的 dev/prod 部署、回滚和状态查询，以及 target-runner 的 plan 均在参数校验后拒绝；不连接目标机、不写目标文件、不产生收据。共享配置覆盖和回滚历史的安全问题修复并验证前，不得使用这些入口交付。

宿主出包并经 SSH 上传至构建点，镜像在服务器构建，由构建侧交接镜像引用与 Image ID；部署职责及限制见 mv-delivery-standards 的 references/deployment-contract.md。构建入口不受部署入口限制。

`deploy-preflight.sh` 可独立检查配置和 SSH 连通性，该检查会连接目标机，不代表部署入口可用。应用回滚不恢复数据库迁移或外部副作用。

Gitleaks/Trivy 为可选集成；缺少工具应报告未执行，不能声称扫描通过。`FF_REQUIRE_SECURITY_SCAN=1` 要求对应扫描器。本仓库分发不自动安装命令 Hook。团队控制由 agent 权限、项目 Hook、仓库分支保护和 CI 落实，skill 指令本身不是强制执行机制。

## 验证

分发前运行 `python3 tests/validate_bundle.py`，检查已注册的 skill 集合、仓库支持的 frontmatter 标量子集、元数据长度与目录一致性、正文 ≤500 行（不含 frontmatter）、所有 Markdown 的显式本地链接目标（不验证锚点）、脚本/模板路径、复制脚本一致性及 Python/Bash 语法。使用脚本时按目标项目运行针对性验证。

description 路由用 `python3 tests/run_trigger_evals.py [skill]` 在临时 HOME/配置与仅含候选工作区 skills 的隔离环境评测，记录候选内容 SHA-256；不加载用户已安装 skills、Hook、MCP，仅允许 Skill 工具。合理的多 skill 协作按职责与用例判定，不因多个 skill 同时触发而告警。CLI 或隔离所需凭据缺失时明确 SKIP，人工核对不等于真实路由通过；详见 [触发契约评测](docs/structure-rules.md#触发契约评测)。技能发现与静态检查通过不代表部署成功或所有 agent 均已实测兼容。
