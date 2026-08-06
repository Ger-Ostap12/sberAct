@echo off
rem ---------------------------------------------------------------------------
rem  Запускает проверку целостности установленного SberAct (check-install.ps1).
rem  Должен лежать рядом с check-install.ps1 и install-manifest.txt.
rem
rem  Сохранять в cp866: cmd разбирает файл в текущей кодировке консоли ДО
rem  выполнения, и кириллица из UTF-8 превращается в кашу (chcp не спасает).
rem ---------------------------------------------------------------------------
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check-install.ps1"
echo.
pause
