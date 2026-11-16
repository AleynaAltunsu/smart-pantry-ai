#!/usr/bin/env bash
# macOS/Linux: backend (8000) + frontend (5500)
set -e
cd "$(dirname "$0")/../backend"
[ -d venv ] || python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
(cd ../frontend && python -m http.server 5500) &
uvicorn app.main:app --reload
