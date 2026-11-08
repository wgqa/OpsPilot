$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$runtime = Join-Path $root '.runtime\user-demo'
$manifestPath = Join-Path $runtime 'processes.json'
$stopRequest = Join-Path $runtime 'shutdown.request'

if (-not (Test-Path -LiteralPath $manifestPath)) {
    Write-Host 'No managed user-demo process manifest exists.'
    exit 0
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ([IO.Path]::GetFullPath([string]$manifest.root) -ne [IO.Path]::GetFullPath($root)) {
    throw 'Process manifest belongs to a different worktree; refusing to stop anything.'
}

function Get-VerifiedProcess($Entry, [string]$Label) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($Entry.pid)" -ErrorAction SilentlyContinue
    if (-not $process) { return $null }
    $exeMatches = [IO.Path]::GetFullPath([string]$process.ExecutablePath) -eq [IO.Path]::GetFullPath([string]$Entry.executable)
    $cmdMatches = ([string]$process.CommandLine).IndexOf([string]$Entry.commandMarker, [StringComparison]::OrdinalIgnoreCase) -ge 0
    if (-not ($exeMatches -and $cmdMatches)) { throw "$Label PID does not match the saved OpsPilot process identity; refusing to stop it." }
    return $process
}

$api = Get-VerifiedProcess $manifest.api 'API'
if ($api) {
    Set-Content -LiteralPath $stopRequest -Value 'graceful-shutdown' -Encoding ASCII
    $deadline = (Get-Date).AddSeconds(30)
    do {
        Start-Sleep -Milliseconds 250
        $api = Get-VerifiedProcess $manifest.api 'API'
    } while ($api -and (Get-Date) -lt $deadline)
    if ($api) {
        throw 'API did not complete graceful shutdown within 30 seconds. It was left running; inspect api.stderr.log before retrying.'
    }
}

$frontend = Get-VerifiedProcess $manifest.frontend 'Frontend'
if ($frontend) {
    Stop-Process -Id ([int]$manifest.frontend.pid) -Force
    $deadline = (Get-Date).AddSeconds(10)
    do {
        Start-Sleep -Milliseconds 250
        $frontend = Get-VerifiedProcess $manifest.frontend 'Frontend'
    } while ($frontend -and (Get-Date) -lt $deadline)
    if ($frontend) { throw 'Vite process is still running; manifest retained for safe recovery.' }
}

if (Test-Path -LiteralPath $stopRequest) { Remove-Item -LiteralPath $stopRequest -Force }
Remove-Item -LiteralPath $manifestPath -Force
Write-Host 'OpsPilot API completed graceful shutdown; local frontend process stopped.'
Write-Host 'Sessions, messages, Domain DB, Checkpoint DB and logs were retained.'
