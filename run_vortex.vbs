Set UAC = CreateObject("Shell.Application")
Set FSO = CreateObject("Scripting.FileSystemObject")
scriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)
batPath = scriptDir & "\Iniciar VortexCore.bat"
UAC.ShellExecute batPath, "", scriptDir, "runas", 1
