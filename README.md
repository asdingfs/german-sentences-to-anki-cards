# German Sentences → Anki

Turn German class material into reviewed Anki sentence cards. See the [setup and usage guide](setup/README.md), [local-workflow brief](brief-german-sentences-anki.md), [remote Telegram workflow brief](brief-telegram-anki-remote-workflow.md), [remote architecture research](research/remote-telegram-anki-architecture.md), [portal-triggered Mac pull design](architecture/portal-triggered-mac-pull.md), [implementation TODO](implementation-plan.md), [changelog](CHANGELOG.md), and [pilot inputs](pilot-inputs.md). Updated 23 September 2026.

Anki integration uses [AnkiConnect’s upstream documentation](https://git.sr.ht/~foosoft/anki-connect) as the primary reference.

## Current state

The Python app is implemented with ChatGPT-authenticated Codex draft generation, a German-only ElevenLabs v3 adapter, audio caching, Anki staging/approval, an indexed SQLite vocabulary ledger, and a separate suspended Anki vocabulary note type/deck for searching approved base forms. No separate OpenAI API key is required. English meanings, grammar, and word explanations stay text-only; grammar points and vocabulary entries render as separate spaced blocks, and each sentence card retains its selected German voice and MP3.

Verified: automated tests; real Codex generation; Anki-Connect v6 on profile `German`; backup export including media; creation of both note types and three decks; seven suspended staging cards (five pilots plus two new held inputs); duplicate-safe staging. Study and the vocabulary ledger remain empty pending user approval. The incomplete and corrected inputs remain held.

Pending: ElevenLabs key and auditioned voice IDs, a live v3 audio request, actual front playback on desktop/iOS, and user review/approval. Paid TTS has not run. App Nap commands and the matching Anki-Connect JSON are in the setup guide; no macOS preferences were changed.

## Next action

Store the ElevenLabs API key in macOS Keychain and add auditioned `voice_ids` to ignored `config.local.json` using the [guide](setup/README.md). Generate audio for the confirmed first sentence, review it in Anki, then verify sync and playback on iOS.

```sh
python3 -m german_anki doctor
python3 -m german_anki audio --id 4ffe
python3 -m german_anki stage --id 4ffe
python3 -m german_anki review
```

For subsequent batches, `python3 -m german_anki run` prompts for pasted sentences. Preserve ignored `.runtime/`, which contains the local database and audio cache.

## Later TODO

- Add a Telegram-bot input once the paste → stage → approve → study path works.
- Revisit a search portal only if Anki Browser search plus the indexed ledger proves insufficient.

Open question: the exact German text for the remaining incomplete pilot fragments, if they should become study cards.
