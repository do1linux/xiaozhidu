@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1

rem One-time Windows setup: venv + deps + two nssm services.
rem Run as Administrator. nssm must be on PATH.
set "REPO=%~dp0..\.."
pushd "%REPO%" || (echo [ERROR] repo directory not found & exit /b 1)
set "REPO=%CD%"
set "VENV=%REPO%\.venv"
set "PY=%VENV%\Scripts\python.exe"

net session >nul 2>&1
if errorlevel 1 (echo [ERROR] Please run as Administrator & popd & exit /b 1)

where nssm >nul 2>&1
if errorlevel 1 (echo [ERROR] nssm not found in PATH & popd & exit /b 1)

if not exist "%REPO%\logs" mkdir "%REPO%\logs" 2>nul

if not exist "%PY%" (
  echo [1/4] Creating venv ...
  where py >nul 2>&1
  if errorlevel 1 (
    python -m venv "%VENV%"
  ) else (
    py -3 -m venv "%VENV%"
  )
)
if not exist "%PY%" (echo [ERROR] Python 3.10+ not found & popd & exit /b 1)

echo [2/4] Installing dependencies ...
"%PY%" -m pip install --disable-pip-version-check -q -i https://pypi.tuna.tsinghua.edu.cn/simple -r "%REPO%\bridge\requirements.txt" -r "%REPO%\bot\requirements.txt"
if errorlevel 1 (echo [ERROR] pip install failed & popd & exit /b 1)

if not exist "%REPO%\.env" copy "%REPO%\.env.example" "%REPO%\.env" >nul
if not exist "%REPO%\config\xiaogpt.yaml" copy "%REPO%\config\xiaogpt.yaml.example" "%REPO%\config\xiaogpt.yaml" >nul

echo [3/4] Registering services ...
nssm install VbBridge "%PY%" "%REPO%\scripts\run_bridge.py"
nssm set VbBridge AppDirectory "%REPO%\bridge" >nul
nssm set VbBridge AppStdout "%REPO%\logs\bridge.out.log" >nul
nssm set VbBridge AppStderr "%REPO%\logs\bridge.err.log" >nul
nssm set VbBridge Start SERVICE_AUTO_START >nul

nssm install VbXiaoai "%PY%" "%REPO%\bot\xiaoai_bot.py" --config "%REPO%\config\xiaogpt.yaml"
nssm set VbXiaoai AppDirectory "%REPO%\bot" >nul
nssm set VbXiaoai AppStdout "%REPO%\logs\xiaoai.out.log" >nul
nssm set VbXiaoai AppStderr "%REPO%\logs\xiaoai.err.log" >nul
nssm set VbXiaoai Start SERVICE_AUTO_START >nul
nssm set VbXiaoai DependOnService VbBridge >nul

echo.
echo [4/4] Registered. This script does NOT fill in secrets. Next steps:
echo   1. Edit  %REPO%\.env                  (NEWAPI_KEY, XIAOZHI_WS_URL)
echo   2. Edit  %REPO%\config\xiaogpt.yaml   (Mi account, password, hardware)
echo   3. Login check:
echo      "%PY%" "%REPO%\bot\xiaoai_bot.py" --check --config "%REPO%\config\xiaogpt.yaml"
echo   4. Start:  nssm start VbBridge   then   nssm start VbXiaoai
echo   5. Health: curl http://127.0.0.1:8100/healthz
echo   6. Task Scheduler: run scripts\windows\pull_update.bat every 30/60 min
echo.
popd
exit /b 0
