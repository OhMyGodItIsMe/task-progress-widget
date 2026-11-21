' Double-click to open the floating Claude progress widget (no console window).
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
script = fso.GetParentFolderName(WScript.ScriptFullName) & "\progress_widget.py"

' Find Python's windowless launcher: the per-user install, the all-users one,
' or whatever is on PATH.
pyw = "pyw"
localPyw = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Launcher\pyw.exe"
winPyw = sh.ExpandEnvironmentStrings("%WINDIR%") & "\pyw.exe"
If fso.FileExists(localPyw) Then
    pyw = localPyw
ElseIf fso.FileExists(winPyw) Then
    pyw = winPyw
End If

sh.Run """" & pyw & """ -3 """ & script & """", 0, False
