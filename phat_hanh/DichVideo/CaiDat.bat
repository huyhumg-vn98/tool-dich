@echo off
rem Cai dat tool Dich Video tren Windows: chay script PowerShell ben canh.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0CaiDat.ps1"
echo.
pause
