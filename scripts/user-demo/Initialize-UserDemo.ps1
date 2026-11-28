$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$runtime = Join-Path $root '.runtime\user-demo'
$domain = Join-Path $runtime 'domain.sqlite3'
$checkpoint = Join-Path $runtime 'checkpoint.sqlite3'
$envFile = Join-Path $root '.env'
$envExample = Join-Path $root '.env.user-demo.example'

if ((Test-Path -LiteralPath $domain) -or (Test-Path -LiteralPath $checkpoint)) {
    throw 'The user-demo database already exists. Initialization refused to reset existing sessions.'
}
if (-not (Test-Path -LiteralPath $envFile)) {
    if (-not (Test-Path -LiteralPath $envExample)) { throw 'Missing .env.user-demo.example.' }
    Copy-Item -LiteralPath $envExample -Destination $envFile
    Write-Host 'Created the ignored local .env template. Set the two required demo passwords before starting.'
}

$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $command = Get-Command python -ErrorAction Stop
    $python = $command.Source
}
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
Push-Location $root
try {
    & $python (Join-Path $PSScriptRoot 'initialize_demo.py')
    if ($LASTEXITCODE -ne 0) { throw "Demo database initialization failed (exit $LASTEXITCODE). Existing files were preserved." }
} finally {
    Pop-Location
}
Write-Host "Initialized isolated Domain data at $domain"
Write-Host 'The Checkpoint file is created by first normal app startup and retained on later starts.'
Write-Host 'No Runtime Grant, Provider allowance, experiment Claim, or external business action was created.'
