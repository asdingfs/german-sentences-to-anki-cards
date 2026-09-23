# Architecture design: portal-triggered Mac pull

**Status:** Proposed · **Date:** 23 September 2026 · **Decision owner:** User

## 1. Problem and constraints

The always-on server accepts Telegram sentences, enriches them, generates German audio, and keeps a durable ready queue. Nothing pushes into the Mac. When ready, the user opens the server portal on the Mac and clicks **Open Anki and import N ready cards**. An installed Mac helper opens or focuses Anki, waits for localhost AnkiConnect, pulls a frozen batch, imports it into suspended Staging notes, syncs, and opens Anki Browse filtered to that batch.

The portal must not transfer an Anki database. The server and Anki remain separate stores; the pull retrieves immutable, versioned card envelopes and audio.

Every design must satisfy:

- explicit user gesture; no background polling or inbound connection to the Mac;
- AnkiConnect stays on `127.0.0.1` and Anki Desktop is the writer;
- active profile must be exactly `German` before the first write;
- `WorkflowId`, monotonic revision, content hash, and audio SHA-256 make retries safe;
- wrong profile, schema drift, stale revision, or changed hash fails closed;
- imported cards enter `German Sentences::Staging` suspended; vocabulary notes remain an approval-time effect;
- a crash after a local write but before acknowledgement cannot create duplicates;
- Anki is the editing authority; the portal initiates approval of an exact locally captured selection through the installed helper. See the approval design in section 8.

### Dependency classification

| Dependency | Category | Design treatment |
|---|---|---|
| normalization, hashing, validation, reconciliation | In-process | Hidden inside the deep module |
| local journal, cache, lock | Local-substitutable | SQLite/filesystem production adapters; in-memory test adapters |
| server queue and Mac bridge | Remote but owned | Narrow port with HTTPS and in-memory adapters |
| Telegram, model provider, ElevenLabs, macOS launcher, Keychain, AnkiConnect | True external | Injected ports with production and mock adapters |

## 2. Design A — minimal pull module

Expose one deep interface:

```python
class MacPullWorkflow:
    def run(self, activation: PullActivation) -> PullResult: ...
```

`run()` hides ticket redemption, Anki launch/readiness, queue leasing, hash validation, `WorkflowId` reconciliation, media storage, acknowledgement recovery, sync, and result presentation. The portal’s custom URL handler and a recovery CLI both call this interface.

**Strengths:** Maximum depth and locality; callers cannot violate ordering; trivial common case; smallest test surface.  
**Weaknesses:** A caller cannot separately preview a detailed transfer plan or subscribe to progress without extending the result model. It is deliberately specialized to the personal workflow.

## 3. Design B — goal-state transfer coordinator

Expose a richer declarative interface:

```python
class TransferCoordinator:
    def plan(self, intent: PullIntent) -> TransferPlan: ...
    def apply(self, commit: PlanCommit) -> RunReceipt: ...
    def observe(self, run_id: RunId, after: EventCursor | None) -> EventPage: ...
```

The caller describes a selector, desired state, target, review authority, and safety limits. A digest-pinned plan supports dry runs, filters, multiple devices, alternate `.apkg` artifacts, and future portal approval.

**Strengths:** High leverage if multiple targets, approval authorities, artifact formats, and live progress are genuinely required. The immutable plan is an excellent safety seam.  
**Weaknesses:** `PullIntent`, selectors, plans, commits, capabilities, and events are a large interface for a one-user import button. This risks designing hypothetical variation before a second adapter exists.

## 4. Design C — portal-first ready-queue importer

Expose one user-purpose interface while making the portal activation explicit:

```python
class ReadyQueueImporter:
    def import_ready_queue(self, activation: Activation) -> ImportRunResult: ...
```

The server snapshots the ready queue when the portal button is pressed. The activation contains only a run ID and one-use ticket. The helper uses its separate Keychain device credential to claim the run; it then launches Anki, validates the environment, leases the snapshot, imports it, and reports progress to the existing portal tab.

