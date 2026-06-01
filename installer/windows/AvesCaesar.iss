#define AppName "Aves Caesar"
#define AppPublisher "Aves Caesar"
#define AppExeName "AvesCaesar.exe"
#define AppArchitecture "x64"

#ifndef AppVersion
#define AppVersion "0.0.0"
#endif

#ifndef SourceDir
#define SourceDir "..\..\dist\AvesCaesar"
#endif

#ifndef OutputDir
#define OutputDir "..\..\dist\installer"
#endif

[Setup]
AppId={{7B0DB6F1-6A6C-4E06-9862-B22AD7C07C0A8}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\Aves Caesar
DefaultGroupName=Aves Caesar
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=AvesCaesarSetup-{#AppVersion}-{#AppArchitecture}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
VersionInfoVersion={#AppVersion}
LicenseFile=..\..\NOTICE.txt
#ifexist "..\..\build\aves-caesar.ico"
SetupIconFile=..\..\build\aves-caesar.ico
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Messages]
english.LicenseAccepted=I accept the GNU Affero General Public License v3.0 or later.
english.LicenseNotAccepted=I do not accept the license terms.
french.LicenseAccepted=J'accepte la Licence publique générale GNU Affero version 3.0 ou ultérieure.
french.LicenseNotAccepted=Je n'accepte pas les termes de la licence.
spanish.LicenseAccepted=Acepto la Licencia Pública General Affero de GNU v3.0 o posterior.
spanish.LicenseNotAccepted=No acepto los términos de la licencia.
german.LicenseAccepted=Ich akzeptiere die GNU Affero General Public License Version 3.0 oder neuer.
german.LicenseNotAccepted=Ich akzeptiere die Lizenzbedingungen nicht.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
Type: filesandordirs; Name: "{app}\*"; Check: IsUpdateInstall

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Excludes: "_internal\resources\models\*"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceDir}\_internal\resources\models\*"; DestDir: "{app}\_internal\resources\models"; Flags: ignoreversion recursesubdirs createallsubdirs nocompression solidbreak
Source: "..\..\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\NOTICE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\LICENSES\*"; DestDir: "{app}\LICENSES"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Aves Caesar"; Filename: "{app}\{#AppExeName}"
Name: "{userdesktop}\Aves Caesar"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon; Check: ShouldCreateDesktopIcon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,Aves Caesar}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\{#AppExeName}"; Flags: nowait skipifnotsilent; Check: ShouldLaunchAfterSilentUpdate
Filename: "{cmd}"; Parameters: "/C timeout /T 2 /NOBREAK >NUL & del /F /Q ""{code:GetDeleteInstallerPath}"""; Flags: runhidden nowait; Check: ShouldDeleteInstaller

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\Aves Caesar"

[Code]
function IsUpdateInstall: Boolean;
begin
  Result := ExpandConstant('{param:UPDATE|0}') = '1';
end;

function ShouldCreateDesktopIcon: Boolean;
begin
  Result := not IsUpdateInstall;
end;

function ShouldLaunchAfterSilentUpdate: Boolean;
begin
  Result := IsUpdateInstall;
end;

function GetDeleteInstallerPath(Param: String): String;
begin
  Result := ExpandConstant('{param:DELETEINSTALLER|}');
end;

function StartsWith(Text: String; Prefix: String): Boolean;
begin
  Result := CompareText(Copy(Text, 1, Length(Prefix)), Prefix) = 0;
end;

function ShouldDeleteInstaller: Boolean;
var
  DeleteInstallerPath: String;
  UpdateCachePath: String;
begin
  DeleteInstallerPath := GetDeleteInstallerPath('');
  UpdateCachePath := AddBackslash(ExpandConstant('{userappdata}\Aves Caesar\cache\updates'));
  Result := IsUpdateInstall and (DeleteInstallerPath <> '') and StartsWith(DeleteInstallerPath, UpdateCachePath) and FileExists(DeleteInstallerPath);
end;
