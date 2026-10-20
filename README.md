# 团队工程 Skills

面向团队 Git 发布、本机调试、镜像构建与容器部署、工具链管理、非功能性需求采集、编码规范、技术栈约定、工程文档写作、文档配图和离场无人值守的可独立安装 skills。每个目录包含自己的脚本与参考资料，通过 [skills CLI](https://github.com/vercel-labs/skills) 分发。

这是团队工程实践合集，不代表任何 Agent、框架或端点安全厂商的官方产品或认证。

## 十一个 skills

| Skill | 范围 |
| --- | --- |
| `mv-toolchain-manager` | JDK、Node.js、Python、Maven、Gradle、npm、pnpm、yarn、uv 的项目检测与便携准备，优先 wrapper 和项目内分发 |
| `mv-local-debug` | 本机（宿主）直启调试：前台可见运行、断点热更新、宿主构建与启动排障（零 WSL、零镜像） |
| `mv-image-build` | 宿主出包与瘦镜像构建：Java 模块由模块内 Jib 插件定义，非 Java 模块用 `Dockerfile.delivery`；经 WSL 或本机 Docker 载入。只构建不运行，镜像身份（IMAGE_ID）交部署侧（工具链配合 mv-toolchain-manager） |
| `mv-container-deploy` | 镜像包部署 dev/prod 服务器、健康验证、同镜像晋级与回滚 |
| `mv-git-publisher` | 按逻辑变更提交并推送、创建与检查 GitHub PR；纯起草/评审 commit 与 PR 短文本时只输出文稿 |
| `mv-nfr-intake` | 开工前采集确认规模/网络/部署等非功能性需求并落盘项目画像 |
| `mv-java-backend-standards` | 遵循项目约定的 Java 后端规范；Spring Boot 与 JPA 条款按项目实际框架应用 |
| `mv-tech-stack-standards` | 技术栈选型、版本基线、依赖引入与升级决策 |
| `mv-engineering-doc-writer` | PRD/HLD/LLD/RFC/API 文档与生产 MOP 的编写、重写和评审 |
| `mv-document-figure-production` | 给 Markdown、Word、PPT 制图并保留图源，渲染与插入/替换文档中的图片 |
| `mv-unattended-watch` | 离场且全权委托时激活、回归或取消时解除；Claude Code 值守 Hook、保守决策与日志，其他 agent 降级为当前上下文模式 |

命名规范：统一采用 `mv-` + 对象 + 职责词——`mv-` 是本仓库的来源前缀（与 Maven 无关），对象与职责词的选定走两步法与三条检查。职责词按技能的主体职责选定，与 description 和正文一致。具体规则见 [仓库结构规则](docs/structure-rules.md)。

把 skills 安装到本机为可选项：需要时执行 `bash scripts/sync-installed.sh`（加 `--remote` 改从 GitHub 源安装），脚本安装全部并清理旧版本，避免重复触发；是否安装由使用者决定。

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

## 容器构建与部署

本地"跑一下"默认宿主直启：`java -jar`、`npm run dev` 等在宿主前台可见 shell 运行（实时日志、Ctrl-C 可停），禁止后台静默——归 `mv-local-debug`，纯宿主、零 WSL。Windows 的 WSL 就是一台开发服务器，Linux/macOS 宿主的 Docker 同样是：在 WSL/容器里跑属于部署，归 `mv-container-deploy`（dev 默认目标机是本机容器运行时——Windows 为 WSL、Linux/macOS 为宿主 Docker，验证健康后写收据；prod 需明确授权）。两者之间是 `mv-image-build`：宿主出包后打包只含运行时的瘦镜像（Windows 经 WSL，Linux/macOS 直连宿主 Docker），只构建不运行，以镜像身份（`IMAGE=<repo>:<tag>` 与 `IMAGE_ID`）交接部署侧；晋级 prod 要求同一 Image ID 的 dev 健康收据。镜像定义与模块同源：Java 模块在 `pom.xml` / `build.gradle(.kts)` 声明 Jib，非 Java 模块在模块内自备 `Dockerfile.delivery`（Node 静态前端可用内置模板）；宿主没有容器运行时（Windows 无 WSL、Linux/macOS 无 Docker）时明确失败并给安装指引，不在宿主安装 Docker。项目文档化的开发拓扑就是容器（compose 起全套依赖、宿主无法独立启动）时，"本地跑一下"按项目约定直接走 `mv-container-deploy` 的 dev 交付。其他产物布局用 `FF_ARTIFACT` 指定。准备 `.dockerignore` 与未跟踪的 `.env.dev`/`.env.prod`。经管道向 WSL 分发文件前（Windows 桥接模式），wsl-bridge.sh 校验明文：命中企业终端透明加密的 `%XXXX-Header` 密文头即报错终止，不产出损坏镜像；无此类环境的机器该检查为空操作。详见 [镜像构建契约](mv-image-build/references/build-contract.md)、[交付契约](mv-container-deploy/references/deployment-contract.md) 与 [部署安全模型](mv-container-deploy/references/security-model.md)。

```bash
SKILL_ROOT="/实际绝对路径/mv-image-build"
# Windows 校验 WSL+Docker；Linux/macOS 校验本机 Docker
bash "$SKILL_ROOT/scripts/wsl-bridge.sh" require
# Java 模块：在模块目录调用模块自己的 Jib 插件
bash "$SKILL_ROOT/scripts/jib-build.sh" build dev myapp
# 非 Java 模块：产物 + Dockerfile.delivery（或内置 Node 模板）
bash "$SKILL_ROOT/scripts/image-build.sh" build dev myapp

SKILL_ROOT="/实际绝对路径/mv-container-deploy"
bash "$SKILL_ROOT/scripts/deploy.sh" deploy dev myapp 'myapp:TAG'
bash "$SKILL_ROOT/scripts/deploy.sh" status dev myapp
```

Docker 路径构建需要 Docker/Compose（Windows 侧装在 WSL 内）；Java 模块的 Jib 插件随 Maven/Gradle 构建运行，无需额外 CLI。远程交付使用 SSH。生产部署和回滚需要明确的用户请求与目标配置；`--approve-prod` 是脚本保护，不是授权证明。默认生产晋级要求同一镜像 ID 的 dev 健康验证收据。运行状态保存在 `~/.mv/` 下（构建暂存 `~/.mv/image-build/`，仅 Windows 桥接模式，其余宿主用本地临时目录；收据与发布历史 `~/.mv/container-deploy/`）。应用回滚不回滚数据库迁移或外部副作用。

Gitleaks/Trivy 为可选集成；缺少工具应报告未执行，不能声称扫描通过。`FF_REQUIRE_SECURITY_SCAN=1` 要求对应扫描器。本仓库分发不自动安装命令 Hook；唯一例外是 mv-unattended-watch 的值守 Hook，由用户显式运行 `mv-unattended-watch/scripts/install_hooks.py` 安装到用户级 settings.json（`--remove` 可卸载；未安装或未正常运行时该 skill 仅在当前上下文内有效）。值守 Hook 机制依赖 Claude Code 的 Hook 事件（UserPromptSubmit/SessionStart/PreToolUse）与 `~/.claude/settings.json`，仅 Claude Code 上可安装；分发到其他 agent 时无法安装 Hook，该 skill 自动降级为仅当前上下文有效的值守模式。

## 验证

分发前运行 `python3 tests/validate_bundle.py`，检查十一个 skill 集合、仓库支持的 frontmatter 标量子集、元数据长度与目录一致性、正文 ≤500 行（不含 frontmatter）、所有 Markdown 的显式本地链接目标（不验证锚点）、脚本/模板路径、复制脚本一致性及 Python/Bash 语法。使用脚本时按目标项目运行针对性验证。

description 路由用 `python3 tests/run_trigger_evals.py [skill]` 在临时 HOME/配置与仅含候选工作区 skills 的隔离环境评测，记录候选内容 SHA-256；不加载用户已安装 skills、Hook、MCP，仅允许 Skill 工具。合理的多 skill 协作按职责与用例判定，不因多个 skill 同时触发而告警。CLI 或隔离所需凭据缺失时明确 SKIP，人工核对不等于真实路由通过；详见 [触发契约评测](docs/structure-rules.md#触发契约评测)。技能发现与静态检查通过不代表部署成功或所有 agent 均已实测兼容。
