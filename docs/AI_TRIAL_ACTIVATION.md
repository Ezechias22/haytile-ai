# Real-provider trial activation

Public beta: https://haytile-ai.onrender.com (Render Free). The live service still
has no Google provider key. The changes described here are prepared in source;
they do not constitute a live generation receipt.

## Required operator configuration

Set `HAYTILE_GEMINI_API_KEY` as a **secret in the Render service environment**.
Never put it in Git, browser code, mobile configuration, logs, or chat. The cloud
secret currently permits Google requests only. Its proxy placeholder is not a
portable API key. Changing that existing binding requires environment settings;
a draft update cannot override its destination restrictions.

Confirm Google billing/quota and provider terms before enabling models. Free
Render hosting does not include free Google image, song, or video inference.
Images always cost users zero application credits; the operator pays provider
charges. Quotas can still prevent generation.

The following account-visible candidates were verified through model discovery
and official documentation on 2026-10-24. Discovery is not a successful generation
or proof of billing access:

| Studio | Candidate | Published free tier |
|---|---|---|
| Text / drama planning | gemini-2.5-flash-lite | Eligible, account quotas apply |
| Voice | gemini-2.5-flash-preview-tts | Eligible, account quotas apply |
| Images | gemini-3.1-flash-lite-image | No |
| Songs / vocals | lyria-3.5 | No |
| Video | gemini-omni-1.1-flash | No |

Sources: [pricing](https://ai.google.dev/gemini-api/docs/pricing),
[music](https://ai.google.dev/gemini-api/docs/music-generation),
[video](https://ai.google.dev/gemini-api/docs/omni),
[speech](https://ai.google.dev/gemini-api/docs/speech-generation),
[Interactions](https://ai.google.dev/gemini-api/docs/interactions).
Recheck rates, region eligibility, licenses and quotas before activation.

After explicit operator acceptance of provider charges, set server-only
`HAYTILE_OPERATOR_BILLING_ACK=1`, `HAYTILE_TRIAL_AI=1`, and
`HAYTILE_MODEL_CONFIG` to a JSON array of `{studio, model_id, credits: 0}` records
using verified candidate IDs. Leave unapproved studios absent. Bootstrap checks
the actual account catalog again. Episode mode needs minidrama, image and video
entries; nonzero-credit episode pricing remains blocked pending an aggregate quote.

Keep `HAYTILE_DAILY_JOB_LIMIT=10`,
`HAYTILE_TRIAL_PER_STUDIO_PER_DAY=2`,
`HAYTILE_TRIAL_MAX_VIDEO_SECONDS=8` and
`HAYTILE_TRIAL_MAX_EPISODE_SECONDS=16` for initial trials. These limits bound
requests, not a guaranteed dollar budget. Each episode can make several provider
calls. Retries count toward trial attempts. Paid-credit operations require
PostgreSQL. SQLite uses serialized write admission and worker claims.

Deploy only to the existing free service. Redeployment can erase temporary
accounts and media. Do not enable public paid-provider access without suitable
operator quotas and abuse controls; app quotas reset with this temporary database.

## Acceptance checks and limitations

For each activated studio, submit a real job, wait for `completed`, download the
private result and open it. Record model, job ID, time and output metadata without
keys or private content. Test a failed/quota-limited job and retry behavior too.
Never interpret fixture tests as live AI acceptance.

Video/music operations retain provider interaction IDs for bounded polling and
safe recovery. Requests use `store: true`; Google retention and usage terms apply.
Signed provider media redirects are restricted to Google destinations, and API
credentials are never forwarded to the storage CDN. Ambiguous multi-scene work
requires reconciliation instead of blind resubmission.

Episode mode saves an editable project, generates character reference images and
native scene clips, then uses FFmpeg to produce one validated MP4. Intermediate
assets survive a later scene failure while the final job stays failed. Mechanical
checks cover decodability, duration, aspect and audio presence. They do not prove
exact spoken dialogue, lip sync, visual continuity or absence of deformation.
Automatic subtitles, dedicated lip sync and visual quality review remain open.

## Validation receipt

Local backend suite: 40 tests passed before the additional character-reference
transport regression. Tests include real FFmpeg assembly/download with explicit
provider fixtures, SQLite concurrency, bounded trials, bootstrap discovery,
operation recovery, PCM-to-WAV and safe URI delivery. Web production build,
web/mobile TypeScript and four locale/discovery tests passed. No Google generation
was executed in this activation preparation. No paid Render resource was created.
