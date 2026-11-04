# Conversational chat and durable creative jobs

Current policy update: see [SIDEBAR_VOICE_AND_IMAGE_BILLING.md](SIDEBAR_VOICE_AND_IMAGE_BILLING.md).
Plain text remains free; images now have positive quotes with the paid-image flag.
The initial rollout receipt below records the earlier image-free release.

The web workspace opens HAYTILE Chat: a composer, user messages, assistant replies,
conversation history, a model selector, copy and text download. The initial greeting
identifies HAYTILE AI as an AI assistant. The provider receives a server-owned system
instruction with that identity and explicit limits: it must not invent completed
media, tools, files or downloads. Replies arrive from real queued text jobs; the UI
shows actual pending states rather than simulated token streaming. No live Google
generation was used to validate this release.

The backend reconstructs context from this owner's completed jobs and output assets,
checks the conversation/parent relationship, and caps it at 12 previous turns and
16,000 characters. A new prompt can contain up to 12,000 characters. Only the recent
bounded context is sent upstream. Clients cannot inject system or assistant roles.
Failed jobs have an explicit retry button; transport retries reuse the submission's
idempotency key. Chat uses the free text credit policy and still consumes the
operator's provider quota/budget. Admission defaults to 20 chat submissions per
user/day and 50 globally/day, separate from expensive creative-job limits;
these can be adjusted with `HAYTILE_CHAT_PER_DAY` and `HAYTILE_DAILY_CHAT_LIMIT`. No attachments, browsing or media generation tools
are attached to this text chat. The native applications have not been republished;
the new conversational interface is currently a web change.

## Persistence and credit settlement

With `HAYTILE_ACCOUNT_PROVIDER=firestore`, jobs, output metadata and storyboards are
canonical Firestore records; local SQL is a projection. Migration 0005 adds remote
versions. SQL before-commit hooks atomically write remote metadata, wallet reserve,
debit/release events and an account-active precondition using compare-and-swap.
The worker commits its claim before any paid provider request. Completion publishes
asset metadata and the single debit in one remote commit. Failed jobs release the
reservation. Ambiguous commits retain uploaded files and require reconciliation
instead of blind submission. Namespace `main` is used for production claims;
Firebase fixture probes must use a unique separate namespace.

Jobs survive local SQL loss and returning owners hydrate their own metadata. Media
is private object storage with short-lived authorized download URLs. Plain text generation always costs zero Haytile credits. Images require positive
quotes with `HAYTILE_PAID_IMAGES=1`; earlier free jobs retain their original price.
Other studios use an exact server quote before consent. The UI opens My
Creations after acceptance, polls actual stages, permits title edits during/after
work, and exposes only completed paid results.

Before replacement of a legacy Render instance, run
`scripts/migrate_render_metadata.py` with explicit Firebase credentials supplied
securely in the process environment. It uses owner-scoped exports, archives stable
IDs, verifies private object metadata, removes its temporary sessions, and aborts
if a job is active. It never generates AI. Do not infer recovery of metadata that
was already lost on the old temporary server. Unmapped private files must not be
assigned arbitrarily to users.

A free Render instance can sleep and has limited CPU/RAM. Firebase persistence
does not make a sleeping worker run, nor provide unlimited video compute. Interrupted
paid requests with uncertain upstream outcomes require reconciliation; no automatic
paid resubmission is promised. Long video assembly uses files and streaming storage
uploads rather than loading a complete three-minute movie into RAM. Video/episodes
accept 8–180 seconds and use at most 23 planned clips, actual scene counters,
FFmpeg assembly and file integrity inspection. Visual continuity and lip-sync are
not guaranteed or exhaustively checked.

## Verified pricing policy

`HAYTILE_PRICING_POLICY=verified` uses official Google rates archived on 2026-11-03,
with the source at https://ai.google.dev/gemini-api/docs/pricing. The internal
reference credit is USD 0.01. It is not a Google billing unit or an implemented
retail purchase price. Costs include explicit app input/operation reserves, then
are multiplied by 4 and rounded up to whole credits. Rates are snapshots and must
be reviewed as upstream terms change; unknown paid models remain unavailable.

