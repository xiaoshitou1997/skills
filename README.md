# 团队工程 Skills

[English](README.en.md)

面向团队 Git 发布、WSL 容器构建/调测/部署、工具链管理、编码规范、技术栈约定和工程文档写作的可独立安装 skills。每个目录包含自己的脚本与参考资料，通过 [skills CLI](https://github.com/vercel-labs/skills) 分发。

这是团队工程实践合集，不代表任何 Agent、框架或端点安全厂商的官方产品或认证。

## 七个 skills

| Skill | 范围 |
| --- | --- |
| `mv-toolchain-manager` | JDK/Maven/Gradle/Node.js 检测与准备，优先项目管理器及 wrapper |
| `mv-container-delivery` | 宿主出包、WSL 出镜像；本地调测与 dev/prod 部署、同镜像晋级与回滚的统一管线 |
| `mv-git-publisher` | 按逻辑变更提交并推送（默认整体动作）、创建与检查 GitHub PR |
| `mv-java-backend-standards` | 遵循项目约定的 Java 后端规范；Spring Boot、MyBatis-Plus、JPA 条款按项目实际框架应用 |
| `mv-tech-stack-standards` | 技术栈选型、版本基线、依赖引入与升级决策；存量项目沿用现状优先 |
| `mv-engineering-doc-writer` | PRD/HLD/LLD/RFC/API 文档与生产 MOP 的编写、重写和评审 |
| `mv-skill-curator` | 把随手发来的工作习惯与流程沉淀进本仓库：归类、合并、拆分、重构与校验 |

命名规范：统一采用 `mv-` + 对象 + 职责词，职责词按技能的主体职责选定，与 description 和正文一致。具体规则见 [仓库结构规则](mv-skill-curator/references/structure-rules.md)。

把 skills 安装到本机为可选项：需要时执行 `bash mv-skill-curator/scripts/sync-installed.sh`（加 `--remote` 改从 GitHub 源安装），脚本安装全部并清理旧版本，避免重复触发；是否安装由使用者决定。

这里的“通用”指团队内跨项目复用，不是面向所有公司或团队的统一标准。Skills 以已确认的团队规范为默认基线，项目业务细节留在各项目中；团队 Git 规则为 commit、push 前都先 pull 并解决冲突，保持线性历史、禁止 merge commit。

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

## WSL 构建部署

`mv-container-delivery` 将本地调测与 dev/prod 交付统一为同一条管线：编译出包在宿主完成（工具链由 mv-toolchain-manager 准备），产物在 WSL 内打包为只含运行时的瘦镜像，部署到本机 WSL（dev，即本地服务器）或远程服务器（prod）。自带模板面向 Java 可执行 JAR 和 Node 静态前端；其他产物布局用 `FF_ARTIFACT` 指定或项目自备 `Dockerfile.delivery`。准备 `.dockerignore` 与未跟踪的 `.env.dev`/`.env.prod`。详见 [交付契约](mv-container-delivery/references/deployment-contract.md) 与 [安全模型](mv-container-delivery/references/security-model.md)。

```bash
SKILL_ROOT="/实际绝对路径/mv-container-delivery"
bash "$SKILL_ROOT/scripts/wsl-bridge.sh" require
bash "$SKILL_ROOT/scripts/deliver.sh" build dev myapp
bash "$SKILL_ROOT/scripts/deliver.sh" deploy dev myapp 'myapp:TAG'
bash "$SKILL_ROOT/scripts/deliver.sh" status dev myapp
```

构建需要 Docker/Compose，远程交付使用 SSH。生产部署和回滚需要明确的用户请求与目标配置；`--approve-prod` 是脚本保护，不是授权证明。默认生产晋级要求同一镜像 ID 的 dev 健康验证收据。运行状态保存在 `~/.local/share/skills/`。应用回滚不回滚数据库迁移或外部副作用。

Gitleaks/Trivy 为可选集成；缺少工具应报告未执行，不能声称扫描通过。`FF_REQUIRE_SECURITY_SCAN=1` 要求对应扫描器。本仓库不安装自动命令 Hook。

## 验证

分发前检查 skill 名称、引用、文档脚本路径及 Python/Bash 语法；使用脚本时按目标项目运行针对性验证。技能发现与静态检查通过不代表部署成功或所有 agent 均已实测兼容。
