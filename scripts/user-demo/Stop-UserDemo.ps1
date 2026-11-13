param([string]$RuntimeName = 'user-demo')

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
Import-Module (Join-Path $PSScriptRoot 'UserDemoRuntime.psm1') -Force
$runtime = Resolve-UserDemoRuntimePath -RepositoryRoot $root -RuntimeName $RuntimeName
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
if ($manifest.PSObject.Properties.Name -contains 'runtimeName') {
    if ([string]$manifest.runtimeName -cne $RuntimeName) {
        throw 'Process manifest belongs to a different User Demo runtime; refusing to stop anything.'
    }
} elseif ($RuntimeName -ne 'user-demo') {
    throw 'Legacy process manifest does not prove ownership of the selected isolated runtime; refusing to stop anything.'
}
$expectedDomain = Join-Path $runtime 'domain.sqlite3'
$expectedCheckpoint = Join-Path $runtime 'checkpoint.sqlite3'
if ($manifest.PSObject.Properties.Name -contains 'domainDb' -and
    [IO.Path]::GetFullPath([string]$manifest.domainDb) -ne [IO.Path]::GetFullPath($expectedDomain)) {
    throw 'Process manifest Domain path does not match the selected runtime; refusing to stop anything.'
}
if ($manifest.PSObject.Properties.Name -contains 'checkpointDb' -and
    [IO.Path]::GetFullPath([string]$manifest.checkpointDb) -ne [IO.Path]::GetFullPath($expectedCheckpoint)) {
    throw 'Process manifest Checkpoint path does not match the selected runtime; refusing to stop anything.'
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
$frontend = Get-VerifiedProcess $manifest.frontend 'Frontend'
if ($api -or $frontend) {
    Set-Content -LiteralPath $stopRequest -Value 'graceful-shutdown' -Encoding ASCII
}
if ($api) {
    $deadline = (Get-Date).AddSeconds(30)
    do {
        Start-Sleep -Milliseconds 250
        $api = Get-VerifiedProcess $manifest.api 'API'
    } while ($api -and (Get-Date) -lt $deadline)
    if ($api) {
        throw 'API did not complete graceful shutdown within 30 seconds. It was left running; inspect api.stderr.log before retrying.'
    }
}

if ($manifest.frontend) {
    $deadline = (Get-Date).AddSeconds(30)
    do {
        Start-Sleep -Milliseconds 250
        $frontend = Get-VerifiedProcess $manifest.frontend 'Frontend'
    } while ($frontend -and (Get-Date) -lt $deadline)
    if ($frontend) {
        throw 'Frontend did not complete graceful shutdown within 30 seconds. It was left running; inspect web.stderr.log before retrying.'
    }
}

if (Test-Path -LiteralPath $stopRequest) { Remove-Item -LiteralPath $stopRequest -Force }
Remove-Item -LiteralPath $manifestPath -Force
Write-Host 'OpsPilot API, Worker and local frontend completed graceful shutdown.'
Write-Host 'Sessions, messages, Domain DB, Checkpoint DB and logs were retained.'
