@echo off
chcp 65001 >nul
echo 正在停止媒体双向管家后台进程...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*sync_daemon.py*' } | ForEach-Object { Stop-Process $_.ProcessId -Force; Write-Host ('[+] 已停止进程 PID: ' + $_.ProcessId) }"
echo 完成！
pause
