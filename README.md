# HAYTILE AI

[Open HAYTILE AI](https://haytile-ai.onrender.com) — free Render hosting and private Firebase media. Provider generation is paused while API funds are unavailable.

Current deployment uses private Firebase media storage. Account/job/credit metadata
is still temporary SQLite. Latest image/text generation probes returned Google
quota errors; see [live Firebase acceptance and remaining limits](docs/FIREBASE.md).

A working development foundation for the Haytile creative platform: Next.js web,
Expo Android/iOS source, FastAPI, PostgreSQL, a durable background worker, optional
Redis wakeups and private media storage.

Implemented and connected: registration/login/logout, profile/language settings,
private library, text drafts, validated media uploads, previews, expiring downloads,
rename/delete, text-to-studio handoff, account data export/deletion, administrator
model configuration and audited credit grants. Background jobs reserve credits
atomically, debit only after validated output and release reservations on failure.
Basic image generation always uses zero user credits.

Google adapters exist for text, image/reference, TTS, Lyria music and Omni video.
Real image, song and 8-second video generation/save/download passed on the public
service. Current text and TTS models replace account-visible legacy IDs that failed
real calls; see [activation and acceptance receipts](docs/AI_TRIAL_ACTIVATION.md).
Video assembly supports 8–180 seconds; the current trial caps video at 8 seconds
and episodes at 16 seconds. AI continuity and voice/lyrics quality require review.
MiniDrama includes editable character/scene storyboards and assembly of uploaded or generated clips; automatic lip-sync and continuity scoring are not implemented.

```sh
cd /workspace/haytile-ai
bash scripts/setup.sh
bash scripts/start.sh
bash scripts/test.sh
```

- [Run and deployment instructions](docs/DEPLOYMENT.md)
- [Current implementation and limitations](docs/PROGRESS.md)
- [Selected Firebase media storage and migration](docs/FIREBASE.md)
- [Direct media delivery, Firestore counters and compute limits](docs/FIREBASE_OFFLOAD.md)
- [Verified public Google documentation and prices](docs/PROVIDER_RESEARCH.md)
- [Architecture](docs/PHASE_1.md)
- [Data/security design](docs/DATA_SECURITY.md)

Payments and mobile store releases are not implemented. The public web deployment is a test service.

Render free testing is configured in `render.yaml`; see [the free-mode limitations](docs/RENDER.md). Download creations promptly because accounts and media on that deployment are temporary.
