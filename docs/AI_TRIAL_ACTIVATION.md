# Real-provider trial activation

Public beta: https://haytile-ai.onrender.com (Render Free). On 2026-10-24 the
operator configured the Render provider key and confirmed active Google billing.
Zero-credit, bounded provider trials were enabled without changing the hosting
plan. See acceptance receipts below; catalog visibility alone is insufficient.

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
| Text / drama planning | gemini-3.5-flash-lite | Eligible, account quotas apply |
| Voice | gemini-3.8-flash-lite-tts | Eligible, account quotas apply |
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

Local backend suite: 42 tests passed after current TTS support. Seven targeted
video/project/drama tests also passed after the native clip copy optimization.
Tests include real FFmpeg assembly/download with explicit
provider fixtures, SQLite concurrency, bounded trials, bootstrap discovery,
operation recovery, PCM-to-WAV and safe URI delivery. Web production build,
web/mobile TypeScript and four locale/discovery tests passed previously.

The first public, real-provider acceptance run produced and privately downloaded:

| Studio | Job | Validated artifact |
|---|---|---|
| Image | af41c0e6-3fa7-414c-9e05-ada1e0bb9366 | JPEG, 1,028,443 bytes; image opened and inspected |
| Music | 5babaf91-468f-405d-a66e-001dbaab4e3b | MP3, 66.847292 seconds, 44.1 kHz |
| Video | b0fee168-45e2-4910-93d9-aeea4d77123b | MP4, exactly 8 seconds, H.264 1280×720 + AAC 48 kHz |
| Text | 7a09397d-283a-457d-ae64-d6009b14edfe | UTF-8 text, 311 bytes, four Haitian Creole sentences |
| Voice | 9a5593d9-c9e0-46ba-b7eb-af104dbe19e4 | WAV, 6.04 seconds, PCM 24 kHz |
| MiniDrama | 3cac0322-fbaa-42b0-b59f-e232c00fec83 | Final MP4, 16.104329 seconds, H.264 1280×720 + AAC 48 kHz |

The old text ID returned NOT_FOUND with an explicit new-user availability notice,
despite appearing in the catalog. The old TTS ID returned finishReason OTHER with
no content. A direct real call confirmed usable output from gemini-3.5-flash-lite
and a 3.68-second WAV from gemini-3.8-flash-lite-tts using the current speech
Interactions API. Release 76be6ff implements that speech protocol; 6444483 avoids
redundant video encoding. Deployment dep-dbe297jrjlhs738pofo0 of 6444483 is live
on the existing free service. End-to-end text, voice and episode acceptance passed
on that deployment. The episode saved one stable character with a generated
reference, two generated scene assets, unchanged planned dialogue and a final
asset ID. Scene cuts total 16 seconds; the MP4 container is 16.104329 seconds,
within the existing 150 ms muxing tolerance. Anonymous access to its private
download-link endpoint returned HTTP 401. Direct local processing of the real
native video also passed assembly and full decode after the copy optimization.

All three downloaded audio/video samples (song, voice and standalone video) passed
local full decode and contained non-silent audio. This is not a listening or
pronunciation assessment. The current service exposes the configured models and
reports provider_generation_disabled=false, trial_ai=true, 8-second video and
16-second episode limits. Operator-requested real trials incurred Google usage;
no exact billing total is claimed without the Google billing statement.

These receipts prove real generation, file validation, private saving and download;
they do not certify pronunciation, exact lyrics, dialogue or visual continuity.
Private outputs and account tokens stay in ignored artifacts/.local directories.
No paid Render resource was created.
