@echo off
echo 停止梦宝进程中...
taskkill /FI "WINDOWTITLE eq 梦宝*" /F 2>nul
taskkill /FI "IMAGENAME eq python.exe" /FI "WINDOWTITLE eq *梦宝*" /F 2>nul
echo 梦宝已停止~ 拜拜
pause
