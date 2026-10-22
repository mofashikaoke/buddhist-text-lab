; 佛典研究工作台 · Inno Setup 安装脚本
; 由 GitHub Actions 在 Windows 上编译：iscc installer/BuddhistTextLab.iss /DAppVersion=0.3.123
#define AppName "佛典研究工作台"
#define AppExe "BuddhistTextLab.exe"
#ifndef AppVersion
  #define AppVersion "0.3.0"
#endif

[Setup]
AppId={{725321B8-20EE-4F31-9652-5140EBD1FCA6}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=mofashikaoke
AppPublisherURL=https://github.com/mofashikaoke/buddhist-text-lab
DefaultDirName={autopf}\BuddhistTextLab
DefaultGroupName=佛典研究工作台
OutputDir=installer-output
OutputBaseFilename=BuddhistTextLab-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=佛典研究工作台
WizardStyle=modern
PrivilegesRequired=admin
DisableProgramGroupPage=no

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Files]
Source: "..\dist\BuddhistTextLab\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\佛典研究工作台"; Filename: "{app}\{#AppExe}"
Name: "{group}\卸载佛典研究工作台"; Filename: "{uninstallexe}"
Name: "{autodesktop}\佛典研究工作台"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项:"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExe}"; Description: "安装完成后启动佛典研究工作台"; Flags: nowait postinstall skipifsilent
