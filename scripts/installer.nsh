; Кастомные шаги установщика SberAct.
;
; Конвертер (3.5+ ГБ) нельзя вшить в NSIS-payload: 7z-распаковка installer'а
; 32-битная и падает на >4 ГБ. Поэтому конвертер едет на флешке ОТДЕЛЬНОЙ папкой
; converter/ рядом с установщиком, а тут мы копируем его в приложение обычной
; шелл-копией (CopyFiles через SHFileOperation — размер не ограничен).
;
; Если папки converter/ рядом нет (запустили только exe) — тихо пропускаем,
; приложение работает без OCR-конвертации.

; Строка «Требуется места» берётся из размера install-секции. electron-builder
; в .onInit жёстко ставит его равным размеру app (~720 МБ) через SectionSetSize,
; поэтому конвертер (устанавливается вне payload) в оценку не попадает.
; customInit выполняется в том же .onInit ПОСЛЕ этой установки — дочитываем
; размер конвертера к секции, чтобы NSIS показал правду и не дал ставить на диск
; без места. Индекс 0 — единственная install-секция в шаблоне electron-builder
; (Section "install"); ${INSTALL_SECTION_ID} здесь ещё не объявлен (объявляется
; ниже по файлу), поэтому индекс явный.
;
; 3 900 000 КБ — распакованный converter/ (3.6 ГБ) с небольшим запасом. Прежние
; 6 300 000 остались от сборки, куда входила неиспользуемая LLM gemma-3-4b
; (2.37 ГБ); с завышенной оценкой установщик отказывался ставиться на диск, где
; места на самом деле хватало. Архив читается с флешки и на целевом диске места
; не занимает.
!macro customInit
  SectionGetSize 0 $0
  IntOp $0 $0 + 3900000   ; КБ, распакованный converter/ (~3.6 ГБ)
  SectionSetSize 0 $0

  ; Штатная проверка electron-builder закрывает только окно приложения. Бэкенд,
  ; запущенный отдельно (ярлыком из resources\backend или вручную из cmd при
  ; разборе логов), остаётся жив и держит SberAct.exe открытым: установщик тогда
  ; пишет файл поверх занятого — и на диск попадает недописанный PE. Windows
  ; встречает такой файл сообщением «Неподдерживаемое 16-разрядное приложение»
  ; (ошибка 193, BAD_EXE_FORMAT). Снимаем процесс до распаковки; если его нет,
  ; taskkill просто вернёт ненулевой код, который нам неинтересен.
  nsExec::Exec 'taskkill /F /T /IM SberAct.exe'
  Pop $0
!macroend

