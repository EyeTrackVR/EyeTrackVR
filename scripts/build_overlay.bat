@echo off
setlocal EnableExtensions
REM ==========================================================================
REM  Build the calibration overlay from the overlay\ submodule into
REM  EyeTrackApp\Tools\ and stamp each folder with the commit it came from.
REM
REM    scripts\build_overlay.bat [windows|linux|arm64|all]   (default: all)
REM
REM    windows  overlay\build.bat (vcpkg)        -> EyeTrackApp\Tools\
REM    linux    WSL Ubuntu-22.04                 -> EyeTrackApp\Tools\linux\
REM    arm64    Docker ubuntu:24.04 arm64 (QEMU) -> EyeTrackApp\Tools\linux-arm64\
REM
REM  Bump the submodule first (cd overlay, git checkout <commit>), then run
REM  this and commit the submodule and Tools\ together.
REM ==========================================================================

cd /d "%~dp0.."
set "REPO_WIN=%CD%"
set "DISTRO=Ubuntu-22.04"
set "WHICH=%~1"
if "%WHICH%"=="" set "WHICH=all"

if not exist "overlay\CMakeLists.txt" (
    echo ERROR: overlay\ is empty; run: git submodule update --init overlay
    exit /b 1
)
if not exist "overlay\external\OpenVR\headers\openvr.h" (
    echo [overlay] fetching the overlay's OpenVR SDK submodule...
    git -C overlay submodule update --init --depth 1 external/OpenVR || exit /b 1
)

if /i "%WHICH%"=="windows" goto :windows
if /i "%WHICH%"=="linux" goto :linux
if /i "%WHICH%"=="arm64" goto :arm64
if /i "%WHICH%"=="all" goto :windows
echo Usage: scripts\build_overlay.bat [windows^|linux^|arm64^|all]
exit /b 1

:windows
echo.
echo [overlay] building for Windows...
call overlay\build.bat || exit /b 1
cd /d "%REPO_WIN%"
set "OUT=overlay\build\Release"
for %%f in (EyeTrackVR-Overlay.exe jsoncpp.dll openvr_api.dll openxr_loader.dll vulkan-1.dll) do (
    copy /y "%OUT%\%%f" "EyeTrackApp\Tools\" >nul || exit /b 1
)
copy /y "%OUT%\assets\OpenSans-Regular.ttf" "EyeTrackApp\Tools\assets\" >nul || exit /b 1
for /f %%c in ('git -C overlay rev-parse HEAD') do > "EyeTrackApp\Tools\OVERLAY_COMMIT" echo %%c
echo [overlay] Windows overlay installed into EyeTrackApp\Tools\
if /i not "%WHICH%"=="all" exit /b 0

:linux
echo.
echo [overlay] building for Linux x86_64 in WSL %DISTRO%...
for /f "delims=" %%p in ('wsl.exe -d %DISTRO% -- wslpath -a "%REPO_WIN%"') do set "REPO_WSL=%%p"
if not defined REPO_WSL (
    echo ERROR: WSL %DISTRO% is not available
    exit /b 1
)
wsl.exe -d %DISTRO% -u root -- bash -c "tr -d '\r' < '%REPO_WSL%/scripts/build_overlay.sh' | bash -s -- '%REPO_WSL%'" || exit /b 1
if /i not "%WHICH%"=="all" exit /b 0
REM Stopping the distro drops Docker Desktop's arm64 QEMU handler; see build_release.bat.
wsl.exe --terminate %DISTRO% >nul 2>&1

:arm64
echo.
echo [overlay] building for Linux arm64 in Docker (QEMU, slow)...
docker info >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker is not running - start Docker Desktop and retry
    exit /b 1
)
docker run --privileged --rm tonistiigi/binfmt@sha256:400a4873b838d1b89194d982c45e5fb3cda4593fbfd7e08a02e76b03b21166f0 --install arm64 >nul || exit /b 1
docker run --rm --platform linux/arm64 -v "%REPO_WIN%:/repo" ubuntu:24.04 bash -c "export DEBIAN_FRONTEND=noninteractive && apt-get update -qq && apt-get install -y -qq --no-install-recommends build-essential cmake ninja-build libvulkan-dev libopenxr-dev libstb-dev patchelf git curl ca-certificates >/dev/null && tr -d '\r' < /repo/scripts/build_overlay.sh | bash -s -- /repo" || exit /b 1
exit /b 0
