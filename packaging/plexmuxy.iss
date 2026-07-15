#ifndef MyAppVersion
  #define MyAppVersion "0.2.0"
#endif

#define MyAppName "PlexMuxy"
#define MyAppExe "plexmuxy-gui.exe"
#define MyAppAumid "com.plexmuxy.gui"

[Setup]
AppId={{9D751EA1-421A-47C8-A329-5B6AE179DC9D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=PlexMuxy contributors
AppPublisherURL=https://github.com/Masterain98/PlexMuxy
AppSupportURL=https://github.com/Masterain98/PlexMuxy/issues
DefaultDirName={localappdata}\Programs\PlexMuxy
DefaultGroupName=PlexMuxy
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2
SolidCompression=yes
OutputDir=..\dist
OutputBaseFilename=plexmuxy-{#MyAppVersion}-windows-x64-setup
SetupIconFile=..\logo\plexmuxy-app.ico
UninstallDisplayIcon={app}\{#MyAppExe}
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Files]
Source: "..\dist\plexmuxy-gui\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PlexMuxy"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"; AppUserModelID: "{#MyAppAumid}"
Name: "{autodesktop}\PlexMuxy"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"; AppUserModelID: "{#MyAppAumid}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Registry]
Root: HKCU; Subkey: "Software\Classes\plexmuxy"; ValueType: string; ValueData: "URL:PlexMuxy task"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\plexmuxy"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\plexmuxy\DefaultIcon"; ValueType: string; ValueData: "{app}\{#MyAppExe},0"
Root: HKCU; Subkey: "Software\Classes\plexmuxy\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExe}"" ""%1"""

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Launch PlexMuxy"; Flags: nowait postinstall skipifsilent