; Конвертер приезжает в одном из двух видов, рядом с установщиком:
;   converter.zip — основной формат (быстрая последовательная запись на флешку,
;                   CRC на каждый файл, «наполовину установленным» быть не может);
;   converter\    — старый формат, папкой (поддерживаем ради уже нарезанных флешек).
!macro customInstall
  IfFileExists "$EXEDIR\converter.zip" sberact_converter_zip 0
  IfFileExists "$EXEDIR\converter\*.*" sberact_converter_dir 0
  Goto sberact_skip_converter

  ; --- Архив: распаковываем PowerShell'ом (в NSIS нет своего распаковщика) ---
  sberact_converter_zip:
    DetailPrint "Установка модуля конвертации PDF из архива (несколько минут)..."
    InitPluginsDir
    File "/oname=$PLUGINSDIR\extract-converter.ps1" "${PROJECT_DIR}\scripts\extract-converter.ps1"
    nsExec::ExecToLog 'powershell -NoProfile -ExecutionPolicy Bypass -File "$PLUGINSDIR\extract-converter.ps1" -Zip "$EXEDIR\converter.zip" -Dest "$INSTDIR\resources"'
    Pop $0
    ${if} $0 != 0
      DetailPrint "Распаковка модуля конвертации завершилась с ошибкой (код $0)."
      Goto sberact_converter_broken
    ${endif}
    Goto sberact_converter_verify

  ; --- Папка: обычная шелл-копия ---
  sberact_converter_dir:
    DetailPrint "Установка модуля конвертации PDF (несколько минут, ~4-7 ГБ)..."
    CopyFiles "$EXEDIR\converter" "$INSTDIR\resources"
    Goto sberact_converter_verify

  ; CopyFiles (SHFileOperation) не сообщает об ошибке: при обрыве копирования
  ; (нехватка места, сбой USB, отмена в диалоге Windows) установка завершается
  ; «успешно» с полупустой папкой, а пользователь узнаёт об этом только при
  ; первой конвертации — «Конвертер не найден». Проверяем ключевые файлы:
  ; интерпретатор (без него main.py:_converter_command вернёт None) и код API.
  sberact_converter_verify:
    IfFileExists "$INSTDIR\resources\converter\pyruntime\python.exe" 0 sberact_converter_broken
    IfFileExists "$INSTDIR\resources\converter\docling_dev\api.py" 0 sberact_converter_broken
    IfFileExists "$INSTDIR\resources\converter\vendor\tesseract\tesseract.exe" 0 sberact_converter_broken
    DetailPrint "Модуль конвертации PDF установлен."
    Goto sberact_skip_converter

  sberact_converter_broken:
    DetailPrint "ВНИМАНИЕ: модуль конвертации установлен не полностью."
    MessageBox MB_ICONEXCLAMATION|MB_OK "Модуль конвертации PDF установлен не полностью.$\r$\n$\r$\nПриложение установится и будет работать, но конвертация PDF будет недоступна.$\r$\n$\r$\nВероятные причины: не хватило места на диске или сбой чтения с флешки.$\r$\nОсвободите место (нужно ~7 ГБ) и запустите установку заново."

  sberact_skip_converter:

  ; --- MSVC-рантайм для torch -----------------------------------------------
  ; Колесо torch не везёт системный C++-рантайм, а bundled-питон приносит из
  ; установщика CPython только vcruntime140{,_1}.dll — msvcp140.dll нет нигде.
  ; На машине сборки она лежит в System32 вместе с Visual Studio, поэтому дефект
  ; виден лишь на чистой Windows: конвертер падает на импорте с WinError 126
  ; (torch_python.dll «or one of its dependencies»). Кладём рантайм в две папки,
  ; которые Windows и torch и так просматривают, — без прав администратора.
  ;
  ; Шаг выполняется независимо от того, ставили ли мы конвертер сейчас: при
  ; обновлении customRemoveFiles сохраняет прежний converter\, и рантайм в нём
  ; всё равно нужен.
  IfFileExists "$INSTDIR\resources\msvc-runtime\msvcp140.dll" 0 sberact_skip_msvc
  IfFileExists "$INSTDIR\resources\converter\pyruntime\python.exe" 0 sberact_skip_msvc

  DetailPrint "Установка библиотек Microsoft Visual C++ для модуля конвертации..."
  ; Каталог python.exe всегда в путях поиска DLL — покрывает все пакеты сразу.
  CopyFiles /SILENT "$INSTDIR\resources\msvc-runtime\*.dll" "$INSTDIR\resources\converter\pyruntime"
  ; Дубль в torch\lib: torch добавляет эту папку через os.add_dll_directory,
  ; страховка на случай запуска интерпретатора не из pyruntime.
  IfFileExists "$INSTDIR\resources\converter\.venv\Lib\site-packages\torch\lib\torch_python.dll" 0 sberact_msvc_verify
  CopyFiles /SILENT "$INSTDIR\resources\msvc-runtime\*.dll" "$INSTDIR\resources\converter\.venv\Lib\site-packages\torch\lib"

  sberact_msvc_verify:
    IfFileExists "$INSTDIR\resources\converter\pyruntime\msvcp140.dll" 0 sberact_msvc_broken
    DetailPrint "Библиотеки Microsoft Visual C++ установлены."
    Goto sberact_skip_msvc

  sberact_msvc_broken:
    DetailPrint "ВНИМАНИЕ: не удалось разложить библиотеки Microsoft Visual C++."
    MessageBox MB_ICONEXCLAMATION|MB_OK "Не удалось установить библиотеки Microsoft Visual C++ для модуля конвертации.$\r$\n$\r$\nПриложение будет работать, но конвертация PDF, скорее всего, откажет.$\r$\n$\r$\nЛечится установкой Microsoft Visual C++ 2015-2022 Redistributable (x64)."

  sberact_skip_msvc:

  ; --- Бэкенд: файл должен быть на месте и целым ------------------------------
  ; Недописанный SberAct.exe (занят другим процессом, кончилось место, вмешался
  ; антивирус) даёт при запуске «Неподдерживаемое 16-разрядное приложение», и
  ; понять это без разбора невозможно — приложение просто не находит бэкенд.
  ; Эталон onedir-сборки ~16 МБ; всё, что меньше 8 МБ, целым быть не может.
  ClearErrors
  FileOpen $0 "$INSTDIR\resources\backend\SberAct.exe" r
  IfErrors sberact_backend_broken
  FileSeek $0 0 END $1
  FileClose $0
  IntCmp $1 8000000 sberact_backend_ok sberact_backend_broken sberact_backend_ok

  sberact_backend_broken:
    DetailPrint "ВНИМАНИЕ: файл бэкенда отсутствует или повреждён."
    MessageBox MB_ICONSTOP|MB_OK "Файл resources\backend\SberAct.exe установлен не полностью.$\r$\n$\r$\nПриложение запустится, но работать не будет.$\r$\n$\r$\nЗакройте приложение и все окна SberAct, освободите место на диске (нужно ~7 ГБ), при необходимости отключите антивирус и установите заново."
    Goto sberact_backend_done

  sberact_backend_ok:
    DetailPrint "Бэкенд установлен."

  sberact_backend_done:
!macroend

; --- Удаление файлов: сохраняем конвертер при ОБНОВЛЕНИИ, сносим при удалении ---
; Определяя customRemoveFiles, мы полностью замещаем штатный блок удаления
; деинсталлятора (по умолчанию RMDir /r $INSTDIR). Это нужно, чтобы при
; ОБНОВЛЕНИИ (electron-updater перезапускает установщик, ${isUpdated} = true) НЕ
; снести внешний конвертер (~6 ГБ, живёт в resources\converter, обновляется
; отдельным converter-sync с флешки). Переносим его на тот же том рядом
; (мгновенно, это move в пределах диска), чистим $INSTDIR, возвращаем на место —
; новая установка кладёт app+backend поверх сохранённого конвертера. При
; НАСТОЯЩЕМ удалении сносим всё, включая конвертер.
!macro customRemoveFiles
  ${if} ${isUpdated}
    ${if} ${FileExists} "$INSTDIR\resources\converter\*.*"
      Rename "$INSTDIR\resources\converter" "$INSTDIR.converter-keep"
    ${endif}
    RMDir /r "$INSTDIR"
    ${if} ${FileExists} "$INSTDIR.converter-keep\*.*"
      CreateDirectory "$INSTDIR\resources"
      Rename "$INSTDIR.converter-keep" "$INSTDIR\resources\converter"
    ${endif}
  ${else}
    RMDir /r "$INSTDIR"
  ${endif}
!macroend
