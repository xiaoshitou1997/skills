# 团队工程 Skills

面向团队本地开发、Git 发布和 Docker 交付的可独立安装 skills。每个目录包含自己的脚本与参考资料，通过 [skills CLI](https://github.com/vercel-labs/skills) 分发。

这是团队工程实践合集，不代表任何 Agent、框架或端点安全厂商的官方产品或认证。

## 六个 skills

| Skill | 范围 |
| --- | --- |
| `toolchain-manager` | JDK/Maven/Gradle/Node.js 检测与准备，优先项目管理器及 wrapper |
| `local-development` | 本地启动、复现、调试、停止和针对性验证 |
| `git-publisher` | 按逻辑变更提交、按需推送、创建与检查 GitHub PR |
| `docker-delivery` | 容器内构建、Compose 部署、同镜像晋级、健康验证及应用回滚 |
| `spring-boot-standards` | 遵循项目约定的 Spring Boot 规范；适用时采用 MyBatis-Plus 条款 |
| `windows-dlp-environment` | 本机专用的 Windows DLP/EDR 诊断、读写与 WSL 构建经验 |

名称迁移：`application-delivery` → `docker-delivery`，`java-backend-standards` → `spring-boot-standards`，`dlp-machine-env` → `windows-dlp-environment`。已安装旧版本时，显式移除旧名称后安装新名称，避免重复触发。

这里的“通用”指团队内跨项目复用，不是面向所有公司或团队的统一标准。除本机专用的 `windows-dlp-environment` 外，其余 skills 以已确认的团队规范为默认基线，项目业务细节留在各项目中；团队 Git 规则为先 pull、解决冲突，再 commit，并保持线性历史、禁止 merge commit。

## 维护原则

- 从实际经验提炼团队可复用的方法、规范和验证标准；团队规则可直接写入 skill，不因其他团队可能不同而弱化为可选项。不复制项目业务口径、固定路径或凭据。
- 主文件保留当前有效工作流，环境/框架细节按需放入 references；更新流程时同步描述、示例、执行入口与引用，避免旧操作指令残留。
- 编译、单测、mock 联调和真实系统联调分别记录证据；静态检查不能替代行为验证。反复出现的机械错误优先增加范围明确的机器检查，而非堆叠提醒。

## 安装

从本仓库安装：

```bash
npx skills@latest add xiaoshitou1997/skills --list
npx skills@latest add xiaoshitou1997/skills
npx skills@latest add xiaoshitou1997/skills --skill git-publisher -g -a claude-code
# 本地仓库：只列出 skills，不安装
npx skills@latest add . --list
```

CLI 支持多个 agent，使用 `-a` 选择目标；技能加载方式取决于目标 agent。CLI 需要 Node.js；Python 脚本需要 Python 3，按环境使用 `python3`、`python` 或 `py -3`。Shell 脚本需要 Bash 及对应工具。Windows 环境诊断 skill 本身是纯文档，不要求额外安装运行时。

## 使用脚本

通过本次加载的 `SKILL.md` 定位实际安装目录。下文 `SKILL_ROOT` 需要明确赋值，不保证 agent 自动设置。项目命令应从用户应用仓库执行：

```bash
SKILL_ROOT="/实际绝对路径/toolchain-manager"
python3 "$SKILL_ROOT/scripts/doctor.py" --project .

SKILL_ROOT="/实际绝对路径/git-publisher"
python3 "$SKILL_ROOT/scripts/stage_audit.py"
bash "$SKILL_ROOT/scripts/pr.sh" view
```

提交语言与格式优先遵循用户和仓库约定；没有约定时可默认中文 Conventional Commits。已有暂存内容先识别、审查，不擅自清空。

## Docker 交付

自带模板面向 Java 可执行 JAR 和 Node 静态前端；其他架构需项目自备 Dockerfile/Compose。准备 `.dockerignore` 与未跟踪的 `.env.dev`/`.env.prod`。详见 [交付契约](docker-delivery/references/deployment-contract.md) 与 [安全模型](docker-delivery/references/security-model.md)。

```bash
SKILL_ROOT="/实际绝对路径/docker-delivery"
bash "$SKILL_ROOT/scripts/deliver.sh" build dev myapp
bash "$SKILL_ROOT/scripts/deliver.sh" deploy dev myapp 'myapp:TAG'
bash "$SKILL_ROOT/scripts/deliver.sh" status dev myapp
```

构建需要 Docker/Compose，远程交付使用 SSH。生产部署和回滚需要明确的用户请求与目标配置；`--approve-prod` 是脚本保护，不是授权证明。默认生产晋级要求同一镜像 ID 的 dev 健康验证收据。运行状态保存在 `~/.local/share/skills/`。应用回滚不回滚数据库迁移或外部副作用。

Gitleaks/Trivy 为可选集成；缺少工具应报告未执行，不能声称扫描通过。`FF_REQUIRE_SECURITY_SCAN=1` 要求对应扫描器。本仓库不安装自动命令 Hook。

## 验证

分发前检查 skill 名称、引用、文档脚本路径及 Python/Bash 语法；使用脚本时按目标项目运行针对性验证。技能发现与静态检查通过不代表部署成功或所有 agent 均已实测兼容。
