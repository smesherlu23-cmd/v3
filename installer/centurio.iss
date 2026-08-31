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
; Зашита прямо в CenturioSetup.exe, чтобы пользователю не пришлось отдельно
; искать и ставить её самому — extract на диск (в {tmp}) только если её ещё
; нет. skipifsourcedoesntexist — чтобы локальная сборка без интернета
; (когда файл рядом не скачался) не ломала компиляцию .iss.
Source: "vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall skipifsourcedoesntexist; Check: not VCRedistInstalled

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--hidden"; Tasks: startup

[Run]
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "Устанавливаем компоненты Microsoft Visual C++..."; Check: ShouldRunVCRedist; Flags: waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Code]
function VCRedistInstalled: Boolean;
var
  Installed: Cardinal;
begin
  // Ключ реестра общий для всей линейки VC++ 2015-2022 (ABI-совместимы,
  // отсюда единая версия "14.0") — тот же, что проверяют официальные
  // бутстрапперы Microsoft. Если он уже есть, ставить второй раз незачем
  // и небезопасно: у пользователя может стоять версия новее той, что
  // зашита в этот установщик, а /install её бы откатил назад.
  Result := RegQueryDWordValue(HKLM, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\X64',
    'Installed', Installed) and (Installed = 1);
end;

function ShouldRunVCRedist: Boolean;
begin
  // Двойная проверка: не только «нужен ли редистрибутив», но и правда ли
  // он лежит в {tmp} — Check у [Files] мог его туда не положить (сборка
  // без интернета, см. skipifsourcedoesntexist выше).
  Result := (not VCRedistInstalled) and FileExists(ExpandConstant('{tmp}\vc_redist.x64.exe'));
end;
