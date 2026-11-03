# Durable accounts on free Render

## Cause and correction

Render's free instance uses an ephemeral filesystem. The old SQL-only authentication tables in `/tmp/haytile/haytile.db` were recreated when an instance was replaced. Firebase media storage did not make SQL accounts durable.

`HAYTILE_ACCOUNT_PROVIDER=firestore` changes the identity authority to the existing private Firestore database **`default`** in project `haytile-ai`. This retains the existing password-based API; it is not an integration with Firebase Authentication's separate client SDK/service.

Firestore persists:

- Account UUID, normalized email, scrypt password hash, name, locale, admin role, creation date and authentication epoch.
- Unique hashed-email index, created atomically with the account.
- Hashed session-token documents with 7-day expiry, not raw bearer tokens.
- Hashed reset-token documents with 20-minute expiry and an authentication epoch. SMTP must still be configured to send actual reset emails.
- Minimal account/role/profile/delete audit events.

SQL users are an identity projection for existing relational foreign keys. An authenticated request rebuilds a missing local user with the same UUID. SQL credentials/roles are never an authentication fallback when Firestore is enabled. Firestore outage returns `ACCOUNT_STORE_UNAVAILABLE` (503), rather than accepting stale local credentials or pretending to register a durable account.

Account/email creation is one atomic commit with nonexistence preconditions. Profile/role changes use document-version preconditions and bounded conflict retries. Password reset rotates the authentication epoch in the same commit as consuming its reset token: existing sessions, old reset tokens and racing old-password logins cannot mint a new valid session. Deletion removes email/password/profile access, retains a minimal deletion tombstone, and prevents an old session or stale local migration from resurrecting the identity. Expired session/reset documents can be physically cleaned with Firestore TTL policies; expiry is always enforced by the backend, even without TTL.

## Scope limits

**Wallet balances/reservations, credit ledger, memberships, jobs, project documents and library asset metadata still use SQL.** Media bytes remain private in Firebase Cloud Storage. Do not mistake account persistence for the full application data migration. The financial-operation PostgreSQL guard stays enabled; no paid credit balance is awarded on disposable SQLite. The durable admin directory shows unavailable wallet amounts as `—`, rather than fabricating restored credit balances. Its indexed search matches normalized **email prefixes**; it does not scan every account to search names.

Once enabled, future account/session persistence is independent of Render instance replacement. Already-deleted SQL accounts cannot be recovered without a backup. A pre-cutover account that exists only in an inaccessible old Render filesystem cannot be exported by this release before that filesystem disappears. No recovery of such accounts is claimed.

## Security and operating configuration

- Backend-only explicit `FIREBASE_SERVICE_ACCOUNT_JSON`, project ID and actual database ID. No inherited ADC identity; no client-side admin SDK credentials.
- The existing deployed named-database rules were inspected: `projects/haytile-ai/releases/cloud.firestore/default` denies all client document reads/writes. Preserve that rule; do not enable test-mode rules. `infra/firebase/firestore.rules` records the backend-only policy. IAM authorizes the backend.
- No provider AI calls or paid Render resources are needed for this correction. Firestore is on the operator's existing Blaze plan: document operations remain subject to Firebase pricing/quotas; no claim of unlimited free storage.
- `HAYTILE_ACCOUNT_IMPORT_LOCAL=0` normally. A trusted operator can set it to `1` for a **one-time import from an intentionally preserved legacy SQL database**. IDs and password hashes are preserved; an existing remote account is never overwritten. Deleted remote identities are skipped. Disable import after migration. Never point a local development fixture database at production Firebase with import enabled.
- Admin activation still requires the configured owner email, authenticated account and private activation code. The resulting role is now saved in Firestore and survives a restart. A trusted `promote-admin` CLI writes the remote authority too.
- Do not roll back to SQL-only auth or turn off the provider setting as a workaround for a Firestore outage. Maintain access to the same database/service account and restore service instead.

## Verification

78 backend tests pass; web production build, mobile TypeScript and all four local browser workflows pass. Local backend tests cover complete SQL loss between API instances, original-ID/password/session retention, duplicate-email concurrency, profile/admin-role retention, fail-closed outages, reset/revocation/replay, expiration, deleted-account non-resurrection and explicit legacy import. The existing product tests continue to run against the independent SQL implementation.

A separate probe exercised actual Firestore create/read/session/query/profile/role/reset/delete operations. Another probe used **two independent Python API processes and two new SQLite files** against the real Firestore database: the second process authenticated the original session and password with the original UUID. Disposable probe documents/accounts were removed. No billable AI generation was used. Public rollout verification is recorded below once complete.


## Public deployment verification

Commit `9160fc9` is live on the existing free Render service. Initial rollout
`dep-dbkk9bajnfac73964pn0` enabled Firestore authority. A disposable public account was created and its
profile edited. A second real deployment (`dep-dbkka849v7es73ejdlfg`) of the same commit replaced the
service instance. After it reached live, the original bearer session still
returned the same UUID, name and language; signing in with the original password
also returned that UUID, without re-registration. Account deletion then revoked
the session. Anonymous access to its Firestore document returned 403. Disposable
probe documents were cleaned up; no real user was deleted or promoted by the probe.

`HAYTILE_ACCOUNT_IMPORT_LOCAL=0` after cutover. Public runtime reports
`account_store=firestore`, `temporary_accounts=false`, `temporary_database=true`.
Generation stays paused and background processing disabled. The remaining SQL
metadata/credit limitation is intentional and remains visible in Settings.
