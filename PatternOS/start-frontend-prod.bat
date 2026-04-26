@echo off
REM Production UI: build once, then next start — much lighter than dev mode (npm run dev).
cd /d "%~dp0frontend"
if "%PORT%"=="" set PORT=3000
echo [frontend-prod] PORT=%PORT%
echo [frontend-prod] Set NEXT_PUBLIC_API_BASE_URL in .env if API is not on the same host.
call npm run build
if errorlevel 1 exit /b 1
call npm run start
