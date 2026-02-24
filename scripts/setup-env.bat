@echo off
setlocal EnableDelayedExpansion

:: ========================================
:: Linly-Talker-Stream - Environment setup (Windows)
:: ========================================

chcp 65001 >nul 2>&1

set "PROJECT_ROOT=%~dp0.."
set "PYTHON_VERSION=3.10"
set "DEFAULT_AVATAR=%~1"
if "%DEFAULT_AVATAR%"=="" set "DEFAULT_AVATAR=wav2lip"

echo.
echo ========================================
echo   Linly-Talker-Stream - Environment setup
echo ========================================
echo.

:: Show usage
if "%~1"=="--help" goto :usage
if "%~1"=="-h" goto :usage

:: Validate avatar
if "%DEFAULT_AVATAR%"=="wav2lip" goto :avatar_ok
if "%DEFAULT_AVATAR%"=="musetalk" goto :avatar_ok
if "%DEFAULT_AVATAR%"=="ernerf" goto :avatar_ok
if "%DEFAULT_AVATAR%"=="talkinggaussian" goto :avatar_ok
echo [ERROR] Unsupported avatar: %DEFAULT_AVATAR%
goto :usage

:avatar_ok
echo [OK] Selected avatar: %DEFAULT_AVATAR%
echo.

:: Check uv
echo [*] Checking uv...
where uv >nul 2>&1
if errorlevel 1 (
    echo [ERROR] uv not found.
    echo Install uv: https://docs.astral.sh/uv/getting-started/installation/
    echo On Windows: powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 ^| iex"
    exit /b 1
)
for /f "tokens=*" %%v in ('uv --version 2^>nul') do set UV_VER=%%v
echo [OK] uv: !UV_VER!
echo.

:: Check Python (uv will use its own Python if needed)
echo [*] Checking Python...
where python >nul 2>&1
if errorlevel 1 (
    echo [INFO] No system Python found; uv will download Python if needed.
) else (
    for /f "tokens=*" %%p in ('python --version 2^>^&1') do echo [OK] %%p
)
echo.

:: Create venv
echo [*] Setting up virtual environment...
cd /d "%PROJECT_ROOT%"
if exist ".venv" (
    set /p RECREATE=".venv already exists. Recreate? (y/N): "
    if /i "!RECREATE!"=="y" (
        echo Removing existing .venv...
        rmdir /s /q .venv
    ) else (
        echo [OK] Using existing .venv
        goto :core_deps
    )
)
echo Creating new .venv...
uv venv --python %PYTHON_VERSION%
if errorlevel 1 (
    uv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv
        exit /b 1
    )
)
echo [OK] Virtual environment ready
echo.

:core_deps
echo [*] Installing core dependencies...
uv sync
if errorlevel 1 (
    echo [ERROR] uv sync failed
    exit /b 1
)
echo [OK] Core dependencies installed
echo.

:: Install avatar
echo [*] Installing %DEFAULT_AVATAR% avatar...
set "AVATAR_PATH=src\avatars\%DEFAULT_AVATAR%"
if not exist "%AVATAR_PATH%" (
    echo [ERROR] Avatar path not found: %AVATAR_PATH%
    exit /b 1
)

if "%DEFAULT_AVATAR%"=="musetalk" goto :install_musetalk
if "%DEFAULT_AVATAR%"=="talkinggaussian" goto :install_talkinggaussian

:: Standard avatar (wav2lip, ernerf)
uv pip install -e "%AVATAR_PATH%"
if errorlevel 1 (
    echo [ERROR] Failed to install %DEFAULT_AVATAR%
    exit /b 1
)
goto :avatar_done

:install_musetalk
echo [*] Installing MuseTalk dependencies...
uv pip install chumpy==0.70 --no-build-isolation
uv pip install -e "%AVATAR_PATH%"
uv run mim install mmengine
uv run mim install mmcv==2.2.0 --no-build-isolation
uv run mim install mmdet==3.1.0
uv run mim install mmpose==1.3.2
if exist "scripts\post_musetalk_install.bat" (
    call scripts\post_musetalk_install.bat
) else (
    echo [INFO] Run scripts\post_musetalk_install.sh in Git Bash if you use MuseTalk and see mmcv/mmdet errors.
)
goto :avatar_done

:install_talkinggaussian
uv pip install -e "%AVATAR_PATH%"
echo [*] Installing TalkingGaussian submodules...
uv pip install -e src\avatars\talkinggaussian\submodules\diff-gaussian-rasterization\ --no-build-isolation
uv pip install -e src\avatars\talkinggaussian\submodules\simple-knn\ --no-build-isolation
uv pip install -e src\avatars\talkinggaussian\gridencoder\ --no-build-isolation
goto :avatar_done

:avatar_done
echo [OK] %DEFAULT_AVATAR% avatar installed
echo.

:: Frontend
echo [*] Installing frontend dependencies...
where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Install from https://nodejs.org/
    exit /b 1
)
for /f "tokens=*" %%n in ('node --version 2^>nul') do echo [OK] Node %%n
where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm not found
    exit /b 1
)
cd /d "%PROJECT_ROOT%\web"
npm install
if errorlevel 1 (
    echo [ERROR] npm install failed
    exit /b 1
)
cd /d "%PROJECT_ROOT%"
echo [OK] Frontend dependencies installed
echo.

:: Verify
echo [*] Verifying...
cd /d "%PROJECT_ROOT%"
if not exist ".venv" (
    echo [ERROR] .venv missing
    exit /b 1
)
for /f "tokens=*" %%a in ('uv run python --version 2^>^&1') do echo [OK] %%a
set "CONFIG_FILE=config\config_%DEFAULT_AVATAR%.yaml"
if exist "!CONFIG_FILE!" (
    echo [OK] Config: !CONFIG_FILE!
) else (
    echo [WARN] Config not found: !CONFIG_FILE!
)
if exist "web\node_modules" (
    echo [OK] Frontend node_modules present
) else (
    echo [WARN] Frontend node_modules missing
)
echo.

:: Done
echo ========================================
echo   Setup complete.
echo ========================================
echo.
echo Next steps:
echo   1. Set API key (if using online LLM):
echo      set DASHSCOPE_API_KEY=your_api_key_here
echo.
echo   2. Start services:
echo      scripts\start-all.bat config\config_%DEFAULT_AVATAR%.yaml
echo.
echo   3. Or start separately:
echo      scripts\start-backend.bat config\config_%DEFAULT_AVATAR%.yaml
echo      scripts\start-frontend.bat config\config_%DEFAULT_AVATAR%.yaml
echo.
echo   4. Open: http://localhost:3000
echo.
exit /b 0

:usage
echo Usage: %~nx0 [avatar_name]
echo.
echo Supported avatars:
echo   wav2lip          - 2D (default)
echo   musetalk         - 2D
echo   ernerf           - 3D
echo   talkinggaussian  - 3D
echo.
echo Examples:
echo   %~nx0              # install wav2lip
echo   %~nx0 musetalk     # install musetalk
echo.
exit /b 0
