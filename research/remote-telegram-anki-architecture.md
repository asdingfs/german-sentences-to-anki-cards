# Remote Telegram → German enrichment → Anki architecture research

_Researched 2026-09-23. Primary-source links are attached to the claims they support._

> **Product decision after research (2026-09-23):** Keep the server-side durable queue, but replace background Mac polling with a user-triggered pull from the server portal. The portal’s “Open Anki & import” action invokes an installed Mac handler, which launches/focuses Anki and performs the same safe localhost import. The factual research below remains unchanged; its automatic-polling recommendation is superseded by this interaction decision.

> **Approval revision:** Keep editing in Anki, but initiate approval from the portal. The [updated architecture](../architecture/portal-triggered-mac-pull.md#8-anki-metadata-and-approval) proposes capturing the current Browse selection locally, previewing it in the portal, and approving only that unchanged snapshot through the installed helper. This supersedes Desktop-only approval recommendations below. No remote execution endpoint or approval feature has been implemented; portal compromise and optional native confirmation are explicit design considerations.

## Executive conclusion

There is no supported public AnkiWeb REST API for creating notes in a specific account. Anki's maintainer points developers to AnkiConnect for local scripting and explains that global AnkiWeb API access would increase the free service's hosting costs; AnkiWeb itself is not open source ([Anki maintainer replies](https://forums.ankiweb.net/t/is-there-any-plan-to-expose-rest-api-for-anki/43106/2), [hosting-cost reply](https://forums.ankiweb.net/t/is-there-any-plan-to-expose-rest-api-for-anki/43106/5), [AnkiWeb source reply](https://forums.ankiweb.net/t/is-there-any-plan-to-expose-rest-api-for-anki/43106/7)). Anki's manual also says an `.apkg` cannot be imported on AnkiWeb; it must be imported by a desktop or mobile client and then synced ([Anki manual](https://docs.ankiweb.net/contrib.html#sharing-decks-privately)). Reverse-engineering AnkiWeb endpoints or browser cookies would therefore be an unsupported, fragile and unnecessarily risky foundation.

The recommended design is an **always-on public intake/processing server plus an outbound-polling bridge on the Mac that runs Anki Desktop**:

```text
Telegram user
    ↓ HTTPS webhook
Public intake API → durable queue → German enrichment + German TTS
    ↓ stores draft, audio and workflow state
Private server API
    ↑ outbound authenticated polling (when the Mac is available)
Mac bridge → localhost AnkiConnect → target Anki profile → AnkiWeb sync → AnkiMobile
```

This preserves the existing custom note types and validation logic, lets the server accept submissions while the Mac is asleep, and keeps AnkiConnect bound to loopback instead of exposing a collection-modifying API to the internet. The durable queue absorbs the Mac's offline periods; the bridge imports each job idempotently once Anki is available.

## What Anki officially supports

### AnkiWeb is a sync service, not a card-creation API

AnkiWeb synchronizes a local collection across clients. Desktop sync normally runs when a profile opens or closes, and it also transfers referenced sound and image media ([Anki sync manual](https://docs.ankiweb.net/syncing.html#automatic-syncing), [media syncing](https://docs.ankiweb.net/syncing.html#media)). Only one local profile should be connected to a given AnkiWeb account; connecting multiple profiles to one account can overwrite data ([Anki profiles manual](https://docs.ankiweb.net/profiles.html)). Consequently, the account/profile binding should remain inside the user's existing `German` desktop profile, not be recreated as AnkiWeb credentials on the public application server.

The current evidence supports the following conclusion: **there is no documented, supported third-party AnkiWeb endpoint for adding a note directly to an account**. The supported integration named by Anki's maintainer and the official self-hosted-sync documentation is AnkiConnect ([maintainer reply](https://forums.ankiweb.net/t/is-there-any-plan-to-expose-rest-api-for-anki/43106/2), [self-hosted sync manual](https://docs.ankiweb.net/sync-server.html#contributing-changes)).

### AnkiConnect requires Anki Desktop

AnkiConnect is an add-on loaded by Anki Desktop. Its own documentation says Anki must remain running; the add-on starts an HTTP server on port 8765 when Anki launches ([AnkiConnect's source-owned project and README](https://git.sr.ht/~foosoft/anki-connect/tree/master/item/README.md)). It therefore cannot simply be installed as a standalone web API without Anki Desktop.

AnkiConnect provides the operations needed by this project: creating notes, storing media, reporting/loading profiles, and triggering AnkiWeb sync. Its `storeMediaFile` operation places media into Anki's media folder, and its `sync` operation synchronizes the local collection with AnkiWeb ([AnkiConnect source-owned README](https://git.sr.ht/~foosoft/anki-connect/tree/master/item/README.md)).

Security defaults matter. AnkiConnect binds to `127.0.0.1` by default; network binding can be enabled, but authentication is disabled until `apiKey` is configured ([AnkiConnect source-owned README](https://git.sr.ht/~foosoft/anki-connect/tree/master/item/README.md), [source defaults](https://git.sr.ht/~foosoft/anki-connect/tree/master/item/plugin/util.py)). For this workflow, keep `webBindAddress` on `127.0.0.1` and set an API key even on loopback. The public server should never call port 8765 over the open internet.

### “Headless Anki” is possible in pieces, but it is not a drop-in AnkiWeb API

The official `anki` Python package can open and modify a collection outside the GUI, and Anki explicitly recommends its collection methods instead of direct SQL because the methods preserve sync metadata and collection validity ([Anki module documentation](https://github.com/ankitects/anki/blob/main/docs-site/addons/the-anki-module.mdx#the-collection), [warning against direct database writes](https://github.com/ankitects/anki/blob/main/docs-site/addons/the-anki-module.mdx#the-database)). This could be used to generate `.apkg` artifacts on a server, but it is not AnkiConnect and the official documentation does not present it as a supported public service that writes directly into an AnkiWeb account.

Anki also ships an official standalone sync server that does not require GUI dependencies, but it implements the Anki sync protocol, not note-ingestion REST endpoints. Its documentation explicitly says REST APIs are outside its intended scope and again points to AnkiConnect for API access ([installation choices](https://docs.ankiweb.net/sync-server.html#installingrunning), [scope statement](https://docs.ankiweb.net/sync-server.html#contributing-changes)). Using that server would also mean pointing every client, including AnkiMobile, at a custom sync endpoint instead of the user's present AnkiWeb account. It is an advanced, self-supported replacement for AnkiWeb, not an ingestion adapter for AnkiWeb ([warnings and client setup](https://docs.ankiweb.net/sync-server.html#self-hosted-sync-server)).

Running a complete graphical Anki instance in a Linux virtual display on a server is technically conceivable, but neither Anki nor AnkiConnect documents it as a supported headless deployment. It adds GUI lifecycle, profile locking, upgrades and remote-display recovery to a small personal automation. It should not be the MVP.

## Cross-machine import patterns

| Pattern | Anki Desktop required? | Automation | Main trade-off | Recommendation |
|---|---:|---:|---|---|
| Public server calls AnkiWeb | N/A | High | No supported note-creation API | Reject |
| Server exposes AnkiConnect from a hosted Anki GUI | Yes | High | Fragile GUI/headless operations; collection service exposed on a server | Avoid |
| Server pushes to home AnkiConnect | Yes, at home | High when online | Requires an inbound route to the home machine | Possible only through a private VPN; not the default |
| **Home bridge pulls from server, then calls localhost AnkiConnect** | **Yes, at home** | **High when online** | Import waits until the Mac and Anki are running | **Recommended** |
| Server generates `.apkg`; user imports it | Desktop or mobile import client | Low | Manual import; good emergency fallback | Keep as fallback |
| Server generates TSV/CSV plus audio | Desktop for practical media setup | Low | Media must be copied into `collection.media`; more user steps | Last-resort/debug export |
| Official self-hosted sync server | No GUI for sync server | Medium | Replaces AnkiWeb and has no ingestion REST API | Out of scope for the desired account |

An `.apkg` can contain notes, cards, note types and media; importing a deck package adds/updates notes rather than replacing the collection ([Anki export manual](https://docs.ankiweb.net/exporting.html#packaged-decks), [packaged-deck update rules](https://docs.ankiweb.net/importing/packaged-decks.html#updating)). It is therefore a sound recovery/export format. Plain text import supports deck/note-type headers and stable first-field IDs, but audio files must separately be copied into `collection.media` and referenced as `[sound:filename.mp3]` ([Anki text import headers and duplicate handling](https://docs.ankiweb.net/importing/text-files.html#file-headers), [media import](https://docs.ankiweb.net/importing/text-files.html#importing-media)).

### Reliable bridge protocol

The remote server should remain the durable job store. Suggested states are:

```text
received → processing → draft_ready → delivered_to_staging
         ↘ failed_retryable
draft_ready/delivered_to_staging → approved → imported_to_study → synced
                              ↘ rejected
```

Each Telegram update and each resulting card needs stable identifiers:

- Deduplicate intake by Telegram `update_id`. Telegram documents it as a unique identifier that is useful for ignoring repeated or out-of-order webhook deliveries ([Telegram `Update`](https://core.telegram.org/bots/api#update)).
- Give each sentence an immutable `workflow_id` and content revision. Put that ID in the existing Anki `WorkflowId` field and use it for every retry.
- The bridge requests a small lease on ready jobs, downloads structured JSON and audio, verifies a content hash, writes via AnkiConnect, and acknowledges the exact revision. A timed-out lease is safe to retry because the bridge searches by `WorkflowId` before adding.
- Before every write, the bridge calls `getActiveProfile` and **fails closed unless it is the configured `German` profile**. Automatically switching profiles while the user is reviewing is surprising; explicit failure is safer. After a successful batch it can call AnkiConnect `sync`, subject to a single-process lock so import, approval and sync cannot overlap.
- The server must never edit `collection.anki2` over file sharing. Anki warns that synchronizing its live data directory with file-sync services or placing it on network filesystems can corrupt the database ([Anki files manual](https://docs.ankiweb.net/files.html#dropbox-and-file-syncing), [network-filesystem warning](https://docs.ankiweb.net/files.html#network-filesystems)).

## Remote German enrichment under a ChatGPT Plus plan

The enrichment contract should stay provider-neutral and return the same validated schema already used locally: normalized/corrected German, English meaning, grammar points, selected base-form vocabulary with articles/case/variants, uncertainty flags, and a correction requiring explicit approval when source text changed. TTS remains a separate ElevenLabs step and only receives the final German sentence.

### Option 1 — Codex CLI signed in with ChatGPT: acceptable personal MVP

Codex is included with ChatGPT Plus, and signing the CLI in with ChatGPT consumes the plan's Codex allowance; using an API key instead uses separate API pricing ([OpenAI ChatGPT Work/Codex billing explanation](https://help.openai.com/en/articles/20001275/)). Codex usage is limited and depends on task size, complexity, context and tools ([OpenAI usage-limit explanation](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan)). The current local implementation already proves this route with `codex exec` and a strict output schema.

A remote Linux server can authenticate a personal Codex CLI interactively and then run non-interactively. The source-owned CLI implements `codex login --device-auth` specifically for remote/headless machines ([OpenAI Codex source](https://github.com/openai/codex/blob/main/codex-rs/cli/src/login.rs)). Treat the resulting cached ChatGPT credentials as a password and keep them in a protected service account/home directory.

This is a reasonable low-volume MVP, but it is not the best long-term service dependency: quota exhaustion or an expired/revoked user session can pause the queue, and a personal ChatGPT login is not a narrowly scoped service credential. Jobs must remain retryable and show `blocked_auth` or `blocked_quota` instead of being lost. Do not promise immediate processing.

### Option 2 — paid model API: recommended production path

ChatGPT and API billing are separate; a Plus subscription does not include general API usage ([OpenAI billing documentation](https://help.openai.com/en/articles/9039756)). The API, however, is the cleanest unattended service interface: use a low-cost multilingual model, require Structured Outputs against the existing JSON Schema, cap output length, and set project-level spend alerts/limits. OpenAI's Structured Outputs are designed to adhere to a supplied JSON Schema and expose refusals programmatically ([Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs)). Current model selection and prices should be taken from the live [model guide](https://developers.openai.com/api/docs/models) and [pricing page](https://developers.openai.com/api/docs/pricing), not hard-coded into the brief.

For non-urgent bulk processing, the Batch API offers a 50% discount but can take up to 24 hours, so it is suitable for an optional nightly backlog rather than the normal Telegram response path ([OpenAI Batch API](https://developers.openai.com/api/docs/guides/batch)).

### Option 3 — local model on the server: lowest marginal cost, highest QA burden

Ollama supports constraining local-model responses with a JSON Schema ([Ollama Structured Outputs](https://ollama.com/blog/structured-outputs)). A local model removes per-call model fees but transfers cost to RAM/GPU, maintenance and evaluation. German correction and grammar teaching quality must be measured, not assumed. Before adopting it, build a golden set of at least the existing pilot cards plus deliberately misspelled, fragmentary and case-heavy sentences; compare correction, translation, lemma/article extraction and explanation accuracy. A sensible hybrid is local first-pass plus paid-API fallback when the model flags uncertainty or the schema/rules validator rejects output.

DeepL can optionally provide an independent translation/correction signal, but it does not replace the grammar/vocabulary explainer. Its correction endpoint is currently an API Pro feature, not an API Free feature ([DeepL Write API](https://developers.deepl.com/api-reference/improve-text)).

### Recommendation

Keep two interchangeable enrichment adapters:

1. `codex_cli` for the first personal deployment, reusing the proven prompt/schema and accepting queue pauses when allowance/auth is unavailable.
2. `openai_api` as the supported unattended fallback/upgrade, initially disabled and protected by a small monthly spend ceiling.

Do not make the Telegram request wait for either model. Acknowledge receipt, enqueue work, then send a later preview/status message.

## Security design

### Telegram → public server

Telegram webhooks require an HTTPS URL. `setWebhook` can attach a 1–256 character `secret_token`; Telegram sends it in `X-Telegram-Bot-Api-Secret-Token`, and Telegram retries deliveries that do not receive a 2xx response ([Bot API `setWebhook`](https://core.telegram.org/bots/api#setwebhook)). The official webhook guide requires TLS 1.2+ and currently lists ports 443, 80, 88 and 8443; it also publishes Telegram's current source ranges while warning that they may change ([Telegram webhook guide](https://core.telegram.org/bots/webhooks)).

Use all of the following controls:

- Validate the webhook secret header with constant-time comparison **before parsing or enqueueing**.
- Allow only the owner's numeric Telegram user ID and intended private chat ID. The webhook secret authenticates the configured webhook sender; the user/chat allowlist authorizes who may create or approve cards.
- Deduplicate by `update_id`, restrict accepted update types to `message` and `callback_query`, cap request-body/text size, validate JSON, and rate-limit expensive work. Telegram may retry and explicitly documents `update_id` for duplicate suppression ([Telegram `Update`](https://core.telegram.org/bots/api#update)).
- Optionally allowlist Telegram's published IP ranges as defense in depth, not as the primary identity control, because Telegram says the ranges may change ([webhook network requirements](https://core.telegram.org/bots/webhooks#the-short-version)).
- Enqueue and return 2xx quickly; model/TTS work belongs in a worker. Persist failures and retry with backoff.
- Keep the bot token, webhook secret, ElevenLabs key and model credentials in a managed secret store; use distinct secrets, rotate them, never log them and never commit them. OWASP recommends least-privilege access, rotation/revocation and masking secrets from logs ([OWASP Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)).
- Expose only the webhook and authenticated review UI. The queue, database, worker metrics and bridge endpoints remain private. HTTPS and endpoint-level authorization are baseline REST controls ([OWASP REST Security](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)).

### Server → Mac/Anki

Prefer **outbound polling from the Mac** over an inbound connection to the home network. The bridge authenticates to a narrow server API with a separate revocable credential that can only: lease ready jobs, fetch a job/audio object, acknowledge import, and report status. It cannot submit Telegram updates, administer users, read unrelated secrets, or change server configuration.

Recommended controls:

- HTTPS for every bridge request; a high-entropy per-device bearer token is adequate for the first single-user version if stored in macOS Keychain and the server's secret manager. Add short-lived tokens or mutual TLS if the deployment grows; OWASP specifically notes mTLS as additional protection for highly privileged services ([OWASP REST Security](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html#https)).
- Never log authorization headers, Telegram bot tokens, AnkiConnect keys or signed audio URLs. Store only a hash of bridge tokens server-side when practical.
- Give audio downloads short expirations or serve them through the authenticated bridge endpoint. Verify a server-provided SHA-256 digest before sending media to Anki.
- Keep AnkiConnect on `127.0.0.1` with its own API key. The bridge is the only process that knows that key.
- Use a local single-instance lock, target-profile check, per-job transaction log and a backup/health check before schema migrations.
- If a direct server-to-Mac channel is later required, put it behind a private overlay network and firewall it to the one server identity. Tailscale documents private device connectivity without opening public inbound ports ([Tailscale firewall guidance](https://tailscale.com/docs/reference/faq/firewall-ports)). Even then, expose the bridge's narrow API, not raw AnkiConnect.

## Bulk approval options

### 1. Anki Desktop Browser — recommended MVP

Keep the existing behavior: remote jobs eventually enter `German Sentences::Staging` as suspended notes; the user filters the Browser, edits fields, selects the reviewed rows, and runs the existing `approve --selected` command. Approval validates the exact `WorkflowId`, required German confirmation and audio, moves valid sentence cards to Study, creates/updates suspended vocabulary-ledger notes, then syncs. This is the smallest change and preserves Anki as the review source of truth.

Add two safe conveniences:

- `approve --batch <batch_id>`: approve only cards from a named Telegram submission batch after showing count and validation failures.
- `approve --query '<Anki search>' --dry-run`: print the exact cards, then require an explicit second command with the generated approval token. Do not add an unscoped `approve --all` that can sweep unresolved cards.

### 2. Telegram buttons — good for clear individual cards, weak for detailed edits

After processing, the bot can send a compact preview with `Approve`, `Needs correction`, and `Reject` inline buttons. Telegram callback buttons send a callback query containing the sender, and `callback_data` is limited to 1–64 bytes ([Telegram inline keyboard and callback query](https://core.telegram.org/bots/api#inlinekeyboardbutton), [CallbackQuery](https://core.telegram.org/bots/api#callbackquery)). Put only an opaque one-use action token in callback data; retrieve the card and intended action from the database, re-check the allowed Telegram user ID, revision and current status, consume the token atomically, and call `answerCallbackQuery` promptly as required by Telegram ([answering callbacks](https://core.telegram.org/bots/api#answercallbackquery)).

For bulk approval, send a batch summary with `Approve N ready cards` and `Open review` buttons. The approval must be revision-pinned: if any card changed since the summary, reject the stale action and issue a fresh summary. Telegram is unsuitable for deleting individual vocabulary rows or carefully editing multi-paragraph grammar, so it should remain a fast path for already-clean cards.

### 3. Small web portal / Telegram Mini App — best eventual experience

A portal can show a table of draft cards, full field editors, vocabulary checkboxes, audio playback, validation errors, filters and “Approve selected.” The cleanest mobile entry is a Telegram Mini App launched from the bot. Telegram requires the backend to validate the Mini App's `initData` signature and warns not to trust `initDataUnsafe` without server-side validation ([Telegram Mini App validation](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app)). The portal must still enforce the expected Telegram user ID and short session lifetime on every mutation.

Avoid a split-brain editor. Once the portal is introduced, make the server's versioned draft the editing source of truth and treat Anki Staging as a rendered mirror. Portal approval freezes a revision; the local bridge applies that exact revision to Anki and acknowledges it. Direct edits in Anki Staging should either be disabled by convention or explicitly pulled back into the server before approval.

### Recommended rollout

1. **MVP:** Telegram webhook + durable queue + remote Codex-CLI adapter + local outbound bridge + current Anki Desktop bulk selection/approval.
2. **Hardening:** API enrichment adapter, spend limits, queue dashboard, signed audio delivery, automatic post-import AnkiWeb sync and end-to-end idempotency tests.
3. **Approval UX:** Telegram one-card approvals, then a Mini App/web portal only after the basic pipeline is reliable. Preserve Desktop approval as a recovery path.

## Concrete project decisions for the brief

- Anki Desktop remains the authoritative writer to the existing `German` profile in the first remote version.
- The public server never receives the AnkiWeb password and never exposes AnkiConnect.
- The remote server owns intake, asynchronous enrichment/TTS and durable delivery state; the Mac owns Anki import, profile verification and AnkiWeb sync.
- `WorkflowId` and revision make every stage idempotent; Telegram `update_id` prevents duplicate submissions.
- ChatGPT Plus/Codex may power the personal MVP, but the service must tolerate exhausted allowance/auth. Paid API and local-model adapters remain replaceable options.
- Bulk approval begins in Anki Desktop with selected or batch-scoped notes. Telegram buttons are a shortcut; a versioned, authenticated portal is the later full editor.
- `.apkg` with media is the emergency/manual transfer format. TSV/CSV is a debugging export, not the primary path.

## Questions that still need a product decision

1. How quickly must a Telegram submission appear in Staging: seconds, a few minutes, or “next time the Mac is on”?
2. Should the Mac bridge start automatically at login and launch Anki, or only import while Anki is already open?
3. In the first release, should approval remain exclusively in Anki, or should a simple Telegram `Approve` button ship at the same time?
4. Where will the public service run, and does that platform provide a managed database, queue, object storage and secret manager?
5. Is temporary storage of class sentences and generated audio on that service acceptable, and what deletion period is desired?
