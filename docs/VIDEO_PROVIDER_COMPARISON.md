# Video provider verification — 4 November 2026

The user's instruction prohibits spending real generation credits on tests. This
research used only official documentation, public schemas and a GET of the
configured Gemini account's paginated model catalog. No predictions, interactions,
generation jobs, purchases, API enablement or provider subscriptions were created.
Production model activation and prices were not changed by this research.

## Current Gemini account

The complete models.list response contained 60 entries. Only these video-related
candidates were present:

- models/gemini-omni-1.1-flash
- models/gemini-omni-flash-preview

Both list generateContent/countTokens. Catalog visibility is not proof of a
successful video request, available quota or quality. Current public pricing
covers the GA Omni model; no distinct verified cheaper preview tariff was found.

Google's video documentation says the Gemini API Veo 3.1 Preview, Fast Preview
and Lite Preview endpoints shut down on 22 October 2026. This does not mean all
Veo services disappeared: separate GA models are documented on Google's cloud
platform. They do not automatically become available through this Gemini key.

Sources:
- https://aistudio.google.com/docs/video
- https://aistudio.google.com/docs/pricing
- https://aistudio.google.com/docs/omni

Omni pricing: USD17.50/million generated video tokens and 5,792 output tokens per
720p second: USD0.10136/second. 180 generated seconds are USD18.2448 before input,
clip rounding/overruns, retries, storage, editing, FX, taxes or Haytile margin.
The model docs also list 360p output; no explicit 360p token-rate conversion was
found. Do not invent a cheaper 360p price or assume pixel counts determine billing.

## Documented alternatives

These are provider charges in USD, not customer prices or activated Haytile offers.
180-second examples assume the necessary short clips are assembled and exclude
regeneration, boundaries, extra assets, storage, input fees and lip-sync unless
explicitly stated. Successful access and actual output quality remain untested.

| Provider / model | Documented rate | Illustrative 180s provider cost |
| --- | --- | --- |
| Google Omni Flash 720p | USD0.10136/second | USD18.2448 |
| fal MiniMax H3 Max Turbo 480P, regular | USD0.025/second | USD4.50 |
| fal MiniMax H3 Max Turbo 768P, regular | USD0.04/second | USD7.20 |
| fal LTX-2.3 Fast 1080p | USD0.06/second | USD10.80 |
| Runway Gen-4 Turbo, image-to-video | 5 Runway credits/second at USD0.01/credit | USD9, plus reference images |
| Replicate Wan 2.2 T2V Fast, 480p | USD0.05 per default output clip | About USD1.80 for 36 default clips |
| Replicate Wan 2.2 T2V Fast, 720p | USD0.10 per default output clip | About USD3.60 for 36 default clips |

Sources:
- https://fal.ai/models/minimax/h3-max-turbo/text-to-video
- https://fal.ai/models/minimax/h3-max-turbo/text-to-video/llms.txt
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=minimax/h3-max-turbo/text-to-video
- https://fal.ai/models/fal-ai/ltx-2.3/text-to-video/fast
- https://docs.dev.runwayml.com/guides/pricing/
- https://docs.dev.runwayml.com/guides/models/
- https://replicate.com/wan-video/wan-2.2-t2v-fast

H3 Max Turbo's 1–15 November promotion is USD0.0175/second at480P,
USD0.028 at768P and USD0.056 at1080P. Regular rates resume 16 November:
USD0.025, USD0.04 and USD0.08 respectively. Budget regular rates rather than
promise permanent promotional prices. Schema duration is 0.92–15 seconds;
output may run about0.7seconds longer than requested and billing uses generated
duration. Supported ratios include16:9 and9:16. The endpoint is marked commercial
use; provider terms, regional availability and account access still apply.

Replicate's page embeds the tariff and input schema in its public component JSON:
81 default frames at16fps (about5seconds), minimum81, maximum121. Its description
says81frames give the best results. Pricing mentions a16fps duration basis.
The illustrative36-clip estimates use default settings only; do not extrapolate
unchanged prices to longer clips, different FPS or other model endpoints.
A separate /license URL returned404, so current commercial licensing for that
specific optimized service was not independently confirmed. Resolve it before
activation; don't infer a license from the Wan family name alone.

## Wan Turbo on fal: low price but announced retirement

https://fal.ai/models/fal-ai/wan/v2.2-a14b/text-to-video/turbo
publishes USD0.10 per720pvideo, USD0.075 per580pvideo and USD0.05 per480pvideo.
Its public schema does not expose duration/frame-count fields. Do not promise a
180-second total from that per-video price without verifying clip length.
The page announces retirement on4January2027 and points to H3 Max Turbo. Therefore
it is not the recommended long-term default despite the low advertised price.

## Singing and lip-sync are separate requirements

A cheap moving-video model is not proof of synchronized singing. H3's documented
`target_audio_url` replaces/pins the soundtrack (max15MB, longer audio trimmed to
the generated clip); its schema does not promise lip-sync driven by that audio.
Do not market soundtrack replacement as mouth synchronization.

fal LatentSync documents video_url/audio_url inputs and commercial use:
https://fal.ai/models/fal-ai/latentsync
https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/latentsync

It lists USD0.20 per request for video up to40seconds and USD0.005 per output
second for longer requests. One supported180secondrequest would be USD0.90,
but36short scene requests would cost USD7.20 because each hits the minimum.
Neither full-song/3D singing quality nor multi-face behavior was tested. Do not
silently loop video to fit audio: the schema's loop_mode must not be used as a
substitute for generating the requested original moving scenes. Segment audio,
track the intended singer, align scenes and validate results before approval.

## Recommended implementation route

Add a real fal provider adapter, with H3 Max Turbo480P as economy,768P as standard,
LTX-2.3 Fast1080p as another model and existing Omni as a premium choice. Keep
provider-specific duration caps, queued request IDs, bounded retries, FFmpeg
assembly, private input/result storage, transparent full-project quotes and
atomic credit reservations. Image-to-video and lip-sync are separate adapters,
not capabilities automatically inherited by a text-to-video endpoint.

The scoped Render check found no configured FAL_KEY, REPLICATE_API_TOKEN or
RUNWAY_API_KEY. Google's key and balance cannot pay these other providers. For
the recommended route the owner must configure a fal account, its billing and
FAL_KEY securely in Render; never paste a key into chat or commit it. No provider
account or billing was activated during research. Do not display alternatives as
available in the app before credentials and integration actually work.

Prepare transport, queue-resume, pricing, ownership and media-validation tests
with offline stubs first. The owner may then run their own explicitly paid output
checks; do not spend real credits on automatic generation tests. Quality,
commercial/regional conditions and current quota still need verification against
the selected account. Self-hosted open weights need paid GPU capacity; neither
Firebase Storage nor the existing CPU Render service supplies free video GPUs.
