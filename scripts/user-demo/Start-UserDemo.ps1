param(
    [ValidateSet('S1', 'S2')]
    [string]$Profile = 'S1',
    [ValidateSet('Offline', 'Live')]
    [string]$Mode = 'Offline',
    [string]$RuntimeName = 'user-demo'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
Import-Module (Join-Path $PSScriptRoot 'UserDemoRuntime.psm1') -Force
$runtime = Resolve-UserDemoRuntimePath -RepositoryRoot $root -RuntimeName $RuntimeName
$domain = Join-Path $runtime 'domain.sqlite3'
$checkpoint = Join-Path $runtime 'checkpoint.sqlite3'
$envFile = Join-Path $root '.env'
$manifestPath = Join-Path $runtime 'processes.json'
$stopRequest = Join-Path $runtime 'shutdown.request'

if (-not (Test-Path -LiteralPath $domain)) { throw "Demo data is missing for '$RuntimeName'. Run Initialize-UserDemo.ps1 -RuntimeName '$RuntimeName' once." }
if ($RuntimeName -ne 'user-demo' -and -not (Test-Path -LiteralPath $checkpoint)) {
    throw "Checkpoint data is missing for '$RuntimeName'. Reinitialize only a fresh runtime after confirming the directory is absent."
}
if (-not (Test-Path -LiteralPath $envFile)) { throw 'Local .env is missing. Run Initialize-UserDemo.ps1 and set demo passwords.' }
if (Test-Path -LiteralPath $manifestPath) { throw 'A process manifest already exists. Run Stop-UserDemo.ps1 before starting again.' }
if (Test-Path -LiteralPath $stopRequest) { throw 'A prior shutdown request remains. Inspect process/log state before starting.' }

function Read-LocalEnv([string]$Path) {
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) { continue }
        if ($trimmed -notmatch '^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') { throw 'Invalid .env line. Use KEY=VALUE syntax.' }
        $value = $Matches[2].Trim()
        if ($value.Length -ge 2 -and (($value[0] -eq '"' -and $value[-1] -eq '"') -or ($value[0] -eq "'" -and $value[-1] -eq "'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $values[$Matches[1]] = $value
    }
    return $values
}

$dotenv = Read-LocalEnv $envFile
$templateFile = Join-Path $root '.env.user-demo.example'
$template = if (Test-Path -LiteralPath $templateFile) { Read-LocalEnv $templateFile } else { @{} }
$processEnvironment = [Environment]::GetEnvironmentVariables('Process')
function Get-EffectiveEnv([string]$Name) {
    if ($processEnvironment.Contains($Name)) { return [string]$processEnvironment[$Name] }
    if ($dotenv.ContainsKey($Name)) { return [string]$dotenv[$Name] }
    return ''
}
foreach ($name in @('OPSPILOT_WEB_SUPPORT_PASSWORD', 'OPSPILOT_WEB_APPROVER_PASSWORD')) {
    $value = Get-EffectiveEnv $name
    $templateValue = if ($template.ContainsKey($name)) { [string]$template[$name] } else { '' }
    if ($value.Length -lt 12 -or $value -match '^(?i:CHANGE_ME|REPLACE_ME|YOUR_)' -or ($templateValue -and $value -ieq $templateValue)) {
        throw "Set a private local password of at least 12 characters for $name in .env or the process environment; the example value is not accepted."
    }
}

$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = (Get-Command python -ErrorAction Stop).Source }
& $python -c 'import fastapi, uvicorn, langchain_openai, langgraph, langgraph.checkpoint.sqlite'
if ($LASTEXITCODE -ne 0) { throw 'Python dependencies are missing. Install the project and dev dependencies using USER_GUIDE.md.' }
$node = (Get-Command node -ErrorAction Stop).Source
$vite = Join-Path $root 'frontend\node_modules\vite\bin\vite.js'
if (-not (Test-Path -LiteralPath $vite)) { throw 'Frontend dependencies are missing. Run npm ci in frontend.' }
$webLauncher = Join-Path $root 'frontend\user-demo-server.mjs'
if (-not (Test-Path -LiteralPath $webLauncher)) { throw 'The user-demo Vite lifecycle launcher is missing.' }

if ($Mode -eq 'Live') {
    $runtimeAdmin = Join-Path $PSScriptRoot 'runtime_admin.py'
    & $python $runtimeAdmin preflight --runtime-name $RuntimeName
    if ($LASTEXITCODE -ne 0) {
        throw 'Live mode was not started. Fix the Runtime Grant/configuration shown above; no Provider request was sent.'
    }
}

function Test-LocalPort([int]$Port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try { $client.Connect('127.0.0.1', $Port); return $true }
    catch { return $false }
    finally { $client.Dispose() }
}
foreach ($port in @(8000, 5173)) {
    if (Test-LocalPort $port) { throw "Port $port is already in use; no demo process was started." }
}

$logs = Join-Path $runtime 'logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$apiOut = Join-Path $logs 'api.stdout.log'
$apiErr = Join-Path $logs 'api.stderr.log'
$webOut = Join-Path $logs 'web.stdout.log'
$webErr = Join-Path $logs 'web.stderr.log'
$emptyStdin = Join-Path $logs 'empty.stdin'
[System.IO.File]::WriteAllBytes($emptyStdin, [byte[]]::new(0))
$apiLauncher = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'run_api.py')).Path
$profileService = if ($Profile -eq 'S2') { 'orders-demo-s2' } else { 'orders-demo' }
$profileIntegration = if ($Profile -eq 'S2') { 'integration-s2-a' } else { 'integration-a' }
$runtimeEnabled = if ($Mode -eq 'Live') { '1' } else { '0' }
$providerEnabled = if ($Mode -eq 'Live') { '1' } else { '0' }
$providerKey = if ($Mode -eq 'Live') { [string]$dotenv['OPSPILOT_MODEL_API_KEY'] } else { '' }

