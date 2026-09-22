# German Sentences → Anki

Build a low-friction workflow that turns pasted German class material into reviewed Anki sentence cards. The [development brief](brief-german-sentences-anki.md) is the decision record; [pilot inputs](pilot-inputs.md) preserve the examples and their current confirmation status. Source: user conversation, 22 September 2026.

## Current state

The brief is drafted; no automation, Anki decks, note type, credentials, or vocabulary database have been created. Anki desktop is the intended creation/review workstation; AnkiMobile on iOS is the study device. The user approves cards in a staging deck before they reach a study deck. Only approved base-form vocabulary enters the separate encountered-word ledger.

## Next action

Review the brief's assumptions—especially how incomplete fragments are held—and then write the smallest implementation spec for a five-input pilot. Verify Anki-Connect availability and audition German voices before choosing or paying for a TTS provider. Do not ask for or store Anki or TTS passwords here.

## Later TODO

- Add a Telegram-bot input once the paste → stage → approve → study path works.
- Revisit a dedicated vocabulary deck or search portal only if Anki Browser search plus the indexed ledger proves insufficient.

Open question: the exact German text for the remaining incomplete pilot fragments, if they should become study cards.
