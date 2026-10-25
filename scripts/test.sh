#!/usr/bin/env bash
set -euo pipefail
cd /workspace/haytile-ai
bash scripts/services.sh
if ! docker exec haytile-postgres psql -U haytile -tAc "SELECT 1 FROM pg_database WHERE datname = 'haytile_test'" | rg -q 1; then
  docker exec haytile-postgres createdb -U haytile haytile_test
fi
(cd services/api && DATABASE_URL=postgresql+psycopg://haytile@127.0.0.1:5432/haytile_test /workspace/.venvs/haytile-api/bin/python -m pytest tests -q)
python -m unittest discover -s tests -v
node --test tests/proxy-body.test.mjs
npm --prefix apps/web run typecheck
npm --prefix apps/mobile run typecheck
(cd apps/web && npx playwright test)
