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
  echo [ERROR] 未找到 Python。请先安装 Python 3.10 或更高版本，并勾选 Add python.exe to PATH。
  goto :error
)

if not exist "app.py" (
  echo [ERROR] 未找到 app.py。请把本脚本放在项目根目录后再运行。
  goto :error
)

if not exist "requirements.txt" (
  echo [ERROR] 未找到 requirements.txt。请确认项目文件完整。
  goto :error
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] 正在创建虚拟环境...
  %PYEXE% -m venv .venv
  if errorlevel 1 goto :error
)

echo [2/4] 正在升级 pip...
call ".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error

echo [3/4] 正在安装/更新依赖...
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [4/4] 正在启动微博超话周报工具...
echo.
echo 命令行会实时滚动输出后台日志；结束时可按 Ctrl+C。
echo.
call ".venv\Scripts\python.exe" app.py
if errorlevel 1 goto :error

goto :end

:error
echo.
echo 运行失败。请保留这个窗口，并把上面的错误信息发给维护者。
pause
exit /b 1

:end
echo.
echo 程序已退出。
pause
exit /b 0
