# Normal chat admission

The production warning was traced to Haytile's own 20-message/24-hour account
counter, not the displayed wallet balance. At diagnosis the counter was exactly
20, the old global free-chat bucket was 24/50 and the hourly bucket 16/30. Failed
submissions had also consumed these buckets, so the generic capacity message was
misleading after the worker outage.

Normal durable text chat no longer consumes account daily, global chat daily or
free-media hourly admission buckets. It also bypasses temporary trial daily
attempt counts on PostgreSQL and on Firestore-backed SQLite projections. Legacy
counters are retained unchanged for history; they no longer block normal chat.
The old environment knobs remain relevant only to explicitly temporary,
non-durable trials, not the production Firebase chat.

Six new chat submissions per ten seconds per account protect against bursts.
Overflow uses APP_BURST_LIMIT with a seconds-long explanation, separate from
PROVIDER_QUOTA_EXCEEDED. Each conversation has at most one pending new message,
with a specific processing response, while other conversations and paid music
queues do not impose the old three-pending-jobs limit on chat. No provider call
is made by an admission rejection.

The UI clears a previous global error banner when a new message or retry starts,
so an old capacity warning does not remain over a later successful conversation.
The runtime reports null daily/hourly chat ceilings and the actual burst policy.
Text remains zero Haytile credits. Real Google quotas, spend caps, network limits
and hosting capacity still apply; removing message counters does not make API
usage or hosting free or guarantee infinite concurrency. No Google billing cap
or provider safety rule is changed.

Offline checks submit 35 paced messages with all legacy counters already full,
exercise burst rejection and per-conversation ordering, verify that three queued
music jobs do not block chat, and cover Firestore-backed trial bypass. A browser
regression checks that a successful second request removes a stale error banner.
No actual Google generation is used by these checks.
