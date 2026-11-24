@echo off
chcp 65001 >nul
cd /d "%~dp0"
"%~dp0python\python.exe" "%~dp0tools\restore_custom.py"
echo.
pause
