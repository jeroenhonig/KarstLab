; KarstLab Windows Installer
; Requires NSIS 3.x
;
; Build: makensis KarstLab.nsi
; Output: dist/KarstLab-${APP_VERSION}-Setup.exe

!include "MUI2.nsh"

; Application metadata
!define APP_NAME "KarstLab"
!define APP_VERSION "1.0.0"
!define APP_VENDOR "KarstLab"
!define APP_EXE "KarstLab.exe"
!define INSTALL_DIR "$PROGRAMFILES64\KarstLab"
!define REG_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\KarstLab"
!define REG_UNINSTALL "${REG_KEY}"

; Installer settings
Name "${APP_NAME} ${APP_VERSION}"
OutFile "..\..\dist\KarstLab-${APP_VERSION}-Setup.exe"
InstallDir "${INSTALL_DIR}"
InstallDirRegKey HKCU "${REG_UNINSTALL}" "InstallLocation"
RequestExecutionLevel admin

; MUI Settings
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "Dutch"

; Installer sections
Section "${APP_NAME}"
    SetOutPath "$INSTDIR"
    File /r "..\..\dist\KarstLab\*.*"

    ; Create uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; Register uninstaller in Windows
    WriteRegStr HKCU "${REG_UNINSTALL}" "DisplayName" "${APP_NAME}"
    WriteRegStr HKCU "${REG_UNINSTALL}" "UninstallString" "$INSTDIR\Uninstall.exe"
    WriteRegStr HKCU "${REG_UNINSTALL}" "DisplayVersion" "${APP_VERSION}"
    WriteRegStr HKCU "${REG_UNINSTALL}" "Publisher" "${APP_VENDOR}"
    WriteRegStr HKCU "${REG_UNINSTALL}" "InstallLocation" "$INSTDIR"
    WriteRegDWORD HKCU "${REG_UNINSTALL}" "NoModify" 1
    WriteRegDWORD HKCU "${REG_UNINSTALL}" "NoRepair" 1

    ; File association for .karstlab files
    WriteRegStr HKCR ".karstlab" "" "KarstLab.Project"
    WriteRegStr HKCR ".karstlab" "Content Type" "application/x-karstlab"
    WriteRegStr HKCR "KarstLab.Project" "" "KarstLab Project File"
    WriteRegStr HKCR "KarstLab.Project\DefaultIcon" "" "$INSTDIR\${APP_EXE},0"
    WriteRegStr HKCR "KarstLab.Project\shell\open\command" "" '"$INSTDIR\${APP_EXE}" "%%1"'

    ; Create Start Menu shortcuts
    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortCut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
    CreateShortCut "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

    ; Create Desktop shortcut (optional)
    CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
SectionEnd

; Uninstaller section
Section "Uninstall"
    ; Remove installed files
    RMDir /r "$INSTDIR"

    ; Remove shortcuts
    RMDir /r "$SMPROGRAMS\${APP_NAME}"
    Delete "$DESKTOP\${APP_NAME}.lnk"

    ; Remove file associations
    DeleteRegKey HKCR ".karstlab"
    DeleteRegKey HKCR "KarstLab.Project"

    ; Remove registry entries
    DeleteRegKey HKCU "${REG_UNINSTALL}"
SectionEnd

; Functions
Function .onInit
    SetShellVarContext all
FunctionEnd

Function un.onInit
    SetShellVarContext all
FunctionEnd
