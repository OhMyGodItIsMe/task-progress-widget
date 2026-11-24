' Double-click to open the floating Claude progress widget (no console window).
' Never show a script error box: if the .exe can't start, try Python instead.
On Error Resume Next
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)

' The release download ships a ready-made .exe; use it when it's there.
exe = here & "\TaskProgressWidget.exe"
If fso.FileExists(exe) Then
    Err.Clear
    sh.Run """" & exe & """", 0, False
    If Err.Number = 0 Then WScript.Quit
    Err.Clear
End If

' Otherwise run the Python script with Python's windowless launcher: the
' per-user install, the all-users one, or whatever is on PATH.
script = here & "\progress_widget.py"
pyw = "pyw"
localPyw = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Launcher\pyw.exe"
winPyw = sh.ExpandEnvironmentStrings("%WINDIR%") & "\pyw.exe"
If fso.FileExists(localPyw) Then
    pyw = localPyw
ElseIf fso.FileExists(winPyw) Then
    pyw = winPyw
End If

sh.Run """" & pyw & """ -3 """ & script & """", 0, False
