FROM node:24-bookworm-slim AS web
WORKDIR /app/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN --mount=type=secret,id=build_ca \
    if [ -s /run/secrets/build_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/build_ca; fi; \
    npm ci --no-audit --no-fund
COPY apps/web/ ./
COPY packages/ /app/packages/
RUN --mount=type=secret,id=build_ca \
    if [ -s /run/secrets/build_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/build_ca; fi; \
    npm run build && npm prune --omit=dev --no-audit --no-fund

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY services/api/requirements.lock /app/services/api/requirements.lock
RUN --mount=type=secret,id=build_ca \
    if [ -s /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; fi; \
    pip install --no-cache-dir -r /app/services/api/requirements.lock && useradd --uid 1000 --create-home haytile && mkdir -p /var/data/haytile && chown -R haytile:haytile /var/data/haytile
COPY --from=web /usr/local/bin/node /usr/local/bin/node
COPY --from=web --chown=haytile:haytile /app/apps/web/ /app/apps/web/
COPY --from=web --chown=haytile:haytile /app/packages/ /app/packages/
COPY --chown=haytile:haytile services/api/ /app/services/api/
COPY --chown=haytile:haytile infra/render/serve.py /app/infra/render/serve.py
ENV HAYTILE_ENV=production HAYTILE_DATA_DIR=/var/data/haytile PYTHONPATH=/app/services/api PYTHONUNBUFFERED=1 NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
EXPOSE 10000
# The entrypoint prepares the mounted directory, then drops root before migrations or services.
CMD ["python", "/app/infra/render/serve.py"]
