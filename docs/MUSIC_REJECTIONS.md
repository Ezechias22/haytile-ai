# Music provider rejections

A non-explicit song may still be rejected by the music provider. Haytile has no
sensitive-word blacklist for awareness songs. A provider `Input blocked` message
is not evidence identifying a particular lyric, person, policy category, or
billing outcome. Do not tell users a specific word caused a rejection unless
the provider actually identifies it. Never silently rewrite their lyrics,
retry through another paid model, or promise that a prompt adjustment will work.

The live creation card displays the localized provider-content/request/quota
reason and expandable error code plus the bounded provider message already
saved by the worker. Previously this card showed only a generic failure and
always offered Retry, even when the API's job metadata said `retry_mode=blocked`.
The detailed studio history already displayed the message.

Both views now hide Retry on blocked refusals. The retry endpoint also rejects
`PROVIDER_CONTENT_REJECTED` and `PROVIDER_REFUSED_OR_EMPTY` before any reservation,
attempt increment or queue wake, including when `new_request:true` is passed.
The existing job remains unchanged; this does not add a word filter to new
requests or disable provider moderation. A new user-submitted request still
uses normal quotes and explicit credit confirmation.

Offline verification checks that failure releases the app reservation, blocked
retry does not reserve/debit/call the provider again, unrelated chat recovery
continues to work, and the UI displays the original message. A normal music
creation workflow is also tested. No production generation is used for testing.
App credit release does not establish a Google API refund; billing is separate.
