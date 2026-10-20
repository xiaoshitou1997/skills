# 镜像构建安全模型（出包侧）

脚本使用调用者或 agent 的权限运行。Skills 提供操作指导与工具，不承担沙箱、授权网关或云端密钥存储的职责。

## 控制措施

1. **最小暴露面**：Java 路径不组装 Docker 构建上下文，镜像内容由模块内 Jib 配置决定；非 Java 路径的构建上下文只含产物与 Dockerfile，秘密暴露面小于源码构建。`.dockerignore` 必须显式排除 `.git` 与 `.env*` 且不得取反包含；这是最低防线，负向规则与其余秘密仍需人工复核。
2. **秘密信息**：项目 `.env.*` 和私钥不得进入构建上下文、镜像 tar、Git 或命令日志。Windows 桥接模式下产物与 Dockerfile 经 git 透读管道或 `wsl-bridge.sh push`（stdin 管道，带内容校验，校验失败即中止）进入 WSL；Jib 产出的镜像 tar 经 `wsl-bridge.sh push-bin`（stdin 管道，仅校验密文头）进入 WSL，不落 Windows 盘中间态。
3. **可选扫描策略**：`FF_REQUIRE_SECURITY_SCAN=1` 要求构建时使用 Trivy 扫描镜像，源码扫描另用 Gitleaks；扫描器缺失即失败（fail closed），不能将跳过扫描解释为通过。严格策略应由 CI 落实。
4. **平台控制**：本仓库分发不自动安装命令 Hook；唯一例外是 mv-unattended-watch 的值守 Hook，由用户显式安装。团队控制由 agent 权限、项目 Hook、仓库分支保护和 CI 落实，skill 指令本身不是强制执行机制。
5. **镜像常驻的安全理由**：保留构建镜像与基础镜像以便审计与回溯构建输入；清理动作一律禁止，存储不足时报告用户请示。

## 边界

部署授权、生产验证与失败恢复规则归 `mv-container-deploy` 的安全模型；本 skill 不写部署收据，也不执行任何对远端主机的写操作。
