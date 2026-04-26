# Stop the bridge + python orchestrator started by demo-up.ps1.

$root = Resolve-Path "$PSScriptRoot/../.."
$pids = Join-Path $root 'out\demo.pids'

if (-not (Test-Path $pids)) {
  Write-Host "no $pids — nothing to stop"
  exit 0
}

Get-Content $pids | ForEach-Object {
  if ($_ -and ($_ -match '^\d+$')) {
    try {
      Stop-Process -Id [int]$_ -Force -ErrorAction Stop
      Write-Host "stopped pid $_"
    } catch {
      Write-Host "pid $_ not running"
    }
  }
}

Remove-Item $pids -Force
Write-Host 'demo-down complete'
