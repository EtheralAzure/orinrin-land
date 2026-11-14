param([Parameter(Mandatory=$true)][string]$RunDirectory, [Parameter(Mandatory=$true)][int]$OwnerPid)
$ErrorActionPreference = 'Stop'
$run = [IO.Path]::GetFullPath($RunDirectory)
$project = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not $run.StartsWith($project + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Run directory is outside project.' }
$statusPath = Join-Path $run 'audio_guard.json'
$stopPath = Join-Path $run 'audio_guard.stop'
$status = @{ state='starting'; guard_pid=$PID; owner_pid=$OwnerPid; sessions=@(); errors=@(); tail_quiet=$false }
function Save-Status {
    $temporary = $statusPath + '.tmp'
    $status | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $statusPath -Force
}
$mutex = [Threading.Mutex]::new($false, 'Local\OrinrinLandEngineSystemSoundMute')
$held = $false
$guard = $null
try {
    try { $held = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $held = $true; throw 'Previous audio guard ended unexpectedly; check its restoration record before testing.' }
    if (-not $held) { throw 'Another isolated audio guard is active; run tests serially.' }
    $owner = [Diagnostics.Process]::GetProcessById($OwnerPid)
    $ownerStarted = $owner.StartTime.ToUniversalTime().Ticks
    Add-Type -TypeDefinition (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'engine_system_sound_guard.cs') -Raw)
    $guard = [OrinSystemSoundGuard]::new()
    # Let the audio engine apply the mute before allowing an error-producing child.
    Start-Sleep -Milliseconds 200
    $status.state = 'muted'
    $status.sessions = @($guard.Snapshots())
    Save-Status
    $timer = [Diagnostics.Stopwatch]::StartNew()
    while ($timer.Elapsed.TotalSeconds -lt 85 -and -not (Test-Path -LiteralPath $stopPath)) {
        try {
            $currentOwner = [Diagnostics.Process]::GetProcessById($OwnerPid)
            if ($currentOwner.StartTime.ToUniversalTime().Ticks -ne $ownerStarted) { break }
        } catch { break }
        Start-Sleep -Milliseconds 50
    }
} catch {
    $status.errors += $_.Exception.Message
} finally {
    if ($null -ne $guard) {
        try { $guard.WaitForQuiet() } catch { $status.errors += $_.Exception.Message }
        finally { $guard.Dispose() }
        $status.sessions = @($guard.Snapshots())
        $status.errors += @($guard.Errors)
        $status.tail_quiet = $guard.TailQuiet
        $status.state = if ($status.errors.Count -eq 0) {'restored'} else {'restore_failed'}
    } else { $status.state = 'failed' }
    Save-Status
    if ($held) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
if ($status.state -ne 'restored') { exit 1 }
