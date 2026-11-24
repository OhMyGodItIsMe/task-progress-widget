# Claude Code hook for the task progress widget (terminal sessions).
#
# Claude Code runs this on hook events with the event's JSON on stdin; the
# event name comes as the first argument. It keeps one progress file per
# session in ~/.claude/task-progress (cli-<session>.json), the same folder
# the widget reads. Desktop-app sessions are covered by the mod instead; for
# them this only keeps a <session>.waiting.json flag while a permission
# prompt is actually on screen, which the mod can't see by itself.
#
# Set CC_PROGRESS_DEBUG=1 to also log every raw event to
# ~/.claude/task-progress-hook-debug.jsonl.

param([string]$Event = "")

$ErrorActionPreference = "Stop"
try {
    $desktop = $env:CLAUDE_CODE_ENTRYPOINT -eq "claude-desktop"
    # Claude Code sends UTF-8; the console default (e.g. cp949 on Korean
    # Windows) would garble non-English paths and break the JSON.
    $reader = New-Object System.IO.StreamReader([Console]::OpenStandardInput(), (New-Object System.Text.UTF8Encoding($false)))
    $raw = $reader.ReadToEnd()
    if (-not $raw) { exit 0 }
    $e = $raw | ConvertFrom-Json
    if (-not $Event) { $Event = [string]$e.hook_event_name }
    $sid = ([string]$e.session_id) -replace '[^A-Za-z0-9_-]', '_'
    if (-not $sid) { exit 0 }

    $claudeHome = Join-Path $env:USERPROFILE ".claude"
    $dir = Join-Path $claudeHome "task-progress"
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
    $file = Join-Path $dir "cli-$sid.json"
    $utf8 = New-Object System.Text.UTF8Encoding($false)

    if ($env:CC_PROGRESS_DEBUG -eq "1") {
        $line = (@{ event = $Event; at = (Get-Date).ToString("o"); data = $e } | ConvertTo-Json -Depth 20 -Compress)
        [IO.File]::AppendAllText((Join-Path $claudeHome "task-progress-hook-debug.jsonl"), $line + "`n", $utf8)
    }

    if ($desktop) {
        # Desktop session: only the permission-prompt flag.
        $flag = Join-Path $dir "$sid.waiting.json"
        $prompt = $Event -eq "Notification" -and
            @("permission_prompt", "elicitation_dialog") -contains [string]$e.notification_type
        if ($prompt) {
            $now = [long]([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())
            [IO.File]::WriteAllText($flag, (@{ waiting = "permission"; ts = $now } | ConvertTo-Json -Compress), $utf8)
        } elseif (@("PostToolUse", "Stop", "UserPromptSubmit", "SessionEnd") -contains $Event) {
            if (Test-Path $flag) { Remove-Item $flag -Force }
        }
        exit 0
    }

    if ($Event -eq "SessionEnd") {
        if (Test-Path $file) { Remove-Item $file -Force }
        exit 0
    }

    # Async hooks for one session can run at the same time; take turns.
    $mutex = New-Object System.Threading.Mutex($false, "Local\cc-progress-$sid")
    if (-not $mutex.WaitOne(5000)) { exit 0 }
    try {
        $now = [long]([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())

        # Load the session's state (tasks kept as an ordered id -> task map).
        $st = @{ source = "cli"; title = ""; prompt = ""; running = $false; waiting = "";
                 stepStartedAt = 0; avgStepMs = 20000; tasks = [ordered]@{} }
        if (Test-Path $file) {
            try {
                $old = [IO.File]::ReadAllText($file) | ConvertFrom-Json
                foreach ($k in @("title", "prompt", "running", "waiting", "stepStartedAt", "avgStepMs")) {
                    if ($null -ne $old.$k) { $st[$k] = $old.$k }
                }
                if ($old.tasks) {
                    foreach ($p in $old.tasks.PSObject.Properties) {
                        $st.tasks[$p.Name] = @{ subject = [string]$p.Value.subject; status = [string]$p.Value.status }
                    }
                }
            } catch { }
        }
        $doneBefore = @($st.tasks.Values | Where-Object { $_.status -eq "completed" }).Count

        function Set-Task([string]$id, [string]$subject, [string]$status) {
            if (-not $id) { return }
            if (-not $st.tasks.Contains($id)) { $st.tasks[$id] = @{ subject = ""; status = "pending" } }
            if ($subject) { $st.tasks[$id].subject = $subject }
            if ($status) { $st.tasks[$id].status = $status }
        }

        switch ($Event) {
            "UserPromptSubmit" {
                $typed = (([string]$e.prompt) -replace '\s+', ' ').Trim()
                # Short replies ("yes", "ok do it") keep the last longer name.
                $short = $typed.Length -lt 20 -or $typed.Split(' ').Count -le 3
                if (-not ($short -and $st.prompt)) {
                    $st.prompt = $typed.Substring(0, [Math]::Min(60, $typed.Length))
                }
                if ($e.session_title) { $st.title = [string]$e.session_title }
                # Finished tasks belong to earlier turns; keep only open ones.
                $open = [ordered]@{}
                foreach ($k in $st.tasks.Keys) {
                    if ($st.tasks[$k].status -ne "completed") { $open[$k] = $st.tasks[$k] }
                }
                $st.tasks = $open
                $doneBefore = 0
                $st.running = $true; $st.waiting = ""; $st.stepStartedAt = $now
            }
            "TaskCreated" { Set-Task ([string]$e.task_id) ([string]$e.task_subject) "" ; $st.running = $true }
            "TaskCompleted" { Set-Task ([string]$e.task_id) ([string]$e.task_subject) "completed" }
            "PreToolUse" {
                # Tools that wait for the person while they run.
                if (@("AskUserQuestion", "ExitPlanMode") -contains [string]$e.tool_name) { $st.waiting = "question" }
                $st.running = $true
            }
            "PostToolUse" {
                $st.running = $true; $st.waiting = ""
                $in = $e.tool_input
                switch ([string]$e.tool_name) {
                    "TodoWrite" {
                        if ($in.todos) {
                            $st.tasks = [ordered]@{}
                            $i = 0
                            foreach ($t in $in.todos) {
                                $name = if ($t.activeForm -and $t.status -eq "in_progress") { $t.activeForm } else { $t.content }
                                $st.tasks["todo$i"] = @{ subject = [string]$name; status = [string]$t.status }
                                $i++
                            }
                            $doneBefore = [Math]::Min($doneBefore, @($st.tasks.Values | Where-Object { $_.status -eq "completed" }).Count)
                        }
                    }
                    "TaskUpdate" {
                        # Field names aren't documented; accept the likely ones.
                        $id = @($in.taskId, $in.task_id, $in.id) | Where-Object { $_ } | Select-Object -First 1
                        $status = [string]$in.status
                        if ($id) {
                            if ($status -eq "deleted") { $st.tasks.Remove([string]$id) }
                            else { Set-Task ([string]$id) ([string]$in.subject) $status }
                        }
                    }
                }
            }
            "Notification" {
                switch ([string]$e.notification_type) {
                    "permission_prompt" { $st.waiting = "permission" }
                    "elicitation_dialog" { $st.waiting = "question" }
                    "agent_needs_input" { $st.waiting = "question" }
                }
            }
            "Stop" { $st.running = $false; $st.waiting = "" }
        }

        # Progress numbers for the widget.
        $tasks = @($st.tasks.Values)
        $total = $tasks.Count
        $completed = @($tasks | Where-Object { $_.status -eq "completed" }).Count
        $active = $tasks | Where-Object { $_.status -eq "in_progress" } | Select-Object -First 1
        if (-not $active) { $active = $tasks | Where-Object { $_.status -ne "completed" } | Select-Object -First 1 }
        if ($completed -gt $doneBefore -and $st.stepStartedAt -gt 0) {
            # Learn how long a step takes (rolling average, clamped).
            $per = ($now - [long]$st.stepStartedAt) / ($completed - $doneBefore)
            $per = [Math]::Max(1000, [Math]::Min(300000, $per))
            $st.avgStepMs = [long](0.7 * [double]$st.avgStepMs + 0.3 * $per)
            $st.stepStartedAt = $now
        }

        $out = [ordered]@{
            source = "cli"; title = $st.title; prompt = $st.prompt
            total = $total; completed = $completed
            label = if ($active) { [string]$active.subject } else { "" }
            running = [bool]$st.running; done = ($total -gt 0 -and $completed -ge $total)
            waiting = [string]$st.waiting
            stepStartedAt = [long]$st.stepStartedAt; avgStepMs = [long]$st.avgStepMs; ts = $now
            tasks = $st.tasks
        }
        $tmp = "$file.tmp"
        [IO.File]::WriteAllText($tmp, ($out | ConvertTo-Json -Depth 6 -Compress), $utf8)
        Move-Item $tmp $file -Force
    } finally {
        $mutex.ReleaseMutex(); $mutex.Dispose()
    }
} catch {
    # A hook must never break Claude; drop the event (logged in debug mode).
    if ($env:CC_PROGRESS_DEBUG -eq "1") {
        $log = Join-Path $env:USERPROFILE ".claude\task-progress-hook-debug.jsonl"
        [IO.File]::AppendAllText($log, "ERROR $Event line $($_.InvocationInfo.ScriptLineNumber): $($_.Exception.Message)`n")
    }
}
exit 0
