# Media delivery and Render load reduction

The operator requested removal of test-version branding, moving suitable work to
Firebase, and no paid AI generation while provider credits are unavailable.

## Implemented

- Firebase-backed assets have owner-authorized five-minute V4 preview and attachment
  URLs. Web and mobile use them directly for playback/downloads. Large result bytes
  no longer traverse Render for these flows, and web downloads avoid a full Blob
  allocation. Existing signed API paths remain a compatible fallback.
- New objects use private/no-store cache metadata. Signed attachment filenames are
  URL-encoded. No public bucket ACL or permanent Firebase download token is created.
- Firestore stores abuse/rate-limit counters in `haytile_rate_limits`. The actual
  database ID is `default`, not `(default)`. Document IDs hash the counter key; only
  count/reset timestamps are stored. Updates use atomic updateTime/exists preconditions,
  bounded retries and fail-closed behavior. No Firestore SDK/gRPC dependency is added.
- The UI's test-version banner and its nine-language labels are removed. A neutral
  generation-unavailable notice reflects the operator's service switch. Settings
  retain a truthful account-data export warning while account metadata is ephemeral.
- Idle web pages no longer poll assets/jobs/wallet every five seconds. Visible pages
  poll only while jobs are active; focus/actions refresh data as needed.
- `HAYTILE_GENERATION_ENABLED=0` rejects provider job admission before calling AI.
  `HAYTILE_WORKER_ENABLED=0` prevents the Render supervisor from spawning a queue
  worker and blocks assembly admission/retries. It does not create phantom jobs.
  Model bootstrap also skips provider discovery while generation is paused.

Render configuration for this cutover:

```text
HAYTILE_GENERATION_ENABLED=0
HAYTILE_WORKER_ENABLED=0
HAYTILE_RATE_LIMIT_PROVIDER=firestore
FIREBASE_DATABASE_ID=default
```

Firebase Storage/project/service-account configuration remains server-only. The
Render plan remains free. Firebase usage is separate and quota/billing dependent.
Do not re-enable provider generation or local heavy processing automatically when
funds return; review the intended execution placement first.

## What is not moved

Long FFmpeg montage is **paused, not deployed to Firebase compute**. Storage and
Firestore are storage/database services; they do not run FFmpeg by themselves.
Read-only IAM inspection confirmed that the runtime service account lacks the
queried `run.jobs.create`, `run.jobs.run`, `cloudbuild.builds.create`, and
`artifactregistry.repositories.create` deployment capabilities. Deploying a bounded
Cloud Run/Functions media processor in the Firebase-linked Google Cloud project
needs a separate trusted deployer, an image and runtime invocation permissions.
Do not grant broad deployment-administrator roles to the public app's runtime key.
No external compute worker is claimed to exist.

Account/session/job/credit/project records are still SQL-backed. Firestore counters
do not constitute migration of these records, payment readiness or full production
durability. Upload decoding/validation still uses the API; it has not been silently
removed or relabelled as remote validation. Basic media delivery is offloaded;
unlimited Render capacity is not promised.

## Validation

- 62 backend tests, web build, web/mobile TypeScript and four locale/discovery tests pass.
- Three real-backend browser workflows pass with generation paused. An additional
  authenticated browser check found no test-version text and zero idle metadata
  requests over 12 seconds.
- Real Firebase signed preview/download URLs returned the exact payload, correct
  disposition/cache policy and HTTP 206 byte ranges; expiry is five minutes.
  Unsigned Firebase access returned 403. Disposable objects were removed.
- Real Firestore concurrency allowed exactly one of two simultaneous attempts at
  a one-request limit; persisted count was one. Anonymous access returned 403 and
  the disposable counter was removed.
- A 512 MiB / 0.1 CPU local container started API/web with no queue-worker process.
  This is local validation, not a claim about live Render memory or an unlimited SLA.
- No Google AI generation requests were sent during this work.

## Public deployment acceptance

Deploy `dep-dbf2l5jncjis73e270m0` of `fddb194` is live on the existing Render Free
service. Runtime confirms firebase_direct media delivery, Firestore rate-limit
storage, generation_paused=true and background_processing_enabled=false.

The public API passed fresh-account registration through the Firestore limiter;
the resulting counter was independently read back from Firestore. Binary upload,
direct Firebase preview/download, private/no-store headers, 206 ranges, signature
tampering rejection, anonymous/cross-account link denial and fixture cleanup pass.
A provider-job admission returned AI_SERVICE_PAUSED and no job was queued; no AI
generation call was made. Published client assets contain the new service notice
and no old test-version labels; rendered local-browser checks also verified that
the labels are absent. This does not claim remote-browser automation passed.

Public account/job/credit/project metadata remains temporary SQL. The UI's Settings
export warning remains accurate; removing test branding is not a claim of complete
production durability or deployed cloud compute. No additional Render service or
paid Render plan was created.
