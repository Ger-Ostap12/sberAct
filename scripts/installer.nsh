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
; поэтому конвертер (~6.0 ГБ, копируется CopyFiles'ом вне payload) в оценку не
; попадает. customInit выполняется в том же .onInit ПОСЛЕ этой установки —
; дочитываем размер конвертера к секции, чтобы NSIS показал правду и не дал
; ставить на диск без места. Индекс 0 — единственная install-секция в шаблоне
; electron-builder (Section "install"); ${INSTALL_SECTION_ID} здесь ещё не
; объявлен (объявляется ниже по файлу), поэтому индекс явный.
!macro customInit
  SectionGetSize 0 $0
  IntOp $0 $0 + 6300000   ; КБ, размер converter/ (~6.0 ГБ)
  SectionSetSize 0 $0
!macroend

!macro customInstall
  IfFileExists "$EXEDIR\converter\*.*" 0 sberact_skip_converter
    DetailPrint "Установка модуля конвертации PDF (несколько минут, ~4-7 ГБ)..."
    CopyFiles "$EXEDIR\converter" "$INSTDIR\resources"
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
