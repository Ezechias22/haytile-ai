# Chat research, files and location consent

The text chat makes Google's documented `googleSearch` tool available to the
selected Gemini model on every turn. The model decides when current, uncertain
or local facts need research; greetings, creative requests and stable knowledge
should not trigger searches. There is no search toggle. This does not guarantee
that the model always identifies when its memory is outdated.

Grounding metadata, not model-invented links, supplies a numbered HTTPS source
list. When Google's byte-indexed grounding supports are present, claim citations
are inserted at the matching UTF-8 boundaries. Search suggestions supplied by
Google appear inside a sandboxed, script-disabled iframe with a restrictive CSP.
No HTML from a model answer is executed. Plain replies do not get empty source
panels. Failed or absent grounding must not be described as verified research.
No automatic second paid generation or silent provider fallback is added.

## Location

When location is necessary, the model emits the application's reserved
`[HAYTILE_REQUEST_LOCATION]` control marker alongside its explanation. The server
removes the marker from the answer and stores an owner-private request flag.
Only the latest completed requesting turn shows **Authorize location**. Ordinary
messages never call the Geolocation API and there is no permanent location button.
The user sees why location is needed and a disclosure before clicking; the
browser then obtains permission. Denial sends no position and offers manual city
or address input. This depends on HTTPS and browser/OS permission support.

The browser rounds coordinates to three decimal places and submits the original
question again with a distinct, explicit location-bearing chat turn. No watch or
background tracking is started. Coordinates are passed to the provider for that
turn only, retained in the user's private chat for history, and excluded from
subsequent reconstructed model context. They are removed with chat/account data
through existing deletion paths. Nearby web results are not guaranteed complete,
current or the nearest establishment. Immediate danger should be directed to
local emergency services without waiting for an AI search.

The spoken Live API call keeps its existing native-audio path; it does not gain
these text-chat tools. Its identity policy suppresses application control markers
in spoken responses and asks verbally for a city/address when necessary.

## Files

The paperclip uploads PNG, JPEG, WebP, PDF or UTF-8 text (including CSV/Markdown)
to the existing owner-private asset library. Chat accepts at most three files,
five MB per browser upload and eight MB total. PDF parsing validates structure,
rejects encrypted documents and limits each PDF to ten pages. Text uploads are
bounded to one MB. There is no silent page truncation. These are app limits to
bound provider tokens and memory on the existing hosting plan.

The server checks attachment ownership and MIME on admission and again in the
worker. Only file IDs enter durable job documents. The worker reads private bytes
and sends image/PDF inline data directly to Gemini, allowing native document
vision instead of relying solely on extracted text. Text files are decoded as
UTF-8. Prompts treat file/search contents as untrusted data. Vision/OCR quality
and exact document interpretation depend on the model and are not guaranteed.

Follow-up turns reconstruct authorized attachment references. Each unique file
is included once per provider call. An eight-MB context budget favors recent
files; unavailable or older omitted files are explicitly marked unavailable, so
the assistant must request them again rather than claim to read them. Original
uploads remain manageable in the private asset library; deleting a chat removes
its messages and generated replies, while an independently uploaded library file
can be deleted separately. Account deletion covers both.

## Cost and verification

Text chat remains zero Haytile credits. Input tokens, document/image analysis
and actual searches may cost the operator money. Google's documentation checked
on 2026-11-05 describes Gemini 3+ Search billing per executed query, a shared
5,000-query/month allowance, then $14 per 1,000 queries; this is not a promise of
remaining allowance on this account. Existing free-chat admission quotas remain.
The model can choose several queries; the app does not advertise a hard per-call
Google cost cap. No paid Google request was used for development verification.

Official references:
- https://ai.google.dev/gemini-api/docs/google-search
- https://ai.google.dev/api/generate-content
- https://ai.google.dev/gemini-api/docs/document-processing
- https://ai.google.dev/gemini-api/docs/pricing

Offline tests cover complete upload/job/worker/history paths, PDF/image payloads,
source persistence, Unicode citation offsets, cross-account denial, invalid and
encrypted PDFs, location requests, absent permission, per-turn location scope and
native voice regressions. The mobile browser workflow checks no initial location
access, denial without submission, explicit consent, rounded coordinates, private
file attachment, sources, sandbox isolation and an accessible composer.
