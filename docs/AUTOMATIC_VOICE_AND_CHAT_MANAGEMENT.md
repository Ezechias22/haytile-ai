# Automatic voice and chat management

Web release `composer-voice-v4` places voice conversation beside the microphone
and send buttons in the message composer. One click starts speaking, with no
budget form or approval dialog. Voice/model preferences are in a collapsible menu
under the composer; a persistent notice explains that voice uses credits.
Select a text model, a TTS model and a reply voice, then speak. Speech recognition submits a text
turn; the selected text model answers; the selected TTS model speaks the reply and
the microphone resumes after playback. This is not full-duplex native model audio.
Text chat remains free in Haytile credits; voice output and images are paid.

A server-owned Firestore session expires after 30 minutes and limits each spoken
reply to 1,000 characters. For one-click start its internal spending ceiling uses
the currently available wallet balance (at most 5,000 credits); users are never
asked to enter a budget. The server still rejects insufficient funds and validates
the current model rate. Existing explicit-cap API clients remain supported. Each audio job reserves its quoted credits and session
budget atomically. Completion debits once; failure releases the reservation and
restores the budget once. The cap is not an upfront debit. Model, voice and
conversation cannot be changed within an active session. Stopping prevents new
turns; already accepted generation may finish. Browser speech recognition,
language support and autoplay vary; playback controls remain available.

The sidebar has separate Chats and Studios panes, desktop/mobile collapse controls,
and confirmed conversation deletion. Active generation blocks deletion. Owned
messages and media metadata are deleted in bounded transactions; a durable private
cleanup outbox retries object deletion after failures or loss of the SQL cache.
Financial ledger records remain for accounting. Internal budget and cleanup
projects cannot be edited through ordinary project endpoints.

Haytile Topup is suggested only for relevant mobile recharge, gift-card, game-credit
or connectivity shopping requests, with common ownership disclosed. Its official
links are haytiles.com, app.haytiles.com and its verified Android listing. They are
never advertised as AI studio URLs. Product categories come from the public catalog;
stock, regional availability and current prices are not invented.

Validation uses offline providers, simulated browser microphone input and local
playable audio. No Google generation is invoked. A disposable real Firestore probe
also verified budget concurrency, restoration after complete SQL cache loss,
failure refunds and durable cleanup restoration, then removed its own fixtures.
Native mobile voice, store builds and payment collection are not published here.

## Verified web deployment

Source `3ceca5b4e77e3b38ef0169d38aa10537796d7990` is live on the existing
free Render service, deploy `dep-dblg86egekts738b1r90`. Public runtime release
and source fingerprint match. Public navigation controls, logo and 30 voice
options verified; private chat routes reject anonymous access. Authenticated
read/quote checks retained the owner's wallet balance and reservations unchanged.
Text/image/default voice quotes: 0/8/26 Haytile credits. No paid generation.
102 backend tests, 7 offline browser workflows, web build, mobile TypeScript and
4 locale checks passed. Speech recognition inputs and AI outputs were local
fixtures; real-provider audio quality has not been tested with the user's credits.

## Composer placement follow-up

Source `568c347de80c3956e37ea35ef81a71075485c42c`, free Render deploy
`dep-dblggn59el5s73cvvfb0`, is publicly verified as `composer-voice-v4`.
Five focused backend voice tests and six offline browser workflows passed, along
with the web production build and locale/configuration checks. The browser test
starts voice from inside the composer, checks that no budget input or approval
group exists, plays two selected-voice replies, stops, and deletes the conversation.
No Google generation was used.
