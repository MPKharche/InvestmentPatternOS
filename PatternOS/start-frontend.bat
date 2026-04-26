@echo off
REM Development only (hot reload, higher CPU). For servers use start-frontend-prod.bat
cd /d "%~dp0frontend"
set PORT=3000
echo Starting PatternOS frontend (DEV) on http://localhost:%PORT%
npm run dev -- --port %PORT%
