; Inno Setup script for Baseline (NBA).
; Build: installer\build.ps1 (runs the web build, PyInstaller, then this script).
;
; Minimal interaction: per-user install (no admin rights, no UAC prompt), default folder, Start-menu and
; desktop shortcuts, launches the app when done. Fully silent:
;   Baseline_Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART

#define AppName "Baseline NBA"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppExe "Baseline.exe"

[Setup]
AppId={{A3E1C2D4-7B6F-4C1A-9E2D-5B8F0A1C3D7E}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Baseline
DefaultDirName={localappdata}\Programs\Baseline
DefaultGroupName={#AppName}
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableWelcomePage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=Baseline_Setup_{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExe}
CloseApplications=yes
SetupIconFile=..\assets\icon.ico

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: checkedonce

[Files]
Source: "..\dist\Baseline\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; Settings next to the exe. Kept on upgrade if the user edited it.
Source: "app.env"; DestDir: "{app}"; DestName: ".env"; Flags: onlyifdoesntexist

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
