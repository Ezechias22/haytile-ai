# Production generation capacity

Production accounts backed by Firestore or PostgreSQL have no Haytile daily or
hourly generation count quota. The old 100/day global, 30/hour per-user,
8-images/day, and 3-pending-free-jobs admission ceilings are removed. Queued jobs
are processed by the existing bounded background worker; accepting more queued
jobs does not launch them all concurrently. Existing legacy counters are ignored.
`HAYTILE_DAILY_JOB_LIMIT` and `HAYTILE_FREE_IMAGES_PER_DAY` no longer affect admission.

Temporary SQLite-only demonstrations retain opt-in trial restrictions. These do
not apply when Firestore owns accounts and wallets, even if trial environment
variables remain from an earlier deployment. Runtime metadata exposes null
production count limits and does not present production accounts as trial users.

Short burst protection (6 submissions per 10 seconds), authentication/upload
protections, private-file bounds, atomic credit reservation, one pending turn per
conversation and paid-request reconciliation remain. Native provider quotas,
model input/output limits, API balances and the supported 8–180-second video
pipeline remain unchanged. Provider errors are distinct from application limits;
otherwise generic capacity errors include their exact code for diagnosis.
