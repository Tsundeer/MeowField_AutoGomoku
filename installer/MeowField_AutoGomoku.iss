; Inno Setup 6 脚本 —— MeowField_AutoGomoku 安装器
; 由 scripts/build-win-x64.ps1 调用：
;   iscc /DMyAppVersion=x.y.z /DPublishDir=<pyinstaller onedir> installer\MeowField_AutoGomoku.iss

#ifndef MyAppVersion
  #error "请通过 /DMyAppVersion 指定版本号"
#endif

#ifndef PublishDir
  #error "请通过 /DPublishDir 指定 PyInstaller 输出目录"
#endif

#define MyAppName "MeowField_AutoGomoku"
#define MyAppPublisher "薮猫"
#define MyAppURL "https://github.com/Tsundeer/MeowField_AutoGomoku"
#define MyAppExeName "MeowField_AutoGomoku.exe"

[Setup]
AppId={{7C4E1D2A-9B3F-4E86-A5C1-2F8D6B7E9014}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=..\artifacts\installer
OutputBaseFilename=MeowField_AutoGomoku-{#MyAppVersion}-win-x64-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："

[Files]
Source: "{#PublishDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
// 安装前结束运行中的实例
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Exec('taskkill', '/F /IM {#MyAppExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := True;
end;

// 卸载前结束运行中的实例
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
    Exec('taskkill', '/F /IM {#MyAppExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;
