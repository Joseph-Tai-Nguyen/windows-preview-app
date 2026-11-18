; Inno Setup script for the WinPreview offline installer.
; Build with scripts\build_installer.ps1 (runs PyInstaller first, then ISCC).
; Everything the app needs, including the Python runtime, Qt and MuPDF, is
; inside the single setup .exe, so installing needs no internet connection.

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#define AppName "WinPreview"
#define AppExe "WinPreview.exe"
; AppUserModelID must match APP_USER_MODEL_ID in src\winpreview\app.py.
#define AppUserModelID "WinPreview.WinPreview"
#define SourceDir "..\dist\WinPreview"

[Setup]
; Never change AppId: Windows uses it to recognise upgrades and uninstalls.
AppId={{8F3C6B2E-5D41-4A7B-9E2F-3C1D7A6B9E40}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=WinPreview contributors
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Installs per-user without admin rights by default; the user may choose
; "Install for all users" in a dialog (then it asks for elevation).
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\release
OutputBaseFilename=WinPreview-{#AppVersion}-setup-x64
SetupIconFile=..\src\winpreview\resources\icons\winpreview.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
LicenseFile=..\LICENSE
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes
CloseApplications=yes
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} Setup

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "openwith"; Description: "Add {#AppName} to the ""Open with"" menu for PDF files"; GroupDescription: "File associations:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "{#AppUserModelID}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "{#AppUserModelID}"; Tasks: desktopicon

[Registry]
; "Open with" entry only - WinPreview never takes over the default PDF viewer.
Root: HKA; Subkey: "Software\Classes\WinPreview.PDF"; ValueType: string; ValueName: ""; ValueData: "PDF Document"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\WinPreview.PDF\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\WinPreview.PDF\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: none; ValueName: "WinPreview.PDF"; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".pdf"; ValueData: ""; Flags: uninsdeletekey; Tasks: openwith
; Remove the app's own settings (window size, last folder) on uninstall.
Root: HKCU; Subkey: "Software\WinPreview"; Flags: uninsdeletekey dontcreatekey

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
