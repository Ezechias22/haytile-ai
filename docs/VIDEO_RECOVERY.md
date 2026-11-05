# Paid video recovery and assembly protection

Google can charge for successfully generated scenes even if local assembly fails.
Releasing a Haytile wallet reservation does not reverse a Google invoice. An
operator must reconcile provider usage separately; never promise an automatic
Google refund or infer exact billing/currency conversion from an app error.

## Durable scenes and safe retries

Video Studio stores a versioned `video_checkpoints` map on the owned job. Before
a new external submission it records that submission has started. Each known
provider operation ID is retained by scene index instead of overwriting the only
copy with the last scene. Completed clip bytes are uploaded to private object
storage and recorded with size and SHA256 before final assembly.

A retry reuses saved clip bytes, or retrieves an already-submitted operation with
GET. It may create genuinely unstarted scenes only while the video model is
approved. A submitted scene without a known operation or saved file requires
manual reconciliation: it cannot be blindly submitted again. Legacy multi-scene
failures with paid scenes but no checkpoints are similarly held. An explicit
incident hold cannot be bypassed by retry. Reservations/debits remain atomic and
the final result is charged once; tests cover a failed assembly, cached recovery
with provider calls forbidden, and one successful debit.

After successful completion, an internal private-media deletion outbox is
committed together with the final asset/job/debit. It removes temporary clips
idempotently after restart or SQL-cache loss. Failed-job checkpoints are retained
for recovery; account deletion also removes their private media. They are not
published as independent completed creations.

## Frame-accurate assembly

Coverage is based on the video track, not AAC/container padding. Intermediate
tracks use a common video timescale. Native-compatible clips still use packet
copy as the first choice. If the resulting container or video-track duration
fails the existing tolerance, FFmpeg re-encodes the already-generated scenes with
normalized timestamps and frame-accurate trimming. Final duration and resolution
must still pass; the tolerance is not relaxed, and missing footage is not looped
or stretched. This fallback never invokes a generation provider.

Tests include actual FFmpeg media, a forced out-of-bound copy result followed by
frame-accurate recovery, missing/short media rejection, checkpoint reuse and
unknown-submission/legacy retry refusal. Test generation providers are offline.

## Operator incident response

1. Inspect owned job status, attempts, completed scenes and known operation IDs.
2. Pause video admission and retain the failure/reconciliation hold; check queues.
3. Preserve the pause across restart with `enabled:false` on the video entry of
   `HAYTILE_MODEL_CONFIG`. Bootstrap respects that explicit flag; other models
   remain independent. Do not silently reactivate paid video after an incident.
4. Retrieve existing operations/media with read-only GET, without new inference.
5. If identifiers were overwritten, historical Firestore document reads may help
   within the database's retained version window. This is emergency recovery,
   not a durability strategy or a promise that historical data always exists.
6. Assemble and validate the actual recovered scenes. Never deliver repeated
   diagnostic clips as the user's completed creation.
7. Make the validated result available privately for user review. A complimentary
   recovery must not silently rewrite the original debit/refund history.

Provider billing may continue to post already-incurred charges after the app
queue is empty. An empty queue proves no app work was active at that check, not
that Google has finished billing or that another client never used the same key.
Use Google's billing/usage report for exact monetary attribution.
