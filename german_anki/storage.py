"""Local state and the append-only encountered-vocabulary ledger."""

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import sqlite3
import uuid

from .domain import Draft, WorkflowError


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, directory):
        self.root = Path(directory).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "audio").mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.root / "vocabulary.sqlite3")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS drafts (
          id TEXT PRIMARY KEY, data TEXT NOT NULL, confirmed_german TEXT,
          voice_id TEXT, audio_key TEXT, audio_file TEXT, note_id INTEGER UNIQUE,
          status TEXT NOT NULL DEFAULT 'draft', updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS usage (
          id TEXT PRIMARY KEY, draft_id TEXT NOT NULL REFERENCES drafts(id),
          created_at TEXT NOT NULL, characters INTEGER NOT NULL,
          estimated_usd REAL NOT NULL, status TEXT NOT NULL,
          request_id TEXT, reported_cost TEXT);
        CREATE INDEX IF NOT EXISTS usage_by_month ON usage(created_at);
        CREATE TABLE IF NOT EXISTS vocabulary (
          lemma_key TEXT PRIMARY KEY, lemma TEXT NOT NULL, meaning TEXT NOT NULL,
          details TEXT NOT NULL, first_encountered TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS encounters (
          draft_id TEXT NOT NULL REFERENCES drafts(id),
          lemma_key TEXT NOT NULL REFERENCES vocabulary(lemma_key),
          note_id INTEGER NOT NULL, meaning TEXT NOT NULL, details TEXT NOT NULL,
          encountered_at TEXT NOT NULL, PRIMARY KEY(draft_id, lemma_key));
        CREATE INDEX IF NOT EXISTS encounters_by_lemma ON encounters(lemma_key);
        ''')

    def close(self):
        self.db.close()

    @contextmanager
    def lock(self):
        with (self.root / "workflow.lock").open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise WorkflowError("Another workflow command is running. Wait for it to finish.") from exc
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def metadata(self, key, value=None):
        if value is not None:
            with self.db:
                self.db.execute("INSERT OR REPLACE INTO metadata VALUES (?, ?)", (key, json.dumps(value)))
        row = self.db.execute("SELECT value FROM metadata WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def add(self, draft: Draft):
        with self.db:
            self.db.execute('''INSERT OR IGNORE INTO drafts
                (id, data, confirmed_german, updated_at) VALUES (?, ?, ?, ?)''',
                (draft.id, json.dumps(draft.as_dict(), ensure_ascii=False),
                 None if draft.needs_confirmation or draft.warnings else draft.german, now()))
        return draft.id

    def get(self, draft_id):
        row = self.db.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        if not row:
            raise WorkflowError(f"Unknown draft: {draft_id}")
        return dict(row)

    def draft(self, draft_id):
        return Draft.parse(json.loads(self.get(draft_id)["data"]))

    def update(self, draft_id, **changes):
        allowed = {"data", "confirmed_german", "voice_id", "audio_key", "audio_file", "note_id", "status"}
        if not changes or set(changes) - allowed:
            raise ValueError("Invalid draft state update")
        with self.db:
            self.db.execute(f"UPDATE drafts SET {', '.join(k + ' = ?' for k in changes)}, updated_at = ? WHERE id = ?",
                            (*changes.values(), now(), draft_id))

    def all(self):
        return [dict(row) for row in self.db.execute("SELECT * FROM drafts ORDER BY updated_at, id")]

    def reserve_usage(self, draft_id, characters, rate, limit):
        month = now()[:7]
        used = self.db.execute("SELECT COALESCE(SUM(characters), 0) FROM usage WHERE created_at LIKE ?",
                               (month + "%",)).fetchone()[0]
        if used + characters > limit:
            raise WorkflowError(f"Monthly TTS limit reached: {used}/{limit} characters reserved. Adjust the limit in config only if intended.")
        request = uuid.uuid4().hex
        # Commit before the network call; unknown outcomes still consume local allowance.
        with self.db:
            self.db.execute("INSERT INTO usage VALUES (?, ?, ?, ?, ?, 'reserved', NULL, NULL)",
                            (request, draft_id, now(), characters, characters / 1000 * rate))
        return request

    def finish_usage(self, request, status, request_id=None, cost=None):
        with self.db:
            self.db.execute("UPDATE usage SET status=?, request_id=?, reported_cost=? WHERE id=?",
                            (status, request_id, cost, request))

    def usage(self):
        return [dict(row) for row in self.db.execute("SELECT * FROM usage ORDER BY created_at")]

    def approve(self, draft_id, note_id, words):
        # Anki promotion happens first. Re-running approval completes this transaction
        # after a crash; unique indexes preserve earlier encounters and prevent doubles.
        with self.db:
            for word in words:
                self.db.execute("INSERT OR IGNORE INTO vocabulary VALUES (?, ?, ?, ?, ?)",
                                (word.key, word.lemma, word.meaning, word.details, now()))
                self.db.execute("INSERT OR IGNORE INTO encounters VALUES (?, ?, ?, ?, ?, ?)",
                                (draft_id, word.key, note_id, word.meaning, word.details, now()))
            self.db.execute("UPDATE drafts SET status='approved', note_id=?, updated_at=? WHERE id=?",
                            (note_id, now(), draft_id))

    def words(self, query=""):
        # Instr treats user text literally; it is not interpolated SQL or a LIKE pattern.
        return [dict(row) for row in self.db.execute('''
            SELECT v.*, COUNT(e.draft_id) AS encounters,
                   GROUP_CONCAT(DISTINCT e.details) AS encountered_details FROM vocabulary v
            JOIN encounters e USING (lemma_key)
            WHERE instr(v.lemma_key, ?) > 0 OR instr(lower(v.meaning || ' ' || v.details), ?) > 0
              OR EXISTS (SELECT 1 FROM encounters search WHERE search.lemma_key = v.lemma_key
                         AND instr(lower(search.meaning || ' ' || search.details), ?) > 0)
            GROUP BY v.lemma_key ORDER BY v.lemma_key''', (query.casefold(), query.casefold(), query.casefold()))]

    def word_sources(self, lemma_key):
        rows = self.db.execute('''SELECT d.data FROM encounters e JOIN drafts d ON d.id = e.draft_id
                                  WHERE e.lemma_key = ? ORDER BY e.encountered_at, e.draft_id''',
                               (lemma_key,)).fetchall()
        return [json.loads(row[0])["german"] for row in rows]

    def word_details(self, lemma_key):
        rows = self.db.execute('''SELECT DISTINCT details FROM encounters
                                  WHERE lemma_key = ? ORDER BY encountered_at, details''',
                               (lemma_key,)).fetchall()
        return [row[0] for row in rows if row[0]]
