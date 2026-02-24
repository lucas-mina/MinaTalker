@echo off
setlocal EnableDelayedExpansion

REM ========================================
REM Linly-Talker-Stream - Frontend startup (Windows)
REM Real-time streaming digital human dialogue
REM ========================================

REM Project root (parent of scripts folder)
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
for %%I in ("%SCRIPT_DIR%") do set "PROJECT_ROOT=%%~dpI"
set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
set "FRONTEND_DIR=%PROJECT_ROOT%\web"

REM Config file: first argument or default config_wav2lip.yaml
set "CONFIG_ARG=%~1"
if "%CONFIG_ARG%"=="" set "CONFIG_ARG=config/config_wav2lip.yaml"
set "CONFIG_FILE=%CONFIG_ARG%"

echo ========================================
echo   Linly-Talker-Stream - Frontend
echo   Real-time streaming digital human
echo ========================================
echo.

REM Check config exists
if not exist "%PROJECT_ROOT%\%CONFIG_FILE%" (
    echo [ERROR] Config file not found: %CONFIG_FILE%
    goto :show_usage
)
echo [OK] Config: %CONFIG_FILE%

REM Check Node.js
where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js not found. Install Node.js 16+ from https://nodejs.org/
    exit /b 1
)
for /f "tokens=*" %%v in ('node --version 2^>nul') do set NODE_VER=%%v
echo [OK] Node.js: !NODE_VER!

REM Check npm
where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] npm not found. It usually comes with Node.js.
    exit /b 1
)
for /f "tokens=*" %%v in ('npm --version 2^>nul') do set NPM_VER=%%v
echo [OK] npm: !NPM_VER!

REM Install dependencies if needed
pushd "%FRONTEND_DIR%"
if not exist "node_modules" (
    echo [INFO] Installing dependencies...
    call npm install
    if errorlevel 1 exit /b 1
    echo [OK] Dependencies installed.
) else (
    echo [OK] node_modules present.
)
popd

REM Check and free port 3000 (Windows)
set "PORT=3000"
echo Checking port %PORT%...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    set "PID=%%a"
    goto :kill_port
)
goto :port_ok
:kill_port
if defined PID (
    echo Port %PORT% in use by PID !PID!. Killing...
    taskkill /PID !PID! /F >nul 2>nul
    timeout /t 2 /nobreak >nul
    echo [OK] Port %PORT% freed.
)
:port_ok

REM Config basename for env (e.g. config\config_wav2lip.yaml -> config_wav2lip.yaml)
for %%F in ("%CONFIG_FILE%") do set "CONFIG_FILE_ENV=%%~nxF"

echo.
echo ========================================
echo   Starting Vite dev server...
echo ========================================
echo.
echo Local:  http://localhost:3000
echo Network: http://^<your-ip^>:3000
echo Config: %CONFIG_FILE_ENV%
echo Press Ctrl+C to stop.
echo.

pushd "%FRONTEND_DIR%"
set "CONFIG_FILE=%CONFIG_FILE_ENV%"
call npm run dev
popd
endlocal
goto :eof

:show_usage
echo Usage: %~nx0 [config_file]
echo.
echo Examples:
echo   %~nx0
echo   %~nx0 config/config_wav2lip.yaml
echo   %~nx0 config/config_musetalk.yaml
echo.
exit /b 1
