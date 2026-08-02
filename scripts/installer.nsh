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
