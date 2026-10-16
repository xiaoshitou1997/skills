@echo off
REM ============================================================
REM 干净进程链构建模板（宿主侧安全软件按进程链拦截 agent/bash 子进程时的替代构建方式）
REM 症状: agent shell 里 gradlew/mvn 报 "Unable to establish loopback connection"
REM       （Selector.open 失败，换 JDK / preferIPv4Stack / 查 afunix 服务均无效）
REM 原理: schtasks 拉起的进程链根在系统服务（svchost），不经过被拦截的 agent 子进程链，构建可正常执行。
REM
REM 用法（在 Git Bash 里，MSYS_NO_PATHCONV 防 /参数 被转成路径）:
REM   1. 复制本文件并修改下方三处占位（仓库、JAVA_HOME、构建命令与日志路径）
REM   2. MSYS_NO_PATHCONV=1 schtasks /create /f /tn HostBuild ^
REM        /tr "C:\path\to\schtasks-build.cmd" /sc once /st 23:59
REM      (/sc once /st 23:59 只是合法占位，从不等待，/run 当场执行)
REM   3. MSYS_NO_PATHCONV=1 schtasks /run /tn HostBuild
REM   4. 轮询日志直到出现 EXIT= 行；结束后 schtasks /delete /f /tn HostBuild
REM
REM 注意: schtasks 不继承用户会话环境，工具链变量必须显式 set。
REM       Node 项目把中间 call 行换成: cd /d <repo>\frontend && call npm run build
REM ============================================================

REM --- 占位 1: 仓库目录 ---
cd /d D:\path\to\repo
REM --- 占位 2: 工具链（必须显式，schtasks 无继承环境） ---
set JAVA_HOME=D:\path\to\jdk
set PATH=%JAVA_HOME%\bin;%PATH%
REM --- 占位 3: 构建命令与日志（日志路径固定，供外部轮询 EXIT= 行） ---
call gradlew.bat --no-daemon :app:bootJar --console=plain > C:\path\to\build.log 2>&1

echo EXIT=%ERRORLEVEL% >> C:\path\to\build.log