**Strengths:** The interface matches the most common caller exactly, produces the requested one-click experience, and keeps portal concerns out of import correctness.  
**Weaknesses:** Requires installing and signing a small macOS helper. Detailed planning/filtering would require a later deepening rather than being available on day one.

## 5. Comparison

| Criterion | A: Minimal pull | B: Coordinator | C: Portal-first |
|---|---|---|---|
| External interface | 1 entry point | 3 entry points plus rich types | 1 entry point |
| Depth | Highest | High, but broader | Highest for requested use |
| Portal experience | Good | Powerful but indirect | Best |
| MVP implementation | Smallest | Largest | Small |
| Future multi-target flexibility | Limited | Best | Moderate |
| Locality of safety rules | Strong | Strong | Strong |
| Risk of shallow caller orchestration | Low | Low | Low |
| Risk of speculative seams | Low | Highest | Low |

## 6. Recommendation — combine C’s activation with A’s depth

Select the portal-first interaction and the one-entry deep module:

```python
@dataclass(frozen=True)
class Activation:
    run_id: UUID
    ticket: SecretStr

@dataclass(frozen=True)
class ImportRunResult:
    run_id: UUID
    batch_id: UUID | None
    state: Literal[
        "nothing_ready",
        "imported_and_synced",
        "imported_sync_pending",
        "needs_attention",
        "failed_before_write",
    ]
    imported: int
    already_present: int
    conflicted: int
    failed: int
    errors: tuple[ImportError, ...]

class ReadyQueueImporter:
    def import_ready_queue(self, activation: Activation) -> ImportRunResult: ...
```

This is deeper than exposing `launch_anki()`, `fetch_queue()`, `import_notes()`, and `sync()` separately. Those methods would force every caller to learn ordering and failure recovery. Portal approval now has a separate domain operation described below; it shares the existing local validation and promotion logic rather than duplicating it in portal code.

### Browser-to-local activation seam

Register a signed macOS helper for:

```text
germananki://pull?run=<uuid>&ticket=<one-use-ticket>
```

