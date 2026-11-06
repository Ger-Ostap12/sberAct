!ifndef BUILD_UNINSTALLER
Var sberactLegacyDir
Var sberactLegacyScope
Var sberactUserDir


!macro sberactInstallApplicationFiles
  !ifdef APP_PACKAGE_URL
    !error "SberAct supports offline NSIS installers only"
  !endif
  !insertmacro extractEmbeddedAppPackage
  !insertmacro copyFile "$EXEPATH" "$LOCALAPPDATA\${APP_INSTALLER_STORE_FILE}"
  WriteUninstaller "$INSTDIR\${UNINSTALL_FILENAME}"
!macroend

!macro customInstallMode
  StrCpy $isForceCurrentInstall "1"
!macroend

!macro sberactInitMigration
  ${GetParameters} $R0
  ClearErrors
  ${GetOptions} $R0 "/allusers" $R1
  ${ifNot} ${Errors}
    MessageBox MB_ICONSTOP|MB_OK "SberAct устанавливается только для текущего пользователя. Запустите установщик без /allusers."
    SetErrorLevel 2
    Quit
  ${endif}
  StrCpy $sberactUserDir "$LOCALAPPDATA\Programs\SberAct"
  StrCpy $sberactLegacyDir ""
  ReadRegStr $R0 HKCU "${INSTALL_REGISTRY_KEY}" InstallLocation
  ${if} $R0 != ""
    GetFullPathName $R0 "$R0"
    ${if} $R0 != $sberactUserDir
      StrCpy $sberactLegacyDir $R0
      StrCpy $sberactLegacyScope "currentuser"
    ${endif}
  ${endif}
  ReadRegStr $R0 HKLM "${INSTALL_REGISTRY_KEY}" InstallLocation
  ${if} $R0 != ""
    GetFullPathName $R0 "$R0"
    ${if} $R0 != $sberactUserDir
      ${if} $sberactLegacyDir != ""
      ${andIf} $sberactLegacyDir != $R0
        MessageBox MB_ICONSTOP|MB_OK "Обнаружены две прежние установки SberAct. Переход остановлен: требуется отдельно выбрать сохраняемую установку."
        SetErrorLevel 2
        Quit
      ${endif}
      StrCpy $sberactLegacyDir $R0
      StrCpy $sberactLegacyScope "allusers"
    ${endif}
  ${endif}
!macroend

!macro sberactPrepareMigration
  InitPluginsDir
  File "/oname=$PLUGINSDIR\migrate-install.ps1" "${PROJECT_DIR}\scripts\migrate-install.ps1"
  ${if} $sberactLegacyDir != ""
    StrCpy $keepShortcuts "false"
    DetailPrint "Подготовка перехода из $sberactLegacyDir в $INSTDIR..."
    nsExec::ExecToLog 'powershell -NoProfile -ExecutionPolicy Bypass -File "$PLUGINSDIR\migrate-install.ps1" -Mode Prepare -Source "$sberactLegacyDir" -Target "$INSTDIR" -AppExe "${APP_EXECUTABLE_FILENAME}"'
    Pop $0
    ${if} $0 != 0
      MessageBox MB_ICONSTOP|MB_OK "Не удалось подготовить переход. Прежняя установка сохранена. Проверьте свободное место. Журнал: $LOCALAPPDATA\SberAct\logs"
      SetErrorLevel 2
      Abort
    ${endif}
  ${endif}
!macroend

!macro sberactRetireLegacy
  ${if} $sberactLegacyDir != ""
    DetailPrint "Проверка новой установки и удаление прежней версии..."
    nsExec::ExecToLog 'powershell -NoProfile -ExecutionPolicy Bypass -File "$PLUGINSDIR\migrate-install.ps1" -Mode Retire -Source "$sberactLegacyDir" -Target "$INSTDIR" -Scope "$sberactLegacyScope" -AppExe "${APP_EXECUTABLE_FILENAME}"'
    Pop $0
    ${if} $0 != 0
      MessageBox MB_ICONSTOP|MB_OK "Переход не завершён. Новая установка не зарегистрирована. Проверьте журнал в $LOCALAPPDATA\SberAct\logs и повторите установку."
      SetErrorLevel 2
      Abort
    ${endif}
  ${endif}
!macroend
!endif
