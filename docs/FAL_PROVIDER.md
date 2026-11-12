# fal.ai integration

The backend supports fal as an additional provider across Image, Music, Video,
Voice, text Chat and MiniDrama. It does not replace Google credentials or share
Google billing funds. Set `FAL_KEY` on the backend only. The existing Render name
`Fal_key` is also accepted. No key is embedded in web/mobile bundles or model
settings. No new SDK/runtime dependency is required.

## Model profiles and activation

Fourteen schema-reviewed profiles are shipped, disabled until pricing review:
ACE-Step, MiniMax Music 2.5, FLUX Schnell, BiRefNet, BRIA background removal,
Clarity upscale, FLUX Kontext editing, Kling 2.5 Turbo, Wan 2.2, Kling 3 Standard
text-to-video and image-to-video, Kokoro American English, and GPT-OSS 120B through
fal AnyLLM for text and drama scripts. Profiles are opaque `fal-<hash>` aliases;
client input cannot choose arbitrary endpoints, premium submodels, batch counts,
GPU settings or safety settings. Google choices remain available.

Administration > fal.ai offers the official catalog search, supported-profile
list, current account pricing verification, terms links, markup, activation and
disabling. Catalog discovery is not equivalent to integration/approval of every
fal endpoint. Metadata and pricing reads do not submit inference work.
Variable GPU-compute pricing is rejected when it cannot be bounded by the
adapter. BiRefNet therefore remains unapproved; BRIA provides fixed-unit removal.
No model is described as supporting all content or bypassing provider moderation.

Profiles and audit changes persist in Firestore `haytile_provider_config`, using
one snapshot for both the merge and compare-and-swap version. PostgreSQL/local
development uses the existing audit table. No relational schema change is needed.
No Firebase client access is granted to this collection. Every admitted job freezes
its approved provider profile; editing a model cannot change queued job parameters.
Private profile/checkpoint data is omitted from public history responses.

## Capabilities and actual limits

- Music lyrics and the single musical-style prompt map to separate native fields.
  Lines are preserved; no lyrics optimizer, automatic paid extension or replacement
  with TTS is used. ACE-Step accepts 5–240 seconds; an automatic estimate exceeding
  this cap is disclosed in the UI. MiniMax 2.5 accepts at most 3,500 lyric characters
  and has no native duration parameter; a five-minute song is not guaranteed.
- Image generation is fixed to one output with server-owned dimensions. Background
  removal/editing/upscale require an owned, completed private image. Image-size
  metadata is cached without retaining image bytes. Upscale is limited to 5 MP
  input to fit the existing 20 MP output validation; quoted output megapixels are
  rounded up. Requests cannot point the backend at arbitrary external input URLs.
- Kokoro American English exposes its actual male/female voice IDs and speed.
  It supports English in this integration. Selecting a supported output language
  is explicit; the app never silently switches to English. Voice text is bounded.
- Wan 2.2 and Kling 2.5 profiles are silent video choices. Kling 3 native audio is
  documented for English/Chinese; other languages would be translated by the
  provider and are therefore rejected before spending. Video targets of 8–180 s
  use native clips and the existing validated FFmpeg assembly. No still-image loop
  or artificial stretching replaces generated scenes.
- Fal text chat is free in Haytile credits but costs the operator upstream. Its
  profile is text-only, without Google Search grounding, file analysis or a native
  live-audio session. These capabilities are disclosed; no hidden Google fallback
  is used. Existing Google models retain their tools and native Live voice.
- MiniDrama can select an approved fal script, initial-character image and native
  audio/video model. Silent/auto-translating video combinations are rejected before
  planning. Reference-required scenes must contain declared characters. File/QC
  success does not guarantee perfect faces, lip sync, music, pronunciation or dialogue.

## Cost and interruption safety

Current account prices are read from `api.fal.ai/v1/models/pricing` and explicitly
reviewed; the original response currency/unit is retained. A model is not activated
if the adapter cannot conservatively count those units. Quotes freeze output
counts, resolution, voice/submodel and allowed controls. UI parameters cannot
increase billing dimensions without a new quote. Text remains free; other models
use the existing atomic reservation/debit/release mechanism. Credits are an app
pricing policy, not provider currency; retail discounts, FX, tax and fees still
need business monitoring. No guaranteed profit is inferred from model markup.

Submission is marked durably before the queue POST. The request ID is saved before
polling. `X-Fal-No-Retry: 1` and fallback-disable headers prevent implicit app retry
behavior. An uncertain submission without an ID requires reconciliation, not
another paid POST. Existing request IDs resume through status/result GETs. Per-scene
video checkpoints remain separate; parent result caches are never reused as new
scenes. Provider rejections remain blocked for an unchanged paid request. A failed fal
MiniDrama episode that already started provider work requires reconciliation;
its full multi-provider pipeline is not blindly resubmitted from the beginning.

Results download without API credentials from allowlisted fal CDN hosts, with
redirect revalidation, size bounds, and disk streaming for audio/video. Inputs use
short-lived signed private asset links. Fal IO retention is disabled and output
lifecycle requested at 24 hours; final files are copied to private Firebase storage.
Fal generation runs off Render. FFmpeg assembly/file validation still uses the
existing bounded backend worker and needs external worker capacity as traffic grows.
The original incident-held Google video model is not reactivated when approving a
fal-only video option. All provider work still respects the global service pause.

## Verification

Provider HTTP/queue/media calls are intercepted in unit and browser fixtures.
Tests cover native input mappings, exact lyrics, model/language limits, billing,
RBAC activation, CAS configuration, media SSRF/auth separation, no duplicate
submission/debit, resumable request IDs, male voices, chat, video assembly and drama.
Production verification uses only metadata/pricing/session/quote/configuration
operations. It never posts a real queue generation to fal or Google.

Sources checked 2026-11-12:
- https://fal.ai/docs/platform-apis/v1/models
- https://fal.ai/docs/platform-apis/v1/models/pricing
- https://fal.ai/docs/api-reference/inference-api/queue/submit-path
- https://fal.ai/models/fal-ai/ace-step/api
- https://fal.ai/models/fal-ai/minimax-music/v2.5/api
- https://fal.ai/models/fal-ai/kling-video/v3/standard/text-to-video/api
