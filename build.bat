.\build.bat@echo off
cd /d "%~dp0"

echo === SberAct build for Windows (EXE only) ===

python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python not found. Install Python and add to PATH.
    pause
    exit /b 1
)

echo.
echo Checking dependencies...
REM Проверяем наличие PyInstaller
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller -q
)

echo.
echo Building React frontend...
cd electron-app
call npm install
call npm run build
cd ..
if not exist "electron-app\build\index.html" (
    echo Error: React build failed. Run "cd electron-app && npm run build" manually.
    pause
    exit /b 1
)

echo.
echo Cleaning PyInstaller cache...
if exist "build" rmdir /s /q "build"
if exist "__pycache__" rmdir /s /q "__pycache__"
for /d /r python-backend %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"

echo.
echo Running PyInstaller to rebuild EXE...
pyinstaller --clean --noconfirm SberAct.spec

if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo === Done ===
echo Output: dist\SberAct\SberAct.exe
echo Run: dist\SberAct\SberAct.exe
echo Note: Put Shablony folder next to exe if needed.
echo.
pause
