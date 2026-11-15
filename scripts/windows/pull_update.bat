@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1

rem Windows pull-mode updater. Repo root is derived from this script's location,
rem so no drive letter is hard-coded. Run from Task Scheduler with highest privileges.
set "REPO=%~dp0..\.."
pushd "%REPO%" || (echo [ERROR] repo directory not found & exit /b 1)
set "REPO=%CD%"

if not exist "%REPO%\logs" mkdir "%REPO%\logs" 2>nul
set "LOG=%REPO%\logs\pull.log"

set "BRANCH=%~1"
if "%BRANCH%"=="" (
  for /f "delims=" %%i in ('git symbolic-ref --short HEAD 2^>nul') do set "BRANCH=%%i"
)
if "%BRANCH%"=="" set "BRANCH=main"

net session >nul 2>&1
if errorlevel 1 call :log "WARN: no admin rights; service restart will fail"

call :log "===== start (branch %BRANCH%) ====="
for /f "delims=" %%i in ('git rev-parse HEAD 2^>nul') do set "OLD=%%i"

rem git stderr is discarded on purpose: remote URL may embed a token.
git fetch --prune origin %BRANCH% --quiet >nul 2>&1
if errorlevel 1 (
  call :log "fetch failed (network or credential), skip this round"
  popd & exit /b 1
)
for /f "delims=" %%i in ('git rev-parse "origin/%BRANCH%" 2^>nul') do set "REMOTE=%%i"
if "%REMOTE%"=="" (
  call :log "cannot resolve origin/%BRANCH%, skip this round"
  popd & exit /b 1
)

if /i "!OLD!"=="!REMOTE!" (
  call :log "no update (!REMOTE:~0,8!), skip restart"
) else (
  git reset --hard "origin/%BRANCH%" --quiet >nul 2>&1
  if errorlevel 1 (
    call :log "reset failed, skip this round"
    popd & exit /b 1
  )
  call :log "update !OLD:~0,8! -> !REMOTE:~0,8!, restart services"
  net stop VbXiaoai  >nul 2>&1
  net stop VbBridge  >nul 2>&1
  net start VbBridge >nul 2>&1
  net start VbXiaoai >nul 2>&1
)
call :log "===== done ====="
popd
exit /b 0

:log
echo [%date% %time%] %~1
echo [%date% %time%] %~1 >> "%LOG%"
exit /b 0
