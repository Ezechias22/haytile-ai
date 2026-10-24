#!/usr/bin/env bash
set -euo pipefail
cd /workspace/haytile-ai
bash scripts/services.sh
python -m venv /workspace/.venvs/haytile-api
/workspace/.venvs/haytile-api/bin/pip install --cache-dir /workspace/.cache/pip --disable-pip-version-check -r services/api/requirements.lock
(cd services/api && /workspace/.venvs/haytile-api/bin/alembic upgrade head)
npm --prefix apps/web ci --cache /workspace/.npm-cache
npm --prefix apps/mobile ci --cache /workspace/.npm-cache
npm --prefix apps/web run build
EXPO_NO_TELEMETRY=1 EXPO_OFFLINE=1 npm --prefix apps/mobile run typecheck
