$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$envFile = Join-Path $root '.env'
$runtimeDir = Join-Path $root '.runtime\user-demo'

if (-not (Test-Path -LiteralPath $envFile)) {
    throw 'Local .env is missing. Run Initialize-UserDemo.ps1 once first.'
}
if (-not (Test-Path -LiteralPath (Join-Path $runtimeDir 'domain.sqlite3'))) {
    throw 'Isolated User Demo database is missing. Run Initialize-UserDemo.ps1 once first.'
}

$ignore = & git -C $root check-ignore .env
if ($LASTEXITCODE -ne 0 -or -not $ignore) {
    throw 'The repository does not confirm that .env is ignored; refusing to write credentials.'
}

function Read-SecretText([string]$Prompt) {
    $secure = Read-Host -Prompt $Prompt -AsSecureString
    if ($secure.Length -lt 1) { throw 'A required secret was empty.' }
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        $secure.Dispose()
    }
}

$apiKey = Read-SecretText 'DeepSeek API key (hidden input; saved only to ignored .env)'
$supportPassword = Read-SecretText 'Choose a private SUPPORT password (minimum 12 characters)'
if ($apiKey.Length -lt 12 -or $apiKey -match '[\r\n]') { throw 'Provider key input is invalid.' }
if ($supportPassword.Length -lt 12 -or $supportPassword -match '[\r\n]') {
    throw 'SUPPORT password must be at least 12 characters and one line.'
}

$random = [byte[]]::new(32)
$randomGenerator = [Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $randomGenerator.GetBytes($random)
} finally {
    $randomGenerator.Dispose()
}
$unusedApproverPassword = [Convert]::ToBase64String($random)
[Array]::Clear($random, 0, $random.Length)

$values = [ordered]@{
    OPSPILOT_DB_PATH = '.runtime/user-demo/domain.sqlite3'
    OPSPILOT_CHECKPOINT_DB_PATH = '.runtime/user-demo/checkpoint.sqlite3'
    OPSPILOT_WEB_ORIGIN = 'http://127.0.0.1:8000'
    OPSPILOT_WEB_SUPPORT_PASSWORD = $supportPassword
    OPSPILOT_WEB_APPROVER_PASSWORD = $unusedApproverPassword
    OPSPILOT_WEB_SUPPORT_B_PASSWORD = ''
    OPSPILOT_WEB_APPROVER_B_PASSWORD = ''
    OPSPILOT_DEMO_SERVICE_ID = 'orders-demo'
    OPSPILOT_DEMO_INTEGRATION_ID = 'integration-a'
    OPSPILOT_DEMO_TICKET_ID = 'INC-A-001'
    OPSPILOT_ASSISTANT_RUNTIME_ENABLED = '0'
    OPSPILOT_ASSISTANT_PROVIDER_ENABLED = '0'
    OPSPILOT_LEGACY_PROVIDER_ENABLED = '0'
    OPSPILOT_ASSISTANT_EXPERIMENT_ID = ''
    OPSPILOT_MODEL_API_KEY = $apiKey
    OPSPILOT_MODEL_NAME = 'deepseek-flash'
    OPSPILOT_MODEL_BASE_URL = 'https://api.deepseek.com'
    OPSPILOT_MODEL_CONFIG_VERSION = 'C01-B2-LIVE-01-2026-11-11'
    OPSPILOT_MODEL_PRICE_VERSION = 'DEEPSEEK_FLASH_PEAK_2026-11-11'
    OPSPILOT_MODEL_INPUT_RATE_MICRO_PER_MILLION = '300000'
    OPSPILOT_MODEL_OUTPUT_RATE_MICRO_PER_MILLION = '1320000'
    OPSPILOT_ASSISTANT_SERVICE_IDENTITY = 'opspilot-c01-b2-live-01-local'
}

$lines = [Collections.Generic.List[string]]::new()
$lines.Add('# Local C01-B2 live assessment credentials and Runtime configuration.')
$lines.Add('# This file is ignored by Git. Do not copy it into reports or share it.')
foreach ($entry in $values.GetEnumerator()) {
    $lines.Add("$($entry.Key)=$($entry.Value)")
}
[IO.File]::WriteAllLines($envFile, $lines, [Text.UTF8Encoding]::new($false))

$currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$acl = Get-Acl -LiteralPath $envFile
$acl.SetAccessRuleProtection($true, $false)
$acl.Access | ForEach-Object { [void]$acl.RemoveAccessRule($_) }
$acl.SetAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
    $currentIdentity, 'FullControl', 'Allow'))
$acl.SetAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
    'NT AUTHORITY\SYSTEM', 'FullControl', 'Allow'))
Set-Acl -LiteralPath $envFile -AclObject $acl

$apiKey = $null
$supportPassword = $null
$unusedApproverPassword = $null
Write-Host 'Saved local credentials and the pinned DeepSeek configuration. Values were not printed.'
Write-Host 'No Provider request was sent. The isolated $1 Runtime Grant is checked by the next Live preflight.'
