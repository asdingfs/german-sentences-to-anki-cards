# Brief: German class sentences to Anki

**In one line:** A paste-to-approved-Anki-card workflow for one German learner so that class material becomes accurate, searchable, audio-backed review without repetitive manual card creation.  
**Owner:** User, with Codex for implementation · **Deliverable:** Development project brief and subsequent workflow · **Due:** No fixed date; complete the first workflow before Telegram input (assumed) · **Status:** Draft v1 · **Date:** 22 September 2026

## 1. Background: why this, why now

The user wants to turn German class material into Anki cards without manually translating, explaining, voicing, and formatting each one. An existing Anki account syncs other cards, but no German deck or note type needs preserving. Five class examples are in [pilot inputs](pilot-inputs.md); the first was corrected to “Bitte lesen Sie den Brief und markieren Sie die Sätze.” Source: user conversation, 22 September 2026.

## 2. Objective

Process about 5 pasted inputs through drafting, staging, correction, approval, and study placement, recording only approved base-form vocabulary. Class-follow-up time should go to learning, not card formatting.

## 3. Audience

The user is the sole learner and approver, using Anki desktop for import and AnkiMobile for iOS review. They need to edit drafts, remove irrelevant explanations, and approve only trustworthy cards.

## 4. Core message

When I paste German class material, I need a draft I can correct and approve in Anki before it becomes a trustworthy study card with fixed German audio and useful grammar.

## 5. Deliverable and scope

The first build uses a new note type, staging and study decks, and a separate indexed encountered-vocabulary ledger. Each note produces one German-to-English card. Fields: German text/audio, English meaning, grammar, selected vocabulary, searchable base forms, and source/status. The front displays German and plays audio; the back displays English and explanations without English audio.

**In scope:** Paste/batch input; translation and targeted grammar; selectable base forms with articles, inflections, and cases; review; deck promotion; duplicate-safe ledger updates; fixed German audio; iOS playback check.  
**Out of scope:** Telegram input, voice cloning, a custom portal, learned-word status, English audio, and automatic approval.

## 6. Supporting content

- **Approval:** Edit staged notes in Anki Browse, then move approved cards with Change Deck. The deck move triggers an idempotent ledger update. [Anki Browse](https://docs.ankiweb.net/browsing.html).
- **Vocabulary:** An indexed SQLite ledger stores approved base forms, meanings, articles, relevant variants/cases, encounter dates, and source-card links; Redis is unnecessary. Later removal from a card explanation does not erase an encounter. Anki Browser searches note fields, so no vocabulary deck is needed initially. [Anki search](https://docs.ankiweb.net/searching).
- **Quality:** [LEO](https://www.leo.org/german-english/) may help check words. Explain critical new patterns, such as *aus + dative*, rather than every token. Flag fragments; never silently complete them.

## 7. Tone, style and references

Precise: distinguish the supplied German, a proposed correction, and a verified card.  
Plain: explain grammar in short English with an example of the changed form.  
Selective: prioritize new words and sentence-critical patterns over exhaustive analysis.  

References to emulate: the user's *aus der ganzen Welt* breakdown in [pilot inputs](pilot-inputs.md); it connects meaning, base form, and dative change. Avoid: unreviewed fluent-sounding translations that conceal uncertain source text.

## 8. Constraints and mandatories

Cloud translation and TTS are permitted. Use official APIs, not browser-cookie automation; keep keys out of project notes. Anki-Connect is the local writing path, with text-plus-media import as fallback; AnkiWeb credentials only handle sync. [Anki manual](https://docs.ankiweb.net/sync-server.html); [text import](https://docs.ankiweb.net/importing/text-files.html). Check front audio auto-play on desktop and iOS. [Anki audio options](https://docs.ankiweb.net/deck-options.html).

ElevenLabs is preferred for TTS: its API supports German MP3; free API use exists, but shared library voices require payment. On 22 September 2026, Starter listed US$6/month and 30,000 credits. Budget against under 1,000 TTS words weekly, including regenerations. [API](https://elevenlabs.io/docs/api-reference/text-to-speech/convert); [voice access](https://elevenlabs.io/docs/eleven-creative/voices/voice-library); [pricing](https://elevenlabs.io/pricing). TTSMaker Free/Lite lack API access, making it a manual fallback. [Pricing](https://pro.ttsmaker.com/pricing). Audition German-capable voices, randomly select once per card, and retain its clip.

## 9. Timeline

No calendar deadline was supplied. Confirm fields and voices; implement the five-input paste-to-staging pilot; verify approval, ledger, sync, and iOS playback. Telegram follows only after the user approves the completed workflow.

## 10. Success metrics

Process about 5 pilot inputs without duplicate notes or ledger entries. Every promoted card has approved German/English, useful grammar and selected vocabulary, stable playable German audio on desktop/iOS, and searchable approved base forms. Unresolved fragments stay staged.

## 11. Assumptions and open questions

Assumed: no fixed deadline; the complete first workflow takes precedence over Telegram. Owner: user.  
Assumed: the pilot acceptance test is correctness and successful end-to-end movement, not a specified correction-rate threshold. Owner: user.  
Assumed: incomplete or questionable German may be staged with a warning, but audio and study promotion wait until the exact front is confirmed; this follows the user's correction of the first sample. Owner: user.  
Assumed: Anki Browser search plus SQLite is sufficient; a separate vocabulary deck is deferred to minimize features. Owner: user.  
Open: confirm pilot inputs 2–5 before promoting them. Owner: user.  
Open: audition voices and verify API access, cost, and pronunciation before subscribing. Owner: user and Codex.

## 12. Next step

Write a feature-spec document from this brief and [pilot inputs](pilot-inputs.md), then build the paste → stage → approve → study path. Telegram remains a later [TODO](README.md).
