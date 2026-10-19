; Build from the frozen Windows bundle, never from a Linux executable.
#ifndef AppVersion
  #error Pass /DAppVersion with the application version.
#endif
#define ProjectRoot SourcePath + ".."

[Setup]
AppId={{873E567A-FA6B-43AA-A779-1771D17BFBF4}
AppName=SquackTS
AppVersion={#AppVersion}
AppPublisher=Squack TS
DefaultDirName={localappdata}\Programs\SquackTS
DefaultGroupName=SquackTS
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#ProjectRoot}\dist\installer
OutputBaseFilename=SquackTS-Setup-{#AppVersion}-x64
SetupIconFile={#ProjectRoot}\build\assets\squackts.ico
UninstallDisplayIcon={app}\SquackTS.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableWelcomePage=yes
DisableReadyPage=yes
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"

[Messages]
portuguese.FinishedLabel=A aplicação [name] está instalada. Pode abri-la pelo atalho no Ambiente de Trabalho.

[InstallDelete]
; Clear obsolete libraries on upgrade, without touching the separate user data.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#ProjectRoot}\dist\SquackTS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userdesktop}\SquackTS"; Filename: "{app}\SquackTS.exe"; WorkingDir: "{app}"
Name: "{userprograms}\SquackTS"; Filename: "{app}\SquackTS.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\SquackTS.exe"; Description: "Abrir SquackTS"; Flags: nowait postinstall skipifsilent
