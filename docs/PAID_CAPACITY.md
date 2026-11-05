# Paid generation capacity

Paid generations backed by Firestore wallets no longer use the legacy global
10-jobs/day or trial per-studio daily quotas. Daily and hourly admission counters
and the three-pending-jobs limit apply only to free requests. Each paid request
still reserves its quoted credits atomically; background processing stays serial.

Paid submissions and voice-call starts allow six starts per ten seconds per user
to protect against accidental repeated clicks. Rejected bursts return
APP_BURST_LIMIT before any provider request. Real provider quotas remain separate;
users cannot bypass Google limits by adding Haytile credits. Free text quotas
continue to protect the owner's provider budget.

A refunded Haytile wallet reservation does not refund Google charges for work
already performed. No paid provider generation was invoked during these tests.
Video remains disabled following the earlier quality and cost incident.

Verification: 137 backend tests, an offline web build, and two browser workflows.
Fixtures cover multiple billing periods on one voice socket, Stop, insufficient
funds, resumption, token throttling and paid music admission beyond legacy caps.
