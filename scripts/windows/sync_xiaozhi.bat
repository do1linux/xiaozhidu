@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1

rem ============================================================================
rem xiaozhi-esp32-server 上游同步（源码部署 / Windows 本机）
rem
rem   sync_xiaozhi.bat            同步一轮（默认）
rem   sync_xiaozhi.bat status     只看版本状态，不改代码
rem   sync_xiaozhi.bat install    注册任务计划（每 INTERVAL 分钟，需管理员）
rem   sync_xiaozhi.bat uninstall  删除该任务计划（需管理员）
rem
rem 上游 = xinnan-tech/xiaozhi-esp32-server（官方）。reset 只动 git 跟踪的
rem 代码；data/.config.yaml 与 models/model.pt 是你的私有数据，脚本额外做
rem 备份 + 校验，防止升级把它们冲掉。日志只记结论与短哈希，不记远端地址、
rem 密钥与用户数据。
rem
rem 可用环境变量覆盖下面的默认值（方便不改脚本）：
rem   XIAOZHI_DIR    git 仓库根目录
rem   SERVER_DIR     服务端工作目录（含 app.py / data / models）
rem   BRANCH         上游分支，默认 main
rem   XIAOZHI_SERVICE nssm 服务名；留空则只同步不重启
rem   INTERVAL       任务计划间隔分钟，默认 120
rem ============================================================================

if "%XIAOZHI_DIR%"==""         set "XIAOZHI_DIR=D:\ai-mcp\xiaozhi-esp32-server"
if "%SERVER_DIR%"==""          set "SERVER_DIR=%XIAOZHI_DIR%\main\xiaozhi-server"
if "%BRANCH%"==""              set "BRANCH=main"
if "%INTERVAL%"==""            set "INTERVAL=120"
rem 注意：SERVICE_NAME 不设默认值，避免误重启别的 nssm 服务；要重启请显式指定
set "UPSTREAM_URL=https://github.com/xinnan-tech/xiaozhi-esp32-server.git"
set "TASK_NAME=XiaoZhiUpstreamSync"

set "REPO=%~dp0..\.."
pushd "%REPO%" || (echo [ERROR] repo directory not found & exit /b 1)
set "REPO=%CD%"
set "LOG=%REPO%\logs\xiaozhi_sync.log"
if not exist "%REPO%\logs" mkdir "%REPO%\logs" 2>nul

set "CONFIG=%SERVER_DIR%\data\.config.yaml"
set "MODEL=%SERVER_DIR%\models\SenseVoiceSmall\model.pt"
set "REQUIREMENTS=%SERVER_DIR%\requirements.txt"
set "TPL=%SERVER_DIR%\config.yaml"
set "BAK=%XIAOZHI_DIR%\.sync_bak"

set "ACTION=%~1"
if "%ACTION%"=="" set "ACTION=sync"

if /i "%ACTION%"=="install"   goto :do_install
if /i "%ACTION%"=="uninstall" goto :do_uninstall
if /i "%ACTION%"=="status"    goto :do_status
if /i "%ACTION%"=="sync"      goto :do_sync

echo Usage: %~nx0 [sync^|status^|install^|uninstall]
popd
exit /b 64

:do_sync
call :sync
exit /b %errorlevel%

:do_status
call :status
exit /b %errorlevel%

:do_install
call :install
exit /b %errorlevel%

:do_uninstall
call :uninstall
exit /b %errorlevel%

rem ------------------------------------------------------------------ 同步主流程
:sync
call :log "===== start (branch %BRANCH%) ====="

if not exist "%XIAOZHI_DIR%\.git" (
  call :log "ERROR: 不是 git 仓库: %XIAOZHI_DIR%"
  exit /b 1
)
if not exist "%SERVER_DIR%" (
  call :log "ERROR: 服务端目录不存在: %SERVER_DIR%"
  exit /b 1
)

pushd "%XIAOZHI_DIR%" || (call :log "ERROR: 无法进入仓库目录" & exit /b 1)

rem upstream remote：没有才添加，已存在则尊重用户自定义的镜像地址
git remote get-url upstream >nul 2>&1
if errorlevel 1 git remote add upstream "%UPSTREAM_URL%" >nul 2>&1

for /f "delims=" %%i in ('git rev-parse HEAD 2^>nul') do set "OLD=%%i"
if "%OLD%"=="" (call :log "ERROR: 读取本地 HEAD 失败" & popd & exit /b 1)

rem stderr 一律丢弃：远端地址可能带凭据，不进日志
git fetch --prune upstream %BRANCH% --quiet >nul 2>&1
if errorlevel 1 (
  call :log "ERROR: fetch 失败（网络/权限），本轮放弃"
  popd & exit /b 1
)
for /f "delims=" %%i in ('git rev-parse "upstream/%BRANCH%" 2^>nul') do set "REMOTE=%%i"
if "%REMOTE%"=="" (
  call :log "ERROR: 无法解析 upstream/%BRANCH%"
  popd & exit /b 1
)

set "UPDATED=0"
if /i "%OLD%"=="%REMOTE%" (
  call :log "无更新（!REMOTE:~0,8!），跳过"
  goto :after_reset
)

