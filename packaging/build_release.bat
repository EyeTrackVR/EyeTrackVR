@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM ==========================================================================
REM  EyeTrackVR one-shot release builder
REM
REM    0. Refuses a working tree with uncommitted or untracked files, runs the
REM       test suite, and checks every version stamp matches version.txt
REM    1. Reads the version from version.txt
REM    2. Builds the Windows app (PyInstaller) and installer (Inno Setup)
REM    3. Builds the Linux tarball inside WSL (Ubuntu-22.04, auto-installed)
REM    4. Builds the Steam Frame zip + FrameDrop manifest in an arm64 Docker
REM       container (Docker Desktop must be running; QEMU-emulated, slow)
REM    5. Collects everything + SHA256SUMS into release\<version>\
REM
REM  Update version.txt, run "python packaging\apply_version.py", commit,
REM  double-click this file, upload release\<version>\*
REM
REM  Options (or the matching environment variable set to 1):
REM    --allow-dirty   ETVR_ALLOW_DIRTY   build even with uncommitted/untracked files
REM    --skip-tests    ETVR_SKIP_TESTS    don't run the test suite first
REM  A build made with either is not a release build: don't upload it.
REM ==========================================================================

cd /d "%~dp0.."
set "REPO_WIN=%CD%"
set "DISTRO=Ubuntu-22.04"
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"

REM After the cd: shift also shifts %0, which the cd above needs.
set "ALLOW_DIRTY=%ETVR_ALLOW_DIRTY%"
set "SKIP_TESTS=%ETVR_SKIP_TESTS%"
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--allow-dirty" (
    set "ALLOW_DIRTY=1"
    shift
    goto :parse_args
)
if /i "%~1"=="--skip-tests" (
    set "SKIP_TESTS=1"
    shift
    goto :parse_args
)
echo ERROR: unknown option "%~1" - use --allow-dirty and/or --skip-tests
goto :fail
:args_done

echo.
echo [0/6] Checking the working tree ...
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo ERROR: git is not installed or this is not a git checkout
    goto :fail
)
set "DIRTY="
for /f "usebackq delims=" %%l in (`git status --porcelain`) do set "DIRTY=1"
if defined DIRTY (
    if "%ALLOW_DIRTY%"=="1" (
        echo     WARNING: building with uncommitted or untracked files - not a release build:
        git status --short
    ) else (
        echo ERROR: the working tree has uncommitted or untracked files:
        git status --short
        echo Commit or remove them, or pass --allow-dirty for a local test build.
        goto :fail
    )
) else (
    echo     clean at commit:
    git log -1 --oneline
)

echo.
echo [0/6] Checking version stamps against version.txt ...
REM --check changes nothing and fails when any stamped file differs from version.txt.
python packaging\apply_version.py --check >nul
if errorlevel 1 (
    echo ERROR: version stamps are out of sync with version.txt:
    python packaging\apply_version.py --check
    echo Run "python packaging\apply_version.py", commit the result and build again.
    goto :fail
)

if "%SKIP_TESTS%"=="1" (
    echo.
    echo [0/6] WARNING: skipping the test suite - not a release build
) else (
    echo.
    echo [0/6] Running the test suite, as .github\workflows\tests.yml does ...
    python packaging\fetch_overlay.py windows linux linux-arm64
    if errorlevel 1 goto :fail
    poetry run python -m pytest tests --ignore=tests/contributions
    if errorlevel 1 goto :fail
    poetry run python -m pytest --confcutdir=tests/contributions tests/contributions
    if errorlevel 1 goto :fail
)

