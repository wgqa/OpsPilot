$ErrorActionPreference='Stop'
$items = @('requirements.lock.txt','frontend/package-lock.json')
$tracked = git ls-files 'docs/evidence/vnext/m3-01'
$files = @($items) + @($tracked)
$lines = foreach ($f in $files | Sort-Object -Unique) {
  if (Test-Path -LiteralPath $f -PathType Leaf) {
    $h = Get-FileHash -Algorithm SHA256 -LiteralPath $f
    "$($h.Hash.ToLower())  $f"
  }
}
$lines | Set-Content -LiteralPath 'docs/evidence/vnext/m3-01-hf-01/FROZEN_SHA256SUMS.txt' -Encoding ascii
