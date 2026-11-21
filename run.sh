#!/usr/bin/env bash
# One-command start: creates a virtualenv, installs deps, runs the server.
set -e
cd "$(dirname "$0")/backend"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
echo "Voice Khata running at http://localhost:8000"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
