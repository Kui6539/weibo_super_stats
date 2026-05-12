@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0.."

set "VERSION=0.10.0"
set "ZIP_NAME=weibo_super_stats_v%VERSION%.zip"
set "DIST_DIR=%CD%\dist"
set "STAGE=%TEMP%\weibo_super_stats_release_%RANDOM%_%RANDOM%"

if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"
if exist "%STAGE%" rmdir /s /q "%STAGE%"
mkdir "%STAGE%"

echo [make_release_zip] Preparing release staging directory...
set "WEIBO_STAGE=%STAGE%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$stage=$env:WEIBO_STAGE; @('app.py','crawler.py','cookie_helper.py','README.md','requirements.txt') | ForEach-Object { if (Test-Path -LiteralPath $_) { Copy-Item -LiteralPath $_ -Destination $stage -Force } }; Get-ChildItem -LiteralPath . -Filter '*.bat' -File | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $stage -Force }"
if errorlevel 1 (
  echo [make_release_zip] Failed to copy root files.
  rmdir /s /q "%STAGE%"
  exit /b 1
)

for %%D in (core server modules export web tests scripts docs) do (
  if exist "%%D" robocopy "%%D" "%STAGE%\%%D" /E /XD __pycache__ .pytest_cache .ruff_cache /XF *.pyc *.pyo *.log >nul
  if errorlevel 8 (
    echo [make_release_zip] Failed to copy %%D.
    rmdir /s /q "%STAGE%"
    exit /b 1
  )
)

if exist "%DIST_DIR%\%ZIP_NAME%" del /q "%DIST_DIR%\%ZIP_NAME%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path '%STAGE%\*' -DestinationPath '%DIST_DIR%\%ZIP_NAME%' -Force"
set "ZIP_RESULT=%ERRORLEVEL%"
rmdir /s /q "%STAGE%"

if not "%ZIP_RESULT%"=="0" (
  echo [make_release_zip] Zip failed.
  exit /b %ZIP_RESULT%
)

echo [make_release_zip] Created: %DIST_DIR%\%ZIP_NAME%
echo [make_release_zip] Excluded .git, .venv, output, local config, CDP profiles and caches.
exit /b 0
