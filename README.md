# HAYTILE AI

[Open the free test app](https://haytile-ai.onrender.com) — temporary accounts/media; AI generation is disabled in this free-beta deployment.

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
They are **not enabled or live-validated** without a server-side key and verified
account model configuration. Video clips can be assembled into an 8–180 second
MP4 with FFmpeg; actual AI continuity and voice/lyrics quality remain unverified.
MiniDrama includes editable character/scene storyboards and assembly of uploaded or generated clips; automatic lip-sync and continuity scoring are not implemented.

```sh
cd /workspace/haytile-ai
bash scripts/setup.sh
bash scripts/start.sh
bash scripts/test.sh
```

- [Run and deployment instructions](docs/DEPLOYMENT.md)
- [Current implementation and limitations](docs/PROGRESS.md)
- [Verified public Google documentation and prices](docs/PROVIDER_RESEARCH.md)
- [Architecture](docs/PHASE_1.md)
- [Data/security design](docs/DATA_SECURITY.md)

No payment integration, mobile store release or public deployment is claimed.

Render free testing is configured in `render.yaml`; see [the free-mode limitations](docs/RENDER.md). Accounts and media on that deployment are temporary, and AI generation is disabled until persistent prerequisites are supplied.
