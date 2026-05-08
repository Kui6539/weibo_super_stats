@echo off
setlocal
cd /d "%~dp0"

set "PYEXE="
where py >nul 2>nul && set "PYEXE=py"
if not defined PYEXE (
  where python >nul 2>nul && set "PYEXE=python"
)

if not defined PYEXE (
  echo [ERROR] Python was not found in PATH.
  goto :error
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] Creating virtual environment...
  %PYEXE% -m venv .venv
  if errorlevel 1 goto :error
)

echo [2/4] Upgrading pip...
call ".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error

echo [3/4] Installing dependencies...
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [4/4] Starting app...
call ".venv\Scripts\python.exe" app.py
if errorlevel 1 goto :error

goto :end

:error
echo.
echo Run failed. Please keep this window and send me the error text.
pause
exit /b 1

:end
echo.
echo App exited.
pause
exit /b 0
