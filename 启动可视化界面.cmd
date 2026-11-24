@echo off
chcp 65001 >nul
cd /d "%~dp0"
python "%~dp0scripts\run-web.py"
echo.
if errorlevel 1 pause
