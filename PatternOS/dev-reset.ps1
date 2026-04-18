param([int]$BackendPort = 8000, [int]$FrontendPort = 3000)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

& (Join-Path $root "dev-clean.ps1") -BackendPort $BackendPort -FrontendPort $FrontendPort
Start-Sleep -Seconds 1
& (Join-Path $root "dev-up.ps1") -BackendPort $BackendPort -FrontendPort $FrontendPort

