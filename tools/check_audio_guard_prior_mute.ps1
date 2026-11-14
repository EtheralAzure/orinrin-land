param([Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference = 'Stop'
$project = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not ([IO.Path]::GetFullPath($OutputPath)).StartsWith($project + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Output path is outside project.' }
Add-Type -TypeDefinition (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'engine_system_sound_guard.cs') -Raw)
$mutex = [Threading.Mutex]::new($false, 'LocalOrinrinLandEngineSystemSoundMute')
if (-not $mutex.WaitOne(0)) { throw 'An audio guard is active.' }
$outer = $null
$inner = $null
$report = @{ passed=$false }
try {
    $outer = [OrinSystemSoundGuard]::new()
    $inner = [OrinSystemSoundGuard]::new()
    $inner.Dispose()
    $report.inner = @($inner.Snapshots())
    $report.passed = @($report.inner | Where-Object {-not $_.InitiallyMuted -or -not $_.Restored}).Count -eq 0
} finally {
    if ($null -ne $inner) { $inner.Dispose() }
    if ($null -ne $outer) { $outer.WaitForQuiet(); $outer.Dispose(); $report.outer=@($outer.Snapshots()); $report.outerErrors=@($outer.Errors) }
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
$report.passed = $report.passed -and $report.outerErrors.Count -eq 0 -and @($report.outer | Where-Object {-not $_.Restored}).Count -eq 0
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
if (-not $report.passed) { exit 1 }
