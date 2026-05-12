@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0.."

set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"

echo [smoke_test] Checking Python and core imports...
"%PYTHON_EXE%" -c "import importlib, sys; print('Python', sys.version); modules=['app','crawler','cookie_helper','core.config','core.job','server.handlers','export.context','export.reexport']; [print('OK', name) or importlib.import_module(name) for name in modules]"

if errorlevel 1 (
  echo [smoke_test] Failed. Please run: pip install -r requirements.txt
  exit /b 1
)

echo [smoke_test] OK.
exit /b 0
