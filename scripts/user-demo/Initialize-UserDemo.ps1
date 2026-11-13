param(
    [string]$RuntimeName = 'user-demo',
    [ValidateSet('standard', 'r2-e07-queued', 'r2-e08-processed-decoy')]
    [string]$S3FixtureProfile = 'standard'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
Import-Module (Join-Path $PSScriptRoot 'UserDemoRuntime.psm1') -Force
$runtime = Resolve-UserDemoRuntimePath -RepositoryRoot $root -RuntimeName $RuntimeName
$domain = Join-Path $runtime 'domain.sqlite3'
$checkpoint = Join-Path $runtime 'checkpoint.sqlite3'
$envFile = Join-Path $root '.env'
$envExample = Join-Path $root '.env.user-demo.example'

if ($RuntimeName -eq 'user-demo' -and $S3FixtureProfile -ne 'standard') {
    throw 'R2 fixture profiles require a separate user-demo-* runtime name.'
}
if ($RuntimeName -ne 'user-demo' -and (Test-Path -LiteralPath $runtime)) {
    throw 'The selected isolated runtime directory already exists. Initialization refused to reuse or reset it.'
}
if ((Test-Path -LiteralPath $domain) -or (Test-Path -LiteralPath $checkpoint)) {
    throw 'The selected user-demo database already exists. Initialization refused to reset existing sessions.'
}
if (-not (Test-Path -LiteralPath $envFile)) {
    if (-not (Test-Path -LiteralPath $envExample)) { throw 'Missing .env.user-demo.example.' }
    Copy-Item -LiteralPath $envExample -Destination $envFile
    Write-Host 'Created the ignored local .env template. Set private demo passwords before starting.'
}

$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $command = Get-Command python -ErrorAction Stop
    $python = $command.Source
}
New-Item -ItemType Directory -Path (Split-Path -Parent $runtime) -Force | Out-Null
Push-Location $root
try {
    & $python (Join-Path $PSScriptRoot 'initialize_demo.py') `
        --runtime-name $RuntimeName --s3-fixture-profile $S3FixtureProfile
    if ($LASTEXITCODE -ne 0) { throw "Demo database initialization failed (exit $LASTEXITCODE). Existing files were preserved." }
} finally {
    Pop-Location
}
Write-Host "Initialized fresh User Demo runtime '$RuntimeName' at .runtime\$RuntimeName\."
Write-Host "Domain: .runtime\$RuntimeName\domain.sqlite3"
Write-Host "Checkpoint: .runtime\$RuntimeName\checkpoint.sqlite3"
Write-Host 'No historical Demo DB, Checkpoint, Session, Task, Memory, Runtime Grant or spend data was copied.'
Write-Host 'No Runtime Grant, Provider allowance, experiment Claim, or external business action was created.'
