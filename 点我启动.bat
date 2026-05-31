@echo off
setlocal
cd /d "%~dp0"

set "PYEXE="

where py >nul 2>nul
if not errorlevel 1 (
  py -3 --version >nul 2>nul
  if not errorlevel 1 set "PYEXE=py -3"
)

if not defined PYEXE (
  where python >nul 2>nul
  if not errorlevel 1 (
    python --version >nul 2>nul
    if not errorlevel 1 set "PYEXE=python"
  )
)

if not defined PYEXE (
  echo [ERROR] Python 3.10+ was not found.
  echo Please install Python 3.10+ first, and tick "Add python.exe to PATH" during installation.
  echo Download: https://www.python.org/downloads/
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

if exist ".venv\Scripts\python.exe" (
  call ".venv\Scripts\python.exe" --version >nul 2>nul
  if errorlevel 1 (
    echo [1/4] Existing virtual environment is broken. Rebuilding...
    rmdir /s /q ".venv"
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] Creating virtual environment...
  %PYEXE% -m venv .venv
  if errorlevel 1 goto :error
) else (
  echo [1/4] Virtual environment OK.
)

echo [2/4] Upgrading pip...
call ".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error

echo [3/4] Installing/updating dependencies...
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [4/4] Starting Weibo Super Topic Weekly Tool...
echo.
echo Backend logs will appear in this window. Press Ctrl+C to stop.
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
