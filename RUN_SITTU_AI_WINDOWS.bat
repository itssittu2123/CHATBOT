@echo off
cd /d "%~dp0"
title Sittu AI - Chrome Browser
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.10 or newer, then try again.
  pause
  exit /b 1
)
echo Starting Sittu AI browser server...
start "Sittu AI in browser" http://127.0.0.1:8765
python server.py
pause
