# Implementation plan: German sentences → Anki

Status: first implementation built; local tests and Anki staging verified. Separate suspended vocabulary notes are implemented. Live ElevenLabs audio and desktop/iOS acceptance remain. Based on the [approved brief](brief-german-sentences-anki.md) and [pilot inputs](pilot-inputs.md). User decision, 22 September 2026: automate German audio through inexpensive ElevenLabs v3; use the existing ChatGPT/Codex plan for meanings and grammar. Updated 22 September 2026.

Implemented in [german_anki](german_anki/); commands and Anki-Connect/macOS configuration are in the [setup guide](setup/README.md). Verification: automated tests pass; live Codex requests succeeded through ChatGPT authentication; Anki-Connect v6 responds on profile `German`; seven suspended drafts exist in Staging and zero cards in Study. Repeating staging preserved the same note IDs. A separate `German Vocabulary Ledger v1` note type/deck is live; it remains empty until approval. The SQLite encountered-word ledger is also empty until approval. Live TTS has not run because its key and voice IDs are not yet configured.

## Smallest complete workflow

Paste German text → generate a structured draft → resolve uncertain German → automatically generate and attach German-sentence MP3 with ElevenLabs v3 → inspect/edit the card in an Anki staging deck → approve it into the study deck → record approved base-form vocabulary in SQLite and searchable, suspended Anki vocabulary notes → sync and review sentences on iOS. The sentence front displays and plays German; its back displays English meaning and explanations as text. Anki desktop must be running for the local [Anki-Connect API](https://github.com/ankicommunity/anki-desktop-addon-connect); AnkiWeb handles device and media sync, not note creation. No web portal, Redis, or Telegram bot in v1.

## What we need before live writes

- Anki desktop signed into the correct syncing profile. Before adding anything, make a recoverable collection export **with media**; Anki's ordinary backups omit media. [Anki backup guide](https://docs.ankiweb.net/backups).
- Anki-Connect installed and responding only on localhost. Its `createModel`, `addNote`, media, Browse-selection, and `changeDeck` actions cover the proposed integration. [Anki-Connect reference](https://github.com/ankicommunity/anki-desktop-addon-connect).
- Draft generation uses the existing ChatGPT-authenticated Codex CLI, verified in a live one-sentence test. Conversation-generated JSON can also be imported. No separate OpenAI API key; usage counts against the subscription's Codex limits. [Official non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode).
- An ElevenLabs account with v3 and the chosen German voices available, plus a restricted API key stored in a local secret store or environment outside this folder. Configure a usage limit and track spend. The user accepts inexpensive paid TTS; choose the cheapest suitable account option during setup. [Key controls](https://elevenlabs.io/docs/help-center/technical/how-do-i-authorize-myself-using-an-api-key); [API pricing](https://elevenlabs.io/pricing/api).
- At least one confirmed German front (already available). For a five-*approved*-card pilot, confirm whether phrases are acceptable card fronts or supply further complete sentences; otherwise the other fixtures exercise the “hold for correction” path.

## Automated German sentence audio: ElevenLabs v3

The TTS input is exclusively the confirmed German sentence field. Never concatenate English translations, grammar, vocabulary definitions, metadata, or generation instructions into that input. Only the resulting German MP3 is attached to the card's German-audio field. The text/grammar generation service remains separate.

1. Assign a stable card ID and randomly select one voice from a small list auditioned for natural German pronunciation. Store the voice ID with the card; retries and later reviews retain it.
2. Submit the confirmed German sentence through the official TTS endpoint using `model_id: eleven_v3` and `output_format: mp3_44100_128`. Retrieve the returned audio bytes, validate the MP3, and save a stable media filename automatically. Record the text, voice, model, and settings fingerprint plus request usage. [Model](https://elevenlabs.io/docs/overview/models); [TTS endpoint](https://elevenlabs.io/docs/api-reference/text-to-speech/convert).
3. Cache the audio by that fingerprint and reuse it on repeated imports. English/grammar/vocabulary edits do not regenerate audio. A changed German sentence invalidates the old clip and requires matching audio before study approval.
4. Attach the MP3 through Anki-Connect and play it on the front with the German text. The back contains English meaning and explanations as text only, without an additional audio field or automatic front-audio replay.
5. Estimate batch cost from German characters, record actual usage, and enforce the configured spending limit. Recover from failures without duplicate Anki notes or unnecessary new generations; retain unresolved audio jobs in staging for retry.

Cost baseline, verified 22 September 2026: v3 API pricing lists US$0.10 per 1,000 characters. At 1,000 German words/week, an illustrative six characters per word including spaces is about 26,000 characters/month, or US$2.60 in gross usage before included allowances, retries, taxes, or voice multipliers. Starter lists US$6/month with 60,000 v3 characters. [API pricing](https://elevenlabs.io/pricing/api). Prefer pay-as-you-go when the selected voices are eligible; use the lowest subscription tier needed for suitable native German voices. PAYG requires a US$5 minimum top-up and retains the underlying plan's voice restrictions. [PAYG details](https://elevenlabs.io/docs/overview/administration/pay-as-you-go). These are planning estimates, not a purchased plan or a user-specified budget ceiling.

## Ordered TODO and completion checks

### 0. Safety and connection spike

- [x] Verify the whole-collection export with Include media enabled before writes: `/Users/asdingfs/Documents/collection-2026-09-22@22-11-37.colpkg`; ZIP integrity passed.
- [x] Confirm active profile `German`, Anki-Connect v6, and loopback-only defaults. Record matching JSON and App Nap instructions in the setup guide.
- [x] Create the workflow's note types/decks and stage seven suspended notes (five pilots and two new inputs); repeat staging without duplicates. Existing cards remain untouched.
- [ ] Verify media-sync settings and desktop→iOS audio on the first confirmed pilot card. No disposable note was deleted.

Done when local note creation and mobile audio are proven, and the backup is available.

### 1. Card contract and fixtures

- [x] Create `German Sentences v1`, `German Sentences::Staging`, and `German Sentences::Study`. Separate fields hold German text/audio, English, grammar, vocabulary, searchable base forms, source, voice ID, workflow ID, and status. Also create `German Vocabulary Ledger v1` in its own deck, with suspended notes for approved base forms only.
- [x] Implement front/back templates and HTML preview. Verify through the live Anki API that the front references GermanAudio and the back contains no audio/FrontSide field.
- [ ] Check actual rendering and playback in desktop Anki and iOS with generated media.
- [x] Add all five [pilot inputs](pilot-inputs.md) as validated JSON fixtures with source text, explicit holds, and grammar explanations.

Done when the schema and one sample card are approved visually in desktop Anki.

### 2. Draft generation

- [x] Build paste, clipboard, and file batch input through the ChatGPT-authenticated Codex CLI with a strict JSON schema; also support conversation-generated draft imports. Live generation verified.
- [x] Preserve source separately from proposed German. Require explicit confirmation for corrections, warnings, and fragments before audio or promotion.
- [x] Test the *aus + dative* fixture, irrelevant-word removal, malformed output, changed/missing source inputs, and repeated imports. Keep the Codex model configurable; report subscription usage as account-level limits rather than inventing API charges.

Done when all five inputs produce inspectable drafts or explicit hold reasons, without invented completions.

### 3. Fixed German audio

- [ ] Configure the ElevenLabs account, restricted API key, and usage limit; audition several accessible German voices with v3 on the same confirmed sentence. Record voice IDs, pronunciation notes, and measured cost.
- [x] Build the v3 adapter: German-only payload, one stored voice per card, automatic MP3 retrieval/validation, caching, and Anki media attachment. Live TTS remains unverified.
- [x] Test that English/explanations never enter the TTS payload, unchanged German reuses audio, English edits make no new TTS call, and changed German requires confirmation/new audio.
- [x] Keep failed/stale audio in staging. Track character reservations and estimated cost, and test the monthly limit plus failed/ambiguous requests. The default configurable limit is 30,000 characters per UTC month.

Done when desktop and iOS play the same correct German sentence on the front, the back remains text only, and repeated imports do not create new TTS charges.

### 4. Staging, approval, and vocabulary

- [x] Implement and live-test duplicate-safe suspended staging, preserved Anki edits, and stored note IDs. Provide text-plus-media export with import instructions.
- [x] Implement `approve --selected`/`--id`: read current Anki edits, validate matching audio, move to Study, unsuspend, and record vocabulary. Explicit approval also reconciles a manually moved card; there is no background Change Deck watcher.
- [x] Create indexed SQLite base-form and encounter tables; test insertion only upon approval, case/variation search, duplicate prevention, and retained history after vocabulary removal.
- [x] Mirror approved base forms into one suspended Anki vocabulary note per lemma. Repeated encounters update it; `sync-ledger` reconciles interrupted writes. These cards do not enter sentence review.
- [x] Test recovery after successful Anki writes with lost responses and after a deck move followed by a failed ledger write. Retrying approval does not duplicate encounters.

Done when one approved card lands in Study with correct vocabulary, and rerunning approval changes nothing.

### 5. Five-input end-to-end pilot

- [x] Import all five fixtures and stage them in the live Anki profile. Only the complete first input is confirmed. Two new user inputs were generated and staged as held corrections; their explanations were refined in Anki.
- [ ] User reviews/corrects drafts, approves confirmed cards with audio, and verifies Anki search for base forms and case explanations.
- [x] Test duplicate prevention, missing/altered audio, failed calls, edited German, partial approval, vocabulary-note suspension, and reruns. Automated tests pass.
- [ ] Sync Anki desktop and iOS; confirm front playback, readable back, no English audio, and no unexpected cards in the study deck.
- [ ] Review actual effort and TTS/model spend with the user, then close or revise the first-version acceptance criteria.

Done when the user approves the pilot and can repeat the workflow without developer intervention.

## Deferred TODO

- [ ] Consider richer portal editing only after portal-triggered import and approval are reliable; editing remains in Anki for this phase.

### 6. Telegram capture and portal-triggered Mac pull

Status: planned and under architecture design; not yet implemented. The [remote workflow brief](brief-telegram-anki-remote-workflow.md) and [primary-source research](research/remote-telegram-anki-architecture.md) are complete.

- [x] Establish that no supported public AnkiWeb note-creation interface exists and that AnkiConnect requires Anki Desktop.
- [x] Decide against background server push or automatic Mac polling. The always-on server owns Telegram intake, enrichment, audio, and the durable queue; the user periodically initiates import from its portal on the Mac.
- [ ] Approve the proposed [portal-triggered Mac pull architecture](architecture/portal-triggered-mac-pull.md): one deep `ReadyQueueImporter` interface, a custom URL activation adapter, and a signed installed helper. The browser requests the action; the helper owns Anki launch, readiness, profile verification, import, acknowledgement, and sync.
- [ ] Define versioned queue/lease semantics using Telegram `update_id`, `WorkflowId`, revision, content/audio hashes, and retry-safe acknowledgements.
- [ ] Implement the authorized Telegram webhook, asynchronous worker, queue/status portal, and provider-neutral enrichment seam.
- [ ] Implement the Mac pull module with a production server transport adapter, in-memory test adapter, OS launcher adapter, and localhost AnkiConnect adapter.
- [ ] Pilot one user-triggered batch containing normal, corrected, duplicate, offline-Mac, and unauthorized cases; verify no wrong-profile or duplicate writes.
- [x] Record the user's revised interaction: edit cards in Anki Desktop, initiate approval from the portal; do not expose arbitrary local script execution.
- [ ] Validate the proposed two-stage interaction: **Read Anki selection** creates a local snapshot and portal preview; **Approve these N cards** commits only that saved set through the paired Mac helper. Separate Advisor consultation remains pending after automatic approval review blocked the private payload; this design is proposed, not independently reviewed.
- [ ] Add snapshot-aware checks inside the shared Python approval path, retaining German/audio validation, Study promotion, and vocabulary recovery. Never run delayed `approve --selected` as a portal commit, since the selection could have changed.
- [ ] Implement operation-bound, expiring, single-use activations; keep the AnkiConnect key local and accept no server-supplied commands, executable paths, or arbitrary AnkiConnect actions.
- [ ] Test empty/closed Browse, wrong profile, foreign notes, changed selection/content/audio, expired/replayed tickets, duplicate commits, and partial failures. Report sync separately from local approval.
- [ ] Resolve the trust choice: portal-only approval trusts the authenticated portal to authorize a narrow action; native confirmation provides an additional local check against portal compromise. An OS “open application” prompt is not card approval.

Done when the portal opens/focuses Anki and imports the exact ready queue into suspended Staging notes; the user can edit in Anki, preview a frozen selection in the portal, and approve precisely those unchanged notes with recoverable per-note results.

Next architecture action: validate the proposed activation and approval contracts in the architecture document before implementation. Local acceptance still requires configuring ElevenLabs voices, generating pilot audio, and verifying playback/sync; the remote workflow must reuse those checks.
