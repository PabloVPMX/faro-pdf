#define AppVersion "1.6.1"
[Setup]
AppId={{FC19C06D-689C-4C3F-ACAA-11E80B6EE439}
AppName=Faro PDF
AppVersion={#AppVersion}
AppPublisher=Faro PDF
DefaultDirName={localappdata}\Programs\FaroPDF
DefaultGroupName=Faro PDF
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\release
OutputBaseFilename=FaroPDF-{#AppVersion}-Instalar
SetupIconFile=..\assets\faro.ico
UninstallDisplayIcon={app}\FaroPDF.exe
Compression=zip
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes
CloseApplications=yes
DisableProgramGroupPage=yes
VersionInfoVersion=1.6.1.0
CreateUninstallRegKey=not ValidationMode
InfoAfterFile=INSTALAR.txt

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Check: not ValidationMode

[Files]
Source: "..\dist\FaroPDF\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Remove only obsolete runtime files from our previous package on upgrade.
Type: files; Name: "{app}\_internal\icuuc.dll"
Type: files; Name: "{app}\_internal\icudt78.dll"
Type: files; Name: "{app}\_internal\ucrtbase.dll"
Type: files; Name: "{app}\_internal\api-ms-win-*.dll"
Type: files; Name: "{app}\_internal\libcrypto-3-x64.dll"
Type: files; Name: "{app}\_internal\libssl-3-x64.dll"

[Icons]
Name: "{group}\Faro PDF"; Filename: "{app}\FaroPDF.exe"; AppUserModelID: "FaroPDF.Desktop"; Check: not ValidationMode
Name: "{autodesktop}\Faro PDF"; Filename: "{app}\FaroPDF.exe"; Tasks: desktopicon; AppUserModelID: "FaroPDF.Desktop"; Check: not ValidationMode

[Registry]
Root: HKCU; Subkey: "Software\Classes\FaroPDF.Document"; ValueType: string; ValueName: ""; ValueData: "Documento PDF"; Flags: uninsdeletekey; Check: not ValidationMode
Root: HKCU; Subkey: "Software\Classes\FaroPDF.Document\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\FaroPDF.exe,0"; Check: not ValidationMode
Root: HKCU; Subkey: "Software\Classes\FaroPDF.Document\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\FaroPDF.exe"" ""%1"""; Check: not ValidationMode
Root: HKCU; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "FaroPDF.Document"; ValueData: ""; Flags: uninsdeletevalue; Check: not ValidationMode
Root: HKCU; Subkey: "Software\Classes\Applications\FaroPDF.exe"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "Faro PDF"; Flags: uninsdeletekey; Check: not ValidationMode
Root: HKCU; Subkey: "Software\Classes\Applications\FaroPDF.exe\SupportedTypes"; ValueType: string; ValueName: ".pdf"; ValueData: ""; Check: not ValidationMode
Root: HKCU; Subkey: "Software\Classes\Applications\FaroPDF.exe\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\FaroPDF.exe"" ""%1"""; Check: not ValidationMode
Root: HKCU; Subkey: "Software\FaroPDF\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "Faro PDF"; Flags: uninsdeletekey; Check: not ValidationMode
Root: HKCU; Subkey: "Software\FaroPDF\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Lector y editor de documentos PDF"; Check: not ValidationMode
Root: HKCU; Subkey: "Software\FaroPDF\Capabilities\FileAssociations"; ValueType: string; ValueName: ".pdf"; ValueData: "FaroPDF.Document"; Check: not ValidationMode
Root: HKCU; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "Faro PDF"; ValueData: "Software\FaroPDF\Capabilities"; Flags: uninsdeletevalue; Check: not ValidationMode

[Run]
Filename: "{app}\FaroPDF.exe"; Description: "Abrir Faro PDF"; Flags: nowait postinstall skipifsilent
Filename: "{app}\FaroPDF.exe"; Flags: nowait skipifnotsilent; Check: ReopenAfterUpdate
Filename: "ms-settings:defaultapps"; Description: "Elegir la aplicacion predeterminada para PDF en Windows"; Flags: shellexec nowait postinstall skipifsilent unchecked

[Code]
function ReopenAfterUpdate: Boolean;
begin
  Result := ExpandConstant('{param:FAROREOPEN|0}') = '1';
end;

function ValidationMode: Boolean;
begin
  Result := ExpandConstant('{param:VALIDATION|0}') = '1';
end;
