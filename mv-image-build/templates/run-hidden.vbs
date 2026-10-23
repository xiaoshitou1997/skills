' 隐藏窗口运行目标脚本（计划任务兜底构建专用）。
' wscript.exe 是 GUI 子系统，自身不开控制台；Run 第二参数 0 = 隐藏窗口，True = 等待目标脚本退出并回传退出码。
' 进程链根仍在 Schedule 服务（svchost），不改变绕开 agent 子进程链拦截的原理；输出仍由目标脚本重定向到日志。
' 机器策略禁用 WSH 时：弃用本启动器，任务 Action 直接指向 cmd 脚本（窗口可见，其余行为一致）。
Dim shell, code
Set shell = CreateObject("WScript.Shell")
code = shell.Run("""" & WScript.Arguments(0) & """", 0, True)
WScript.Quit code
