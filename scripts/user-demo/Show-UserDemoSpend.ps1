$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = (Get-Command python -ErrorAction Stop).Source }
$runtimeAdmin = Join-Path $PSScriptRoot 'runtime_admin.py'
& $python $runtimeAdmin summary
if ($LASTEXITCODE -ne 0) { throw 'Could not read the local Runtime Grant fee summary.' }
