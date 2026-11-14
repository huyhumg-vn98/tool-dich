@echo off
rem Mo tool Dich Video: bat may chu (neu chua chay) roi mo giao dien tren trinh duyet.
cd /d "%~dp0"
set "PATH=%~dp0ffmpeg\bin;%USERPROFILE%\.local\bin;%PATH%"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
curl -s -m 1 http://127.0.0.1:8765/api/ping >nul 2>&1
if not errorlevel 1 goto mo
start "Dich Video - may chu (DUNG TAT cua so nay khi dang dich)" /min "%~dp0pyvideotrans\.venv\Scripts\python.exe" "%~dp0hang_doi.py"
for /l %%i in (1,1,60) do (
  timeout /t 1 /nobreak >nul
  curl -s -m 1 http://127.0.0.1:8765/api/ping >nul 2>&1 && goto mo
)
:mo
start "" http://127.0.0.1:8765
