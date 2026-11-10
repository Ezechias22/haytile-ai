# Interrupted replies, recovery and provider rejections

An interrupted request is not proof that Google did no work. Provider billing
and Haytile wallet refunds are separate. Paid media with an unknown outcome and
no usable operation/checkpoint remains blocked for reconciliation. This release
does not bypass video incident holds or silently resubmit old jobs.

For text generation, the worker now saves a bounded provider-response checkpoint
before parsing, then a plain-text checkpoint before file validation/upload.
Grounding and location-request metadata are collected and committed with that
answer rather than through separate mid-parser writes. Saved replies can resume
local parsing/storage/publishing without another generation request. Checkpoints
are excluded from API job JSON and removed after successful publication. Remote
commit uncertainty still fails closed; the worker does not blindly resubmit.

Optional null grounding fields and null prompt-feedback objects no longer crash
valid text replies. Tests reproduce those response shapes. This is a verified
parser defect prevention, not a claim that it caused every historical failure:
the old generic error did not preserve its underlying cause.

Legacy interrupted zero-credit text without a response checkpoint exposes
`retry_mode: new_request`. Its button is **Send a new request**, accompanied by
an explanation that the old reply could not be recovered. The endpoint requires
an explicit `{new_request:true}` flag before another generation. Empty provider
responses similarly require an explicit restart and discard the unusable cache.
Ordinary recovery uses saved bytes; it does not post to Google again. There is
no automatic retry or extra budget popup. Text remains zero Haytile credits;
a new provider request may still cost the operator money, even if the original
request was also billed. Existing attempt and admission safeguards remain.

Failures now retain an execution phase, original fixed error code, exception
class, and bounded provider status/message when supplied. API-key-looking values
and the configured key are redacted. Owner-only history shows these details.
HTTP 400 is described as a rejected request (parameters, format or content),
not automatically as moderation. Explicit provider safety decisions are reported
as such. Historical error bodies that were never retained cannot be reconstructed.

Music prompts explicitly preserve the user's lyrics and recognize the difference
between non-graphic awareness/prevention and harmful advocacy. No sensitive-word
blacklist is introduced, and lyrics are not automatically rewritten. This can
clarify legitimate context; it does not override Google's content policies or
guarantee acceptance. Explicit sexual content is not requested. No provider safety
thresholds are disabled and other provider rules still apply.

Current account discovery confirmed the same three singing choices:
`lyria-3.5`, `lyria-3-pro-preview`, `lyria-3-clip-preview` (30 seconds). The account
also lists `lyria-realtime-exp`, documented as experimental instrumental generation,
not another full-song/lyrics model. It is not activated as a singing option.
No extra singing model name or price is invented. More providers require their
own account/API credentials; only Google is configured and requested currently.

Verification uses mocked provider responses, local files, a dedicated PostgreSQL
test database and an offline browser server whose external provider transport is
forbidden. Tests cover storage and parser failure recovery with exactly one
upstream call, unknown-outcome explicit resend, empty-result restart, null metadata,
secret redaction and unchanged awareness lyrics. No real generation was used.
