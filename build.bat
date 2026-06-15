@echo off
cd /d "%~dp0"

set RELEASE_VERSION=1.0.5
set WIN_NAME=SberAct-windows-x64.exe

echo === SberAct build for Windows (one-file EXE) ===

python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python not found. Install Python and add to PATH.
    pause
    exit /b 1
)

echo.
echo Checking dependencies...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller -q
)

echo.
if exist "electron-app\build\index.html" (
    echo Frontend already built: electron-app\build\ ^(skipping npm^)
) else (
    echo Building React frontend...
    where npm >nul 2>&1
    if errorlevel 1 (
        echo Error: electron-app\build\index.html not found and npm is unavailable.
        echo Build frontend on another machine:
        echo   cd electron-app ^&^& npm install ^&^& npm run build
        echo then copy electron-app\build\ into the project.
        pause
        exit /b 1
    )
    cd electron-app
    call npm install
    call npm run build
    cd ..
)

if not exist "electron-app\build\index.html" (
    echo Error: electron-app\build\index.html not found.
    pause
    exit /b 1
)

if not exist "electron-app\build\static" (
    echo Error: electron-app\build\static not found - browser UI will not work.
    pause
    exit /b 1
)

if not exist "emplates" (
    echo Warning: emplates\ folder not found - templates will not be bundled.
)

echo.
echo Cleaning PyInstaller cache...
if exist "build" rmdir /s /q "build"
if exist "__pycache__" rmdir /s /q "__pycache__"
for /d /r python-backend %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"

echo.
echo Running PyInstaller (one-file)...
pyinstaller --clean --noconfirm SberAct.spec

if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

if not exist "dist\SberAct.exe" (
    echo Error: dist\SberAct.exe not found after build.
    pause
    exit /b 1
)

echo.
echo Preparing release (binary + external Templates)...
if not exist "release" mkdir "release"
copy /Y "dist\SberAct.exe" "release\%WIN_NAME%" >nul

if exist "emplates" (
    if exist "dist\Templates" rmdir /s /q "dist\Templates"
    if exist "release\Templates" rmdir /s /q "release\Templates"
    xcopy "emplates\*" "dist\Templates\" /E /I /Y >nul
    xcopy "emplates\*" "release\Templates\" /E /I /Y >nul
    echo Templates copied to dist\Templates and release\Templates
    powershell -NoProfile -Command "Compress-Archive -Path 'release\%WIN_NAME%','release\Templates' -DestinationPath 'release\SberAct-%RELEASE_VERSION%-windows-x64.zip' -Force"
) else (
    echo Warning: emplates\ not found - no external Templates folder
    powershell -NoProfile -Command "Compress-Archive -Path 'release\%WIN_NAME%' -DestinationPath 'release\SberAct-%RELEASE_VERSION%-windows-x64.zip' -Force"
)

echo.
echo === Done ===
echo Binary:  dist\SberAct.exe
if exist "dist\Templates" echo Templates: dist\Templates\  ^(edit without rebuild^)
echo Release: release\SberAct-%RELEASE_VERSION%-windows-x64.zip
echo Run:     cd dist ^&^& SberAct.exe
echo.
pause
