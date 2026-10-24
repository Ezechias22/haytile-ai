#!/usr/bin/env bash
set -euo pipefail
# Development services only; authenticate PostgreSQL before any real deployment.
if docker container inspect haytile-postgres >/dev/null 2>&1; then
  docker start haytile-postgres >/dev/null
else
  docker run -d --name haytile-postgres -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=haytile -e POSTGRES_USER=haytile -p 127.0.0.1:5432:5432 -v haytile-pgdata:/var/lib/postgresql/data postgres:17-alpine >/dev/null
fi
if docker container inspect haytile-redis >/dev/null 2>&1; then
  docker start haytile-redis >/dev/null
else
  docker run -d --name haytile-redis -p 127.0.0.1:6379:6379 -v haytile-redisdata:/data redis:7-alpine redis-server --appendonly yes >/dev/null
fi
for attempt in $(seq 1 30); do
  if docker exec haytile-postgres pg_isready -U haytile -d haytile >/dev/null; then exit 0; fi
  sleep 1
done
printf '%s\n' 'PostgreSQL did not become ready.' >&2
exit 1
