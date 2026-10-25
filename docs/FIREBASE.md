# Firebase storage for HAYTILE AI

Firebase is the operator's selected media-storage service (2026-10-25), replacing
the previously proposed Supabase storage option. The operator has now created the
Firebase project and web app and activated Storage and Firestore. Backend credentials
and bucket configuration are now verified on Render. Firebase Storage is deployed
and live; Firestore has not replaced the application's SQLite/PostgreSQL data layer.

## Live acceptance, 2026-10-25

Render Free deploy `dep-dbf1vdom7kps73ffnisg`, source `a187b45`, reports
`storage: firebase`. The operator confirmed that the previous ephemeral deployment
contained test data only before authorizing this cutover. No paid Render resource
was created or enabled.

Real bucket verification passed create/read/range/delete. Anonymous reads returned
HTTP 403 on **both** storage.googleapis.com (GCS IAM) and the Firebase Storage REST
download interface (client Security Rules). The operator probe now checks both;
GCS denial alone does not establish Firebase client-rule privacy.

An isolated API with the real Firebase bucket passed registration, private text
save/download, byte ranges, HEAD, anonymous and cross-account denial, process
restart with unchanged test DB and fixture cleanup. The public Render API passed
text and PNG upload/download, byte ranges/Content-Range, HEAD semantics, two-user
isolation and account/object cleanup. The public proxy path omits Accept-Ranges and
Content-Length; the local Next proxy retains them. Public 206/Content-Range and
empty-body HEAD behavior were verified directly rather than declaring these
missing headers an application success or failure without diagnosis.

Fresh real image and text generation requests failed with Google
`PROVIDER_QUOTA_EXCEEDED`, jobs `20a6e165-d822-4410-a91a-a892d99747ad` and
`e40520e9-5bcd-432b-b3fa-853b1cfaa094`. These are provider failures; they do not
invalidate successful Firebase file storage tests. No successful AI-to-Firebase
generation is claimed from this run. Private fixtures/accounts were removed.

Current runtime: temporary_storage=false, temporary_database=true. Firebase objects
are durable, but account/job/project/credit metadata remains in ephemeral SQLite;
an app restart/deploy can still lose those references. This is not full production
durability. Firestore migration and Google quota availability remain open.

## What moves off Render

Images, audio, video and saved text go into a private Cloud Storage for Firebase
bucket under `haytile/`. Backend ownership checks and five-minute signed API links
remain in force. No public object ACL, Firebase download token or service-account
credential is returned to clients. SDK reads use 256 KiB chunks; the API yields
at most 64 KiB per chunk, including byte ranges for playback.

The worker also spools scene clips to temporary files instead of accumulating an
episode's clips in RAM. Temporary working files are cleaned on success, failure
and early exits. Firebase does not add RAM/CPU to Render: one provider response and
the final assembled result still occupy memory. Long video generation, concurrency,
resource limits and load tests remain relevant. No promise of unlimited capacity
or freedom from Render interruptions is made.

Cloud Storage does **not** replace the PostgreSQL database. Accounts, jobs, credit
transactions and projects still need durable PostgreSQL. Firestore/Auth migration
would be a separate implementation; setting a bucket does not migrate them.

## Create and connect the project

1. Create/select the operator-owned project in https://console.firebase.google.com/.
2. Activate Storage and choose its region after reviewing billing/retention needs.
   Current Firebase documentation requires the Blaze plan for Cloud Storage. A
   Firebase billing account must be linked; Gemini billing alone does not establish
   this. Free allowances, quotas and region-specific charges still apply. No Firebase
   resource or paid Render plan was created by this integration work.
3. Keep the bucket private. Use bucket-level IAM for a dedicated service account
   with the object permissions needed to create/read/delete Haytile's objects
   (for example Storage Object User on that bucket, not project Owner).
4. Enter the account JSON directly as a **Render backend secret**, never chat, Git,
   frontend or mobile code. This SDK must sign OAuth assertions locally: a cloud
   HTTPS proxy placeholder is not a substitute for that private key.

Set these Render environment values:

| Name | Value |
|---|---|
| STORAGE_PROVIDER | `firebase` |
| FIREBASE_STORAGE_BUCKET | Exact bucket name from Firebase, without `gs://` |
| FIREBASE_SERVICE_ACCOUNT_JSON | Complete dedicated service-account JSON, as a secret |

The bucket can end in `.firebasestorage.app` or `.appspot.com`; copy its actual name.
The adapter requires explicit credentials and never uses the cloud machine's
inherited Google identity. Misconfiguration fails startup instead of silently
saving media to Render's temporary filesystem.

`infra/firebase/storage.rules` is a deny-client template for the backend-owned
`haytile/` namespace. Firebase Admin/GCS uses IAM and bypasses client Security Rules.
Review and merge with existing rules before deploying; do not overwrite rules for
other applications. A permissive overlapping rule can still grant access, so test
anonymous and cross-user access against the actual deployed rules/bucket.

## Migration and acceptance

After setting the backend credentials in a trusted operator environment, run from
`services/api`: `python -m haytile.firebase_storage --probe`. It writes and reads
one disposable `haytile/probes/` object, verifies range reads and anonymous denial,
then deletes it. It prints no credentials or signed URLs. This is an explicit test
with provider usage, not an automatic startup action. Do not run against an unrelated
project. A passing probe does not migrate existing records or validate Firestore.

Preserve existing SQLite records, local media and the signing key before any
redeploy. Switching an environment variable alone does not migrate old objects:
each old Asset.key must be copied to `haytile/<key>` in the new bucket and its
checksum/size verified. Database rows and account IDs must be retained. Roll back
configuration if verification fails. Do not silently replace users with an empty DB.

On a dedicated staging bucket, test create-account → save/upload/generate → private
preview → range playback → download → delete. Verify anonymous bucket/API access is
denied and another account cannot obtain links. Restart the app and verify retained
data, then exercise an isolated database/media restore. Only after these pass should
the live deployment use the Firebase backend. API health reports `storage: firebase`;
that label alone does not prove IAM or successful network writes.

## Evidence

Dependency resolution uses pinned google-cloud-storage 3.17.1 and its dependencies;
existing pins were preserved. Protocol tests cover the library write/read/range/
delete lifecycle through the real API with a fixture bucket, no local media write,
and refusal to fall back to unrelated Google credentials. Fixture tests are distinct
from the real acceptance checks recorded above.

Official sources read with HTTPS 200:

- https://firebase.google.com/docs/storage
- https://firebase.google.com/docs/storage/admin/start
- https://firebase.google.com/docs/storage/faqs-storage-changes-announced-sept-2024
