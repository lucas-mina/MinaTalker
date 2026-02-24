@echo off
setlocal EnableDelayedExpansion

REM ========================================
REM Linly-Talker-Stream - Full stack startup script
REM Real-time streaming digital human (Windows)
REM ========================================

REM Project root (parent of script dir)
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
for %%I in ("%SCRIPT_DIR%\..") do set "PROJECT_ROOT=%%~fI"
set "FRONTEND_DIR=%PROJECT_ROOT%\web"

REM Config file (first arg or default)
if "%~1"=="" (
    set "CONFIG_FILE=config\config_talkinggaussian.yaml"
) else (
    set "CONFIG_FILE=%~1"
)

if "%~1"=="--help" goto do_usage
if "%~1"=="/?" goto do_usage

REM Process PIDs
set "BACKEND_PID="
set "FRONTEND_PID="

echo ========================================
echo  Linly-Talker-Stream - Starting services
echo    Real-time streaming digital human
echo ========================================
echo.

goto :run_main

REM Usage (--help / ?)
:do_usage
echo Usage:
echo   %~nx0 [config_file]
echo.
echo Examples:
echo   %~nx0                           # default config (talkinggaussian)
echo   %~nx0 config\config_wav2lip.yaml
echo   %~nx0 config\config_musetalk.yaml
echo   %~nx0 config\config_ernerf.yaml
echo.
endlocal
exit /b 0

REM Cleanup: stop all services
:cleanup
echo.
echo Stopping all services...

if defined BACKEND_PID (
    taskkill /PID %BACKEND_PID% /F >nul 2>&1
    if not errorlevel 1 echo   Backend stopped (PID: %BACKEND_PID%)
)

if defined FRONTEND_PID (
    taskkill /PID %FRONTEND_PID% /F >nul 2>&1
    if not errorlevel 1 echo   Frontend stopped (PID: %FRONTEND_PID%)
)

echo All services stopped.
exit /b 0

REM Check config file
:check_config
if not exist "%PROJECT_ROOT%\%CONFIG_FILE%" (
    echo Error: Config file not found: %CONFIG_FILE%
    echo.
    call :do_usage
    exit /b 1
)
echo [OK] Config: %CONFIG_FILE%
exit /b 0

REM Check system dependencies
:check_system_dependencies
echo Checking dependencies...

where uv >nul 2>&1
if errorlevel 1 (
    echo Error: uv not found.
    echo Install uv: https://docs.astral.sh/uv/getting-started/installation/
    exit /b 1
)
for /f "tokens=*" %%v in ('uv --version 2^>nul') do set UV_VER=%%v
echo [OK] uv: !UV_VER!

where node >nul 2>&1
if errorlevel 1 (
    echo Error: Node.js not found.
    echo Install Node.js 16+: https://nodejs.org/
    exit /b 1
)
for /f "tokens=*" %%v in ('node --version 2^>nul') do set NODE_VER=%%v
echo [OK] Node.js: !NODE_VER!

where npm >nul 2>&1
if errorlevel 1 (
    echo Error: npm not found. It usually comes with Node.js.
    exit /b 1
)
for /f "tokens=*" %%v in ('npm --version 2^>nul') do set NPM_VER=%%v
echo [OK] npm: !NPM_VER!
echo.
exit /b 0

REM Setup backend
:setup_backend
echo Preparing backend...

if not exist "%PROJECT_ROOT%\.venv" (
    echo Error: Virtual env '.venv' not found.
    echo Run: uv venv --python 3.10.19
    exit /b 1
)
echo [OK] .venv found

cd /d "%PROJECT_ROOT%"
for /f "tokens=*" %%v in ('uv run python --version 2^>nul') do set PY_VER=%%v
echo [OK] Python: !PY_VER!
echo.
exit /b 0

REM Setup frontend
:setup_frontend
echo Preparing frontend...

cd /d "%FRONTEND_DIR%"
if not exist "node_modules" (
    echo Installing dependencies...
    call npm install
    if errorlevel 1 exit /b 1
    echo [OK] Dependencies installed
) else (
    echo [OK] node_modules ready
)
cd /d "%PROJECT_ROOT%"
echo.
exit /b 0

REM Check and free port (args: port, service name)
:check_and_kill_port
set "PORT=%~1"
set "SVC=%~2"
echo Checking port %PORT% (%SVC%)...

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    echo Port %PORT% in use by PID %%a, killing...
    taskkill /PID %%a /F >nul 2>&1
    timeout /t 2 /nobreak >nul
    goto :port_check_after
)
echo [OK] Port %PORT% free
exit /b 0

:port_check_after
for /f "tokens=5" %%b in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    echo Failed to free port %PORT%
    exit /b 1
)
echo [OK] Port %PORT% cleared
exit /b 0

REM Start backend
:start_backend
echo Starting backend...

cd /d "%PROJECT_ROOT%"
call :check_and_kill_port 8010 Backend
if errorlevel 1 exit /b 1

echo Backend: http://localhost:8010

start /B "" uv run python src/server/app.py --config "%CONFIG_FILE%"
timeout /t 3 /nobreak >nul

set "BACKEND_PID="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8010 " ^| findstr "LISTENING"') do (
    set "BACKEND_PID=%%a"
    goto :backend_pid_done
)
:backend_pid_done

if not defined BACKEND_PID (
    echo Backend failed to start.
    exit /b 1
)
echo [OK] Backend started (PID: %BACKEND_PID%)
echo.
exit /b 0

REM Start frontend (basename from CONFIG_FILE path)
:start_frontend
echo Starting frontend...

cd /d "%FRONTEND_DIR%"
call :check_and_kill_port 3000 Frontend
if errorlevel 1 exit /b 1

echo Frontend:
echo    Local:  http://localhost:3000
echo    Network: http://^<your-ip^>:3000

for %%F in ("%CONFIG_FILE%") do set "CONFIG_BASENAME=%%~nF"
set "CONFIG_ENV=!CONFIG_BASENAME!.yaml"
echo Config: !CONFIG_ENV!

REM Start Vite with CONFIG_FILE in child process
start /B "" cmd /c "set CONFIG_FILE=!CONFIG_ENV! && cd /d "%FRONTEND_DIR%" && npm run dev"
timeout /t 3 /nobreak >nul

set "FRONTEND_PID="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000 " ^| findstr "LISTENING"') do (
    set "FRONTEND_PID=%%a"
    goto :frontend_pid_done
)
:frontend_pid_done

if not defined FRONTEND_PID (
    echo Frontend failed to start.
    call :cleanup
    exit /b 1
)
echo [OK] Frontend started (PID: %FRONTEND_PID%)
cd /d "%PROJECT_ROOT%"
echo.
exit /b 0

REM ========== Main ==========
:main
cd /d "%PROJECT_ROOT%"

call :check_config
if errorlevel 1 exit /b 1

call :check_system_dependencies
if errorlevel 1 exit /b 1

call :setup_backend
if errorlevel 1 exit /b 1

call :setup_frontend
if errorlevel 1 exit /b 1

call :start_backend
if errorlevel 1 exit /b 1

call :start_frontend
if errorlevel 1 exit /b 1

echo ========================================
echo All services started.
echo ========================================
echo.
echo Backend:  http://localhost:8010
echo Frontend: http://localhost:3000
echo.
echo Press any key to stop all services...
pause >nul

call :cleanup
exit /b 0

REM Run main
:run_main
call :main
if errorlevel 1 exit /b 1
endlocal
exit /b 0
