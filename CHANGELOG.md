# Changelog

## 2026-09-23

Implemented the local German-sentence workflow: ChatGPT/Codex generates English meaning, grammar, and base-form vocabulary; ElevenLabs v3 is wired for fixed German-only audio; AnkiConnect stages suspended `German Sentences v1` notes, validates approval, moves approved cards to Study, and mirrors approved words into a separate suspended vocabulary ledger. The workflow includes duplicate protection, SQLite encounter tracking, secure macOS Keychain lookup for the ElevenLabs key, and collection-backup/profile safeguards.

Improved the card layout so each grammar point and vocabulary entry renders as its own spaced block. Seven current drafts were updated in Anki without being approved or moved, and the automated suite now covers formatting, staging, audio integrity, approval recovery, and vocabulary synchronization.

### Planning updates (not implemented)

Revised the remote workflow to use a server queue and user-triggered Mac pull. Editing stays in Anki; portal approval is proposed via a paired helper, local selection snapshot, preview, and fixed approval operation. Documented changed-selection/content handling, replay protection, partial recovery, and the remaining trust placed in the portal. No production code or Anki cards changed in this planning update.