rem --- 更新前：备份配置 + 记录受保护文件状态 ---
if exist "%CONFIG%" (
  if not exist "%BAK%" mkdir "%BAK%" 2>nul
  copy /Y "%CONFIG%" "%BAK%\config.yaml.bak" >nul 2>&1
  if errorlevel 1 (
    call :log "ERROR: 配置备份失败，中止以免丢配置"
    popd & exit /b 1
  )
)
set "MODEL_BEFORE=0"
if exist "%MODEL%" set "MODEL_BEFORE=1"
for /f "delims=" %%i in ('git hash-object "%TPL%" 2^>nul') do set "TPL_OLD=%%i"
for /f "delims=" %%i in ('git hash-object "%REQUIREMENTS%" 2^>nul') do set "REQ_OLD=%%i"

rem --- 拉取 + 硬重置到上游（只影响 git 跟踪的代码）---
git reset --hard "upstream/%BRANCH%" --quiet >nul 2>&1
if errorlevel 1 (
  call :log "ERROR: reset 失败，尝试恢复配置"
  if exist "%BAK%\config.yaml.bak" copy /Y "%BAK%\config.yaml.bak" "%CONFIG%" >nul 2>&1
  popd & exit /b 1
)
set "UPDATED=1"
call :log "已更新 !OLD:~0,8! -> !REMOTE:~0,8!"

rem --- 更新后：校验并恢复私有数据 ---
if exist "%BAK%\config.yaml.bak" (
  if not exist "%CONFIG%" (
    copy /Y "%BAK%\config.yaml.bak" "%CONFIG%" >nul 2>&1
    call :log "WARN: 配置在更新中丢失，已从备份恢复"
  )
)
if "%MODEL_BEFORE%"=="1" if not exist "%MODEL%" (
  call :log "ERROR: 语音模型丢失！请重新下载 model.pt 到 models\SenseVoiceSmall"
)

rem --- 配置模板 / 依赖清单变化：只提示，不自动合并（涉及密钥）---
for /f "delims=" %%i in ('git hash-object "%TPL%" 2^>nul') do set "TPL_NEW=%%i"
if not "%TPL_OLD%"=="%TPL_NEW%" (
  call :log "NOTE: 上游 config.yaml 模板已变，请核对 data\.config.yaml 是否需补新配置项"
)
for /f "delims=" %%i in ('git hash-object "%REQUIREMENTS%" 2^>nul') do set "REQ_NEW=%%i"
if not "%REQ_OLD%"=="%REQ_NEW%" (
  call :log "NOTE: 依赖清单已变，请在 xiaozhi 的环境执行 pip install -r requirements.txt"
)

:after_reset
popd

rem --- 可选：重启 nssm 服务（仅在有更新且服务存在时）---
if "%XIAOZHI_SERVICE%"=="" (
  call :log "未设 XIAOZHI_SERVICE，仅同步代码，不重启服务"
  goto :done
)
sc query "%XIAOZHI_SERVICE%" >nul 2>&1
if errorlevel 1 (
  call :log "NOTE: 服务 %XIAOZHI_SERVICE% 未安装，仅同步代码"
  goto :done
)
if "%UPDATED%"=="1" (
  net stop  "%XIAOZHI_SERVICE%" >nul 2>&1
  net start "%XIAOZHI_SERVICE%" >nul 2>&1
  if errorlevel 1 (
    call :log "WARN: 服务重启失败，请手动检查 %XIAOZHI_SERVICE%"
  ) else (
    call :log "服务已重启（!REMOTE:~0,8!）"
  )
) else (
  call :log "代码无更新，服务保持运行"
)

:done
call :log "===== done ====="
exit /b 0

rem ------------------------------------------------------------------ 状态查看
:status
if not exist "%XIAOZHI_DIR%\.git" (
  echo [ERROR] 不是 git 仓库: %XIAOZHI_DIR%
  exit /b 1
)
for /f "delims=" %%i in ('git -C "%XIAOZHI_DIR%" rev-parse HEAD 2^>nul') do echo 本地版本:    %%i
for /f "delims=" %%i in ('git -C "%XIAOZHI_DIR%" rev-parse "upstream/%BRANCH%" 2^>nul') do echo 上游版本:    %%i
git -C "%XIAOZHI_DIR%" remote get-url upstream 2>nul >nul && echo 上游 remote: 已配置 || echo 上游 remote: 未配置（首次 sync 会自动添加）
if exist "%CONFIG%" (echo 私有配置:    存在) else (echo 私有配置:    缺失)
if exist "%MODEL%"  (echo 语音模型:    存在) else (echo 语音模型:    缺失)
exit /b 0

rem ------------------------------------------------------------------ 任务计划
:install
net session >nul 2>&1
if errorlevel 1 (echo [ERROR] 需要管理员权限 & exit /b 1)
schtasks /Create /TN "%TASK_NAME%" /TR "\"%~f0\" sync" /SC MINUTE /MO %INTERVAL% /F /RL HIGHEST >nul 2>&1
if errorlevel 1 (echo [ERROR] 注册任务计划失败 & exit /b 1)
call :log "任务计划已注册: %TASK_NAME%，每 %INTERVAL% 分钟"
echo 已注册: %TASK_NAME%（每 %INTERVAL% 分钟，最高权限）
exit /b 0

:uninstall
net session >nul 2>&1
if errorlevel 1 (echo [ERROR] 需要管理员权限 & exit /b 1)
schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>&1
if errorlevel 1 (echo [NOTE] 任务计划不存在或删除失败 & exit /b 1)
echo 已删除: %TASK_NAME%
exit /b 0

rem ------------------------------------------------------------------ 日志
:log
echo [%date% %time%] %~1
echo [%date% %time%] %~1 >> "%LOG%"
exit /b 0
