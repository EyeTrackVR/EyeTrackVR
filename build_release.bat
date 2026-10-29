@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM ==========================================================================
REM  EyeTrackVR one-shot release builder
REM
REM    1. Reads version.txt and stamps it into the app + Inno installer
REM    2. Builds the Windows app (PyInstaller) and installer (Inno Setup)
REM    3. Builds the Linux tarball inside WSL (Ubuntu-22.04, auto-installed)
REM    4. Builds the Steam Frame zip + FrameDrop manifest in an arm64 Docker
REM       container (Docker Desktop must be running; QEMU-emulated, slow)
REM    5. Collects everything + SHA256SUMS into release\<version>\
REM
REM  Update version.txt, double-click this file, upload release\<version>\*
REM ==========================================================================

cd /d "%~dp0"
set "REPO_WIN=%~dp0"
set "REPO_WIN=%REPO_WIN:~0,-1%"
set "DISTRO=Ubuntu-22.04"
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"

echo.
echo [1/6] Stamping version from version.txt ...
set "VERSION="
set "SAFEVERSION="
for /f "usebackq delims=" %%v in (`python scripts\apply_version.py`) do (
    if not defined VERSION ( set "VERSION=%%v" ) else if not defined SAFEVERSION set "SAFEVERSION=%%v"
)
if not defined SAFEVERSION (
    echo ERROR: could not read version from version.txt
    goto :fail
)
set "RELEASE_DIR=%REPO_WIN%\release\%SAFEVERSION%"
echo     version: "%VERSION%"  (files: %SAFEVERSION%)

echo.
echo [2/6] Building Windows app with PyInstaller ...
pushd eyetrackapp
poetry run pyinstaller eyetrackapp.spec --noconfirm
if errorlevel 1 ( popd & goto :fail )
popd
if not exist "eyetrackapp\dist\eyetrackapp.exe" (
    echo ERROR: eyetrackapp.exe missing after PyInstaller build
    goto :fail
)

echo.
echo [2b/6] Building SteamVR gaze driver ...
REM Shipped beside the exe (not inside it: the onefile exe unpacks to a temp folder,
REM and SteamVR needs a stable path). The app registers it when foveation gaze is on.
cmake -S steamvr_driver -B build\steamvr_driver -A x64 >nul
if errorlevel 1 goto :fail
cmake --build build\steamvr_driver --config Release
if errorlevel 1 goto :fail
if exist "eyetrackapp\dist\steamvr_driver" rmdir /s /q "eyetrackapp\dist\steamvr_driver"
xcopy /e /i /q /y "build\steamvr_driver\eyetrackvr" "eyetrackapp\dist\steamvr_driver\eyetrackvr" >nul
if errorlevel 1 goto :fail
if not exist "eyetrackapp\dist\steamvr_driver\eyetrackvr\bin\win64\driver_eyetrackvr.dll" (
    echo ERROR: driver_eyetrackvr.dll missing after the driver build
    goto :fail
)

echo.
echo [2c/6] Building OpenXR eye gaze layer ...
REM Also beside the exe; the app installs it as an implicit OpenXR layer when foveation gaze is on.
cmake -S openxr_layer -B build\openxr_layer -A x64 >nul
if errorlevel 1 goto :fail
cmake --build build\openxr_layer --config Release
if errorlevel 1 goto :fail
if exist "eyetrackapp\dist\openxr_layer" rmdir /s /q "eyetrackapp\dist\openxr_layer"
xcopy /e /i /q /y "build\openxr_layer\eyetrackvr_openxr_layer" "eyetrackapp\dist\openxr_layer" >nul
if errorlevel 1 goto :fail
if not exist "eyetrackapp\dist\openxr_layer\XR_APILAYER_EYETRACKVR_eye_gaze.dll" (
    echo ERROR: XR_APILAYER_EYETRACKVR_eye_gaze.dll missing after the layer build
    goto :fail
)

echo.
echo [3/6] Building Windows installer with Inno Setup ...
if not exist "%ISCC%" (
    echo ERROR: Inno Setup 6 not found at "%ISCC%"
    goto :fail
)
"%ISCC%" /Qp "eyetrackapp\INNO\ETVR_SETUP.iss"
if errorlevel 1 goto :fail

