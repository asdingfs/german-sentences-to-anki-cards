# Local setup and daily use

Requires Python 3.11+ (no runtime packages to install), Anki desktop with Anki-Connect, Codex signed in through ChatGPT, and an ElevenLabs API key. Run commands from this project folder.

## Anki-Connect on this Mac

Primary reference: [AnkiConnect upstream documentation](https://git.sr.ht/~foosoft/anki-connect). It covers installation, configuration, supported actions, and the macOS App Nap note used by this project.

Install add-on **2055492159**, then restart Anki. In **Tools → Add-ons → AnkiConnect → Config**, use [ankiconnect.json](ankiconnect.json):

```json
{
  "apiKey": null,
  "apiLogPath": null,
  "webBindAddress": "127.0.0.1",
  "webBindPort": 8765,
  "webCorsOriginList": ["http://localhost"],
  "ignoreOriginList": []
}
```

These match the installed add-on's defaults verified on 22 September 2026. The Python app connects directly to this Mac, so extra browser origins are unnecessary. Keep the loopback address; do not change it to `0.0.0.0` or add `*` to the origins. `apiKey: null` is the add-on's local default. If you already configured an Anki-Connect key, preserve it and set the same value in `ANKI_CONNECT_KEY` locally; do not replace it with this template. `apiLogPath: null` avoids a separate request log.

The add-on's macOS instructions recommend preventing App Nap from suspending Anki in the background. Run these as **three separate Terminal commands**, then completely quit and reopen Anki:

```sh
defaults write net.ankiweb.dtop NSAppSleepDisabled -bool true
defaults write net.ichi2.anki NSAppSleepDisabled -bool true
defaults write org.qt-project.Qt.QtWebEngineCore NSAppSleepDisabled -bool true
```

These affect background application sleep, not authentication. They are documented here; the workflow does not silently change macOS preferences. Source: [Anki-Connect upstream instructions](https://git.sr.ht/~foosoft/anki-connect), also present in the [GitHub mirror](https://github.com/ankicommunity/anki-desktop-addon-connect#notes-for-macos-users). The JSON keys were additionally checked against the installed add-on's `config.json` and `web.py`.

Keep Anki open. A read-only connection check is:

```sh
curl --silent --show-error --max-time 4 \
  -H 'Content-Type: application/json' \
  -d '{"action":"version","version":6}' \
  http://127.0.0.1:8765
```

Expect `{"result":6,"error":null}`. If a sandboxed assistant cannot connect but Terminal can, the assistant needs permission to reach the local service; this is not a reason to expose Anki to the network.

## Account and local settings

```sh
python3 -m german_anki init
codex login status
```

The first command creates ignored `config.local.json`. Codex should report **Logged in using ChatGPT**. If necessary, use `codex login` and the normal ChatGPT login flow. Draft generation uses that subscription's limits. It does not require an OpenAI API key or turn the ChatGPT subscription into API credit. The generator uses documented `codex exec --output-schema` in a temporary directory with read-only permissions and user integrations disabled. [Official automation docs](https://learn.chatgpt.com/docs/non-interactive-mode); [authentication](https://learn.chatgpt.com/docs/auth).

In ElevenLabs, create a restricted key with TTS and voice-list access and, if available, a key-level credit limit. Do not paste the key into chat or put it in any project file. On this Mac, store it in your login Keychain with this command (the key is entered at the hidden prompt, not as a command argument):

```sh
security add-generic-password -a german-anki -s german-anki-elevenlabs -U -w
```

Press Return after entering the key. The workflow reads that one Keychain item automatically; `doctor` reports only whether a key is present, never its value. macOS may ask you to allow the local `security` utility to read the item. If you prefer a session-only secret, `ELEVENLABS_API_KEY` is supported, but avoid typing the key as a shell command or saving it in shell startup files. If the key is ever exposed, revoke it in ElevenLabs and replace it.

```sh
python3 -m german_anki voices
python3 -m german_anki doctor
```

Audition suitable German voices in ElevenLabs and put their IDs in `voice_ids` in `config.local.json`. The list command shows the first 100 account voices and whether further pages exist; use the ElevenLabs UI to find additional IDs. The default model is `eleven_v3`, MP3 is 44.1 kHz/128 kbps, and only German sentence text goes to TTS. The default local limit is 30,000 characters per UTC calendar month, roughly US$3 at the documented base rate; this is a configurable application default, not a promise about the provider's invoice. Account allowances, taxes, voice multipliers, and subscription fees differ. Failed or ambiguous requests retain their character reservation to avoid undercounting retries.

## First Anki setup

In Anki, export the **whole collection** as `.colpkg` with **Include media** enabled. Then initialize against the exact active profile:

```sh
python3 -m german_anki init-anki --backup '/absolute/path/collection.colpkg' --profile 'German'
```

This verifies the archive, creates `German Sentences v1`, `German Sentences::Staging`, `German Sentences::Study`, and a separate `German Vocabulary Ledger v1` note type in the `German Vocabulary Ledger` deck. Re-run this same command once if you set up an earlier version without the vocabulary note type; existing cards are preserved. Existing note types with different fields are rejected rather than overwritten. The sentence front has German text and audio; its back has English, grammar, and vocabulary, without audio. Audio autoplay must also be enabled in Anki/AnkiMobile's deck options.

## Daily workflow

```sh
python3 -m german_anki run
```

Paste one sentence per line and finish with an empty line. Or copy sentences and use `run --clipboard`; `--text '…'` handles one sentence and `--file sentences.txt` handles a batch. Codex generates drafts, ElevenLabs generates German audio, and Anki receives suspended staging cards. Repeated source text reuses its draft and audio. Held fragments can be staged without audio for inspection, but cannot be approved.

```sh
python3 -m german_anki review
```

In Anki Browse, inspect each Staging note's German front, English meaning, grammar, and vocabulary. Vocabulary is one line per word in the format **base form | meaning | details**; delete the complete line to omit it from approval, or edit its meaning/details. Keep the separators when editing. Include useful articles, plural or inflected forms, and case explanations in details. Do not edit WorkflowId or Source. The BaseForms field refreshes on approval. If the German front is incomplete or corrected, use the confirmation sequence below before approval. Listen to the attached German audio and check that it matches the exact front.

On rendered cards, every grammar point is a separate spaced block. Every vocabulary word has its term and meaning on one line and its explanation on a new line. This formatting is applied automatically to future cards. To reconcile older workflow cards after a formatting update, run `python3 -m german_anki format-cards`; it changes only the owned note type's template/CSS and the Grammar/Vocabulary fields, without moving or approving cards.

Select the reviewed notes in Browse, then:

```sh
python3 -m german_anki approve --selected
python3 -m german_anki sync
```

Approval reads the current Anki fields, checks matching German/audio, moves each sentence card to Study, unsuspends it, and records its selected base forms in SQLite. Each approved base form also becomes one searchable `German Vocabulary Ledger v1` note in its own deck. Vocabulary cards are always suspended, so they do not enter sentence review or vocabulary review. Repeated encounters update the same word note with more source sentences and case/variation details. Use `python3 -m german_anki review-vocabulary` or Anki Browse search `deck:"German Vocabulary Ledger"` to find them. If a vocabulary sync was interrupted, run `python3 -m german_anki sync-ledger` to reconcile it. Do not manually unsuspend or move ledger cards; reconciliation puts them back. `Encountered` means approved on a sentence card, not mastered; there is no learned-state flag yet. Open AnkiMobile and sync, including media. Anki's built-in Change Deck alone does not update the ledger: use `approve --id ID` afterward to reconcile an explicitly reviewed card. If interrupted after a deck move, rerun approval; note and ledger IDs prevent duplication. Later removal of vocabulary never erases an encounter.

For a correction or fragment:

```sh
python3 -m german_anki list
python3 -m german_anki confirm ID --german 'The exact German front goes here'
python3 -m german_anki audio --id ID
python3 -m german_anki stage --id ID
```

Use the real German, not that placeholder. IDs accept unique prefixes. Confirming a study card returns it to suspended staging for review; historical vocabulary remains. English-only edits do not need fresh audio. Editing German in Anki requires confirmation and fresh audio before approval.

For the two new held examples, `1f195` contains two alternative questions. Choose **one** exact front before confirming it; for example, if you mean “How do you say bottle in Indonesian?”, use:

```sh
python3 -m german_anki confirm 1f195 --german 'Was heißt „Flasche“ auf Indonesisch?'
```

If you instead want a question about the German word's meaning, choose that wording in the German field and confirm it. After choosing, remove any vocabulary line that no longer appears in the selected front (such as `bedeuten` if you choose the first question). The second draft proposes the accusative correction `für den Unterricht`:

```sh
python3 -m german_anki confirm 9cb8c --german 'Danke schön für den Unterricht, Herr Dandi! Bis nächsten Dienstag!'
```

Only run either confirmation once you accept the exact text. Then, for each confirmed ID, run `audio --id ID`, `stage --id ID`, inspect/listen in Anki Browse, and finally `approve --id ID`. Approval refuses missing or stale audio. To approve multiple reviewed notes, select **only** those notes in Browse and use `approve --selected`; it is not a blanket approval of the Staging deck.

## Conversation drafts, previews, and export

You can also send class sentences here and have this assistant produce schema-valid drafts, then import them. `schema` and `prompt` print the contract. This avoids needing to invoke Codex CLI for every batch.

```sh
python3 -m german_anki import-drafts examples/pilot-drafts.json
python3 -m german_anki preview
python3 -m german_anki vocabulary Welt
python3 -m german_anki usage
python3 -m german_anki export .runtime/export-batch-1
```

The five pilot drafts are assistant-written review material, not five approved cards. Only the user's complete Brief sentence is confirmed; the other four remain held. Two additional inputs are also staged as held correction proposals. The HTML preview does not approve cards. Export creates `cards.txt`, media, and note-type instructions for manual import if Anki-Connect is unavailable; it does not fabricate approval or vocabulary encounters.

Local runtime state lives in ignored `.runtime/`: drafts and vocabulary in SQLite, fixed MP3s, previews, and backups. Preserve this folder alongside Anki backups; AnkiWeb sync does not sync the SQLite ledger. Do not commit credentials, class batches, or collection backups.

## Development verification

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q german_anki
```

Tests use temporary databases and simulated providers. Live TTS quality, desktop playback, and iOS sync require the real accounts/devices and are tracked separately in the implementation plan.
