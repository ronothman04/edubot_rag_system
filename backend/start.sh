#!/usr/bin/env bash
# Start the EduBot backend using the project's virtualenv interpreter.
#
# Always launch the server through this script (./start.sh). It calls the
# venv's own uvicorn binary directly, so Crawl4AI is available regardless of
# whether the venv is "activated" in your terminal. Running a bare `uvicorn`
# or `python3 -m uvicorn` can pick up system Python (e.g. 3.14), which does
# NOT have crawl4ai installed and silently falls back to the legacy crawler.
set -euo pipefail

# Resolve the directory this script lives in (the backend/ folder).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PY="${SCRIPT_DIR}/.venv/bin/python"
# NOTE: we invoke "python -m uvicorn" rather than the .venv/bin/uvicorn console
# script. Both work now, but the "-m" form is shebang-independent, so it keeps
# working even if the venv is ever moved/copied to another path again (which is
# what originally broke the console scripts here).

if [[ ! -x "${VENV_PY}" ]]; then
  echo "ERROR: venv not found at ${SCRIPT_DIR}/.venv" >&2
  echo "Create it first:  python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -m playwright install chromium" >&2
  exit 1
fi

# Fail fast with a clear message if Crawl4AI isn't importable in this venv.
if ! "${VENV_PY}" -c "import crawl4ai" >/dev/null 2>&1; then
  echo "ERROR: crawl4ai is not installed in the venv (${VENV_PY})." >&2
  echo "Run:  .venv/bin/pip install -r requirements.txt && .venv/bin/python -m playwright install chromium" >&2
  exit 1
fi

cd "${SCRIPT_DIR}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

# Self-heal: if another server (e.g. a stray system-Python uvicorn) is already
# bound to this port, stop it so THIS venv-based server takes over. Otherwise a
# wrong-interpreter server can keep serving and crawl4ai falls back to legacy.
EXISTING_PIDS="$(lsof -ti:"${PORT}" -sTCP:LISTEN 2>/dev/null || true)"
if [[ -n "${EXISTING_PIDS}" ]]; then
  echo "[start.sh] Port ${PORT} is in use by PID(s): ${EXISTING_PIDS} — stopping them to take over."
  # shellcheck disable=SC2086
  kill -9 ${EXISTING_PIDS} 2>/dev/null || true
  sleep 1
fi

echo "[start.sh] Launching EduBot backend with $(${VENV_PY} --version) on ${HOST}:${PORT}"
exec "${VENV_PY}" -m uvicorn api:app --reload --host "${HOST}" --port "${PORT}"
