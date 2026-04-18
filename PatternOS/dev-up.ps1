param([int]$BackendPort = 8000, [int]$FrontendPort = 3000, [switch]$Reload)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"
$runlogsDir = Join-Path $root ".runlogs"
New-Item -ItemType Directory -Force -Path $runlogsDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backendLog = Join-Path $runlogsDir "backend_$stamp.log"
$backendErr = Join-Path $runlogsDir "backend_$stamp.err.log"
$frontendLog = Join-Path $runlogsDir "frontend_$stamp.log"
$frontendErr = Join-Path $runlogsDir "frontend_$stamp.err.log"

function Stop-Port([int]$port) {
  # Kill any process currently LISTENing on the port. Loop to catch respawns (e.g. uvicorn reload).
  for ($i = 0; $i -lt 10; $i++) {
    $pids = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
    if (-not $pids) { break }
    foreach ($procId in $pids) {
      if ($procId -and $procId -ne 0) {
        try { Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue } catch {}
      }
    }
    Start-Sleep -Milliseconds 400
  }
}

function Stop-UvicornOnPort([int]$port) {
  # Best-effort: kill uvicorn parents/reloaders even if they temporarily don't own the socket.
  $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -and $_.CommandLine -match "uvicorn" -and $_.CommandLine -match ("--port\\s+" + $port)
  } | Select-Object -ExpandProperty ProcessId -Unique
  foreach ($procId in $procs) {
    try { Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue } catch {}
  }
}

function Wait-HttpOk([string]$url, [int]$timeoutSec = 60) {
  $sw = [Diagnostics.Stopwatch]::StartNew()
  while ($sw.Elapsed.TotalSeconds -lt $timeoutSec) {
    try {
      $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 -Uri $url
      if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) { return }
    } catch {}
    Start-Sleep -Seconds 1
  }
  throw "Timeout waiting for $url"
}

Write-Host "[dev-up] Freeing ports (frontend/backend + stdtest defaults)..."
foreach ($p in @($FrontendPort, 3001, $BackendPort, 8001)) {
  Stop-UvicornOnPort $p
  Stop-Port $p
}
Start-Sleep -Seconds 1

Write-Host "[dev-up] Writing frontend handshake (.env.local)..."
$envLocal = Join-Path $frontendDir ".env.local"
@(
  "# PatternOS Frontend env"
  "# This file is NOT committed (listed in .gitignore)"
  "# Prefer same-origin proxy (/api/v1) via next.config.ts rewrites"
  "NEXT_PUBLIC_API_BASE_URL=/api/v1"
) | Set-Content -Encoding UTF8 -Path $envLocal

Write-Host "[dev-up] Starting backend on http://localhost:$BackendPort ..."
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONFAULTHANDLER = "1"
$backendArgs = @(
  "-m","uvicorn","app.main:app",
  "--host","127.0.0.1",
  "--port","$BackendPort"
)
if ($Reload) { $backendArgs += "--reload" }
$backendProc = Start-Process -FilePath (Join-Path $root ".venv\Scripts\python.exe") `
  -ArgumentList $backendArgs -WorkingDirectory $backendDir `
  -RedirectStandardOutput $backendLog -RedirectStandardError $backendErr -PassThru

Wait-HttpOk "http://localhost:$BackendPort/health" 60
Write-Host "[dev-up] Backend OK"

Write-Host "[dev-up] Starting frontend on http://localhost:$FrontendPort ..."
$env:PORT = "$FrontendPort"
$env:PATTERNOS_BACKEND_ORIGIN = "http://localhost:$BackendPort"
$frontendProc = Start-Process -FilePath "npm.cmd" -ArgumentList @("run","dev","--","--port","$FrontendPort") `
  -WorkingDirectory $frontendDir `
  -RedirectStandardOutput $frontendLog -RedirectStandardError $frontendErr -PassThru

Wait-HttpOk "http://localhost:$FrontendPort" 90
Write-Host "[dev-up] Frontend OK"

Write-Host "[dev-up] Preflight: capabilities + pipeline status..."
try {
  $cap = Invoke-RestMethod -TimeoutSec 10 -Uri "http://localhost:$BackendPort/api/v1/meta/capabilities"
  $capsOut = ($cap | ConvertTo-Json -Depth 6)
  $capsOut | Set-Content -Encoding UTF8 -Path (Join-Path $runlogsDir "capabilities_$stamp.json")
} catch {
  Write-Host "[dev-up] WARN: capabilities check failed: $($_.Exception.Message)"
}

try {
  $status = Invoke-RestMethod -TimeoutSec 10 -Uri "http://localhost:$BackendPort/api/v1/mf/pipeline/status"
  ($status | ConvertTo-Json -Depth 8) | Set-Content -Encoding UTF8 -Path (Join-Path $runlogsDir "mf_status_$stamp.json")
} catch {
  Write-Host "[dev-up] WARN: MF pipeline status failed (DB not ready or backend error): $($_.Exception.Message)"
}

$state = @{
  started_at = (Get-Date).ToString("o")
  backend = @{ pid = $backendProc.Id; port = $BackendPort; log = $backendLog; err = $backendErr }
  frontend = @{ pid = $frontendProc.Id; port = $FrontendPort; log = $frontendLog; err = $frontendErr }
}
($state | ConvertTo-Json -Depth 6) | Set-Content -Encoding UTF8 -Path (Join-Path $runlogsDir "dev_up_$stamp.json")

Write-Host ""
Write-Host "[dev-up] Ready:"
Write-Host "  UI:  http://localhost:$FrontendPort"
Write-Host "  API: http://localhost:$BackendPort/docs"
Write-Host "  Logs: $runlogsDir"

Write-Host "[dev-up] Ensuring database setup and initial seeding..."

$envPath = Join-Path $root ".env"
$dbFlag = Join-Path $backendDir ".db_initialized"

if (-not (Test-Path $envPath)) {
  Write-Host "[dev-up] Creating .env from .env.example..."
  Copy-Item ".env.example" $envPath -Force
  Write-Host "[dev-up] Edit .env (POSTGRES_PASSWORD etc.) then rerun. Postgres must be running."
  exit 1
}

if (-not (Test-Path $dbFlag)) {
  Write-Host "[dev-up] Running migrations + production seeding (universe, patterns)..."
  Push-Location $backendDir
  $python = Join-Path $root ".venv\Scripts\python.exe"
  & $python migrate.py
  if ($LASTEXITCODE -ne 0) {
    Write-Host "[dev-up] Migration failed. Check: Postgres running? .env creds correct?"
    Pop-Location
    exit 1
  }
  New-Item -ItemType File -Path ".db_initialized" -Force | Out-Null
  Pop-Location
  Write-Host "[dev-up] Database ready (Nifty500 + production patterns seeded)."
}

$mfFlag = Join-Path $backendDir "scripts\.mf_historical_seeded"
if (-not (Test-Path $mfFlag)) {
  Write-Host "[dev-up] Bootstrapping MF historical data (fetches from GitHub)..."
  Push-Location $backendDir
  $python = Join-Path $root ".venv\Scripts\python.exe"
  & $python scripts/mf_seed_historical.py
  if ($LASTEXITCODE -eq 0) {
    New-Item -ItemType File -Path "scripts\.mf_historical_seeded" -Force | Out-Null
    Write-Host "[dev-up] MF historical NAV + schemes seeded."
  } else {
    Write-Host "[dev-up] MF seed skipped (non-fatal)."
  }
  Pop-Location
}
