[Setup]
AppId={{8F3A2C1D-4B7E-4F9A-B2D6-1E5C8A3F7B9D}
AppName=Shark Account System
AppVersion=2.0
AppPublisher=Shark Dev
DefaultDirName={autopf}\Shark Account System
DefaultGroupName=Shark Account System
AllowNoIcons=yes
WizardStyle=modern
Compression=lzma2/ultra64
SolidCompression=yes
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\SharkAccountSystem.exe
UninstallDisplayName=Shark Account System
OutputDir=installer_output
OutputBaseFilename=SharkAccountSystem_v2.0_Setup
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
VersionInfoVersion=2.0.0.0
VersionInfoCompany=Shark Dev
VersionInfoDescription=Shark Account System Setup
VersionInfoProductName=Shark Account System
VersionInfoProductVersion=2.0

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon"; Description: "Zapuskat' pri starte Windows"; GroupDescription: "Avtozapusk:"; Flags: unchecked

[Files]
Source: "dist\SharkAccountSystem\SharkAccountSystem.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\SharkAccountSystem\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*.log,sessions\*,avatars\*,mafs\*,data.db"
Source: "subsitems.js"; DestDir: "{app}"; Flags: ignoreversion
Source: "session_bridge.js"; DestDir: "{app}"; Flags: ignoreversion
Source: "config.json"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist
Source: "node\node.exe"; DestDir: "{app}\node"; Flags: ignoreversion
Source: "node_modules\*"; DestDir: "{app}\node_modules"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "resources\*"; DestDir: "{app}\resources"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "bg.jpg"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Dirs]
Name: "{app}\sessions"; Permissions: users-full
Name: "{app}\avatars"; Permissions: users-full
Name: "{app}\mafs"; Permissions: users-full

[Icons]
Name: "{group}\Shark Account System"; Filename: "{app}\SharkAccountSystem.exe"; IconFilename: "{app}\icon.ico"
Name: "{group}\Udalit' Shark Account System"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Shark Account System"; Filename: "{app}\SharkAccountSystem.exe"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon
Name: "{autostartup}\Shark Account System"; Filename: "{app}\SharkAccountSystem.exe"; Tasks: startupicon

[Run]
Filename: "{app}\SharkAccountSystem.exe"; Description: "{cm:LaunchProgram,Shark Account System}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\*.log"
Type: files; Name: "{app}\subs_success.txt"
Type: files; Name: "{app}\subs_blacklist.txt"
Type: files; Name: "{app}\items_success.txt"
Type: files; Name: "{app}\items_blacklist.txt"
Type: dirifempty; Name: "{app}\mafs"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
  if not IsWin64 then begin
    MsgBox('Shark Account System requires 64-bit Windows 10 or newer.', mbError, MB_OK);
    Result := False;
  end;
end;
