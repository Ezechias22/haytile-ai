# Native live voice and fixed chat layout

This replaces the old SpeechRecognition → text job → TTS conversation path with
native speech-to-speech. The ordinary microphone remains an explicit dictation
feature; the waveform button opens a separate live call. No browser transcription,
text generation job, TTS job, audio file, or transcript is created by live calls.

The browser captures mono audio with echo cancellation, converts it through an
AudioWorklet to 16 kHz signed little-endian PCM, and sends bounded binary frames
over an authenticated same-origin WebSocket. The backend alone holds the Gemini
key and owns the model setup. It forwards native 24 kHz PCM replies immediately.
Web Audio plays chunks as they arrive. Provider interruption messages clear the
playback queue, while the microphone remains connected. Mute, end, microphone
permission failures, backpressure and disconnects clean up capture and playback.

Only the verified `gemini-2.5-flash-native-audio-preview-12-2025` is enabled in this
first native integration. Text/TTS models cannot be assumed to support native
live conversations. Model discovery on the operator's account reported
`bidiGenerateContent`; no paid connection or generation was used to verify it.
The documented setup, PCM formats, named voices, context-window compression and
interruption protocol were checked against the official Live API reference:

- https://ai.google.dev/api/live
- https://ai.google.dev/gemini-api/docs/live
- https://aistudio.google.com/docs/live-api/capabilities
- https://ai.google.dev/gemini-api/docs/pricing#gemini-2.5-flash-native-audio

## Charging and limits

Google's published paid rates for this model are $0.50/$2 per million input/output
text tokens and $3/$12 per million input/output audio tokens. These are provider
rates, not a claim of free or unlimited voice. Haytile charges **70 credits for a
started block of up to 60 seconds**, after the first audio reply is delivered.
This is an app price, not Google's per-minute price. The internal reference is
$0.01/credit. The reserve uses a conservative worst-rate token allowance, context
and output limits, operation allowance and margin. It does not guarantee profit:
provider accounting, context reuse and in-flight usage can vary.

A block also stops at the conservative 8,000 reported-token threshold; the last
in-flight response may overshoot. Output is capped at 1,024 tokens, context
compression triggers at 2,048 tokens with a 1,024-token target, and input is bounded
to real-time audio speed. Each session is currently one block; it does not silently
renew or debit another block. The rate and maximum duration are visible before
starting. No budget dialog is shown. Silence/setup failure before any delivered
reply releases the reservation; delivered audio is charged even after an
interruption or early exit. These limits are safeguards, not universal quality or
provider-cost guarantees. Daily admission limits also apply.

Reservations, debits and releases use existing durable job/wallet transactions.
Single-use claims prevent duplicate socket sessions; the ordinary generation
worker excludes live jobs and expires abandoned reservations. Live jobs are
private and excluded from My Creations. No recording is persisted. Firestore
remains authoritative after Render redeployment or loss of the SQL projection.

## Hosting and layout

The existing FastAPI process now listens on Render's public port, terminates
WebSockets, and forwards website HTTP traffic to Next on loopback port 3000.
Next's existing API forwarding points back to the API's `/v1` endpoints. Unknown
`/v1` requests never recurse through the website. Streaming responses and private
cookies are preserved. No additional paid Render service is introduced.

Application height is bounded to the viewport. Header, sidebar branding/profile
and composer stay in place. Main page content, conversation messages and sidebar
history/tools scroll in their own bounded regions. Long-history browser checks
cover desktop/mobile and opening or collapsing the sidebar.

## Validation boundaries

Native relay tests use a deliberately local provider socket, actual browser
microphone fixtures, AudioWorklet PCM and Web Audio playback. They assert native
setup, binary microphone frames, playback interruption/mute, zero text/TTS jobs,
no transcript/audio file, credit settlement, ownership and origin checks. The
provider API is never called by these tests. A disposable real Firestore probe
verified reserve/debit/refund exactly once and restoration after complete SQL
cache loss, then removed its own fixtures. Real provider voice quality, language
quality, latency and account quota have not been tested using the user's credits.

## Keep the screen awake during web voice calls

The live voice hook holds a Screen Wake Lock during microphone setup and the
active call, including while muted. It releases the lock when setup fails, the
socket ends, the user stops, or the component unmounts. A delayed lock grant after
cleanup is immediately released. When the browser releases a lock while the page
is hidden, returning to the visible call requests it again.

This requires a secure context and browser/OS support. Unsupported devices or a
power-saving denial do not themselves terminate the voice call. A screen wake
lock prevents automatic screen sleep; it does not override the user's power
button, force background microphone access, or extend the server's session limit.

The offline native-voice browser regression exercises lock acquisition, visibility
reacquisition and delayed-grant cleanup alongside PCM audio, interruption, mute,
end and the existing credit debit. No Google generation is used for verification.
