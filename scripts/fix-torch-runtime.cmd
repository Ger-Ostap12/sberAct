@echo off
rem ---------------------------------------------------------------------------
rem  Чинит конвертер на машине без Microsoft Visual C++ Redistributable.
rem
rem  Симптом: конвертация PDF не запускается, в логе бэкенда -
rem      OSError: [WinError 126] Не найден указанный модуль.
rem      Error loading "...\torch\lib\torch_python.dll" or one of its dependencies.
rem
rem  Причина: torch тянет системный MSVC-рантайм (vcruntime140.dll,
rem  vcruntime140_1.dll, msvcp140.dll). В колесо torch они не входят, а на чистой
rem  Windows без VC++ Redistributable их нет. Сами файлы torch при этом целы.
rem
rem  Что делает скрипт: проверяет систему и, если рантайма нет, кладёт его копию
rem  из папки dll\ рядом с собой прямо в torch\lib - torch добавляет эту папку в
rem  путь поиска DLL (os.add_dll_directory), поэтому подхватит. Права
rem  администратора не нужны, откат - удалить скопированные файлы.
rem
rem  ПРАВИЛЬНЫЙ путь, если есть права админа: поставить vc_redist.x64.exe
rem  (Microsoft Visual C++ 2015-2022 Redistributable) - он чинит это для всей
rem  системы, а не для одной папки.
rem ---------------------------------------------------------------------------
setlocal enabledelayedexpansion

set "APP=%LOCALAPPDATA%\Programs\SberAct Document Generator"
set "CONV=%APP%\resources\converter"
set "TORCHLIB=%CONV%\.venv\Lib\site-packages\torch\lib"
set "PY=%CONV%\pyruntime\python.exe"

echo ============================================================
echo  Починка конвертера SberAct (MSVC-рантайм для torch)
echo ============================================================
echo.

if not exist "%TORCHLIB%\torch_python.dll" (
    echo [ОШИБКА] Не найден "%TORCHLIB%\torch_python.dll"
    echo Похоже, приложение установлено в другое место или конвертер не распакован.
    goto :end
)
echo [1/4] Конвертер найден: %CONV%

echo.
echo [2/4] Проверяю системный рантайм...
set MISSING=0
for %%D in (vcruntime140.dll vcruntime140_1.dll msvcp140.dll) do (
    if exist "%SystemRoot%\System32\%%D" (
        echo       %%D - есть
    ) else (
        echo       %%D - НЕТ
        set MISSING=1
    )
)

if "%MISSING%"=="0" (
    echo.
    echo Системный рантайм на месте - копировать нечего.
    echo Если конвертер всё равно не стартует, пришли лог бэкенда целиком.
    goto :test
)

echo.
echo [3/4] Рантайма нет - кладу копию в torch\lib
if not exist "%~dp0dll" (
    echo [ОШИБКА] Рядом со скриптом нет папки dll\ - копировать нечего.
    echo Положи скрипт вместе с папкой dll и запусти заново.
    goto :end
)
copy /Y "%~dp0dll\*.dll" "%TORCHLIB%\" >nul
if errorlevel 1 (
    echo [ОШИБКА] Не удалось скопировать файлы в "%TORCHLIB%"
    goto :end
)
echo       скопировано в %TORCHLIB%

:test
echo.
echo [4/4] Проверяю, грузится ли torch (это занимает 10-30 секунд)...
set "PYTHONPATH=%CONV%\.venv\Lib\site-packages"
set "PYTHONNOUSERSITE=1"
"%PY%" -c "import torch; print('       torch OK', torch.__version__)"
if errorlevel 1 (
    echo.
    echo [РЕЗУЛЬТАТ] torch по-прежнему не грузится. Пришли весь вывод этого окна.
) else (
    echo.
    echo [РЕЗУЛЬТАТ] Готово. Запусти приложение и попробуй конвертацию PDF.
)

:end
echo.
echo ============================================================
pause
