!ifndef BUILD_UNINSTALLER
  ; Registry and /D cannot override the per-user destination.
  !macroundef setInstallModePerUser
  !macro setInstallModePerUser
    StrCpy $installMode CurrentUser
    SetShellVarContext current
    StrCpy $INSTDIR "$LOCALAPPDATA\Programs\SberAct"
  !macroend
  !macro sberactInitMultiUser
    StrCpy $hasPerMachineInstallation "0"
    StrCpy $hasPerUserInstallation "1"
    !insertmacro setInstallModePerUser
  !macroend
!endif
