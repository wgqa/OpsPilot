$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..\..\..')).Path
$runtime = Join-Path $root '.runtime\user-demo'
$stopRequest = Join-Path $runtime 'shutdown.request'
$port = 5174
$log = Join-Path $PSScriptRoot 'launcher-lifecycle-01.log'
$stdout = Join-Path $PSScriptRoot 'launcher-5174.stdout.log'
$stderr = Join-Path $PSScriptRoot 'launcher-5174.stderr.log'
$emptyStdin = Join-Path $runtime 'logs\empty.stdin'
$launcher = Join-Path $root 'frontend\user-demo-server.mjs'

if (Test-Path -LiteralPath $stopRequest) { throw 'An existing shutdown request is present.' }
if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
    throw "Port $port is already in use."
}
New-Item -ItemType Directory -Path (Split-Path -Parent $emptyStdin) -Force | Out-Null
if (-not (Test-Path -LiteralPath $emptyStdin)) { [IO.File]::WriteAllBytes($emptyStdin, [byte[]]::new(0)) }

$lines = [System.Collections.Generic.List[string]]::new()
$node = (Get-Command node -ErrorAction Stop).Source
$oldPort = [Environment]::GetEnvironmentVariable('OPSPILOT_USER_DEMO_WEB_PORT', 'Process')
try {
    [Environment]::SetEnvironmentVariable('OPSPILOT_USER_DEMO_WEB_PORT', [string]$port, 'Process')
    $process = Start-Process -FilePath $node -ArgumentList ('"' + $launcher + '"') `
        -WorkingDirectory (Join-Path $root 'frontend') -WindowStyle Hidden -PassThru `
        -RedirectStandardInput $emptyStdin -RedirectStandardOutput $stdout -RedirectStandardError $stderr
} finally {
    [Environment]::SetEnvironmentVariable('OPSPILOT_USER_DEMO_WEB_PORT', $oldPort, 'Process')
}

$lines.Add("PID=$($process.Id)")
$ready = $false
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    $process.Refresh()
    if ($process.HasExited) { break }
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$port/" -TimeoutSec 2
        if ($response.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
    Start-Sleep -Milliseconds 250
}
if (-not $ready) {
    $lines.Add("HTTP_$port=FAIL; PROCESS_EXITED=$($process.HasExited)")
    [IO.File]::WriteAllLines($log, $lines, [Text.UTF8Encoding]::new($false))
    throw 'Vite launcher did not become ready while using an empty stdin.'
}
$lines.Add("HTTP_$port=200")
$process.Refresh()
if ($process.HasExited) { throw 'Vite exited after stdin reached EOF.' }

Set-Content -LiteralPath $stopRequest -Value 'graceful-shutdown' -Encoding ASCII
if (-not $process.WaitForExit(15000)) {
    $lines.Add('EXIT_AFTER_SHUTDOWN_REQUEST=FAIL; PROCESS_LEFT_RUNNING=true')
    [IO.File]::WriteAllLines($log, $lines, [Text.UTF8Encoding]::new($false))
    throw 'Vite did not exit within 15 seconds; no force termination was attempted.'
}
Remove-Item -LiteralPath $stopRequest -Force
$stillListening = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
$webLog = if (Test-Path -LiteralPath $stdout) { Get-Content -LiteralPath $stdout -Raw } else { '' }
$lines.Add('EXIT_AFTER_SHUTDOWN_REQUEST=true')
$lines.Add("GRACEFUL_CLOSE_LOG=$($webLog -match 'closed gracefully')")
$lines.Add("PORT_${port}_RELEASED=$(-not [bool]$stillListening)")
[IO.File]::WriteAllLines($log, $lines, [Text.UTF8Encoding]::new($false))
Get-Content -LiteralPath $log
Get-Content -LiteralPath $stdout -Tail 10 -ErrorAction SilentlyContinue
if ($stillListening) { throw "Port $port remained in use after process exit." }
if ($webLog -notmatch 'closed gracefully') { throw 'Graceful close log was not observed.' }
