@echo off
cd /d "%~dp0backend"
echo Starting PatternOS backend on http://localhost:8000
echo API docs at http://localhost:8000/docs
..\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