echo.
echo [4/6] Building Linux tarball in WSL ^(%DISTRO%^) ...
wsl.exe -d %DISTRO% -u root -- true >nul 2>&1
if errorlevel 1 (
    echo     %DISTRO% is not installed - installing it now ^(one-time, ~600 MB^) ...
    wsl.exe --install %DISTRO% --no-launch
    if errorlevel 1 goto :fail
)
set "REPO_WSL="
for /f "usebackq delims=" %%p in (`wsl.exe -d %DISTRO% -u root -- wslpath -a "%REPO_WIN%"`) do set "REPO_WSL=%%p"
if not defined REPO_WSL (
    echo ERROR: could not translate repo path with wslpath
    goto :fail
)
wsl.exe -d %DISTRO% -u root -- bash -c "tr -d '\r' < '%REPO_WSL%/scripts/wsl_entry.sh' | bash -s -- '%VERSION%' '%SAFEVERSION%' '%REPO_WSL%'"
if errorlevel 1 goto :fail
REM When the distro stops (it idles out ~20 s after the last command) every
REM binfmt_misc registration in the WSL kernel is dropped, including Docker
REM Desktop's arm64 QEMU handler. Stop it now so that can't happen mid-way
REM through the Frame build, which then fails with "Exec format error".
wsl.exe --terminate %DISTRO% >nul 2>&1

echo.
echo [5/6] Building Steam Frame zip in arm64 Docker ...
docker info >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker is not running - start Docker Desktop and retry
    goto :fail
)
REM (Re)register arm64 QEMU emulation; see the wsl --terminate note above.
docker run --privileged --rm tonistiigi/binfmt@sha256:400a4873b838d1b89194d982c45e5fb3cda4593fbfd7e08a02e76b03b21166f0 --install arm64 >nul
if errorlevel 1 goto :fail
docker run --rm --platform linux/arm64 ubuntu:24.04 true
if errorlevel 1 (
    echo ERROR: arm64 emulation is not working in Docker Desktop
    goto :fail
)
docker build --platform linux/arm64 -t etvr-frame-builder "scripts\frame"
if errorlevel 1 goto :fail
REM The etvr-frame-cache volume keeps Python and the pip cache between builds.
docker run --rm --platform linux/arm64 -v "%REPO_WIN%:/repo" -v etvr-frame-cache:/root/etvr-frame-build etvr-frame-builder bash -c "tr -d '\r' < /repo/scripts/build_frame.sh | bash -s -- '%VERSION%' '%SAFEVERSION%' /repo '/repo/release/%SAFEVERSION%'"
if errorlevel 1 goto :fail

echo.
echo [6/6] Collecting artifacts into release\%SAFEVERSION% ...
if not exist "%RELEASE_DIR%" mkdir "%RELEASE_DIR%"
copy /y "eyetrackapp\INNO\Output\EyeTrackVR-Setup-%SAFEVERSION%.exe" "%RELEASE_DIR%\" >nul
if errorlevel 1 (
    echo ERROR: installer not found in eyetrackapp\INNO\Output
    goto :fail
)
if not exist "%RELEASE_DIR%\EyeTrackVR-%SAFEVERSION%-linux-x86_64.tar.gz" (
    echo ERROR: Linux tarball missing from %RELEASE_DIR%
    goto :fail
)
if not exist "%RELEASE_DIR%\EyeTrackVR-%SAFEVERSION%-steamframe-arm64.zip" (
    echo ERROR: Steam Frame zip missing from %RELEASE_DIR%
    goto :fail
)
del /q "%RELEASE_DIR%\SHA256SUMS.txt" 2>nul
powershell -NoProfile -Command "Get-ChildItem -LiteralPath '%RELEASE_DIR%' -File | Where-Object Name -ne 'SHA256SUMS.txt' | Get-FileHash -Algorithm SHA256 | ForEach-Object { '{0}  {1}' -f $_.Hash.ToLower(), (Split-Path $_.Path -Leaf) } | Set-Content -Encoding ascii '%RELEASE_DIR%\SHA256SUMS.txt'"
if errorlevel 1 goto :fail

echo.
echo ==========================================================================
echo  DONE - upload these to the GitHub release:
echo ==========================================================================
dir /b "%RELEASE_DIR%"
echo.
echo  Tag the release EyeTrackApp-%SAFEVERSION% so the FrameDrop manifest URLs
echo  resolve; the Install with FrameDrop link is printed as FRAMEDROP_LINK above.
echo.
echo  Reminder: version stamping may have modified eyetrackapp.py and
echo  INNO\ETVR_SETUP.iss - commit those changes with the release.
echo.
pause
exit /b 0

:fail
echo.
echo ******************** BUILD FAILED ********************
pause
exit /b 1
