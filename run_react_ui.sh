#!/bin/bash
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q -r requirements.txt

if [ ! -d "frontend/node_modules" ]; then
  echo "Installing React dependencies..."
  (cd frontend && npm install)
fi

cleanup() {
  kill "$API_PID" "$UI_PID" 2>/dev/null || true
}
trap cleanup EXIT

# Stop stale servers so code changes are picked up.
if command -v lsof >/dev/null 2>&1; then
  lsof -ti :8000 | xargs kill -9 2>/dev/null || true
  lsof -ti :5173 | xargs kill -9 2>/dev/null || true
fi

echo ""
echo "Starting API server on http://127.0.0.1:8000"
uvicorn api:app --host 127.0.0.1 --port 8000 --reload &
API_PID=$!

echo "Starting React UI on http://127.0.0.1:5173"
(cd frontend && npm run dev -- --host 127.0.0.1) &
UI_PID=$!

echo ""
echo "Open your browser at: http://127.0.0.1:5173"
echo "Keep this terminal open while using the app."
echo "Press Ctrl+C to stop both servers."
echo ""

wait
