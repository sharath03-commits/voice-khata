#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/backend"
python3 -m pip install -q -r requirements.txt
echo "Voice Khata running at http://localhost:8000"
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
