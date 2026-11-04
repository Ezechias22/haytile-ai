# Firestore manual credits and plans

Current source now includes durable job reservations and settlement; see
[CHAT_AND_DURABLE_CREATIONS.md](CHAT_AND_DURABLE_CREATIONS.md).
The following records the earlier 09ec380 release and its former gates.

With `HAYTILE_ACCOUNT_PROVIDER=firestore`, Firestore is now authoritative for account identity **and** manual wallets/memberships. No SQL balance is copied into or used as a fallback for these wallets. The free Render deployment previously rejected all manual financial mutations, so its new wallet defaults are zero; this is not an automatic migration of a separate funded PostgreSQL wallet.

Admin credit grants and manual Free/Creator/Pro assignments are available on the existing free Render service. Each mutation atomically writes a version-checked wallet, an immutable event with an actor-scoped idempotency fingerprint, a private administrator audit and a precondition on the still-active recipient account. A duplicate request returns the existing result; changing its target, amount or plan payload under the same key is rejected. Concurrent independent gifts use bounded CAS retries, not a read/increment/write that can lose updates. Amounts remain validated server-side. No customer payments or recurring subscriptions are created.

`/me`, `/wallet`, account export and the admin directory read actual Firestore balances and effective plan expiry. The latest 100 events are queried through an indexed user-prefixed ledger key, without requiring a composite index or scanning all accounts. Firestore outages fail closed. Account deletion also deletes its wallet; minimal ID-based transaction and administrator audit records remain for reconciliation. No raw session tokens/passwords are stored in these records.

## Distinct balances and limits

Haytile credits do not recharge or measure the Google API billing account. Granting a user a balance does not make an exhausted provider work. Manual plan names do not enable additional AI capabilities, recurring credits or automatic renewal.

**Per-generation Haytile credit debiting remains gated** (`DURABLE_JOB_BILLING_REQUIRED`), because jobs/reservations/output metadata have not yet migrated from disposable SQL. Configured zero-credit generation can run using the operator's Google billing, and basic images remain zero-credit. A worker in Firestore-wallet mode will not pick a legacy job with a positive SQL credit cost. Do not remove this gate before implementing durable job reservations, settlement/refund and restart reconciliation as one coherent workflow. This release does not pretend that manual gifts implement the entire paid generation pipeline.

The operator confirmed Google was recharged and requested no paid generation tests. The planned rollout enables the existing generation and worker switches, preserving the existing duration, account and global admission limits. Bootstrap may read model metadata; the verification scripts do not call generateContent, Interactions or any paid image/music/video/TTS generation endpoint. Actual generation success after recharge is left to the user's own requests; no fabricated provider result is reported.

## Verification

83 backend tests pass. New tests cover concurrent duplicate/independent grants, plan/credit persistence after complete SQL deletion, expiry, wallet privacy, authorization, outage, export/history and the positive-cost job gate. A regression check also requires the real job-admission path to enqueue a zero-credit job without changing an ordinary user's role; its provider execution is an explicit local fixture.

A disposable real-Firestore probe verified a replay-safe 100-credit gift plus a Creator plan with 25 credits gives exactly 125, with matching history and anonymous document access denied. Probe identities and records were removed. No real user's balance was modified. Web build, mobile TypeScript and all locale checks pass. Public rollout receipt follows after deployment.


## Public rollout receipt

Commit `09ec380` deployed live as `dep-dbkkprk9v7es73ekpkag` on the existing free Render service.
Runtime explicitly reports `api_release=firestore-wallets-v1`, its matching
`source_revision`, `credit_store=firestore`, `generation_paused=false` and
`background_processing_enabled=true`. All six configured studios report available.
These are configuration/metadata checks, not claims that paid provider outputs
were tested after recharge.

A public API probe with two disposable identities verified: an ordinary user
cannot grant credits (403); a 13-credit grant replayed twice adds only 13; a
Creator plan with 7 extra credits yields exactly 20; `/me`, wallet and directory
agree. Probe identities, sessions, wallets, events and audit fixtures were cleaned
up. Real customer balances were not modified. Paid generation test requests: **0**.

The earlier deployment `76eb080` was reported live by Render while the public
endpoint still returned the old paused/locked backend. Do not treat control-plane
status alone as release verification. A cache-cleared rebuild and explicit source
provenance were used for the successful rollout. The web app shell now returns
`private, no-cache, no-store, max-age=0, must-revalidate` rather than a one-year
static shell policy; hashed static assets may still cache normally. When inspecting
Render environment variables, request complete pagination (the default first page
can omit configured keys); never print secret values.
