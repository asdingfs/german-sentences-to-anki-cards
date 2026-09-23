# Brief: German class sentences to Anki

**In one line:** A paste-to-approved-Anki-card workflow for one German learner so that class material becomes accurate, searchable, audio-backed review without repetitive manual card creation.  
**Owner:** User, with Codex for implementation · **Deliverable:** Development project brief and subsequent workflow · **Due:** No fixed date; complete the first workflow before Telegram input (assumed) · **Status:** Approved brief; inexpensive ElevenLabs v3 TTS accepted by user, 22 September 2026 · **Date:** 22 September 2026

## 1. Background: why this, why now

The user wants German class material converted into Anki cards without manual translation, explanation, audio, or formatting. Anki sync is configured; no German deck or note type needs preserving. Five class examples are in [pilot inputs](pilot-inputs.md); the first was corrected to “Bitte lesen Sie den Brief und markieren Sie die Sätze.” Source: user conversation, 22 September 2026.

## 2. Objective

Process about 5 pasted inputs through drafting, staging, approval, and study placement, recording only approved base-form vocabulary.

## 3. Audience

The sole learner and approver uses Anki desktop for import and iOS for review. They edit drafts and remove irrelevant explanations.

## 4. Core message

When I paste German class material, I need an editable Anki draft before it becomes a study card with fixed German audio and useful grammar.

## 5. Deliverable and scope

The first build uses a sentence note type, staging and study decks, an indexed encountered-vocabulary ledger, and a separate searchable vocabulary note type/deck. Each sentence note produces one German-to-English card. Fields: German text/audio, English meaning, grammar, selected vocabulary, searchable base forms, and source/status. The front displays German and plays audio; the back displays English and explanations without English audio. Approved base forms also become suspended vocabulary notes, which never enter study automatically.

**In scope:** Paste/batch input; translation and targeted grammar; selectable base forms with articles, inflections, and cases; review; deck promotion; duplicate-safe ledger updates; fixed German audio; iOS playback check.  
**Out of scope:** Telegram input, voice cloning, a custom portal, learned-word status, English audio, and automatic approval.

## 6. Supporting content

- **Approval:** Edit staged notes in Anki Browse, select reviewed notes, then run `approve --selected`. This moves cards into Study and updates the ledger idempotently. Manual Change Deck requires explicit reconciliation. [Anki Browse](https://docs.ankiweb.net/browsing.html).
- **Vocabulary:** An indexed SQLite ledger stores approved base forms, meanings, articles, variants/cases, dates, and source-card links. The same base forms appear as separate, suspended Anki vocabulary notes for Browser search. Removing a card explanation does not erase an encounter. [Anki search](https://docs.ankiweb.net/searching).
- **Quality:** [LEO](https://www.leo.org/german-english/) may check words. Explain critical patterns such as *aus + dative*. Flag fragments; never silently complete them.

## 7. Tone, style and references

Precise: distinguish the supplied German, a proposed correction, and a verified card.  
Plain: explain grammar in short English with an example of the changed form.  
Selective: prioritize new words and sentence-critical patterns over exhaustive analysis.  

Reference: the user's *aus der ganzen Welt* breakdown in [pilot inputs](pilot-inputs.md) connects meaning, base form, and dative change. Avoid translations that conceal uncertain text.

## 8. Constraints and mandatories

Cloud translation and TTS are permitted. Per the user's 22 September decision, generate drafts through the existing ChatGPT/Codex login or this conversation; no separate OpenAI API key. Use the official ElevenLabs API for audio. Keep keys out of project notes. Anki-Connect writes locally; text-plus-media import is the fallback. AnkiWeb handles sync. Check front audio autoplay on desktop/iOS. [Text import](https://docs.ankiweb.net/importing/text-files.html); [audio options](https://docs.ankiweb.net/deck-options.html).

Use the official ElevenLabs API with `model_id: eleven_v3`; inexpensive paid usage is accepted. Only the confirmed German sentence is sent to TTS and attached as front audio. English meanings, grammar, vocabulary explanations, and instructions remain text. Generate, retrieve, and attach MP3 automatically. Audition German voices, randomly select once per card, and retain the file. Cache audio so explanation edits and repeated imports incur no new TTS charge. Track characters, retries, and estimated cost; use the cheapest account option supporting the chosen voices. [Model](https://elevenlabs.io/docs/overview/models); [API](https://elevenlabs.io/docs/api-reference/text-to-speech/convert); [pricing](https://elevenlabs.io/pricing/api). This decision supersedes the earlier Free-only and manual-download proposals; see the [implementation plan](implementation-plan.md) for cost assumptions.

## 9. Timeline

No calendar deadline was supplied. Confirm fields and voices; implement the five-input paste-to-staging pilot; verify approval, ledger, sync, and iOS playback. Telegram follows only after the user approves the completed workflow.

## 10. Success metrics

Process about 5 pilot inputs without duplicate notes or ledger entries. Every promoted card has approved German/English, useful grammar and selected vocabulary, stable playable German audio on desktop/iOS, and searchable approved base forms. Unresolved fragments stay staged.

## 11. Assumptions and open questions

Assumed: no fixed deadline; the complete first workflow takes precedence over Telegram. Owner: user.  
Assumed: the pilot acceptance test is correctness and successful end-to-end movement, not a specified correction-rate threshold. Owner: user.  
Assumed: incomplete or questionable German may be staged with a warning, but audio and study promotion wait until the exact front is confirmed; this follows the user's correction of the first sample. Owner: user.  
Decided: use a separate, suspended vocabulary deck for searchable approved base forms; a custom portal remains deferred. Owner: user.
Open: confirm pilot inputs 2–5 before promoting them. Owner: user.  
Open: audition German voices and configure the account, API key, and usage limit during implementation. Owner: user and Codex.

## 12. Next step

Complete the live ElevenLabs audio and desktop/iOS checks in the [workflow TODO](implementation-plan.md), then review and approve the pilot. See the [setup guide](setup/README.md). Telegram remains deferred.
