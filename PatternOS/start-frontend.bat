@echo off
cd /d "%~dp0frontend"
set PORT=3000
echo Starting PatternOS frontend on http://localhost:3000 (or next available)
npm run dev -- --port %PORT%
