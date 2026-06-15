@echo off
cd /d "%~dp0"

set RELEASE_VERSION=1.0.4
set STAGING=release\source-staging
set ARCHIVE_BASE=SberAct-%RELEASE_VERSION%-source

echo === Packaging source for release %RELEASE_VERSION% ===

if exist "%STAGING%" rmdir /s /q "%STAGING%"
if not exist "release" mkdir "release"
mkdir "%STAGING%"

for %%D in (electron-app python-backend emplates) do (
    if exist "%%D" (
        echo Copying %%D ...
        xcopy "%%D" "%STAGING%\%%D\" /E /I /Y /Q ^
            /EXCLUDE:package-source-exclude.txt 2>nul
        if errorlevel 1 (
            robocopy "%%D" "%STAGING%\%%D" /E /XD node_modules build dist __pycache__ generated venv .git /NFL /NDL /NJH /NJS /nc /ns /np >nul
        )
    )
)

for %%F in (
    .gitignore build.sh build.bat Dockerfile install.sh install-astralinux.sh
    install-astralinux-deps.sh LICENSE package.json package-lock.json
    SberAct.spec start.sh test_document.txt README.md README astralinux-config
) do (
    if exist "%%F" copy /Y "%%F" "%STAGING%\" >nul
)

powershell -NoProfile -Command "Compress-Archive -Path '%STAGING%\*' -DestinationPath 'release\%ARCHIVE_BASE%.zip' -Force"

if exist "%STAGING%" rmdir /s /q "%STAGING%"

echo.
echo === Done ===
echo Windows: release\%ARCHIVE_BASE%.zip
echo.
echo For Linux .tar.gz run in WSL:
echo   RELEASE_VERSION=%RELEASE_VERSION% ./package-source-release.sh
echo.
pause
