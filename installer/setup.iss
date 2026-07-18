; Inno Setup Script for Bulk Email Manager
; Download Inno Setup from: https://jrsoftware.org/isinfo.php
; Compile this script with Inno Setup to create a professional installer

#define MyAppName "Bulk Email Manager"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "Bulk Email Manager"
#define MyAppURL "https://github.com/your-username/bulk-email-manager"
#define MyAppExeName "BulkEmailManager.exe"

[Setup]
AppId={{B1E2D3F4-5A6B-7C8D-9E0F-A1B2C3D4E5F6}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
LicenseFile=
OutputDir=installer\output
OutputBaseFilename=BulkEmailManager-{#MyAppVersion}-Setup
SetupIconFile=
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridingOwnedConnection

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Copy the PyInstaller build output
Source: "dist\BulkEmailManager\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Copy example env file
Source: ".env.example"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Registry]
; Add to PATH (optional)
Root: HKCU; Subkey: "Environment"; ValueName: "Path"; ValueData: "{app};{olddata}"; ValueType: expandsz; Flags: uninsdeletevalue; Tasks: addtopath

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
