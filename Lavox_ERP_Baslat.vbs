Option Explicit

Dim shell, fileSystem, appDirectory, appScript, executablePath, commandLine
Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")

appDirectory = fileSystem.GetParentFolderName(WScript.ScriptFullName)
appScript = fileSystem.BuildPath(appDirectory, "desktop_app.py")
shell.CurrentDirectory = appDirectory

executablePath = FindExecutable("pythonw.exe")
If executablePath <> "" Then
    commandLine = Quote(executablePath) & " " & Quote(appScript)
Else
    executablePath = FindExecutable("pyw.exe")
    If executablePath <> "" Then
        commandLine = Quote(executablePath) & " -3 " & Quote(appScript)
    Else
        MsgBox "Python masaüstü çalışma zamanı bulunamadı. Sistem yöneticinize başvurun.", _
            vbExclamation, "LAVOX ELEKTRONİK ERP"
        WScript.Quit 1
    End If
End If

shell.Run commandLine, 0, False

Function FindExecutable(executableName)
    Dim pathValue, pathEntries, pathEntry, entry, candidate
    FindExecutable = ""
    pathValue = shell.ExpandEnvironmentStrings("%PATH%")
    pathEntries = Split(pathValue, ";")
    For Each pathEntry In pathEntries
        entry = Trim(Replace(pathEntry, Chr(34), ""))
        If entry <> "" Then
            candidate = fileSystem.BuildPath(entry, executableName)
            If fileSystem.FileExists(candidate) Then
                FindExecutable = candidate
                Exit Function
            End If
        End If
    Next
End Function

Function Quote(value)
    Quote = Chr(34) & value & Chr(34)
End Function
