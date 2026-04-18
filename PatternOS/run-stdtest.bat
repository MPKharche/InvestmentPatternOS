@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File ".\stdtest\run.ps1"