$overrides = @{
    OPSPILOT_DB_PATH = $domain
    OPSPILOT_CHECKPOINT_DB_PATH = $checkpoint
    OPSPILOT_WEB_ORIGIN = 'http://127.0.0.1:5173'
    OPSPILOT_API_ORIGIN = 'http://127.0.0.1:8000'
    OPSPILOT_USER_DEMO_WEB_PORT = '5173'
    OPSPILOT_USER_DEMO_RUNTIME_NAME = $RuntimeName
    OPSPILOT_DEMO_SERVICE_ID = $profileService
    OPSPILOT_DEMO_INTEGRATION_ID = $profileIntegration
    OPSPILOT_ASSISTANT_RUNTIME_ENABLED = $runtimeEnabled
    OPSPILOT_ASSISTANT_PROVIDER_ENABLED = $providerEnabled
    OPSPILOT_LEGACY_PROVIDER_ENABLED = '0'
    OPSPILOT_ASSISTANT_EXPERIMENT_ID = ''
    OPSPILOT_MODEL_API_KEY = $providerKey
}
$apiCredentials = @{
    OPSPILOT_WEB_SUPPORT_PASSWORD = Get-EffectiveEnv 'OPSPILOT_WEB_SUPPORT_PASSWORD'
    OPSPILOT_WEB_APPROVER_PASSWORD = Get-EffectiveEnv 'OPSPILOT_WEB_APPROVER_PASSWORD'
    OPSPILOT_WEB_SUPPORT_B_PASSWORD = Get-EffectiveEnv 'OPSPILOT_WEB_SUPPORT_B_PASSWORD'
    OPSPILOT_WEB_APPROVER_B_PASSWORD = Get-EffectiveEnv 'OPSPILOT_WEB_APPROVER_B_PASSWORD'
}
if ($Mode -eq 'Live') {
    foreach ($name in @(
        'OPSPILOT_MODEL_NAME', 'OPSPILOT_MODEL_BASE_URL', 'OPSPILOT_MODEL_CONFIG_VERSION',
        'OPSPILOT_MODEL_PRICE_VERSION', 'OPSPILOT_ASSISTANT_SERVICE_IDENTITY',
        'OPSPILOT_MODEL_INPUT_RATE_MICRO_PER_MILLION', 'OPSPILOT_MODEL_OUTPUT_RATE_MICRO_PER_MILLION'
    )) {
        if (-not $dotenv.ContainsKey($name)) { throw "Live mode requires $name in this worktree's .env." }
        $overrides[$name] = [string]$dotenv[$name]
    }
}
$oldEnvironment = @{}
foreach ($name in $overrides.Keys) {
    $oldEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    [Environment]::SetEnvironmentVariable($name, [string]$overrides[$name], 'Process')
}
$oldApiCredentials = @{}
foreach ($name in $apiCredentials.Keys) {
    $oldApiCredentials[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
$apiProcess = $null
$webProcess = $null
try {
    foreach ($name in $apiCredentials.Keys) {
        [Environment]::SetEnvironmentVariable($name, [string]$apiCredentials[$name], 'Process')
    }
    $apiProcess = Start-Process -FilePath $python -ArgumentList @('"' + $apiLauncher + '"') -WorkingDirectory $root `
        -WindowStyle Hidden -PassThru -RedirectStandardInput $emptyStdin `
        -RedirectStandardOutput $apiOut -RedirectStandardError $apiErr
    foreach ($name in $apiCredentials.Keys) {
        [Environment]::SetEnvironmentVariable($name, $oldApiCredentials[$name], 'Process')
    }
    $webArgs = '"' + $webLauncher + '"'
    $webProcess = Start-Process -FilePath $node -ArgumentList $webArgs -WorkingDirectory (Join-Path $root 'frontend') `
        -WindowStyle Hidden -PassThru -RedirectStandardInput $emptyStdin `
        -RedirectStandardOutput $webOut -RedirectStandardError $webErr
} finally {
    foreach ($name in $overrides.Keys) {
        [Environment]::SetEnvironmentVariable($name, $oldEnvironment[$name], 'Process')
    }
    foreach ($name in $apiCredentials.Keys) {
        [Environment]::SetEnvironmentVariable($name, $oldApiCredentials[$name], 'Process')
    }
}

$record = [ordered]@{
    root = $root
    runtimeName = $RuntimeName
    domainDb = $domain
    checkpointDb = $checkpoint
    profile = $Profile
    api = [ordered]@{ pid = $apiProcess.Id; executable = $python; commandMarker = $apiLauncher }
    frontend = [ordered]@{ pid = $webProcess.Id; executable = $node; commandMarker = $webLauncher }
    startedAt = (Get-Date).ToUniversalTime().ToString('o')
}
$record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

$apiReady = $false
$webReady = $false
for ($i = 0; $i -lt 60; $i++) {
    if (-not $apiReady) {
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 2
            $apiReady = ($health.status -eq 'ok' -and $health.worker.ready -eq $true)
        } catch { }
    }
    if (-not $webReady) {
        try { $page = Invoke-WebRequest -Uri 'http://127.0.0.1:5173/' -TimeoutSec 2 -UseBasicParsing; $webReady = ($page.StatusCode -eq 200) }
        catch { }
    }
    if ($apiReady -and $webReady) { break }
    Start-Sleep -Milliseconds 500
}
if (-not ($apiReady -and $webReady)) {
    Write-Warning "Startup did not reach both readiness checks. Logs: $logs"
    Write-Warning 'Use Stop-UserDemo.ps1 to request graceful API shutdown and stop the local Vite process.'
    exit 1
}
Write-Host 'API and Worker ready at http://127.0.0.1:8000; frontend HTTP is ready at http://127.0.0.1:5173.'
Write-Host "Runtime '$RuntimeName' uses Domain .runtime\$RuntimeName\domain.sqlite3 and Checkpoint .runtime\$RuntimeName\checkpoint.sqlite3."
Write-Host "Profile $Profile uses $profileService / $profileIntegration for new synchronous investigations."
if ($Mode -eq 'Offline') {
    Write-Host 'Offline mode: real Provider and all legacy Provider paths were forced off for these processes.'
} else {
    Write-Host 'Live mode: ASSISTANT_V1 uses the existing persistent shared Runtime Grant; legacy Provider paths and experiment scope are disabled.'
    Write-Host 'No Provider request is sent at startup. Subsequent user messages may incur charges within the configured shared pool.'
}
Write-Host "Logs: $logs"
