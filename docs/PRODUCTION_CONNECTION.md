# Connecting durable hosting and mobile builds

**Current operator choice:** Firebase for media, not the Supabase storage proposal
below. See [Firebase setup, limits and migration](FIREBASE.md). Durable PostgreSQL
is still required for accounts/jobs/credits; a media bucket does not replace it.

Status, 2026-10-25: the web app has real AI generation. The operator has Expo and
Google Play accounts, no Apple Developer account, and no durable database/storage
project yet. Paid Render resources remain unauthorized. This document does not
claim the full product is ready for production.

## Earlier alternative: Supabase (not the selected media service)

Create a project in [Supabase](https://supabase.com/dashboard). Use its current
pricing/region terms to choose a suitable plan. Its published free allowance is
500 MB database and 1 GB file storage; it is quota-limited and can pause. It is
not an always-on production SLA. The existing free Render service can also sleep.

In the Supabase project:

1. Copy the PostgreSQL **session pooler** connection details from Connect. The
   session pooler supports IPv4; do not substitute a transaction pooler without
   configuring driver/prepared-statement compatibility.
2. Create a **private** Storage bucket, and create server-side S3 credentials in
   Storage settings. An anon/public project key is not an S3 credential.
3. Copy the S3 endpoint and region shown in the dashboard. Do not invent them.

Set these in the **Render service Environment**, never chat, Git or client code:

| Variable | Source |
|---|---|
| DATABASE_URL | Session-pooler PostgreSQL connection string, with actual password |
| STORAGE_ENDPOINT | Supabase S3 endpoint |
| STORAGE_REGION | Actual project region |
| STORAGE_BUCKET | Private bucket name |
| STORAGE_ACCESS_KEY_ID | S3 access key ID |
| STORAGE_SECRET_ACCESS_KEY | S3 secret |
| STORAGE_SERVER_SIDE_ENCRYPTION | `provider-managed` (Supabase rejects AWS SSE headers) |
| HAYTILE_SIGNING_KEY | Preserve the existing server-side key |
| SMTP_HOST / SMTP_FROM / SMTP_PORT | Real transactional email provider, STARTTLS port |
| SMTP_USER / SMTP_PASSWORD | Email credentials if the provider requires them |

Keep `HAYTILE_TRIAL_AI=1`, current per-day quotas and short-video limits during
migration. PostgreSQL migration must not silently increase operator AI spending.
Leave the service labelled beta until data migration, restore and acceptance pass.

Before any deployment, preserve existing data. Free Render local files and SQLite
can disappear on deploy; source tests are not a migration backup. Users can export
their own account JSON and download their own creations. Do not silently erase
accounts or substitute an empty database while claiming migration success.

After safe migration: deploy on the existing free service, let Alembic apply the
schema, verify that old accounts/assets are present, test private save/download,
range playback, restart persistence and user deletion. Verify anonymous bucket
access is denied using a disposable known object. Test a backup restore in an
isolated database and compare row counts plus object checksums. Only then set
`HAYTILE_FREE_BETA=0`. The API refuses normal production startup with SQLite,
missing object storage, HTTP origins/storage endpoints or an implicit signing key.
`GET /v1/admin/operations` is admin-only and reports queue/configuration signals;
passing its checks is not certification of backups, legal or billing readiness.

## Expo and Google Play

An account alone does not grant this environment access. In cloud environment
settings, securely supply `EXPO_TOKEN` and set the real `HAYTILE_EAS_PROJECT_ID`.
The saved draft also suggests public API base
`EXPO_PUBLIC_API_URL=https://haytile-ai.onrender.com/api`. Review/save and publish
the environment draft; runtime propagation and account access must be checked.
The token binding permits only api.expo.dev and expo.dev. Never paste a token here.

Link the existing Expo project, verify its owner/package identity and access, then
build a staging Android APK. Install it on a real device and test accounts, six
studios, background completion, library, audio/video and downloads. Test a compatible
staging OTA and rollback on that installed runtime. Only after acceptance build
the production AAB and validate Google Play internal testing/signing. Store release
and purchases require actual Play Console configuration and sandbox transactions.
The current payment integration is not implemented; do not enable fictitious plans.

iOS publishing requires the operator's Apple Developer access, signing and store
review. It cannot be completed using Google Play credentials.

## Still required for the full specification

Payment/subscription integrations and verified webhooks; Google/Apple login and
email verification; automated lip-sync/visual review/subtitles; exact sung-lyrics
verification; provider usage/budget reconciliation; offsite backup/restore,
monitoring/alerts, moderation and legal/store policies; real device/store/OTA tests.
Do not replace these requirements with an interface label change.

Official sources checked with HTTPS 200 in this session:

- https://supabase.com/pricing
- https://supabase.com/docs/guides/database/connecting-to-postgres
- https://supabase.com/docs/guides/storage/s3/compatibility
