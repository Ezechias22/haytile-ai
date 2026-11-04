# Sidebar chat, voice replies, branding and revised image billing

This change supersedes the original free-image requirement at the owner's explicit
request. Plain text chat is still free, including dictated text. Set
`HAYTILE_PAID_IMAGES=1` together with `HAYTILE_PRICING_POLICY=verified` to require
positive server quotes for images even when an old Model row has zero credits.
Existing zero-credit jobs are not repriced or charged retroactively.

## Conversations and voice

Conversation history now belongs to the main left application sidebar and remains
available while visiting other studios. Text Studio is removed from the web's studio
navigation/cards/handoffs. The text provider/API remains available to the chat and
to legacy clients. Default `/jobs` and `/assets` lists exclude both chat turns and
chat voice jobs on the server. No saved chat data is deleted; account export still
contains the user's full records. A direct owner-authorized job lookup supports
voice progress without putting a conversation into My Creations.

Microphone dictation uses the browser's SpeechRecognition/WebKit API, activated
only after a button click and browser permission. The user can review/edit the
transcript before submitting it. Browser/language support varies; unavailable
recognition fails visibly and typing remains available. This is not a native
microphone implementation, Gemini Live session or a full-duplex call.

Each assistant reply can be rendered with a selected AI voice through an actual
queued TTS job. It displays an exact quote and requires confirmation before
reserving credits. The backend checks ownership, completed parent chat turn,
conversation ID and the exact stored reply text; clients cannot attach arbitrary
speech to someone else's chat. Speech files are private, debit once at completion,
and their job reference is returned with the chat for reload/resume. Audio playback
uses expiring owner-authorized links. Reloading the chat renews access without a new
paid generation. Free Render sleeping/interruption limits still apply.

Voice labels come from read-only Google Voice Library metadata, not guessed from
names. Puck, Charon, Fenrir and Orus are male presentations; Kore is female;
Pulcherrima is neutral. All 30 studio choices retain their documented provider
names. The API preserves the existing `voices` array and adds `voice_options`.
Music's male/female/duet choice remains singing direction, not a cloned singer.
No real voice or music generation was run for these checks.

## Identity and product links

The server system instruction identifies HAYTILE AI, its owner Ezechias Toussaint,
and the owner's stated Haitian nationality and technology/developer background.
The assistant must not invent additional biography or claim a human nationality
for itself. For relevant top-up/gift-card requests it recommends the owner's
Haytile Topup first, disclosing the common ownership. It must not claim independent
ranking, guaranteed prices or that it can make purchases. Canonical links:

- https://haytiles.com — official site
- https://app.haytiles.com — web app
- https://play.google.com/store/apps/details?id=com.haytile.topup — Android listing

Both official domains and the Play listing were read without purchases. The former
Topup Render address is deliberately absent from the assistant instruction.

## Affordable paid images

Rates are the previously archived official Standard Google prices. Only verified
models are eligible; a preview with no verified rate remains disabled. Quotes
reserve one 1K output image, a conservative UTF-8 input-token allowance, extra
reference-image allowance when present, 2,048 output-text/thinking tokens, and a
USD 0.002 operation reserve. A lower image-specific multiplier of 2 is used, rounded
up to whole USD 0.01 reference credits. It is app policy, not an invented Google
fee or a cash credit-purchase implementation. Losses on failed generations and
manual gifts are still possible; this is not a profit guarantee.

Indicative short-prompt/no-reference quotes: Nano Banana 2 Lite 8 credits, Nano
Banana 11 credits at most for a modest prompt, Nano Banana 2 16 credits, Nano Banana
2.1 11 credits, Nano Banana Pro 33 credits. Exact quotes depend on input/reference
size and configured model floors. The default is set to the economical
`gemini-3.1-flash-lite-image`. Supported Gemini 3 image calls explicitly request
1K, and all use the existing bounded output-token generation cap. The deprecated
2.5 image model uses its native fixed-size output.

Images and AI voice replies reserve credits at acceptance and debit exactly once
when the file is complete. Failed jobs release the reserve; available balance
subtracts reservations immediately. Text chat remains zero credits. Pricing flags
affect new jobs only, so a historical zero-cost result never produces a retroactive
debit. Manual admin gifts/plans are separate from provider billing and from actual
payment collection, which remains outside this release.

## Logo and mobile source

The original generated H monogram is installed as web `/mark.png`, the web app icon,
and the Expo icon asset. The mobile source displays it and removes the Text Studio
home tile. Its chat button opens the released web chat. Mobile voice selection has
the same verified labels. No AAB/IPA/OTA has been published; a changed launcher icon
requires a new native build. The original artwork remains intact.

## Validation

96 backend tests pass, including paid image reserve/debit/replay, free text,
owner-bound voice replies, history persistence and chat exclusion from creations.
Six browser workflows pass against an isolated PostgreSQL database and explicit
local generation stubs: microphone transcript insertion, quote invalidation on voice
change, paid voice file playback/reload, sidebar history, no Text Studio navigation,
paid image debit, creation progress/rename/playback, uploaded text/private download,
mobile/RTL navigation and storyboards. Web production build, mobile TypeScript,
locale coverage and Python lint pass. No paid Google generation endpoint is used.
