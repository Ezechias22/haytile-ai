# User-selectable AI models

Each studio has an AI model selector. Web selections are remembered per studio in
localStorage; mobile source uses SecureStore. The selected model ID is sent as the
optional top-level `model_id` of `POST /v1/jobs`. Existing clients that omit it
continue to use the administrator's default studio model.

## Server authority

`HAYTILE_MODEL_CHOICES` is a server-owned JSON allowlist of at most 64 entries:

```json
[
  {"studio":"text","model_id":"gemini-3.5-flash-lite","label":"Gemini 3.5 Flash Lite","credits":0,"enabled":true},
  {"studio":"text","model_id":"gemini-3.8-flash","label":"Gemini 3.8 Flash","credits":0,"enabled":true}
]
```

Environment choices require `HAYTILE_OPERATOR_BILLING_ACK=1`. Existing database
model settings take precedence for that studio's default model and credit price.
Disabling a studio's database model also disables its alternatives, preserving the
existing administrator kill switch.
Disabled choices cannot execute. Unknown/cross-studio IDs are rejected, and new
environment choices are checked against the account catalog at job admission,
outside the credit transaction. Catalog visibility still does not guarantee
generation access, quotas, language quality or availability.

The server calculates credits from the selected choice, validates the user's
confirmation and reserves/debits using the existing ledger. Basic images remain
zero-credit. A job snapshots its selected model and provider; later changes to a
default do not silently reroute it. Changing the requested model while reusing an
idempotency key produces a conflict. Client-supplied model IDs inside arbitrary
`params` are rejected.

The selector links to https://ai.google.dev/gemini-api/docs/pricing and explains
that Haytile credits are distinct from provider API charges. No invented USD/R$
price or exchange-rate estimate is presented.

## Curated choices

A read-only account catalog request returned 60 model records. The configured
subset uses protocols already implemented by the adapters:

| Studio | Choices |
|---|---|
| Text | Gemini 3.5 Flash Lite; Gemini 3.8 Flash |
| Images | Nano Banana 2 Lite; Nano Banana 2 |
| Voice | Gemini 3.8 Flash Lite TTS; Gemini 3.8 Flash TTS |
| Music | Lyria 3.5; Lyria 3 Clip Preview |
| Video | Gemini Omni 1.1 Flash |
| MiniDrama planning/scripts | Gemini 3.5 Flash Lite; Gemini 3.8 Flash |

These are 11 studio/model combinations, nine distinct IDs. Video has only one
curated option; unsupported or retired video models are not invented to fill the
list. MiniDrama selection controls planning/scripts; configured image/video studio
defaults still supply character references and clips. Realtime music models are
excluded because they require a different protocol.

## Availability and validation

Generation and the Render queue worker remain disabled. Users may browse and save
their preference, but selection never resumes AI or consumes unavailable funds.
No paid provider generation was executed for this change. New model variants have
not been live generation-tested while credits are unavailable.

66 backend fixture tests verify selected-model routing, server-owned prices, paid
credit accounting, replay/conflict behavior and rejection of unknown/cross-studio
models. Web production build and mobile TypeScript checks pass. Mobile source
changes are not a claim of a published native build or OTA release.

Local browser acceptance passed selection by studio, persistence after reload and
navigation, the official-pricing link and continued generation disablement. The
three existing account/library/storyboard browser workflows also passed.

Public rollout `dep-dbh92ehsrm7s73f5ceog` of `3f73880` is live on the existing
Render Free service. The public API returns 11 studio/model choices (nine distinct
IDs), all unavailable for generation while paused. Runtime confirms generation
paused and the Render worker disabled. The allowlist was checked against model
metadata using the deployed provider key; no generation was invoked.

## Video consumption price revision

The video model selector now explicitly labels credits per clip. The server quote
shows the planned clip count and full duration total before Generate/confirmation.
A selector's base price is not a quote for a three-minute project.

The regular Gemini Omni Flash source was rechecked at
https://aistudio.google.com/docs/pricing (redirect from the older ai.google.dev URL):
720p output is 5,792 tokens/second at USD17.50/million output tokens. Input/text
costs remain separate. Haytile still reserves up to ten generated seconds plus
USD0.10 of input/operations per clip and plans one clip for each started eight
seconds of requested duration. Output token limits are unchanged.

Video-specific markup changes from4 to1.5; other studios' multipliers and Stripe
credit-pack/subscription prices are unchanged. With no manual admin price floor:
8seconds=168credits;30seconds=672;180seconds=3864(23clips). MiniDrama180seconds
is4202credits including338 for the planning/reference reserve. Manual higher
admin floors still apply. Image prices and free text are unchanged.

This is a retail policy, not a claim that Google changed its price or a guarantee
of net profit. Payment fees, exchange rates, free chat, hosting, retries, refunds
and actual provider usage still require monitoring. Existing purchases, wallets,
job reservations and completed-job debits are not rewritten by this change.
