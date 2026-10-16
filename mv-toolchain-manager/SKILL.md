---
name: mv-toolchain-manager
description: 识别、安装、选择或切换本地 JDK、Maven、Gradle、Node.js 工具链，以及按项目约定选择 npm/pnpm/yarn 时使用。适用于缺少工具、Java class version 不匹配、EBADENGINE 和明确的运行时版本请求；Docker 镜像构建与本地调测使用 mv-image-build，部署晋级归 mv-container-deploy。
---

# Toolchain Manager

## 任务

为**本地调试**准备受控工具链，不污染全局环境，不负责 Git、部署与业务编码。

从加载的 SKILL.md 定位 skill 的实际绝对路径，并赋给 `SKILL_ROOT`；不要假设 agent 自动提供此变量。脚本路径加引号，工作目录保持为用户项目。下文 `python3` 表示可用的 Python 3：Windows 可用 `python` 或 `py -3`，先核实解释器版本。

1. 先检查项目声明（`.mise.toml`、`.tool-versions`、`.nvmrc`、`.node-version`、`.java-version`、`pom.xml`、Gradle Wrapper、`package.json`），再检查当前 Shell 实际版本；使用 `python3 "${SKILL_ROOT}/scripts/detect.py" <project>`（或从本 SKILL.md 所在目录定位脚本）。
2. 以项目自己的 wrapper / lockfile 为优先：Maven `./mvnw`、Gradle `./gradlew`、Node `packageManager` 与锁文件。避免用全局最新版覆盖项目约束。
3. 优先使用项目已采用的 SDKMAN、jenv、nvm、mise 等管理方式；不因机器同时安装 mise 而迁移项目已有约定。
4. 项目没有指定管理方式且已有 mise 时，可先 `mise ls`、`mise doctor`，按需 `mise install` 并用 `mise exec -- <command>` 在作用域内运行。安装与环境修改应符合用户请求的范围。
5. 如果没有版本管理器，使用自带的便携安装器（见下方「便携安装器 fallback」）并取得同意；避免擅自运行远程脚本、写系统 PATH 或编辑用户 shell profile。
6. 安装完成后在**同一 Debug 会话**验证 `java -version`、`mvn -v`、`node -v` 等，记录命中来源、版本及剩余风险。

## 隔离原则

- 不进行系统范围 sudo 安装，不修改注册表、`.bashrc`、`.zshrc` 或 PowerShell profile，除非用户明确授权。
- 优先项目/用户态工具链，严格使用项目要求的 major/minor，不随意升级。
- 自带便携安装器位于 `scripts/installer/`（`runtime_cli.py`），仅在第 3-4 步均无可用方案、且用户同意后使用。
- `mv-image-build` 的产物在宿主构建：宿主 JDK/Maven/Gradle/Node 工具链是交付前置条件，交付前先确认就绪。
- 如果 Python 3 不可用，直接人工检查版本文件；不要因为辅助探测脚本不可用就阻断开发。
- 不按缓存内容拼 classpath：依赖解析与手工验证的完整条款见 [manual-classpath](references/manual-classpath.md)。

## 便携安装器 fallback

面向无 mise/SDKMAN/nvm 的环境，安装到 `~/.mv/toolchain-manager/`，跨会话缓存、会话级激活：

自带安装器管理 JDK、Maven、Gradle、Node.js；它不安装 pnpm/yarn。包管理器按 `packageManager` 和项目约定另行准备，并验证实际版本。

```bash
# 检测 + 比对 + 下载缺失 + 选定（支持 --jdk 17 --node 20 显式版本；--mirror cn 启用大陆镜像）
python3 "${SKILL_ROOT}/scripts/installer/runtime_cli.py" ensure --project .
# 激活（仅当前会话；按 shell 选择 sh / ps1 / cmd）
eval "$(python3 "${SKILL_ROOT}/scripts/installer/runtime_cli.py" activate --print sh)"
```

PowerShell 使用 `activate --print ps1` 生成片段，审查后在当前会话执行；cmd 使用 `activate --print cmd` 生成文件，再在当前会话 `call "%USERPROFILE%\.mv\toolchain-manager\activate.cmd"`。激活和后续构建必须处于同一进程环境，不能假设下一次工具调用继承环境。

硬约束：

1. 默认使用上游发布的便携归档，不运行 `.msi` / `.exe` / `.pkg` / `.dmg` 安装程序；归档模式避免要求管理员权限。显式选择镜像时记录镜像来源。
2. probe-then-GET：先 HEAD 校验候选 URL，仅对 200 响应发起下载。
3. 默认仅官方源；镜像只在 `FF_MIRROR=cn` 或 `--mirror cn` 显式启用，禁止自动选第三方源。
4. 环境变量仅当前会话生效：禁止 `setx`、写 shell profile、改注册表；cmd 激活必须 `call activate.cmd`。

安装器目前不强制验证发行摘要或签名；可达性预检不等于产物完整性校验。需要来源认证时按发行方指南验证产物后再使用。检测细节见 [detection](references/detection.md)，网络和来源见 [mirrors](references/mirrors.md)，工具细节按需读取 [Node.js](references/nodejs.md)、[JDK](references/jdk.md)、[Maven](references/maven.md)、[Gradle](references/gradle.md)。

## 输出

给出项目要求、当前版本、选择或准备的运行时、验证结果，并提示调用 `mv-image-build` 继续出镜像/本地调试（部署晋级归 `mv-container-deploy`）。

## 与项目自检配合

需要一次性诊断 Docker、Git、gh 和基础运行工具是否可用时使用 `python3 "${SKILL_ROOT}/scripts/doctor.py" --project .`。此工具为只读诊断，不替代工具链安装，也不能当作测试通过。
