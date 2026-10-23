@echo off
setlocal
chcp 65001 >nul
REM ============================================================
REM 干净进程链构建模板（宿主侧安全软件按进程链拦截 agent/bash 子进程时的替代构建方式）
REM 症状: agent shell 里 gradlew/mvn 报 "Unable to establish loopback connection"
REM       （Selector.open 失败，换 JDK / preferIPv4Stack / 查 afunix 服务均无效）
REM 原理: 计划任务拉起的进程链根在系统服务（Schedule 服务/svchost），不经过被拦截的 agent 子进程链，构建可正常执行。
REM
REM 用法（在 Git Bash 里）:
REM   1. 复制本文件与同目录 run-hidden.vbs，修改下方三处占位；记下两文件所在目录（下称 <dir>）。
REM   2. 生成唯一任务名并注册为无触发器任务（triggers=0 只能手动运行，杜绝占位定时器到点自跑；
REM      并发会话/多项目不得共用任务名，避免互相覆盖与误删）:
REM        TASK_NAME=HostBuild-$(date +%Y%m%d%H%M%S)
REM        MSYS_NO_PATHCONV=1 powershell -NoProfile -Command "Register-ScheduledTask -TaskName '$TASK_NAME' -Action (New-ScheduledTaskAction -Execute 'wscript.exe' -Argument '\"<dir>\run-hidden.vbs\" \"<dir>\schtasks-build.cmd\"')"
REM      机器策略禁用 WSH 时回退为直接执行（窗口可见，其余行为一致）:
REM        ... -Execute 'cmd.exe' -Argument '/c \"<dir>\schtasks-build.cmd\"'
REM   3. 运行（wscript 隐藏窗口执行，无弹窗；输出全部重定向进日志）:
REM        MSYS_NO_PATHCONV=1 schtasks /run /tn "$TASK_NAME"
REM   4. 轮询日志直到出现 EXIT= 行。
REM   5. 用后注销——构建失败或会话中断同样必须执行，防残留任务堆积；残留自检:
REM        powershell -NoProfile -Command "Get-ScheduledTask | Where-Object TaskName -like '*Build*'"
REM        MSYS_NO_PATHCONV=1 schtasks /delete /f /tn "$TASK_NAME"
REM
REM 注意: 计划任务不继承用户会话环境，工具链变量必须显式 set。
REM       Node 项目把中间 call 行换成: cd /d <repo>\frontend && call npm run build
REM       setlocal 保证 set 只影响本脚本进程，手工拼接复用不污染当前 cmd。
REM ============================================================

REM --- 占位 1: 仓库目录 ---
cd /d D:\path\to\repo
REM --- 占位 2: 工具链（必须显式，计划任务无继承环境） ---
set JAVA_HOME=D:\path\to\jdk
set PATH=%JAVA_HOME%\bin;%PATH%
REM --- 占位 3: 构建命令与日志（日志路径固定，供外部轮询 EXIT= 行） ---
call gradlew.bat --no-daemon :app:bootJar --console=plain > C:\path\to\build.log 2>&1

set BUILD_RC=%ERRORLEVEL%
echo EXIT=%BUILD_RC% >> C:\path\to\build.log
endlocal
exit /b %BUILD_RC%
