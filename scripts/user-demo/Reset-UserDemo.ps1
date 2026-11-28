param([string]$ConfirmText)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$target = Join-Path $root '.runtime\user-demo'
$expected = [IO.Path]::GetFullPath((Join-Path $root '.runtime\user-demo'))
$backups = Join-Path $root '.runtime\user-demo-backups'

if ($ConfirmText -ne 'RESET USER DEMO DATA') {
    throw 'To rebuild, rerun with -ConfirmText "RESET USER DEMO DATA". Existing data will first be moved to a timestamped backup.'
}
if ([IO.Path]::GetFullPath($target) -ne $expected -or -not $expected.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Resolved runtime target is outside the dedicated trial worktree; refusing to move it.'
}
if (Test-Path -LiteralPath (Join-Path $target 'processes.json')) { throw 'Stop the managed demo before rebuilding.' }
function Test-LocalPort([int]$Port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try { $client.Connect('127.0.0.1', $Port); return $true }
    catch { return $false }
    finally { $client.Dispose() }
}
foreach ($port in @(8000, 5173)) {
    if (Test-LocalPort $port) { throw "Port $port is occupied; refusing to move trial data while a local service may be using it." }
}
if (Test-Path -LiteralPath $target) {
    $backupDir = Join-Path $backups (Get-Date -Format 'yyyyMMdd-HHmmss')
    if ([IO.Path]::GetFullPath($backupDir) -eq $expected -or -not ([IO.Path]::GetFullPath($backupDir)).StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Backup target failed worktree containment validation.'
    }
    New-Item -ItemType Directory -Path $backups -Force | Out-Null
    if (Test-Path -LiteralPath $backupDir) { throw 'Timestamped backup already exists; refusing to overwrite it.' }
    Move-Item -LiteralPath $target -Destination $backupDir
    Write-Host "Previous trial data preserved at $backupDir"
}
& (Join-Path $PSScriptRoot 'Initialize-UserDemo.ps1')
if ($LASTEXITCODE -ne 0) { throw 'Fresh demo initialization failed. Previous data remains in its backup directory.' }
