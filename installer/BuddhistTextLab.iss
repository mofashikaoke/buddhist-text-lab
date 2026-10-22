#define AppName "佛典研究工作台"
#define AppExe "BuddhistTextLab.exe"
#ifndef AppVersion
  #define AppVersion "0.4.0"
#endif
[Setup]
AppId={{725321B8-20EE-4F31-9652-5140EBD1FCA6}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=mofashikaoke
AppPublisherURL=https://github.com/mofashikaoke/buddhist-text-lab
AppSupportURL=https://github.com/mofashikaoke/buddhist-text-lab/issues
DefaultDirName={autopf}\BuddhistTextLab
DefaultGroupName=佛典研究工作台
OutputDir=..\installer-output
OutputBaseFilename=BuddhistTextLab-Setup-{#AppVersion}-x64
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=佛典研究工作台
UninstallDisplayIcon={app}\{#AppExe}
WizardStyle=modern
PrivilegesRequired=admin
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no
MinVersion=10.0
SetupLogging=yes
[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"
[Messages]
WelcomeLabel1=欢迎安装 [name]
WelcomeLabel2=安装程序将把佛典研究工作台安装到您的电脑。研究资料与程序分开保存，升级和卸载时保留资料。
ButtonNext=下一步(&N) >
ButtonBack=< 上一步(&B)
ButtonInstall=安装(&I)
ButtonFinish=完成(&F)
ButtonCancel=取消
FinishedHeadingLabel=安装完成
FinishedLabel=佛典研究工作台已安装到您的电脑。可以从开始菜单打开。
[Files]
Source: "..\dist\BuddhistTextLab\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\installer-assets\MicrosoftEdgeWebview2Setup.exe"; Flags: dontcopy
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\WINDOWS.md"; DestDir: "{app}"; Flags: ignoreversion
[Icons]
Name: "{group}\佛典研究工作台"; Filename: "{app}\{#AppExe}"
Name: "{group}\卸载佛典研究工作台"; Filename: "{uninstallexe}"
Name: "{autodesktop}\佛典研究工作台"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项:"; Flags: unchecked
[Run]
Filename: "{app}\{#AppExe}"; Description: "启动佛典研究工作台"; Flags: nowait postinstall skipifsilent
[Code]
function HasWebView2: Boolean;
var Version: String;
begin
  Result := (RegQueryStringValue(HKLM32, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) or
             RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version)) and (Version <> '') and (Version <> '0.0.0.0');
end;
function PrepareToInstall(var NeedsRestart: Boolean): String;
var Code: Integer;
begin
  Result := '';
  if not HasWebView2 then begin
    ExtractTemporaryFile('MicrosoftEdgeWebview2Setup.exe');
    if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, Code) then
      Result := '无法启动 Microsoft WebView2 安装程序。'
    else if not HasWebView2 then
      Result := 'Microsoft WebView2 安装未完成，请连接网络后重新运行安装程序。';
  end;
end;
