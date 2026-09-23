"""Application operations; all Anki writes concern explicitly owned notes."""

import base64
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import shutil
import zipfile

from .domain import (BACK, CSS, FRONT, Draft, WorkflowError, digest, grammar_html, ledger_id,
                     normalized, note_fields, parse_vocabulary, plain, rich, vocabulary_html)
from .services import Anki, ElevenLabs, validate_mp3


def audio_identity(german, voice, config):
    return digest({"text": normalized(german), "voice": voice,
                   "model": config.tts_model, "format": config.tts_output_format})


class Workflow:
    def __init__(self, config, store, *, anki=None, tts=None, validator=validate_mp3,
                 choose_voice=None):
        import secrets
        self.config, self.store = config, store
        self.anki = anki or Anki(config)
        self.tts = tts or ElevenLabs()
        self.validator = validator
        self.choose_voice = choose_voice or secrets.choice

    def initialize_anki(self, backup, profile):
        path = Path(backup).resolve()
        if not path.is_file() or path.suffix != ".colpkg":
            raise WorkflowError("Export the whole Anki collection with media to a .colpkg file first.")
        try:
            with zipfile.ZipFile(path) as package:
                names = set(package.namelist())
                if not any(n.startswith("collection.anki") for n in names) or "media" not in names or package.testzip():
                    raise WorkflowError("Backup must contain an intact collection and media manifest.")
        except zipfile.BadZipFile as exc:
            raise WorkflowError("The collection backup is not a valid Anki package.") from exc
        active = self.anki.call("getActiveProfile")
        if active != profile:
            raise WorkflowError(f"Active profile is {active!r}, not {profile!r}. Select the intended profile in Anki.")
        existing = self.store.metadata("anki")
        if existing and existing["profile"] != profile:
            raise WorkflowError("This local ledger is already bound to another Anki profile. Use a separate data_dir.")
        self.anki.ensure_model()
        self.store.metadata("anki", {"profile": profile, "backup": str(path),
                                     "model": self.config.model_name,
                                     "staging": self.config.staging_deck, "study": self.config.study_deck,
                                     "vocab_model": self.config.vocab_model_name,
                                     "vocab_deck": self.config.vocab_deck})
        return {"profile": profile, "backup": str(path), "model": self.config.model_name,
                "vocab_model": self.config.vocab_model_name, "vocab_deck": self.config.vocab_deck}

    def check_anki(self):
        setup = self.store.metadata("anki")
        if not setup:
            raise WorkflowError("Run init-anki with a collection backup before creating or updating Anki notes.")
        if self.anki.call("getActiveProfile") != setup["profile"]:
            raise WorkflowError("Anki is using a different profile from this workflow's ledger.")
        if (setup["model"], setup["staging"], setup["study"]) != (
                self.config.model_name, self.config.staging_deck, self.config.study_deck):
            raise WorkflowError("Anki configuration changed. Run init-anki again before writing.")
        if (setup.get("vocab_model"), setup.get("vocab_deck")) != (
                self.config.vocab_model_name, self.config.vocab_deck):
            raise WorkflowError("Vocabulary note type/deck not initialized. Run init-anki again with a collection backup.")

    def _note(self, draft_id):
        row = self.store.get(draft_id)
        note = self.anki.find(draft_id)
        if note:
            if plain(note["fields"]["WorkflowId"]["value"]) != draft_id:
                raise WorkflowError("Anki note identity does not match the local draft.")
            if row["note_id"] and note["noteId"] != row["note_id"]:
                raise WorkflowError("Anki note identity changed. Resolve the mismatch before proceeding.")
            if normalized(plain(note["fields"]["Source"]["value"])) != normalized(self.store.draft(draft_id).source):
                raise WorkflowError("The source field was edited. Restore the original source to preserve identity.")
        elif row["note_id"]:
            raise WorkflowError("The staged note was removed from Anki. Do not recreate it implicitly; restore it or use a fresh data directory.")
        return note

    def refresh(self, draft_id):
        """Read the user's Anki edits before generating or approving; never overwrite them."""
        self.check_anki()
        note = self._note(draft_id)
        if note:
            draft = self.store.draft(draft_id)
            f = note["fields"]
            value = draft.as_dict()
            value.update(german=normalized(plain(f["German"]["value"])),
                         english=plain(f["English"]["value"]), grammar=plain(f["Grammar"]["value"]),
                         vocabulary=[w.__dict__ for w in parse_vocabulary(f["Vocabulary"]["value"])])
            edited = Draft.parse(value)
            self.store.update(draft_id, data=json.dumps(edited.as_dict(), ensure_ascii=False), note_id=note["noteId"])
        return note

    def confirm(self, draft_id, german=None):
        row = self.store.get(draft_id)
        if row["note_id"]:
            self.refresh(draft_id)
        draft = self.store.draft(draft_id)
        value = draft.as_dict()
        value.update(german=normalized(german or draft.german), needs_confirmation=False, warnings=[])
        updated = Draft.parse(value)
        if row["note_id"]:
            note = self.anki.info(row["note_id"])
            self.anki.call("suspend", cards=note["cards"])
            self.anki.call("changeDeck", cards=note["cards"], deck=self.config.staging_deck)
            self.anki.call("updateNoteFields", note={"id": row["note_id"], "fields": {
                "German": rich(updated.german), "GermanAudio": "", "Status": "confirmed; audio pending"}})
            self.anki.call("removeTags", notes=[row["note_id"]], tags="german_workflow::approved")
            self.anki.call("addTags", notes=[row["note_id"]], tags="german_workflow::staging")
        self.store.update(draft_id, data=json.dumps(updated.as_dict(), ensure_ascii=False),
                          confirmed_german=updated.german, status="draft")
        return updated

    def audio(self, draft_id):
        row = self.store.get(draft_id)
        if row["note_id"]:
            self.refresh(draft_id)
        row = self.store.get(draft_id)
        draft = self.store.draft(draft_id)
        if normalized(row["confirmed_german"] or "") != normalized(draft.german):
            raise WorkflowError("Confirm the exact German front before generating audio: confirm ID --german '…'")
        voice = row["voice_id"]
        if not voice:
            if not self.config.voice_ids:
                raise WorkflowError("Add auditioned German voice IDs to config.local.json before generating audio.")
            voice = self.choose_voice(self.config.voice_ids)
            self.store.update(draft_id, voice_id=voice)
        key = audio_identity(draft.german, voice, self.config)
        path = self.store.root / "audio" / f"de_{key}.mp3"
        if path.exists():
            self.validator(path)
        else:
            # Fail before reservation when the credential is absent.
            if isinstance(self.tts, ElevenLabs):
                self.tts.headers()
            request_id = self.store.reserve_usage(draft_id, len(normalized(draft.german)),
                self.config.tts_usd_per_1000_characters, self.config.tts_monthly_character_limit)
            try:
                raw, headers = self.tts.synthesize(normalized(draft.german), voice, self.config)
                temp = path.with_suffix(".part")
                temp.write_bytes(raw)
                self.validator(temp)
                temp.replace(path)
                headers = {k.lower(): v for k, v in headers.items()}
                self.store.finish_usage(request_id, "complete", headers.get("request-id"), headers.get("character-cost"))
            except Exception:
                self.store.finish_usage(request_id, "failed_or_unknown")
                raise
        self.store.update(draft_id, audio_key=key, audio_file=str(path))
        return path

    def _valid_audio(self, draft_id, draft):
        row = self.store.get(draft_id)
        if not row["voice_id"] or not row["audio_file"] or not row["audio_key"]:
            return None
        if normalized(row["confirmed_german"] or "") != normalized(draft.german):
            return None
        if row["audio_key"] != audio_identity(draft.german, row["voice_id"], self.config):
            return None
        path = Path(row["audio_file"])
        if not path.is_file():
            return None
        self.validator(path)
        return path

    def stage(self, draft_id):
        self.check_anki()
        note = self.refresh(draft_id)
        row = self.store.get(draft_id)
        if row["status"] == "approved":
            return {"id": draft_id, "note_id": row["note_id"], "status": "approved; unchanged"}
        draft = self.store.draft(draft_id)
        audio = self._valid_audio(draft_id, draft)
        status = "ready for review" if audio else "HOLD: " + "; ".join(draft.warnings or ("German confirmation or audio pending",))
        sound = ""
        if audio:
            uploaded = self.anki.put_audio(audio)
            if uploaded != audio.name:
                raise WorkflowError("Anki returned an unexpected audio filename.")
            sound = f"[sound:{uploaded}]"
        if note:
            # Respect all user edits; only derived media/status fields are refreshed.
            self.anki.call("updateNoteFields", note={"id": note["noteId"], "fields": {
                "GermanAudio": sound, "VoiceId": row["voice_id"] or "", "Status": status}})
            note_id = note["noteId"]
        else:
            note_id = self.anki.call("addNote", note={
                "deckName": self.config.staging_deck, "modelName": self.config.model_name,
                "fields": note_fields(draft, audio=sound, voice=row["voice_id"] or "", status=status),
                "options": {"allowDuplicate": False, "duplicateScope": "collection"},
                "tags": ["german_workflow", "german_workflow::staging"]})
        # Store ID before suspension so interrupted creation is recoverable by lookup.
        self.store.update(draft_id, note_id=note_id, status="staged")
        note = self.anki.info(note_id)
        self.anki.call("suspend", cards=note["cards"])
        return {"id": draft_id, "note_id": note_id, "status": status}

    def approve(self, draft_id):
        self.check_anki()
        note = self.refresh(draft_id)
        if not note:
            raise WorkflowError("Stage and review this draft in Anki before approval.")
        row = self.store.get(draft_id)
        draft = self.store.draft(draft_id)
        if not draft.english.strip() or not draft.grammar.strip():
            raise WorkflowError("Fill in the English meaning and grammar before approval.")
        path = self._valid_audio(draft_id, draft)
        if not path:
            raise WorkflowError("German audio is missing or stale. Confirm the edited German, generate audio, and stage again.")
        fields = note["fields"]
        if fields["GermanAudio"]["value"] != f"[sound:{path.name}]" or plain(fields["VoiceId"]["value"]) != row["voice_id"]:
            raise WorkflowError("The Anki audio/voice differs from this draft. Stage again to attach the matching clip.")
        media = self.anki.call("retrieveMediaFile", filename=path.name)
        try:
            match = media is not False and sha256(base64.b64decode(media, validate=True)).digest() == sha256(path.read_bytes()).digest()
        except (ValueError, TypeError):
            match = False
        if not match:
            raise WorkflowError("Anki's audio file is missing or changed. Stage again to repair it.")
        cards = self.anki.call("cardsInfo", cards=note["cards"])
        if len(cards) != 1 or cards[0]["deckName"] not in {self.config.staging_deck, self.config.study_deck}:
            raise WorkflowError("Expected one workflow card in Staging or Study; resolve the deck/template mismatch first.")
        already_approved = row["status"] == "approved"
        self.store.update(draft_id, status="promoting")
        self.anki.call("updateNoteFields", note={"id": note["noteId"], "fields": {
            "BaseForms": rich("; ".join(w.lemma for w in draft.vocabulary)), "Status": "approved"}})
        self.anki.call("changeDeck", cards=note["cards"], deck=self.config.study_deck)
        # Preserve a user's later suspension on repeat approval.
        if not already_approved:
            self.anki.call("unsuspend", cards=note["cards"])
        self.anki.call("removeTags", notes=[note["noteId"]], tags="german_workflow::staging")
        self.anki.call("addTags", notes=[note["noteId"]], tags="german_workflow::approved")
        self.store.approve(draft_id, note["noteId"], draft.vocabulary)
        for word in draft.vocabulary:
            self.sync_word(word.key)
        return {"id": draft_id, "note_id": note["noteId"], "status": "approved", "vocabulary": len(draft.vocabulary)}

    def sync_word(self, lemma_key):
        """Mirror an approved base form into a searchable, never-studied Anki note."""
        words = [w for w in self.store.words() if w["lemma_key"] == lemma_key]
        if len(words) != 1:
            raise WorkflowError("Vocabulary ledger entry is missing; cannot sync Anki note.")
        word = words[0]
        details = self.store.word_details(lemma_key)
        fields = {"LedgerId": ledger_id(lemma_key), "BaseForm": rich(word["lemma"]),
                  "Meaning": rich(word["meaning"]), "Details": rich("; ".join(details)),
                  "Encounters": str(word["encounters"]),
                  "SourceSentences": rich("\n".join(self.store.word_sources(lemma_key)))}
        note = self.anki.find_ledger(lemma_key)
        if note:
            if plain(note["fields"]["LedgerId"]["value"]) != fields["LedgerId"]:
                raise WorkflowError("Vocabulary note identity mismatch; resolve it in Anki Browse.")
            self.anki.call("updateNoteFields", note={"id": note["noteId"], "fields": fields})
            note_id = note["noteId"]
        else:
            note_id = self.anki.call("addNote", note={
                "deckName": self.config.vocab_deck, "modelName": self.config.vocab_model_name,
                "fields": fields, "options": {"allowDuplicate": False, "duplicateScope": "collection"},
                "tags": ["german_workflow", "german_workflow::vocabulary"]})
        note = self.anki.ledger_info(note_id)
        if len(note["cards"]) != 1:
            raise WorkflowError("Expected one vocabulary card; resolve the note template mismatch.")
        cards = self.anki.call("cardsInfo", cards=note["cards"])
        if cards[0]["deckName"] != self.config.vocab_deck:
            self.anki.call("changeDeck", cards=note["cards"], deck=self.config.vocab_deck)
        self.anki.call("suspend", cards=note["cards"])
        return note_id

    def sync_ledger(self):
        self.check_anki()
        words = self.store.words()
        for word in words:
            self.sync_word(word["lemma_key"])
        return {"vocabulary_notes_synced": len(words), "deck": self.config.vocab_deck,
                "review_state": "suspended"}

    def format_cards(self):
        """Apply readable layout to the note type and all workflow-owned sentence notes."""
        self.check_anki()
        self.anki.update_sentence_formatting()
        updated = 0
        for row in self.store.all():
            if not row["note_id"]:
                continue
            self.refresh(row["id"])
            draft = self.store.draft(row["id"])
            self.anki.call("updateNoteFields", note={"id": row["note_id"], "fields": {
                "Grammar": grammar_html(draft.grammar),
                "Vocabulary": vocabulary_html(draft.vocabulary)}})
            self.refresh(row["id"])
            updated += 1
        return {"note_type": self.config.model_name, "notes_formatted": updated,
                "grammar": "one point per block", "vocabulary": "one word per block"}

    def selected_ids(self):
        self.check_anki()
        ids = []
        for note_id in self.anki.call("guiSelectedNotes"):
            note = self.anki.info(note_id)
            if note["modelName"] != self.config.model_name:
                raise WorkflowError("Select only German sentence staging notes, not vocabulary notes.")
            draft_id = plain(note["fields"]["WorkflowId"]["value"])
            self.store.get(draft_id)
            ids.append(draft_id)
        if not ids:
            raise WorkflowError("Select the reviewed notes in Anki Browse first.")
        return ids

    def preview(self, path):
        sections = []
        for row in self.store.all():
            draft = self.store.draft(row["id"])
            f = note_fields(draft)
            front = FRONT.replace("{{German}}", f["German"]).replace("{{GermanAudio}}", "")
            audio = self._valid_audio(row["id"], draft)
            if audio:
                front += '<audio controls src="data:audio/mpeg;base64,' + base64.b64encode(audio.read_bytes()).decode() + '"></audio>'
            else:
                front += '<p class="pending">German audio pending</p>'
            back = BACK.replace("{{#Vocabulary}}", "").replace("{{/Vocabulary}}", "")
            for field, content in f.items():
                back = back.replace("{{" + field + "}}", content)
            warnings = " · ".join(draft.warnings)
            sections.append(f'<article><div class="meta">{row["id"]} · {escape(row["status"])}</div>'
                            f'<div class="card">{front}<details><summary>Show meaning and grammar</summary>{back}</details></div>'
                            f'<p class="pending">{escape(warnings)}</p></article>')
        document = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
        document += '<title>German sentence drafts</title><style>' + CSS + '''
        body { background:#e9eee7; margin:0; padding:32px 18px; font-family:Arial,sans-serif; }
        main { max-width:820px; margin:auto; } h1 { color:#20312d; font-size:32px; }
        article { margin:24px 0; } .card { border-radius:18px; box-shadow:0 3px 18px #00000008; }
        .meta, .pending { font-size:13px; color:#6d6250; margin:12px 4px; }
        summary { cursor:pointer; color:#355e50; padding:20px 0 8px; } audio { width:100%; }
        </style><main><h1>German sentence drafts</h1><p>Preview only. Review and approve study cards in Anki.</p>'''
        document += "".join(sections) + "</main></html>"
        target = Path(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(document, encoding="utf-8")
        return target

    def export(self, directory):
        """Anki text-plus-media fallback, using the same stable first field."""
        target = Path(directory).resolve()
        if target.exists() and any(target.iterdir()):
            raise WorkflowError("Choose an empty export directory to preserve earlier exports.")
        target.mkdir(parents=True, exist_ok=True)
        media = target / "media"
        media.mkdir(exist_ok=True)
        lines = ["#separator:tab", "#html:true", f"#notetype:{self.config.model_name}",
                 f"#deck:{self.config.staging_deck}", "#tags:german_workflow german_workflow::staging"]
        from .domain import FIELDS
        lines.append("#columns:" + "\t".join(FIELDS))
        for row in self.store.all():
            if row["status"] == "approved":
                continue
            draft = self.store.draft(row["id"])
            audio = self._valid_audio(row["id"], draft)
            if audio:
                shutil.copy2(audio, media / audio.name)
            f = note_fields(draft, audio=f"[sound:{audio.name}]" if audio else "",
                            voice=row["voice_id"] or "", status="draft; review required")
            lines.append("\t".join(f[k].replace("\t", " ") for k in FIELDS))
        (target / "cards.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (target / "note-type.json").write_text(json.dumps({"name": self.config.model_name, "fields": FIELDS,
            "front": FRONT, "back": BACK, "css": CSS}, ensure_ascii=False, indent=2), encoding="utf-8")
        (target / "IMPORT.md").write_text(
            "Create the note type from note-type.json (same field order and templates). Copy media/* into Anki's collection.media folder. "
            "Import cards.txt as tab-separated HTML; match existing notes using WorkflowId. Suspend imported staging cards in Browse. "
            "For tracked approval, later connect Anki-Connect, run init-anki, then stage/approve the same local drafts. "
            "Manual Change Deck alone does not update the SQLite ledger.\n", encoding="utf-8")
        return target
