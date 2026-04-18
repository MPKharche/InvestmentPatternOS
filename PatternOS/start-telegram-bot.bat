@echo off
cd /d "%~dp0backend"
echo Starting PatternOS Telegram bot (polling)...
echo Ensure TELEGRAM_BOT_TOKEN is set in ..\.env and TELEGRAM_MODE=polling
..\.venv\Scripts\python -m app.telegram.worker
