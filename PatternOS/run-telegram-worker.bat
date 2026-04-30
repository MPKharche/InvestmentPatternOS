@echo off
REM PatternOS Telegram polling bot (/chart, /signal, /mf, callbacks).
REM Requires TELEGRAM_BOT_TOKEN and TELEGRAM_MODE=polling in PatternOS\.env
cd /d "%~dp0backend"
python -m app.telegram.worker
pause
