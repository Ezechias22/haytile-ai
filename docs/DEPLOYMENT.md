# Run, test and deploy HAYTILE AI

## Cloud development

Requirements: Node 24, Python 3.12, Docker, FFmpeg/ffprobe. Use the existing checkout;
do not create a worktree. No real credentials are committed.

```sh
cd /workspace/haytile-ai
bash scripts/setup.sh
bash scripts/start.sh
bash scripts/test.sh
```

`setup.sh` uses locked npm/Python dependencies and applies Alembic migrations.
`start.sh` restores the development PostgreSQL/Redis containers, API, worker and
web server. PIDs/logs live in ignored `.local/`; processes must restart after a
cloud snapshot is restored. Never print environment dumps or full provider errors.
The development database uses trust authentication bound to loopback. Do not
expose it publicly. Tests use a separate `haytile_test` database.

The API normally listens on 8000 and web on 3000. Make local requests to
`/api/v1/health` for readiness; the onboarding UI does not support localhost preview links.
For real functional validation: register, save a text draft, preview/download it,
rename, delete and sign out. Browser tests exercise this against the actual backend.

## Configuration and first administrator

Review `.env.example`. Scripts use injected variables; they intentionally do not
source arbitrary `.env` shell code. For local tools, use your process manager's
secret/env loader. Do not paste credentials into a command or commit `.env`.

Register your own account through the app, then promote that account locally:

```sh
cd /workspace/haytile-ai/services/api
/workspace/.venvs/haytile-api/bin/python -m haytile.cli promote-admin you@example.com
```

No hardcoded administrator or initial credits are provided. The admin dashboard
can discover Google account models, configure a studio, set credits and grant
credits with an audited idempotent operation. A model must appear in the account
catalog before it can be enabled. Catalog presence does not validate its modality.
Verify actual capabilities, pricing and terms before accepting operator billing.
Image model configuration rejects nonzero user-credit pricing.

Enter `HAYTILE_GEMINI_API_KEY` only in secure backend settings. Restart API/worker
after runtime variable changes. The app keeps unsupported/unconfigured generation
disabled, while account, drafts and private media remain usable.

Password reset uses SMTP with STARTTLS. Configure SMTP_HOST, SMTP_PORT, SMTP_FROM
and optional SMTP_USER/SMTP_PASSWORD, plus HAYTILE_PUBLIC_ORIGIN. Without SMTP the
reset request explicitly fails; it never pretends an email was sent. Google/Apple
login are not implemented. Production needs email verification and stronger abuse controls.

## Production containers

Dockerfiles and `infra/compose.production.yml` are a deployment starting point,
not a claim of a tested public installation. Configure DNS/TLS ingress, private
PostgreSQL credentials, signed-link key, private S3 bucket, backups and monitoring.
Supply `.env.production` through your secret manager. Do not publish port 8000 or
PostgreSQL to the Internet. Mobile needs a separate HTTPS API ingress with the same
authentication and rate limiting. Browser traffic uses the Next.js server proxy.

```sh
docker compose --env-file .env.production -f infra/compose.production.yml build
docker compose --env-file .env.production -f infra/compose.production.yml run --rm api alembic upgrade head
docker compose --env-file .env.production -f infra/compose.production.yml up -d
```

DATABASE_URL must use `postgresql+psycopg://` and hostname `postgres` in Compose.
Set HAYTILE_PUBLIC_ORIGIN to the actual HTTPS web origin; CSRF validation uses it.
S3 bucket access must be private; stored media never uses public object URLs.
Secure session cookies activate with HAYTILE_ENV=production.
Do not share the development signing key or trust-mode database with production.

CI validates PostgreSQL/API tests, web build and mobile exports on PR/push. It does
not deploy to an invented hosting account. Connect your chosen host's deployment
integration after staging, HTTPS and rollback checks. GitHub workflows have not
executed remotely because this checkout has not been pushed.

## Mobile, EAS Build and OTA

```sh
cd /workspace/haytile-ai/apps/mobile
npm ci
EXPO_NO_TELEMETRY=1 npx expo start
```

Set EXPO_PUBLIC_API_URL to a reachable HTTPS backend; it is a public URL, never an
API key. Loopback addresses on a phone refer to the phone, not the cloud machine.
Set HAYTILE_EAS_PROJECT_ID to your actual EAS project UUID. No fake ID is generated.
Native builds need Expo access, Android signing and Apple developer credentials.

EAS config includes development/staging/production channels and fingerprint runtime
policy. GitHub manual workflows validate source before EAS build/update. Configure
EXPO_TOKEN as a GitHub environment secret, and EAS project/API URL as variables.
Protect the production GitHub environment with required reviewers. Build a staging
binary, install it, verify its runtime fingerprint and then test a compatible OTA.
Native dependencies, permissions or SDK changes require new binaries.

Rollout, rollback and crash monitoring are not yet integrated or exercised; use
Expo's current dashboard controls and validate recovery on staging before enabling
production. The provided update workflow publishes to an explicitly selected channel;
it does not claim percentage rollout or automatic rollback. No AAB/IPA or store
submission has been produced in this session.

## Backups and operational checks

Take encrypted PostgreSQL backups plus media snapshots with retention controls.
Store backups outside the live data volume and regularly restore to a separate DB.
Set concrete RPO/RTO after a measured restore drill. Monitor queue age, failed jobs,
provider spend, API errors and storage capacity. Metrics/alerts, external error
reporting, moderation queues and legal policy review remain release prerequisites.

Interrupted external provider calls do not auto-resubmit: the worker marks them
for manual reconciliation to avoid silent duplicate costs. Operator investigation
must compare provider history before creating a new request. There is no automated
provider-usage reconciliation or payment processing in this release.
