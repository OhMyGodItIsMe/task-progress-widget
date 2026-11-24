# Removes the Claude progress widget for the current Windows user.
# Run it through uninstall.bat (double-click).

param([string]$ClaudeHome = (Join-Path $env:USERPROFILE ".claude"),
      [switch]$NoShortcuts)

$ErrorActionPreference = "Stop"
# Windows PowerShell 5.1 otherwise writes arrays as {"value": [...], "Count": n}.
Remove-TypeData System.Array -ErrorAction SilentlyContinue
$dest = Join-Path $ClaudeHome "mods\task-progress-bar"
$settings = Join-Path $ClaudeHome "settings.json"
$ours = @("~/.claude/mods/task-progress-bar", $dest)

Write-Host ""
Write-Host "Removing the Claude progress widget..."

Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe' OR Name='TaskProgressWidget.exe'" |
    Where-Object { $_.CommandLine -like '*progress_widget*' -or $_.Name -eq 'TaskProgressWidget.exe' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

if (-not $NoShortcuts) {
    foreach ($lnk in @((Join-Path ([Environment]::GetFolderPath("Desktop")) "Claude Progress.lnk"),
                       (Join-Path ([Environment]::GetFolderPath("Startup")) "Claude Progress Widget.lnk"))) {
        if (Test-Path $lnk) { Remove-Item $lnk -Force }
    }
}

if (Test-Path $settings) {
    $cfg = [IO.File]::ReadAllText($settings) | ConvertFrom-Json
    $changed = $false
    $p = $null
    if ($cfg -and $cfg.env) { $p = $cfg.env.PSObject.Properties["CLAUDE_CODE_PLUGIN_DIRS"] }
    if ($p -and ($ours -contains $p.Value)) {
        $cfg.env.PSObject.Properties.Remove("CLAUDE_CODE_PLUGIN_DIRS")
        $changed = $true
    }
    # Our terminal hooks (any entry that runs progress-hook.ps1); others stay.
    if ($cfg -and $cfg.hooks) {
        foreach ($ev in @($cfg.hooks.PSObject.Properties.Name)) {
            $before = @($cfg.hooks.$ev)
            $keep = @($before | Where-Object {
                -not (@($_.hooks) | Where-Object { (@($_.args) -join " ") -like "*progress-hook.ps1*" })
            })
            if ($keep.Count -ne $before.Count) {
                $changed = $true
                if ($keep.Count) { $cfg.hooks.$ev = $keep } else { $cfg.hooks.PSObject.Properties.Remove($ev) }
            }
        }
        if (-not @($cfg.hooks.PSObject.Properties).Count) { $cfg.PSObject.Properties.Remove("hooks") }
    }
    if ($changed -and $cfg.env -and -not @($cfg.env.PSObject.Properties).Count) {
        $cfg.PSObject.Properties.Remove("env")
    }
    if ($changed) {
        Copy-Item $settings "$settings.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        [IO.File]::WriteAllText($settings, ($cfg | ConvertTo-Json -Depth 50), $utf8)
    }
}

foreach ($path in @($dest, (Join-Path $ClaudeHome "task-progress"),
                    (Join-Path $ClaudeHome "task-progress-widget.json"),
                    (Join-Path $ClaudeHome "task-progress-widget.log"))) {
    if (Test-Path $path) { Remove-Item $path -Recurse -Force }
}

Write-Host "Done. Restart Claude to finish."
Write-Host ""
