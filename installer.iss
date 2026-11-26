; ==============================================================================
; VortexCore Hub // Inno Setup Script
; Genera el instalador oficial standalone Vortex-core-hub-Setup.exe
; Desarrollado por Faundezz21
; ==============================================================================

#define MyAppName "VortexCore Hub"
; La versión se lee del archivo VERSION (o se pasa con /DMyAppVersion=x.y.z)
#ifndef MyAppVersion
  #define VersionFile FileOpen(AddBackslash(SourcePath) + "VERSION")
  #define MyAppVersion Trim(FileRead(VersionFile))
  #expr FileClose(VersionFile)
#endif
#define MyAppPublisher "Faundezz21"
#define MyAppURL "https://github.com/Faundezz21/VortexCore-Hub"
#define MyAppExeName "VortexCoreHub.exe"

[Setup]
AppId={{D37F8E8A-9A2E-410F-B4A1-F998394421FA}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\VortexCore Hub
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=dist
OutputBaseFilename=Vortex-core-hub-Setup
SetupIconFile={#SourcePath}\vortex_icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\vortex_icon.ico
UninstallDisplayName={#MyAppName} v{#MyAppVersion}
VersionInfoVersion={#MyAppVersion}
; Cerrar la app (bandeja incluida) si está abierta al actualizar
CloseApplications=force
RestartApplications=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "Iniciar VortexCore Hub automáticamente al encender Windows"; GroupDescription: "Configuración de Inicio:"
Name: "installapo"; Description: "Instalar motor de ecualización global (Equalizer APO) si falta"; GroupDescription: "Audio avanzado:"

[Files]
Source: "dist\VortexCoreHub\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourcePath}\vortex_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\vortex_icon.ico"
Name: "{autoprograms}\{#MyAppName}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\vortex_icon.ico"; Tasks: desktopicon

[Registry]
; Limpieza del auto-inicio antiguo (<= 7.8.6) basado en la clave Run: no funcionaba con apps de Administrador
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "VortexCoreHub"; Flags: deletevalue uninsdeletevalue

[Run]
; Auto-inicio: tarea programada "al iniciar sesión" con privilegios elevados (sin UAC en cada arranque)
Filename: "{app}\{#MyAppExeName}"; Parameters: "--set-autostart on"; StatusMsg: "Configurando inicio automático..."; Flags: runhidden waituntilterminated; Tasks: autostart
Filename: "{app}\{#MyAppExeName}"; Parameters: "--setup-apo"; StatusMsg: "Instalando motor de ecualización global (Equalizer APO)..."; Flags: runhidden waituntilterminated; Tasks: installapo
Filename: "{app}\{#MyAppExeName}"; Parameters: "--setup-vigem"; StatusMsg: "Configurando soporte de mando PS5 (ViGEmBus)..."; Flags: runhidden waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: shellexec nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM {#MyAppExeName} /F"; Flags: runhidden; RunOnceId: "KillVortex"
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /TN VortexCoreHub /F"; Flags: runhidden; RunOnceId: "DelVortexTask"
