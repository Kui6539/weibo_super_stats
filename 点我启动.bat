@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "PYEXE="
where py >nul 2>nul && set "PYEXE=py -3"
if not defined PYEXE (
  where python >nul 2>nul && set "PYEXE=python"
)

if not defined PYEXE (
  echo [ERROR] Python was not found. Please install Python 3.10+ and enable "Add python.exe to PATH".
  goto :error
)

if not exist "app.py" (
  echo [ERROR] app.py was not found. Please put this script in the project root.
  goto :error
)

if not exist "requirements.txt" (
  echo [ERROR] requirements.txt was not found. Please check the project files.
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

echo [3/4] Installing/updating dependencies...
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [4/4] Starting Weibo Super Topic Weekly Tool...
echo.
echo The command line will show live backend logs. Press Ctrl+C to stop.
echo.
call ".venv\Scripts\python.exe" app.py %*
if errorlevel 1 goto :error

goto :end

:error
echo.
echo Run failed. Please keep this window and send the error text above to the maintainer.
pause
exit /b 1

:end
echo.
echo App exited.
pause
exit /b 0
