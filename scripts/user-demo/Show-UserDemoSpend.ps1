param([string]$RuntimeName = 'user-demo')

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
Import-Module (Join-Path $PSScriptRoot 'UserDemoRuntime.psm1') -Force
$runtime = Resolve-UserDemoRuntimePath -RepositoryRoot $root -RuntimeName $RuntimeName
$database = Join-Path $runtime 'domain.sqlite3'
if (-not (Test-Path -LiteralPath $database)) {
    throw "User Demo database for '$RuntimeName' is missing. No fee data was read."
}
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = (Get-Command python -ErrorAction Stop).Source }
$runtimeAdmin = Join-Path $PSScriptRoot 'runtime_admin.py'
& $python $runtimeAdmin summary --runtime-name $RuntimeName
if ($LASTEXITCODE -ne 0) { throw 'Could not read the local Runtime Grant fee summary.' }
