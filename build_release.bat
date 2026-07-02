@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM ==========================================================================
REM  EyeTrackVR one-shot release builder
REM
REM    1. Reads version.txt and stamps it into the app + Inno installer
REM    2. Builds the Windows app (PyInstaller) and installer (Inno Setup)
REM    3. Builds the Linux tarball inside WSL (Ubuntu-22.04, auto-installed)
REM    4. Collects everything + SHA256SUMS into release\<version>\
REM
REM  Update version.txt, double-click this file, upload release\<version>\*
REM ==========================================================================

cd /d "%~dp0"
set "REPO_WIN=%~dp0"
set "REPO_WIN=%REPO_WIN:~0,-1%"
set "DISTRO=Ubuntu-22.04"
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"

echo.
echo [1/5] Stamping version from version.txt ...
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
echo [2/5] Building Windows app with PyInstaller ...
pushd eyetrackapp
poetry run pyinstaller eyetrackapp.spec --noconfirm
if errorlevel 1 ( popd & goto :fail )
popd
if not exist "eyetrackapp\dist\eyetrackapp.exe" (
    echo ERROR: eyetrackapp.exe missing after PyInstaller build
    goto :fail
)

echo.
echo [3/5] Building Windows installer with Inno Setup ...
if not exist "%ISCC%" (
    echo ERROR: Inno Setup 6 not found at "%ISCC%"
    goto :fail
)
"%ISCC%" /Qp "eyetrackapp\INNO\ETVR_SETUP.iss"
if errorlevel 1 goto :fail

echo.
echo [4/5] Building Linux tarball in WSL ^(%DISTRO%^) ...
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

echo.
echo [5/5] Collecting artifacts into release\%SAFEVERSION% ...
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
del /q "%RELEASE_DIR%\SHA256SUMS.txt" 2>nul
powershell -NoProfile -Command "Get-ChildItem -LiteralPath '%RELEASE_DIR%' -File | Where-Object Name -ne 'SHA256SUMS.txt' | Get-FileHash -Algorithm SHA256 | ForEach-Object { '{0}  {1}' -f $_.Hash.ToLower(), (Split-Path $_.Path -Leaf) } | Set-Content -Encoding ascii '%RELEASE_DIR%\SHA256SUMS.txt'"
if errorlevel 1 goto :fail

echo.
echo ==========================================================================
echo  DONE - upload these to the GitHub release:
echo ==========================================================================
dir /b "%RELEASE_DIR%"
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
