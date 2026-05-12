@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0.."

echo [clean_generated] Cleaning Python and test caches...
for /d /r %%D in (__pycache__) do (
  if exist "%%D" rmdir /s /q "%%D"
)
if exist ".pytest_cache" rmdir /s /q ".pytest_cache"
if exist ".ruff_cache" rmdir /s /q ".ruff_cache"
if exist "dist\release_stage" rmdir /s /q "dist\release_stage"

set /p CLEAN_OUTPUT=Clean output directory? This deletes exported reports and cache. [y/N] 
if /i "%CLEAN_OUTPUT%"=="y" (
  if exist "output" rmdir /s /q "output"
) else (
  echo [clean_generated] output directory kept.
)

echo [clean_generated] Done. weibo_stats_config.json is never removed.
exit /b 0
