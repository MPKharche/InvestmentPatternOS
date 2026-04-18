param([int]$BackendPort = 8000, [int]$FrontendPort = 3000)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"

function Stop-ProcsByPattern([string]$pattern) {
  $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -and $_.CommandLine -match $pattern
  } | Select-Object -ExpandProperty ProcessId -Unique
  foreach ($procId in $procs) {
    try { Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue } catch {}
  }
}

function Stop-Port([int]$port) {
  for ($i = 0; $i -lt 15; $i++) {
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

Write-Host "[dev-clean] Stopping PatternOS backend/frontend processes..."
# Kill uvicorn started for PatternOS backend (both reload parent + worker).
Stop-ProcsByPattern ([regex]::Escape($backendDir) + ".*uvicorn.*app\\.main:app")
Stop-ProcsByPattern ("uvicorn\\s+app\\.main:app.*--port\\s+$BackendPort")

# Kill Next dev server for PatternOS frontend.
Stop-ProcsByPattern ([regex]::Escape($frontendDir) + ".*next\\s+dev")

Write-Host "[dev-clean] Freeing ports..."
foreach ($p in @($BackendPort, 8001, $FrontendPort, 3001)) { Stop-Port $p }

Write-Host "[dev-clean] Done."

