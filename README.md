# German Sentences → Anki

Build a low-friction workflow that turns pasted German class material into reviewed Anki sentence cards. The [approved brief](brief-german-sentences-anki.md) records scope; the [implementation plan](implementation-plan.md) is the authoritative TODO; [pilot inputs](pilot-inputs.md) preserve examples and confirmation status. Source: user conversation, 22 September 2026.

## Current state

The brief and implementation plan reflect the user's decision on 22 September 2026: use automated ElevenLabs v3 TTS, with inexpensive paid usage acceptable. Only the confirmed German sentence becomes audio; English meanings, grammar, and vocabulary explanations remain text. Each card keeps its randomly selected German voice and generated MP3 across reviews.

No automation, Anki decks, note type, credentials, or vocabulary database have been created. Anki desktop is the creation/review workstation; AnkiMobile on iOS is the study device. The user approves cards in a staging deck before they reach a study deck. Only approved base-form vocabulary enters the separate encountered-word ledger.

## Next action

Start implementation with [plan step 0](implementation-plan.md): back up the existing Anki collection with media, verify Anki-Connect locally, and prove one disposable audio card syncs to iOS. Then build the card contract and draft generation, followed by the ElevenLabs v3 adapter and a German voice audition. Configure the API key outside project notes.

## Later TODO

- Add a Telegram-bot input once the paste → stage → approve → study path works.
- Revisit a dedicated vocabulary deck or search portal only if Anki Browser search plus the indexed ledger proves insufficient.

Open question: the exact German text for the remaining incomplete pilot fragments, if they should become study cards.
