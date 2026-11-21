# Installs the Claude progress widget for the current Windows user.
# Run it through install.bat (double-click), or:
#   powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1
# Optional: -ClaudeHome <folder> installs somewhere other than ~\.claude
# (used for testing).

param([string]$ClaudeHome = (Join-Path $env:USERPROFILE ".claude"),
      [switch]$NoShortcuts, [switch]$NoLaunch)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$src = Join-Path $here "task-progress-bar"
$dest = Join-Path $ClaudeHome "mods\task-progress-bar"
$settings = Join-Path $ClaudeHome "settings.json"
$pluginDir = "~/.claude/mods/task-progress-bar"
if ($ClaudeHome -ne (Join-Path $env:USERPROFILE ".claude")) { $pluginDir = $dest }

function Say($text) { Write-Host $text }

Say ""
Say "Installing the Claude progress widget..."
Say ""

# 1. Python with tkinter (the widget's window toolkit).
$pyOk = $false
foreach ($py in @("py", "python")) {
    try {
        $pyArgs = @("-c", "import tkinter")
        if ($py -eq "py") { $pyArgs = @("-3") + $pyArgs }
        & $py @pyArgs 2>$null
        if ($LASTEXITCODE -eq 0) { $pyOk = $true; break }
    } catch { }
}
if (-not $pyOk) {
    Say "Python 3 was not found (or it has no tkinter)."
    Say "Install it from https://www.python.org/downloads/ (keep the default options),"
    Say "then run this installer again."
    exit 1
}
Say "[ok] Python found"

# 2. Close a running widget so its files can be replaced.
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*progress_widget*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

# 3. Copy the mod and widget.
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
New-Item -ItemType Directory -Force (Split-Path $dest) | Out-Null
Copy-Item $src $dest -Recurse
New-Item -ItemType Directory -Force (Join-Path $ClaudeHome "task-progress") | Out-Null
Say "[ok] Files copied to $dest"

# 4. Turn the mod on in Claude's settings, keeping every other setting.
$utf8 = New-Object System.Text.UTF8Encoding($false)
if (Test-Path $settings) {
    $raw = [IO.File]::ReadAllText($settings)
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    Copy-Item $settings "$settings.bak-$stamp"
    try { $cfg = $raw | ConvertFrom-Json } catch {
        Say "Could not read $settings (it is not valid JSON). Nothing was changed there."
        Say "Add this to it by hand:  `"env`": { `"CLAUDE_CODE_PLUGIN_DIRS`": `"$pluginDir`" }"
        exit 1
    }
    if ($null -eq $cfg) { $cfg = New-Object PSObject }
} else {
    $cfg = New-Object PSObject
}
if (-not ($cfg.PSObject.Properties.Name -contains "env")) {
    $cfg | Add-Member -NotePropertyName env -NotePropertyValue (New-Object PSObject)
}
$current = $cfg.env.PSObject.Properties["CLAUDE_CODE_PLUGIN_DIRS"]
if ($current -and $current.Value -and $current.Value -ne $pluginDir) {
    Say ""
    Say "Your Claude settings already load another mod folder:"
    Say "    $($current.Value)"
    Say "I did not change it. To use this widget too, ask Claude to add"
    Say "    $pluginDir"
    Say "to CLAUDE_CODE_PLUGIN_DIRS in $settings"
    Say ""
} else {
    if ($current) { $current.Value = $pluginDir }
    else { $cfg.env | Add-Member -NotePropertyName CLAUDE_CODE_PLUGIN_DIRS -NotePropertyValue $pluginDir }
    [IO.File]::WriteAllText($settings, ($cfg | ConvertTo-Json -Depth 50), $utf8)
    Say "[ok] Mod turned on in $settings"
}

# 5. Desktop and startup shortcuts.
$launcher = Join-Path $dest "widget\Open Claude Progress.vbs"
if (-not $NoShortcuts) {
    $shell = New-Object -ComObject WScript.Shell
    foreach ($place in @(
            @([Environment]::GetFolderPath("Desktop"), "Claude Progress.lnk"),
            @([Environment]::GetFolderPath("Startup"), "Claude Progress Widget.lnk"))) {
        $lnk = $shell.CreateShortcut((Join-Path $place[0] $place[1]))
        $lnk.TargetPath = Join-Path $env:WINDIR "System32\wscript.exe"
        $lnk.Arguments = "`"$launcher`""
        $lnk.WorkingDirectory = Split-Path $launcher
        $lnk.IconLocation = (Join-Path $env:WINDIR "System32\imageres.dll") + ",186"
        $lnk.Description = "Open the floating Claude progress widget"
        $lnk.Save()
    }
    Say "[ok] Desktop shortcut added, and it opens when Windows starts"
}

# 6. Open the widget.
if (-not $NoLaunch) {
    Start-Process explorer.exe "`"$launcher`""
    Say "[ok] Widget opened (top-right corner of your main screen)"
}

Say ""
Say "Done. Last step: fully quit Claude and open it again."
Say "Sessions only show up in the widget after that restart."
Say ""
