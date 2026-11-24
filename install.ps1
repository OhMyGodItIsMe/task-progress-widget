# Installs the Claude progress widget for the current Windows user.
# Run it through install.bat (double-click), or:
#   powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1
# Optional: -ClaudeHome <folder> installs somewhere other than ~\.claude
# (used for testing).

param([string]$ClaudeHome = (Join-Path $env:USERPROFILE ".claude"),
      [switch]$NoShortcuts, [switch]$NoLaunch, [switch]$NoTerminalHooks)

$ErrorActionPreference = "Stop"
# Windows PowerShell 5.1 otherwise writes arrays as {"value": [...], "Count": n}.
Remove-TypeData System.Array -ErrorAction SilentlyContinue
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

# 1. The widget: the ready-made .exe from the release download, or else
#    Python with tkinter (the widget's window toolkit).
$hasExe = Test-Path (Join-Path $src "widget\TaskProgressWidget.exe")
$pyOk = $hasExe
if ($hasExe) { Say "[ok] Using the included TaskProgressWidget.exe (no Python needed)" }
foreach ($py in @("py", "python")) {
    if ($pyOk) { break }
    try {
        $pyArgs = @("-c", "import tkinter")
        if ($py -eq "py") { $pyArgs = @("-3") + $pyArgs }
        & $py @pyArgs 2>$null
        if ($LASTEXITCODE -eq 0) { $pyOk = $true; break }
    } catch { }
}
if (-not $pyOk) {
    Say "Python 3 was not found (or it has no tkinter)."
    Say "Either download the release ZIP, which includes a ready-made .exe:"
    Say "    https://github.com/OhMyGodItIsMe/task-progress-widget/releases/latest"
    Say "or install Python from https://www.python.org/downloads/ (default options),"
    Say "then run this installer again."
    exit 1
}
if (-not $hasExe) { Say "[ok] Python found" }

# 2. Close a running widget so its files can be replaced.
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe' OR Name='TaskProgressWidget.exe'" |
    Where-Object { $_.CommandLine -like '*progress_widget*' -or $_.Name -eq 'TaskProgressWidget.exe' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

# 3. Copy the mod and widget. Windows keeps a closing .exe locked for a
#    moment, so retry the removal briefly.
if (Test-Path $dest) {
    for ($i = 1; $i -le 10; $i++) {
        try { Remove-Item $dest -Recurse -Force -ErrorAction Stop; break }
        catch { if ($i -eq 10) { throw "Couldn't replace $dest (is the widget still running?): $_" }; Start-Sleep -Milliseconds 500 }
    }
}
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
    Say "[ok] Mod turned on (Claude desktop app)"
}

# 4b. Hooks for Claude Code in a terminal. Any earlier copy of ours is
# replaced; other hooks are left as they are.
$hookScript = Join-Path $dest "cli\progress-hook.ps1"
$hookEvents = [ordered]@{
    UserPromptSubmit = $null; PreToolUse = "AskUserQuestion|ExitPlanMode"; PostToolUse = "*"
    TaskCreated = $null; TaskCompleted = $null; Stop = $null; SessionEnd = $null
    Notification = "permission_prompt|elicitation_dialog|agent_needs_input"
}
if (-not ($cfg.PSObject.Properties.Name -contains "hooks")) {
    $cfg | Add-Member -NotePropertyName hooks -NotePropertyValue (New-Object PSObject)
}
foreach ($ev in $hookEvents.Keys) {
    $groups = @()
    if ($cfg.hooks.PSObject.Properties.Name -contains $ev) {
        $groups = @($cfg.hooks.$ev | Where-Object {
            -not (@($_.hooks) | Where-Object { (@($_.args) -join " ") -like "*progress-hook.ps1*" })
        })
    }
    if (-not $NoTerminalHooks) {
        $group = [ordered]@{}
        if ($hookEvents[$ev]) { $group.matcher = $hookEvents[$ev] }
        $group.hooks = @([ordered]@{
            type = "command"; command = "powershell.exe"
            args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $hookScript, $ev)
            async = $true
        })
        $groups += [pscustomobject]$group
    }
    if ($cfg.hooks.PSObject.Properties.Name -contains $ev) { $cfg.hooks.$ev = $groups }
    elseif ($groups.Count) { $cfg.hooks | Add-Member -NotePropertyName $ev -NotePropertyValue $groups }
}
[IO.File]::WriteAllText($settings, ($cfg | ConvertTo-Json -Depth 50), $utf8)
if (-not $NoTerminalHooks) { Say "[ok] Hooks added for Claude Code in a terminal" }

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
