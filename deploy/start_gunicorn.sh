#!/bin/sh
# Start FixPro with gunicorn (Linux)
cd "$(dirname "$0")/.."
if [ -f .venv/bin/activate ]; then
  . .venv/bin/activate
fi
exec gunicorn -w 4 -b 0.0.0.0:8000 app:app
