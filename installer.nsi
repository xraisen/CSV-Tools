; NSIS installer script
Name "CSV Tools"
OutFile "dist\CSVToolsSetup.exe"
InstallDir "$PROGRAMFILES\CSVTools"
RequestExecutionLevel admin

!include MUI2.nsh

!define MUI_ICON "assets\installer.ico"
!define MUI_UNICON "assets\uninstaller.ico"

!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "Main"
  SetOutPath $INSTDIR
  File "dist\CSVProcessor.exe"
  File "dist\CSVSplitter.exe"
  File "dist\CSVSearchAI.exe"
  File "assets\icon.ico"
  
  ; Create shortcuts in Start Menu
  CreateDirectory "$SMPROGRAMS\CSV Tools"
  CreateShortcut "$SMPROGRAMS\CSV Tools\CSV Processor.lnk" "$INSTDIR\CSVProcessor.exe" "" "$INSTDIR\icon.ico"
  CreateShortcut "$SMPROGRAMS\CSV Tools\CSV Splitter.lnk" "$INSTDIR\CSVSplitter.exe" "" "$INSTDIR\icon.ico"
  CreateShortcut "$SMPROGRAMS\CSV Tools\CSV Search AI.lnk" "$INSTDIR\CSVSearchAI.exe" "" "$INSTDIR\icon.ico"
  
  ; Create shortcuts on Desktop
  CreateShortcut "$DESKTOP\CSV Processor.lnk" "$INSTDIR\CSVProcessor.exe" "" "$INSTDIR\icon.ico"
  CreateShortcut "$DESKTOP\CSV Search AI.lnk" "$INSTDIR\CSVSearchAI.exe" "" "$INSTDIR\icon.ico"
  
  ; Add to PATH
  EnVar::SetHKCU
  EnVar::AddValue "Path" "$INSTDIR"
  
  ; Write uninstaller
  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$INSTDIR\CSVProcessor.exe"
  Delete "$INSTDIR\CSVSplitter.exe"
  Delete "$INSTDIR\CSVSearchAI.exe"
  Delete "$INSTDIR\icon.ico"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  
  Delete "$SMPROGRAMS\CSV Tools\CSV Processor.lnk"
  Delete "$SMPROGRAMS\CSV Tools\CSV Splitter.lnk"
  Delete "$SMPROGRAMS\CSV Tools\CSV Search AI.lnk"
  RMDir "$SMPROGRAMS\CSV Tools"
  
  Delete "$DESKTOP\CSV Processor.lnk"
  Delete "$DESKTOP\CSV Search AI.lnk"
  
  ; Remove from PATH
  EnVar::SetHKCU
  EnVar::DeleteValue "Path" "$INSTDIR"
SectionEnd
