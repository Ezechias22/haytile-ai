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
Replies now render Markdown, lists, tables and code with react-markdown/remark-gfm;
raw HTML remains disabled. Inline citation chips open a keyboard-accessible source
dialog (side panel on desktop, bottom sheet on mobile). The compact source summary
opens numbered cards with domains and links, plus actual provider search queries
when supplied. Copy/download include the source URLs. Google search suggestions
remain visible alongside the answer in their sandbox. Plain replies do not get
empty source panels. Failed or absent grounding must not be described as verified research.
No automatic second paid generation or silent provider fallback is added.

## Remembered location

For a location-related question without a saved choice, the model emits the
reserved `[HAYTILE_REQUEST_LOCATION]` marker with an explanation. The server
replaces the marker with a consent button. The consent text now explicitly covers
remembering the choice and using location in later chats. Earlier one-message
consent is not silently migrated into continuing sharing.

`GET/PATCH/DELETE /v1/chat/location` stores a private internal Project document
per authenticated account: enabled/disabled choice, latest device-reported fix,
accuracy in meters, capture time and consent version. This survives redeployment
through the existing canonical Firestore records. Internal preferences are hidden
from storyboard APIs. Permission denial and explicit Stop retain a disabled choice
and clear the latest fix, so the assistant does not repeatedly request permission.
Account deletion removes the preference; existing chat messages remain governed
by their normal deletion paths.

After authorization, the browser requests high-accuracy geolocation. While the
chat is visible and browser permission remains granted, a foreground watch updates
the current fix. Server publication is throttled to once per 30 seconds, without
AI calls. Hiding the page, leaving the chat or signing out clears the watch.
Browser permission revocation disables sharing. A compact control shows active,
last-known or unavailable status with reported accuracy and allows refresh/Stop.
Enabling GPS alone does not grant browser permission; other browsers/devices may
still require their own native permission. There is no background location access.

Coordinates are no longer artificially rounded to three decimal places. The
provider receives device coordinates (six decimal places), measured accuracy and
capture time, and is instructed never to promise exact/current location when the
fix is uncertain or stale. The latest saved position can be reused without asking
again while enabled. A timestamped last-known fix is not proof of current location.
The visible page's own fix takes priority when a message is sent.

Updates require a matching consent version. Delayed updates and queued messages
with a revoked version cannot restore sharing or forward the revoked fix. Re-enable
requires an explicit authorization action. Location is kept in private account
metadata and, for directly shared turns, private chat parameters; search/provider
processing may use it while sharing is enabled. Stop clears the saved latest fix
but does not rewrite earlier conversation messages or recall in-flight provider
requests. Nearby search results are not guaranteed complete, current or nearest.
Immediate danger should be directed to local emergency services without waiting.

The native spoken Live API call remains on its existing audio path; it does not
gain these text-chat research tools. Its policy suppresses control markers in
spoken responses and asks verbally for city/address if needed.

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
