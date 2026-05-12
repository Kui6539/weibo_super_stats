@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0.."

set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"

echo [run_tests] Python: %PYTHON_EXE%
"%PYTHON_EXE%" -m unittest discover -s tests
exit /b %ERRORLEVEL%
