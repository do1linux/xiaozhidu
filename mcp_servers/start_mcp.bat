@echo off
setlocal
rem Start one free MCP server and connect it to the xiaozhi SERVER MCP endpoint.
rem No Xiaozhi speaker / ESP32 hardware is involved.
rem Usage: start_mcp.bat [free_tools.py|fetch_lite.py]

set "REPO=%~dp0.."
pushd "%REPO%" || (echo [ERROR] repo directory not found & exit /b 1)

set "VENV=%REPO%\.venv\Scripts"
if not exist "%VENV%\python.exe" (
    echo [ERROR] venv python not found: %VENV%\python.exe
    echo         Run scripts\windows\install_services.bat first.
    popd
    exit /b 1
)

rem mcp_pipe.py spawns the child with the literal command "python".
rem Put the venv first in PATH so that "python" resolves to this venv.
set "PATH=%VENV%;%PATH%"

set "SCRIPT=%~dp0free_tools.py"
if not "%~1"=="" set "SCRIPT=%~dp0%~1"
if not exist "%SCRIPT%" (
    echo [ERROR] script not found: %SCRIPT%
    popd
    exit /b 1
)

if "%MCP_ENDPOINT%"=="" (
    echo [WARN] MCP_ENDPOINT not in environment; mcp_pipe.py will try .env under %REPO%
)

"%VENV%\python.exe" "%REPO%\mcp_pipe.py" "%SCRIPT%"
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
