#ifndef MyAppVersion
  #error MyAppVersion is required. Build via scripts/build_installer.ps1, or pass /DMyAppVersion=<version from plexmuxy/VERSION>.
#endif

#define MyAppName "PlexMuxy"
#define MyAppExe "plexmuxy-gui.exe"
#define MyAppAumid "dev.masterain.plexmuxy"

[Setup]
; AppId is fixed so a newer setup detects and upgrades an existing install in place.
AppId={{9D751EA1-421A-47C8-A329-5B6AE179DC9D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
; Display as "PlexMuxy 0.2.0" instead of the default "PlexMuxy version 0.2.0".
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=PlexMuxy contributors
AppPublisherURL=https://github.com/Masterain98/PlexMuxy
AppSupportURL=https://github.com/Masterain98/PlexMuxy/issues
AppUpdatesURL=https://github.com/Masterain98/PlexMuxy/releases
DefaultDirName={localappdata}\Programs\PlexMuxy
UsePreviousAppDir=yes
DisableDirPage=auto
DisableProgramGroupPage=yes
DefaultGroupName=PlexMuxy
UninstallDisplayName={#MyAppName}
; Per-user install: no UAC prompt, standard uninstall via "Apps & features".
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2
SolidCompression=yes
OutputDir=..\dist
OutputBaseFilename=plexmuxy-{#MyAppVersion}-windows-x64-setup
SetupIconFile=..\logo\plexmuxy-app.ico
UninstallDisplayIcon={app}\{#MyAppExe}
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCompany=PlexMuxy contributors
VersionInfoCopyright=MIT License
WizardStyle=modern
CloseApplications=yes
RestartApplications=yes

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
