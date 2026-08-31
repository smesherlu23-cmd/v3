; Inno Setup script for Centurio.
; Packages the `flet build windows` output into a Windows installer with a
; Start-Menu shortcut and an optional "launch at startup" checkbox.
;
; Build first:   flet build windows
; Then compile:  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\centurio.iss
; Output:        installer\Output\CenturioSetup.exe
;
; Проще запускать scripts\build_release.ps1 — он делает и то, и другое,
; сверяя версии и подписывая результат.

#define MyAppName "Centurio"
#define MyAppVersion "1.2.0"
#define MyAppPublisher "Centurio"
#define MyAppExeName "Centurio.exe"
#define MyAppDescription "Панель запуска приложений, всегда доступная из трея"
; flet build windows output directory (relative to this script's parent):
#define BuildDir "..\build\windows"

[Setup]
; Настоящий GUID: по AppId Windows опознаёт «то же приложение» при
; обновлении и удалении. Прежнее значение содержало буквы CENTURIO, которые
; не являются шестнадцатеричными цифрами. Менять его после первого
; публичного релиза нельзя — старая установка перестанет опознаваться.
AppId={{5DB06D53-80BB-4A28-8A1C-869D1F09FD9F}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputBaseFilename=CenturioSetup
OutputDir=Output
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
SetupIconFile=..\assets\centurio.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
; Пустые свойства файла — самостоятельный признак для эвристик антивирусов
; и первое, что видит пользователь в свойствах установщика.
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} — {#MyAppDescription}
VersionInfoProductName={#MyAppName}
VersionInfoCopyright=© {#MyAppPublisher}

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startup"; Description: "Запускать Centurio при входе в Windows"; GroupDescription: "Автозапуск:"; Flags: unchecked

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--hidden"; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
