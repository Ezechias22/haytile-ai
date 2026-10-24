# Kontra done, sekirite ak API

Sa a se konsepsyon sib la. Schema aktyèl ak migrasyon aplike yo nan services/api/migrations; PROGRESS.md se sous estati aplikasyon an. Tab/kontra ki nan dokiman sa a pa tout aplike.

## Antite PostgreSQL

Tout ID piblik UUID; timestamps UTC; foreign keys ak indexes sou owner/status/date.

| Tab | Done ak kontrent prensipal |
|---|---|
| users | identity_subject UNIQUE, locale, role, deletion_requested_at |
| projects | owner_id, studio, title, revision, approval_status |
| characters | project_id, stable_id UNIQUE pa pwojè, aparans, rad, lang, voice_ref |
| character_revisions | character_id, revision, referans asset ak continuity notes |
| scenes | project_id, order UNIQUE pa revision, script egzak, duration_target, paramèt |
| jobs | owner_id, project_id, idempotency_key UNIQUE pa owner, status, attempt, provider_job_id |
| job_events | job_id, previous_status, status, dat, safe_error_code |
| assets | owner_id, job_id, private_object_key UNIQUE, mime, bytes, sha256, validation_status |
| provider_models | provider, model_id, verified_at, capabilities, terms_url, enabled |
| price_versions | model_id, unit, currency, rate, source_url, effective_at |
| quotes | owner_id, params_hash, price_version, max_credits, expires_at |
| wallets | user_id UNIQUE, balance integer CHECK >= 0, reserved integer CHECK >= 0 |
| credit_ledger | wallet_id, job_id, kind, amount integer, dedup_key UNIQUE |
| subscriptions | user_id, store, external_id UNIQUE, status |
| payment_events | provider, external_event_id UNIQUE, signature_verified_at |
| outbox | event_id UNIQUE, payload, published_at |
| consent_records | user_id, purpose, policy_version, date, withdrawal |
| admin_audit | actor_id, action, target, safe_diff, date |

Kredi itilize antye, pa floating point. Rezèvasyon tcheke balance-reserved sou yon
row lock nan tranzaksyon; menm tranzaksyon an ekri job ak outbox. Redis pa sous verite.
Dedup_key garanti finalize/refund yon sèl fwa. Yon echèk lage rezèvasyon san double
ranbousman; travay gratis pa kreye debit. Webhook verifye siyati epi replay pa double kredi.
Provider invocation sèvi ak kle idempotency si li sipòte sa. Sinon rekonsilye remote job
anvan retry; exactly-once pa garanti sou rezo ekstèn.

## Workflow ak API pwopoze

`queued → processing → quality_check → completed`; echèk antre `failed` ak kòd
ki pa ekspoze sekrè. Retry kreye attempt sou menm idantite travay la; sèlman yon
worker posede lease aktif, epi tranzisyon sèvi ak compare-and-swap/version.
Lease renewal ak rekiperasyon travay abandone fèt ak plafon retry.

`/v1/me`, `/v1/projects`, `/v1/characters`, `/v1/scenes`, `/v1/models`,
`/v1/quotes`, `/v1/jobs`, `/v1/jobs/{id}/retry`, `/v1/assets/{id}/download`,
`/v1/wallet`, `/v1/payments/webhooks/{store}`, `/v1/admin/*`.
Sa yo se kontra pwopoze; endpoint yo poko egziste.

## Kontwòl sekirite obligatwa

- OIDC + JWT verifye issuer/audience/expiry/signature; sesyon web HttpOnly/Secure,
  CSRF sou aksyon ki itilize cookie. Mobil itilize secure storage ak PKCE.
- Tcheke owner nan chak lekti/ekriti; PostgreSQL RLS kòm dezyèm baryè. Tès itilizatè
  A pa ka wè fichye/travay B, menm si li konnen UUID la.
- RBAC pou admin, MFA, audit append-only ak ekspòtasyon log san done sansib.
- URL siyen kout dire sèlman apre otorizasyon; pa gen bucket piblik.
- Upload limite bytes/dire/piksèl, verifye MIME pa kontni, scan, retire metadata sansib.
  Pa aksepte URL ekstèn san pwoteksyon SSRF, redirect ak adrès rezo prive.
- Worker FFmpeg an sandbox ak resous limite, timeout, non fichye entèn; pa entèpole
  prompt/URL itilizatè nan shell. Storage uploads nan quarantine jiskaske valide.
- Rate limits kont/IP/job; moderasyon avan jenerasyon ak sou rezilta. Mesaj klè
  sou refi/apèl; pa reklame yon filtè detekte tout kontni danjere.
- Kle AI backend sèlman; pa itilize NEXT_PUBLIC oswa EXPO_PUBLIC pou sekrè.
  Rotation ak secret manager; log pa janm dump headers, env oswa prompt prive.
- LGPD: minimizasyon, baz legal, konsantman apa pou fonksyon opsyonèl, aksè/ekspòtasyon,
  koreksyon/efasman, retansyon defini ak kontra subprocessors. Revizyon legal anvan lansman.
- Efase kont revoke sesyon, anile travay, efase assets ak done selon retansyon legal;
  backup expire dapre politik dokimante, pa pwomèt efasman enstantane tout backup.
- Backup PostgreSQL ak object versioning kote apwopriye; restore drill, RPO/RTO mezire,
  alert queue age, failure rate, provider spend, disk ak erè otorizasyon.

## Pòt tès avan lansman

Tès concurrency debit/refund, webhook replay, cross-tenant access, upload malveyan,
queue worker crash/retry, migrasyon/restore, quotes expire, free image zero debit,
media decode, download expiry, rollback OTA ak delete-account lifecycle.
Peman Web/Apple/Google dwe pase sandbox ak server-side verification. Pa aktive
peman reyèl ni apèl AI peye san quote ak plafon depans verifye.
