# Bring both Sage backend processes up on Windows.
# Mirrors demo-up.sh — logs tailed into out/demo.log; PIDs tracked in out/demo.pids.

$ErrorActionPreference = 'Stop'
$root = Resolve-Path "$PSScriptRoot/../.."
Set-Location $root

$out  = Join-Path $root 'out'
New-Item -ItemType Directory -Path $out -Force | Out-Null
$log  = Join-Path $out 'demo.log'
$pids = Join-Path $out 'demo.pids'
Set-Content -Path $log -Value '' -Encoding utf8
Set-Content -Path $pids -Value '' -Encoding utf8

function Say($msg)  { Write-Host "› $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "✓ $msg" -ForegroundColor Green }
function Bad($msg)  { Write-Host "✗ $msg" -ForegroundColor Red }

# ── start python orchestrator ──────────────────────────────────────────────
Say 'starting python orchestrator on :7777'
$py = Start-Process -FilePath 'python' `
  -ArgumentList @('-m', 'uvicorn', 'sage.app:app', '--app-dir', 'backend/py/src', '--port', '7777') `
  -RedirectStandardOutput $log -RedirectStandardError $log `
  -PassThru -NoNewWindow
Add-Content -Path $pids -Value $py.Id

# ── start node bridge ──────────────────────────────────────────────────────
$stagehandEnv = if ($env:STAGEHAND_ENV) { $env:STAGEHAND_ENV } else { 'LOCAL' }
Say "starting node bridge on :3001 (STAGEHAND_ENV=$stagehandEnv)"
$env:STAGEHAND_ENV = $stagehandEnv
$node = Start-Process -FilePath 'node' `
  -ArgumentList @('backend/node/src/bridge.js') `
  -RedirectStandardOutput $log -RedirectStandardError $log `
  -PassThru -NoNewWindow
Add-Content -Path $pids -Value $node.Id

# ── wait for health ────────────────────────────────────────────────────────
function Wait-Healthy($url, $name) {
  for ($i = 0; $i -lt 20; $i++) {
    try {
      $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
      if ($r.StatusCode -eq 200) { Ok "$name healthy"; return $true }
    } catch { }
    Start-Sleep -Milliseconds 500
  }
  Bad "$name never came healthy at $url — see $log"
  return $false
}

if (-not (Wait-Healthy 'http://localhost:7777/health' 'python')) { exit 1 }
if (-not (Wait-Healthy 'http://localhost:3001/health' 'bridge')) { exit 1 }

Write-Host ''
Write-Host "both up. logs: Get-Content $log -Wait"
Write-Host "to stop:        powershell -File backend/scripts/demo-down.ps1"
