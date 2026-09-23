# Brief: Telegram-triggered remote German-to-Anki workflow

**In one line:** A remote workflow for one German learner so that a Telegram sentence becomes an editable, explicitly approved card in the correct Anki account and profile.  
**Owner:** User · **Deliverable:** Researched architecture and implementation plan · **Due:** No fixed deadline (assumed) · **Status:** Draft v1 · **Date:** 23 September 2026

## 1. Background: why this, why now

The local workflow creates meanings, grammar, vocabulary, and German-only audio; stages suspended sentence notes; promotes validated approvals to Study; and mirrors approved words into a suspended vocabulary ledger. It includes duplicate protection, SQLite tracking, secure keys, profile safeguards, bulk approval, and readable formatting. Changes are recorded in [CHANGELOG.md](CHANGELOG.md).

The next problem is capture and delivery: sentences should be sent to a Telegram bot, processed on an always-reachable server, then pulled from a server-hosted portal on the Mac into the existing `German` profile when the user is ready.

## 2. Objective

Build and validate a 5-sentence pilot in which every authorized Telegram submission creates exactly one versioned staging draft, and every approved draft creates the expected Study sentence plus suspended vocabulary notes without duplicate, unauthorized, or wrong-profile writes.

Remove capture friction while preserving human review and language quality.

## 3. Audience

The sole initial user owns the Telegram bot, remote service, Anki account, and `German` profile. They capture anywhere, then periodically open the server portal on their Mac and click once to open Anki and pull the queued drafts. Codex implements; the user owns credentials, service choices, and acceptance.

## 4. Core message

When I send a German sentence from my phone, the server should queue a trustworthy draft that I can later pull into my existing Anki workflow from a portal on my Mac.

## 5. Deliverable and scope

Produce an architecture, threat model, state contract, and build plan for Telegram intake, enrichment/TTS, delivery, Anki import, and approval.

**In scope:** One private Telegram chat; text sentences; asynchronous status; current card schema; German-only ElevenLabs audio; durable queue; authenticated portal; user-triggered Mac pull; Anki launch/readiness; profile checks; AnkiWeb sync; Anki editing with portal bulk approval; `.apkg` recovery export.  
**Out of scope:** Background push/polling, Telegram groups, multiple users, photos or voice messages, public AnkiConnect access, reverse-engineered AnkiWeb endpoints, replacing AnkiWeb, and a full portal-based card editor in the MVP.

## 6. Supporting content

- **Anki delivery:** There is no supported public AnkiWeb note-creation API. AnkiConnect requires Anki Desktop, so the server keeps the queue and a user-triggered Mac pull module launches or focuses Anki, waits for localhost AnkiConnect, imports a leased batch, acknowledges it, and syncs. See the [research report](research/remote-telegram-anki-architecture.md) and [AnkiConnect documentation](https://git.sr.ht/~foosoft/anki-connect).
- **Remote enrichment:** Preserve the validated JSON contract. Start with ChatGPT-authenticated Codex CLI, tolerating quota/auth pauses. ChatGPT Plus does not include general API credit; retain paid-API and local-model adapters as alternatives.
- **Security:** Verify Telegram’s webhook secret before parsing, allow only the owner’s numeric user/chat IDs, deduplicate `update_id`, rate-limit work, and store secrets outside code. The Mac initiates outbound authenticated requests; AnkiConnect remains on `127.0.0.1` with its own key.
- **Portal and approval:** Edit in Anki. Proposed: load the Browse selection into a portal preview, then approve that frozen set through the installed helper. Changed content requires another preview; changed selection cannot substitute notes. Reuse local validation and vocabulary updates, never arbitrary remote commands.

## 7. Tone, style and references

**Simple:** Minimize services and avoid duplicating Anki’s editing UI prematurely.  
**Secure:** Fail closed at every identity, profile, revision, and approval boundary.  
**Auditable:** Make each state transition, retry, cost, and external write traceable.  
**Conservative:** Prefer supported APIs and recoverable queues over browser automation or private endpoints.

## 8. Constraints and mandatories

The server acknowledges Telegram quickly and processes asynchronously. `WorkflowId`, revision, and `update_id` make retries idempotent. AnkiWeb credentials and AnkiConnect stay local. The installed helper accepts only fixed, authenticated operations and verifies profile, ownership, saved content, and audio. Portal-only approval trusts the portal; native confirmation is needed to resist a compromised portal authorizing actions. Secrets stay out of logs.

## 9. Timeline

Phase 1: activation interface, threat model, and job schema. Phase 2: webhook, queue, worker, portal, and replies. Phase 3: Mac pull, Anki import, sync, and pilot. Phase 4: snapshot-bound portal approval and hardening. Phase 5: evaluate portal editing.

## 10. Success metrics

The pilot covers normal/corrected sentences, duplicate delivery, offline Mac, and unauthorized requests. Approval tests cover stale content, selection changes, replay, and partial failure. Success means no duplicate or wrong-profile writes, no logged secrets, restart recovery, correct German-only audio, and expected sentence/ledger notes.

## 11. Assumptions and open questions

Assumed: there is no hard deadline; correctness precedes convenience. Owner: user.  
Assumed: one private user and text-only input are sufficient for the MVP. Owner: user.  
Decided: the Mac runs Anki periodically; import begins only when the user clicks from the server portal, and the local pull module may open Anki. Owner: user.  
Decided: edit cards in Anki and initiate approval from the portal. Proposed: preview the frozen selection before approval. Owner: user.  
Assumed: choose the smallest low-cost host after comparing secrets, queue/database, backups, and region. Owner: user and Codex.  
Open decisions: native approval confirmation; hosting; data retention; activation design validation. Separate Advisor review remains pending after automatic approval review blocked the private consultation payload.

## 12. Next step

Use codebase-design to review the [proposed architecture](architecture/portal-triggered-mac-pull.md), resolve confirmation policy, then implement import before snapshot-aware portal approval. No remote feature is implemented yet.
