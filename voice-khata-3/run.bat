@echo off
cd /d %~dp0backend
python -m pip install -q -r requirements.txt
echo.
echo Voice Khata running at http://localhost:8000
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