echo.
echo [1/6] Reading version from version.txt ...
set "VERSION="
set "SAFEVERSION="
for /f "usebackq delims=" %%v in (`python packaging\apply_version.py --check`) do (
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
REM The spec collects into a folder named "dist" under --distpath: build\windows\dist.
REM ETVR_RELEASE_BUILD makes the spec bundle the release marker (eyetrackapp\build_info.py),
REM which hides developer-only options such as the DFR "Debug view" quality.
set "ETVR_RELEASE_BUILD=1"
poetry run pyinstaller packaging\windows\eyetrackapp.spec --noconfirm --distpath build\windows --workpath build\windows\work
if errorlevel 1 goto :fail
if not exist "build\windows\dist\eyetrackapp.exe" (
    echo ERROR: eyetrackapp.exe missing after PyInstaller build
    goto :fail
)

echo.
echo [2b/6] Building SteamVR gaze driver ...
REM Shipped beside the exe, not inside the bundle: SteamVR needs a stable, plain path. The app registers it when foveation gaze is on.
REM Both native builds start clean, like packaging/linux/build.sh, so a stale CMake cache
REM (e.g. one generated before the sources moved to native/) cannot break the release.
if exist "build\steamvr_driver" rmdir /s /q "build\steamvr_driver"
cmake -S native\steamvr_driver -B build\steamvr_driver -A x64 >nul
if errorlevel 1 goto :fail
cmake --build build\steamvr_driver --config Release
if errorlevel 1 goto :fail
if exist "build\windows\dist\steamvr_driver" rmdir /s /q "build\windows\dist\steamvr_driver"
xcopy /e /i /q /y "build\steamvr_driver\eyetrackvr" "build\windows\dist\steamvr_driver\eyetrackvr" >nul
if errorlevel 1 goto :fail
if not exist "build\windows\dist\steamvr_driver\eyetrackvr\bin\win64\driver_eyetrackvr.dll" (
    echo ERROR: driver_eyetrackvr.dll missing after the driver build
    goto :fail
)

echo.
echo [2c/6] Building OpenXR eye gaze layer ...
REM Also beside the exe; the app installs it as an implicit OpenXR layer when foveation gaze is on.
if exist "build\openxr_layer" rmdir /s /q "build\openxr_layer"
cmake -S native\openxr_layer -B build\openxr_layer -A x64 >nul
if errorlevel 1 goto :fail
cmake --build build\openxr_layer --config Release
if errorlevel 1 goto :fail
if exist "build\windows\dist\openxr_layer" rmdir /s /q "build\windows\dist\openxr_layer"
xcopy /e /i /q /y "build\openxr_layer\eyetrackvr_openxr_layer" "build\windows\dist\openxr_layer" >nul
if errorlevel 1 goto :fail
if not exist "build\windows\dist\openxr_layer\XR_APILAYER_EYETRACKVR_eye_gaze.dll" (
    echo ERROR: XR_APILAYER_EYETRACKVR_eye_gaze.dll missing after the layer build
    goto :fail
)

echo.
echo [3/6] Building Windows installer with Inno Setup ...
if not exist "%ISCC%" (
    echo ERROR: Inno Setup 6 not found at "%ISCC%"
    goto :fail
)
"%ISCC%" /Qp "packaging\windows\installer.iss"
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
wsl.exe -d %DISTRO% -u root -- bash -c "tr -d '\r' < '%REPO_WSL%/packaging/linux/wsl_entry.sh' | bash -s -- '%VERSION%' '%SAFEVERSION%' '%REPO_WSL%'"
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
docker build --platform linux/arm64 -t etvr-frame-builder "packaging\steamframe"
if errorlevel 1 goto :fail
REM The etvr-frame-cache volume keeps Python and the pip cache between builds.
docker run --rm --platform linux/arm64 -v "%REPO_WIN%:/repo" -v etvr-frame-cache:/root/etvr-frame-build etvr-frame-builder bash -c "tr -d '\r' < /repo/packaging/steamframe/build.sh | bash -s -- '%VERSION%' '%SAFEVERSION%' /repo '/repo/release/%SAFEVERSION%'"
if errorlevel 1 goto :fail

echo.
echo [6/6] Collecting artifacts into release\%SAFEVERSION% ...
if not exist "%RELEASE_DIR%" mkdir "%RELEASE_DIR%"
copy /y "build\windows\installer\EyeTrackVR-Setup-%SAFEVERSION%.exe" "%RELEASE_DIR%\" >nul
if errorlevel 1 (
    echo ERROR: installer not found in build\windows\installer
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
for /f "usebackq delims=" %%c in (`git rev-parse HEAD`) do echo  Built from commit %%c - tag that commit.
if defined DIRTY echo  WARNING: built from a working tree with uncommitted changes - do not upload.
if "%SKIP_TESTS%"=="1" echo  WARNING: the test suite was skipped - do not upload.
echo.
pause
exit /b 0

:fail
echo.
echo ******************** BUILD FAILED ********************
pause
exit /b 1
