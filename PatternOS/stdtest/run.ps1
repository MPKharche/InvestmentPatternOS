$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"
$compose = Join-Path $PSScriptRoot "docker-compose.stdtest.yml"
$py = Join-Path $root ".venv\\Scripts\\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

$runId = Get-Date -Format "yyyyMMdd_HHmmss"
$artifactDir = Join-Path $PSScriptRoot ".artifacts\$runId"
New-Item -ItemType Directory -Force -Path $artifactDir | Out-Null

function Stop-Port([int]$port) {
  $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
  if (-not $conns) { return }
  $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
  foreach ($procId in $pids) {
    if ($procId -and $procId -ne 0) {
      try { Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue } catch {}
    }
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

function Docker-Available() {
  try {
    docker info *> $null
    if ($LASTEXITCODE -ne 0) { return $false }
    return $true
  } catch {
    return $false
  }
}

function Read-DotEnv([string]$path) {
  if (-not (Test-Path $path)) { return @{} }
  $map = @{}
  Get-Content $path | ForEach-Object {
    $line = $_.Trim()
    if (-not $line) { return }
    if ($line.StartsWith("#")) { return }
    $idx = $line.IndexOf("=")
    if ($idx -lt 1) { return }
    $k = $line.Substring(0, $idx).Trim()
    $v = $line.Substring($idx + 1).Trim()
    $map[$k] = $v
  }
  return $map
}

$useDocker = Docker-Available

if ($useDocker) {
  Write-Host "[stdtest] Starting postgres (docker)..."
  docker compose -f $compose up -d | Out-Null
} else {
  Write-Host "[stdtest] Docker not available; using local Postgres from .env (no containers)."
}

try {
  Write-Host "[stdtest] Freeing stdtest ports (8001/3001)..."
  # Stop any running dev servers in this repo; Next.js locks the project dir even across ports.
  foreach ($p in @(8000, 8001, 3000, 3001)) { Stop-Port $p }
  Start-Sleep -Seconds 1

  if ($useDocker) {
    Write-Host "[stdtest] Waiting for postgres health (docker)..."
    Start-Sleep -Seconds 3

    $env:POSTGRES_HOST = "localhost"
    $env:POSTGRES_PORT = "55432"
    $env:POSTGRES_DB = "patternos_stdtest"
    $env:POSTGRES_USER = "patternos"
    $env:POSTGRES_PASSWORD = "patternos"
  } else {
    $envMap = Read-DotEnv (Join-Path $root ".env")
    $env:POSTGRES_HOST = "localhost"
    if ($envMap.ContainsKey("POSTGRES_HOST")) { $env:POSTGRES_HOST = $envMap["POSTGRES_HOST"] }

    $env:POSTGRES_PORT = "5432"
    if ($envMap.ContainsKey("POSTGRES_PORT")) { $env:POSTGRES_PORT = $envMap["POSTGRES_PORT"] }

    $env:POSTGRES_USER = "postgres"
    if ($envMap.ContainsKey("POSTGRES_USER")) { $env:POSTGRES_USER = $envMap["POSTGRES_USER"] }

    $env:POSTGRES_PASSWORD = "postgres"
    if ($envMap.ContainsKey("POSTGRES_PASSWORD")) { $env:POSTGRES_PASSWORD = $envMap["POSTGRES_PASSWORD"] }
    $env:POSTGRES_DB = "patternos_stdtest_local"

    Write-Host "[stdtest] Ensuring local stdtest DB exists ($($env:POSTGRES_DB))..."
    Push-Location $backendDir
    & $py -c @"
import os, psycopg2
host=os.environ.get('POSTGRES_HOST','localhost')
port=int(os.environ.get('POSTGRES_PORT','5432'))
user=os.environ.get('POSTGRES_USER','postgres')
pw=os.environ.get('POSTGRES_PASSWORD','')
db=os.environ.get('POSTGRES_DB','patternos_stdtest_local')
conn=psycopg2.connect(host=host,port=port,user=user,password=pw,dbname='postgres')
conn.autocommit=True
cur=conn.cursor()
cur.execute('SELECT 1 FROM pg_database WHERE datname=%s',(db,))
if cur.fetchone() is None:
    cur.execute('CREATE DATABASE ' + '\"%s\"' % db.replace('\"','\"\"'))
cur.close(); conn.close()
"@ | Out-Null
    Pop-Location
  }

  $env:APP_ENV = "test"
  $env:LLM_DISABLED = "true"
  $env:TELEGRAM_ALERTS_ENABLED = "false"
  $env:TELEGRAM_MODE = "disabled"

  Write-Host "[stdtest] Migrating DB..."
  Push-Location $backendDir
  # Ensure scripts under backend/scripts can import `app.*`.
  $env:PYTHONPATH = $backendDir
  & $py migrate.py 2>&1 | Tee-Object -FilePath (Join-Path $artifactDir "migrate.log") | Out-Null
  & $py scripts/stdtest_seed.py 2>&1 | Tee-Object -FilePath (Join-Path $artifactDir "seed.log") | Out-Null
  Pop-Location

  Write-Host "[stdtest] Starting backend (8001)..."
  $backendLog = Join-Path $artifactDir "backend.log"
  $backendErr = Join-Path $artifactDir "backend.err.log"
  $backendProc = Start-Process -FilePath $py -ArgumentList @(
    "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8001"
  ) -WorkingDirectory $backendDir -RedirectStandardOutput $backendLog -RedirectStandardError $backendErr -PassThru

  Wait-HttpOk "http://localhost:8001/health" 60

  Write-Host "[stdtest] Starting frontend (3001)..."
  $frontendLog = Join-Path $artifactDir "frontend.log"
  $frontendErr = Join-Path $artifactDir "frontend.err.log"
  $env:PORT = "3001"
  $env:NEXT_PUBLIC_API_BASE_URL = "http://localhost:8001/api/v1"
  $frontendProc = Start-Process -FilePath "npm.cmd" -ArgumentList @("run","dev","--","--port","3001") -WorkingDirectory $frontendDir -RedirectStandardOutput $frontendLog -RedirectStandardError $frontendErr -PassThru

  Wait-HttpOk "http://localhost:3001" 90

  Write-Host "[stdtest] Running backend unit tests..."
  Push-Location $backendDir
  & $py -m pytest -q 2>&1 | Tee-Object -FilePath (Join-Path $artifactDir "pytest.log") | Out-Null
  Pop-Location

  Write-Host "[stdtest] Running Playwright E2E..."
  Push-Location $frontendDir
  $env:PLAYWRIGHT_BASE_URL = "http://localhost:3001"
  $env:E2E_API_BASE = "http://localhost:8001/api/v1"
  npm run test:e2e 2>&1 | Tee-Object -FilePath (Join-Path $artifactDir "playwright.log") | Out-Null
  Pop-Location

  Write-Host "[stdtest] OK (artifacts: $artifactDir)"
}
finally {
  if ($frontendProc -and -not $frontendProc.HasExited) { Stop-Process -Id $frontendProc.Id -Force }
  if ($backendProc -and -not $backendProc.HasExited) { Stop-Process -Id $backendProc.Id -Force }
  if ($useDocker) {
    docker compose -f $compose down -v | Out-Null
  }
}
