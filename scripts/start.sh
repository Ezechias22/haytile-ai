#!/usr/bin/env bash
set -euo pipefail
cd /workspace/haytile-ai
bash scripts/services.sh
mkdir -p .local/logs
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
# The API terminates the public WebSocket; Next stays on the internal web port.
export HAYTILE_API_URL="http://127.0.0.1:3000"
export HAYTILE_WEB_UPSTREAM="http://127.0.0.1:3001"
export HAYTILE_PUBLIC_ORIGIN="${HAYTILE_PUBLIC_ORIGIN:-http://localhost:3000}"
# Source-of-truth config is the injected process environment. Never print it.
start_service() {
  local name="$1"
  shift
  local pidfile="/workspace/haytile-ai/.local/${name}.pid"
  if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    printf '%s\n' "$name is already running"
  else
    nohup "$@" >"/workspace/haytile-ai/.local/logs/${name}.log" 2>&1 < /dev/null &
    printf '%s\n' "$!" > "$pidfile"
  fi
}
cd services/api
/workspace/.venvs/haytile-api/bin/alembic upgrade head
start_service api /workspace/.venvs/haytile-api/bin/uvicorn haytile.main:app --host 0.0.0.0 --port 3000 --ws-max-size 8192 --ws-max-queue 8
start_service worker /workspace/.venvs/haytile-api/bin/python -m haytile.worker
cd ../../apps/web
start_service web npm run start -- --hostname 127.0.0.1 --port 3001
for attempt in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:3000/api/v1/health >/dev/null 2>&1; then
    printf '%s\n' 'Web, API and PostgreSQL readiness check passed. Validate sign-in and a saved draft after configuration changes.'
    exit 0
  fi
  sleep 1
done
printf '%s\n' 'Readiness check failed. Inspect .local/logs without exposing credentials.' >&2
exit 1
