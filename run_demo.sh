#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

echo "[Financial Path Twin] Demo readiness check"
if ! python scripts/check_demo_readiness.py; then
  echo
  echo "Demo is not ready."
  echo "Run this first:"
  echo "  python scripts/run_pipeline.py --force --export-charts"
  exit 1
fi

echo
echo "Starting Streamlit demo..."
DEMO_PORT="${DEMO_PORT:-8501}"
echo "Browser URL: http://localhost:${DEMO_PORT}"
python scripts/start_streamlit.py --port "${DEMO_PORT}" --keep-running