The URL contains no card data, profile, server credential, or AnkiConnect key. The ticket is short-lived, single-use, operation-bound, and paired to the registered Mac; redemption also requires a long-lived device credential from Keychain. Scheme registration or app signing alone does not authorize a request: another app can register the same scheme, and any webpage may try invoking it. Apple documents both the validation requirement and handler ambiguity in its [custom URL guidance](https://developer.apple.com/documentation/Xcode/defining-a-custom-url-scheme-for-your-app). A downloaded handoff file may be added later; its integrity format and validation remain to be specified. Avoid a localhost browser listener in the MVP because it adds origin, CSRF, port-discovery, and persistent local attack-surface concerns.

The helper accepts a small fixed set of operations: import a queue batch, read the Anki selection, and approve an existing selection snapshot. It imports locally installed Python functions. It accepts no shell commands, script paths, Python expressions, arbitrary URLs, or raw AnkiConnect actions from the server or deep link. Updates to executable code are a separate installation action; queue messages cannot update the helper. The configured server origin and local profile binding cannot be overridden by a link.

### Internal seams and adapters

```python
class RemoteQueue:
    def claim_and_lease(self, activation: Activation, device_proof: DeviceProof) -> BatchLease: ...
    def acknowledge(self, lease_id: UUID, receipts: tuple[ImportReceipt, ...]) -> AckResult: ...

class AnkiWorkspace:
    def apply(self, profile: str, batch: PreparedBatch) -> ApplyReport: ...
    def sync(self) -> SyncReport: ...
```

- `HttpsRemoteQueueAdapter` / `InMemoryRemoteQueueAdapter`
- `MacAnkiWorkspaceAdapter` / `InMemoryAnkiWorkspaceAdapter`
- internal `MacOSAnkiLauncherAdapter`, `AnkiConnectAdapter`, `KeychainCredentialAdapter`
- `SQLiteImportJournalAdapter` / `InMemoryImportJournalAdapter`
- `CustomUrlActivationAdapter` / `CliActivationAdapter` / recovery-file adapter

The external interface remains `import_ready_queue`; internal seams exist for testing and replacement, not for callers.

## 7. Ordering, state, and recovery

```text
portal POST creates frozen run
→ browser invokes custom URL
→ helper obtains single-run lock and claims run
→ helper launches/focuses Anki and waits with a bounded timeout
→ verify profile, schema fingerprint, decks, and note types
→ lease frozen batch only after Anki is ready
→ download and validate complete manifest and audio
→ reconcile each WorkflowId and write/read back
→ persist local receipt before remote acknowledgement
→ acknowledge imported state
→ sync and report synced or sync-pending separately
→ open Browse filtered by ImportBatchId
```

Server item states:

```text
received → processing → ready → leased → staged_local → synced
                  ↘ failed_retryable      ↘ sync_pending
                  ↘ quarantined
```

A sync failure must not return an item to `ready`; local import already succeeded. A lost acknowledgement is retried from the local journal. A lease expiry is safe because every retry first searches Anki by `WorkflowId` and checks revision/hash.

## 8. Anki metadata and approval

**User decision:** edit cards in Anki; initiate approval from the server portal. **Design status:** the snapshot interaction below is proposed, not implemented. The separate Advisor consultation was not run: automatic approval review rejected transmission of the private design packet. No substitute consultation was attempted.

### Why a remote portal needs an installed helper

`127.0.0.1` means the machine executing a request. A request from the remote backend to that address reaches the server itself. Browser JavaScript executes on the Mac, but giving it direct access to AnkiConnect would put a broad collection-editing interface within reach of portal code. The selected design uses a custom link to ask macOS to open a deliberately installed helper. That helper makes the local AnkiConnect requests and outbound authenticated server requests.

The current implementation already provides `Workflow.selected_ids()` and `Workflow.approve()`. AnkiConnect's installed `guiSelectedNotes` returns the Browse window's selected note IDs, or an empty list when Browse is closed. Approval also refreshes edits, validates German/audio, changes decks, unsuspends cards, records SQLite encounters, and mirrors vocabulary. A single `changeDeck` request would omit these effects. Reuse the Python workflow functions locally; do not expose a remote shell that runs a supplied command.

### Proposed portal interaction

1. Edit cards in Anki Browse, finish/save edits, and highlight the desired rows.
2. In the portal, click **Read Anki selection**. A one-use, paired-device activation opens the helper, which verifies the `German` profile, reads `guiSelectedNotes` once, validates ownership, and freezes the selected notes and their saved field/media state locally. If Browse is closed or selection is empty, report that condition; do not open a different Browse search or choose a default batch.
3. The helper sends the portal a short preview: note IDs, German fronts, counts, validation blockers, and an opaque snapshot reference/digest. The server cannot infer the Mac selection before this exchange. Unconfirmed or stale audio is shown as a blocker; final approval does not silently confirm German or spend money regenerating speech.
4. Click **Approve these N cards** in the portal. This is the approval button. It creates an authenticated, CSRF-protected, single-use request bound to the owner, paired device, operation, snapshot ID, digest, and expiry, then invokes the helper again.
5. The helper loads its own saved snapshot, checks every referenced note and current profile, and revalidates each note immediately before invoking the shared approval implementation. It never rereads the live selection to choose approval targets. Selection changes therefore cannot substitute different notes; content/media changes make affected notes stale and require a fresh preview.
6. Persist per-note outcomes locally, acknowledge them to the portal, and report Anki sync separately. A duplicate activation returns/resumes the same operation. Interrupted work reports partial results and retries only the original snapshot's eligible unfinished items.

There is one final approval button after the selection is loaded. A literal single click starting from an unknown selection would approve whichever rows happen to be selected when the helper runs; that is a different, more trusting interaction. An alternative is one portal button followed by a native confirmation preview, which gives local intent checking but places final confirmation on the Mac helper. Neither shortcut is implemented by this plan update.

### Small approval interface

```python
class SelectedNoteApproval:
    def prepare(self, activation: SelectionActivation) -> SelectionPreview: ...
    def commit(self, activation: ApprovalActivation) -> ApprovalReport: ...
```

These are proposed interfaces, not current commands. The module takes injected Anki, journal, and portal transport adapters. Its implementation hides authentication, profile checks, saved-field refresh, snapshot lifetime, fingerprints, validation, idempotent promotion, vocabulary recovery, and receipts. Callers cannot supply replacement note IDs or fields at commit time.

The local snapshot binds profile plus local collection binding, device, note IDs, WorkflowIds, relevant fields, German confirmation state, voice/audio digest, deck, and revision. Do not confuse `RemoteContentHash` (original delivered data) with this approval fingerprint (current Anki edits). The portal gets only preview data needed for the user's choice, not an entire collection or database. Preview expiry/retention must be configured alongside the server data-retention policy.

`Workflow.approve()` currently rereads fields and has no expected-fingerprint argument. Implementation must add snapshot-aware checks inside the shared promotion path before exposing portal approval. The process lock prevents concurrent helper runs, but does not lock Anki's editor. AnkiConnect calls are not one atomic cross-application transaction; recheck immediately before each mutation, detect changed results on read-back, preserve a recovery journal, and ask the user to finish editing during approval. Strict compare-and-write atomicity would need a separate Anki-side operation and is not claimed here.

### Trust and limits

Pairing, expiry, one-use tickets, and fixed operations reduce which requests the helper accepts; they do not prove a human clicked Approve if the authenticated portal is compromised. With portal-only final approval, the portal is trusted to authorize this narrow action. A compromised portal/session could request allowed imports, obtain permitted previews, or authorize eligible captured notes; it still must not be able to execute arbitrary commands, alter the configured profile, read arbitrary files, or bypass local audio/ownership checks. Hashes detect changes, not the trustworthiness of a compromised origin supplying both content and hashes.

If protection from a compromised portal authorizing approvals is required, enable a native confirmation displaying the exact snapshot before commit. That extra local gesture is a separate product choice, not something authentication or a browser “open application” prompt can replace. Revoke the paired-device credential to stop remote requests. Store that credential and the AnkiConnect key locally in Keychain; never grant portal JavaScript an AnkiConnect key or wildcard access.

### Metadata

Add backup-protected hidden fields to the sentence note type:

- `RemoteRevision`
- `RemoteContentHash`
- `ImportBatchId`

Existing local cards start at revision `0`. The batch ID lets the helper open exactly the imported rows and later enables batch-scoped approval previews. Preserve `approve --selected` as a local recovery command; portal commit must use the frozen snapshot, not run this command after a delay against a potentially different selection. Approval creates vocabulary notes only from the edited vocabulary lines in the accepted snapshot.

## 9. Implementation slices

1. Define envelopes, revisions, hashes, queue states, receipts, and in-memory adapters.
2. Implement and test `ReadyQueueImporter` entirely against in-memory queue/Anki adapters.
3. Add server HTTPS transport and device pairing/Keychain credentials.
4. Add macOS helper, custom URL activation, CLI fallback, Anki launcher, and AnkiConnect adapter.
5. Add portal queue view, frozen-run creation, progress reporting, and recovery-file fallback.
6. Migrate the note type after a fresh collection backup; import a 5-item failure-oriented pilot.
7. Add `SelectedNoteApproval.prepare/commit`, portal selection preview and approval, and snapshot-aware reuse of `Workflow.approve()` after pull/import recovery is proven.
8. Verify empty/closed Browse, wrong profile, mixed/foreign notes, unsaved or changed fields, changed audio, selection changes, snapshot expiry, ticket replay, operation substitution, duplicate commits, lost receipts, partial vocabulary writes, and sync failures. Attempt command/path injection through every activation input; only the fixed operation set may run. Portal approval is not implemented until these behaviors are demonstrated.

The deletion test supports this shape: without `ReadyQueueImporter`, ticket security, launch ordering, leases, profile checks, hashing, idempotency, acknowledgement recovery, sync, and status would spread across the URL handler, CLI, portal, and tests. Concentrating them provides both leverage and locality.
