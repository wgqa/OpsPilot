param([string]$RuntimeName = 'user-demo')

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
Import-Module (Join-Path $PSScriptRoot 'UserDemoRuntime.psm1') -Force
$runtime = Resolve-UserDemoRuntimePath -RepositoryRoot $root -RuntimeName $RuntimeName
$domain = Join-Path $runtime 'domain.sqlite3'
if (-not (Test-Path -LiteralPath $domain)) {
    throw "Demo data is missing for '$RuntimeName'. Initialize this runtime before configuring Live mode."
}
if (-not (Test-Path -LiteralPath (Join-Path $root '.env'))) {
    throw 'Local .env is missing. Run Initialize-UserDemo.ps1 and configure Live-only values there.'
}

$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = (Get-Command python -ErrorAction Stop).Source }
$runtimeAdmin = Join-Path $PSScriptRoot 'runtime_admin.py'
& $python $runtimeAdmin configure --runtime-name $RuntimeName
if ($LASTEXITCODE -ne 0) {
    throw 'No Runtime Grant was created. Review the error above; the command does not send a Provider request.'
}