| Work | Haytile quote basis |
| --- | --- |
| Basic images and text/chat | 0 credits; operator pays actual provider costs |
| Lyria 3 clip | USD 0.04 official request basis → 16 credits |
| Lyria 3.5 / 3 Pro | USD 0.08 official request basis → 32 credits |
| Omni 1.1 Flash video | 5,792 output tokens/sec at USD 17.50/million; reserve 10 native seconds plus USD 0.10 per planned 8s clip → 446 credits/clip |
| 180s video | 23 clips → 10,258 credits |
| 180s MiniDrama episode | 23 clips plus USD 2.25 planning/reference reserve → 11,158 credits |
| Voice | Model-specific regular announced input/audio token rates, 4,000 input-token reserve and 4,096 output audio tokens per 1,000 characters, plus USD 0.01 operation reserve; actual upstream output is capped |

The reserves are app policy, not invented Google fees. Multiplying by four leaves
room for retries and operations but cannot guarantee profit. Free generations,
manual gifts, taxes, FX changes, infrastructure and provider failures still cost
money. Payment collection, recurring subscriptions and store billing are not
implemented by this change; giving credits is not revenue. Keep provider budget
caps and admission limits enabled. Google credit and Haytile wallet balances are
independent.

The curated manifest has 36 per-studio entries, drawn from a previously read
60-model account catalog: image 6, text 10, voice 5, music 3, video 2, MiniDrama
planners 10. Some models appear in multiple studios. One video preview is visible
but disabled because its price is not verified. A catalog entry is not proof a
paid generation will succeed with the current account, region, quota or input.
The application offers only supported configured choices, not invented alternative
video providers. TTS has 30 selectable prebuilt voices; music has vocal direction
(auto/male/female/duet/instrumental), not guaranteed singer identity or voice cloning.

## Validation

Backend tests cover owner privacy, chat identity/context, title changes during
work, quotes, real local 180s portrait assembly, wallet CAS/idempotency, metadata
rehydration after SQL loss and ambiguous remote commits. Browser tests use a
separate disposable PostgreSQL database and explicit offline provider stubs to
verify chat replies/context/reload and the creation/consent/progress/rename/playback
workflow. No Google generation endpoint is used in tests. Web production build,
web/mobile TypeScript, locale coverage and upload proxy limits are checked.

Publishing Expo OTA or native builds remains a separate release operation requiring
real Expo project/token/signing access. This web rollout does not claim an AAB/IPA,
App Store release, complete payment integration or a fully finished product.

A real Firestore-only disposable probe additionally verified one reserve, one
debit (100 → 93, reserved 0), and Job/Asset/Project restoration after complete
in-memory SQL loss. Its isolated queue namespace prevented production claims;
no provider was invoked, fixture records were cleaned, and real users were untouched.

## Public rollout receipt

Source `de567c39f10f03f663f7c11795cdc93a4eff562b` is live on the existing free
Render service as `dep-dbl7vuutlv9c73b8qjkg`. Public runtime source_revision and
HTML were verified, not just the control-plane status. Runtime reports
`durable-creations-chat-v1`, Firestore identity/wallet/metadata, and both duration
caps at 180. A short-lived owner-authorized session verified private chat access,
admin durable finances and exact free/paid quotes; it was removed afterwards.
No real balance changed and no generation endpoint was invoked. The legacy
preflight found two accounts, zero extant SQL job/asset/project metadata, and
zero active jobs. This does not claim recovery of previously lost creations.

Validation: 93 backend tests, five browser workflows, production web build,
web/mobile TypeScript, four locale/discovery checks and two upload proxy tests.
Browser responses and media were explicit offline fixtures. Public checks are
configuration/read/quote checks, not live paid model output quality tests.

## Account welcome and concise replies (2026-11-04)

New, empty chats display a short greeting with the first name from the signed-in
profile, using the selected UI language and device local hour: morning before
12:00, afternoon before 18:00, evening thereafter. Haitian Creole uses Bonjou
in the morning and Bonswa thereafter. All nine locale files contain the labels.
Opening an existing conversation does not prepend another welcome.

`POST /v1/chat/welcome` claims the introduction once per authenticated account.
Production stores `chat_introduced` on the canonical Firestore account with an
optimistic version precondition and retries conflicts. Existing chat history
also suppresses reintroduction. SQL development uses an internal, deterministic
project marker excluded from project listings; no database migration is needed.
No Google call, credit charge, or generated creation is involved in the greeting.

Welcome suggestion cards were removed. The shared assistant instructions ask for
direct drafts, no repetitive identity preamble, no unsolicited studio promotion
or app URLs. Identity questions still receive an honest identity; requested media
navigation may briefly name the relevant in-app menu. Topup recommendations remain
limited to relevant digital-product requests. These are model instructions, not a
promise that every generated response will obey perfectly. Provider behavior was
not tested with paid Google requests.
