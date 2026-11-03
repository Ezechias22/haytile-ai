# Private administration

Firestore retains accounts, sessions, roles, manual credit balances and manual
plan assignments. See [WALLETS.md](WALLETS.md) for the still-gated per-generation
credit billing. Older deployment receipts below describe their specific releases.

Web: sign in, open Settings, activate administrator access using the server's private activation code, then open Administration in the navigation.

## Owner setup

Set backend-only `HAYTILE_ADMIN_EMAIL` to the owner's account email. Set `HAYTILE_ADMIN_ACTIVATION_CODE` to a unique random secret of at least 32 characters in the Render environment dashboard, then redeploy. Never put this code in source control, public/mobile variables, a URL, screenshots or logs. The owner signs in with their own password and enters the code under Settings. An email alone cannot grant administrator access. Activation is rate limited by account and IP; role changes are audited. With the Firestore identity provider enabled, the admin role survives Render restarts. Clear the activation code after successful activation. The SQL-only identity provider still requires an actually persistent database.

A trusted server operator can alternatively run `python -m haytile.cli promote-admin OWNER_EMAIL` with the same identity-provider configuration. There is no public API for changing arbitrary roles.

## Implemented controls

- Authenticated admin-only user directory, 25-user pages. Firestore uses indexed email-prefix search and returns its durable wallet balances; SQL mode supports escaped substring search and stored balances/plan expiry.
- Positive credit grants, with backend validation, user-row locking, ledger, actor audit and idempotency. A repeated request cannot grant twice. A reused key with a different target or amount is rejected.
- Manual Free / Creator / Pro assignment for 1–366 days, optional 0–100,000 one-time credits, required reason and audit. Assignment and credits commit in one database transaction. Changing a plan does not remove existing credits or cancel active jobs. Free-plan assignments cannot include bonus credits.
- Expired memberships report Free. Memberships are **manual labels plus optional explicit credit grants**; they do not implement different AI capabilities, recurring credits, recurring billing or store subscriptions. No prices or purchased status are fabricated. Google provider billing is independent of Haytile credits.
- Existing model controls, model discovery, counts and audit history. These do not override the global server generation/worker pause.
- Nine interface languages. The admin web interface works on small screens; there is no new native app release.

## Current deployment limitation

Firestore retains credentials, sessions, profiles, roles, manual balances and manual plans. Jobs, project documents and asset metadata still use disposable SQL. Manual credit and plan buttons are now enabled with Firestore. Per-generation credit charging is still blocked until durable job reservations/settlement are implemented. All currently configured models have zero Haytile credit quotes; the operator's Google API billing remains independent. No paid Render service or store subscription was created.

Migration `0004` adds memberships without replacing user rows. Test on a dedicated database; the backend test suite empties its test database deliberately.

## Validation

83 backend tests pass, including admin authorization, directory privacy, concurrent assignment replay, credit-grant replay/conflicts, expiration, activation-code/email validation and temporary-database blocking. Web build and mobile TypeScript checks pass. These local tests use a dedicated PostgreSQL database and explicit activation/provider fixtures; no billable Google generation is required. See release progress for browser/deployment validation.

## Initial admin deployment receipt (historical)

Commit `8094e3a` deployed live to the existing **free** Render service
(`dep-dbkk0hrbc2fs739ilgcg`). Public web returns 200; unauthenticated directory,
plan assignment and activation endpoints all return 401. Global generation is
still paused and the worker is disabled. Owner email is configured server-side;
the private activation code is intentionally **not** created or exposed by this
release. The owner must set it in Render before activation. No live account was
promoted, no live credits/plan were awarded, and no paid AI request was made.
SQLite migration 0003 → 0004 was also checked with an existing fixture user and
balance retained. Full browser verification used a local persistent PostgreSQL
fixture, not the public Render service.
