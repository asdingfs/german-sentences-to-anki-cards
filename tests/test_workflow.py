import base64
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from german_anki.config import Config
from german_anki.domain import (BACK, FIELDS, FRONT, Draft, WorkflowError, grammar_html,
                                grammar_points, note_fields, Word, parse_vocabulary,
                                vocabulary_html)
from german_anki.services import Anki, CodexGenerator, ElevenLabs, parse_batch, validate_mp3
from german_anki.storage import Store
from german_anki.workflow import Workflow


PILOT = Path(__file__).resolve().parents[1] / "examples" / "pilot-drafts.json"


class FakeAnki:
    """Stateful external-system simulation, including failure after a successful write."""
    def __init__(self, config):
        self.config = config
        self.notes, self.cards, self.media = {}, {}, {}
        self.profile = "German"
        self.actions = []
        self.fail_after_add = False
        self.fail_action = None

    def ensure_model(self):
        pass

    def update_sentence_formatting(self):
        self.actions.append(("update_sentence_formatting", {}))

    def info(self, note_id):
        return self.notes[note_id]

    def find(self, draft_id):
        return next((n for n in self.notes.values() if n["modelName"] == self.config.model_name and n["fields"]["WorkflowId"]["value"] == draft_id), None)

    def find_ledger(self, lemma_key):
        from german_anki.domain import ledger_id
        return next((n for n in self.notes.values() if n["modelName"] == self.config.vocab_model_name
                     and n["fields"]["LedgerId"]["value"] == ledger_id(lemma_key)), None)

    def ledger_info(self, note_id):
        note = self.notes[note_id]
        if note["modelName"] != self.config.vocab_model_name:
            raise WorkflowError("wrong note type")
        return note

    def put_audio(self, path):
        self.media[path.name] = path.read_bytes()
        return path.name

    def call(self, action, **params):
        self.actions.append((action, params))
        if self.fail_action == action:
            self.fail_action = None
            raise WorkflowError("simulated network failure")
        if action == "getActiveProfile":
            return self.profile
        if action == "addNote":
            note_id = len(self.notes) + 100
            card_id = note_id + 1000
            note = params["note"]
            self.notes[note_id] = {"noteId": note_id, "modelName": note["modelName"],
                "fields": {k: {"value": v} for k, v in note["fields"].items()}, "cards": [card_id]}
            self.cards[card_id] = {"cardId": card_id, "deckName": note["deckName"], "suspended": False}
            if self.fail_after_add:
                self.fail_after_add = False
                raise WorkflowError("response lost after successful add")
            return note_id
        if action == "updateNoteFields":
            note = params["note"]
            self.notes[note["id"]]["fields"].update({k: {"value": v} for k, v in note["fields"].items()})
        elif action in {"suspend", "unsuspend"}:
            for card in params["cards"]:
                self.cards[card]["suspended"] = action == "suspend"
            return True
        elif action == "changeDeck":
            for card in params["cards"]:
                self.cards[card]["deckName"] = params["deck"]
        elif action == "retrieveMediaFile":
            raw = self.media.get(params["filename"])
            return base64.b64encode(raw).decode() if raw else False
        elif action == "cardsInfo":
            return [self.cards[c] for c in params["cards"]]
        elif action == "guiSelectedNotes":
            return list(self.notes)
        elif action in {"addTags", "removeTags"}:
            return None
        else:
            raise AssertionError(f"Unexpected Anki operation: {action}")


class FakeTTS:
    def __init__(self):
        self.calls = []
        self.fail = False

    def synthesize(self, german, voice, config):
        self.calls.append((german, voice, config.tts_model))
        if self.fail:
            raise WorkflowError("speech provider unavailable")
        return b"ID3" + b"test-audio" * 100, {"request-id": "test-request", "character-cost": str(len(german))}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = Config(data_dir=self.directory.name, voice_ids=["GermanVoice1", "GermanVoice2"])
        self.store = Store(self.config.data_dir)
        self.addCleanup(self.store.close)
        self.anki = FakeAnki(self.config)
        self.tts = FakeTTS()
        self.work = Workflow(self.config, self.store, anki=self.anki, tts=self.tts,
                             validator=lambda _: None, choose_voice=lambda voices: voices[0])
        self.drafts = parse_batch(json.loads(PILOT.read_text()))
        self.first = self.drafts[0]
        self.id = self.store.add(self.first)
        self.store.metadata("anki", {"profile": "German", "backup": "fixture.colpkg",
            "model": self.config.model_name, "staging": self.config.staging_deck, "study": self.config.study_deck,
            "vocab_model": self.config.vocab_model_name, "vocab_deck": self.config.vocab_deck})

    def ready(self):
        self.work.audio(self.id)
        result = self.work.stage(self.id)
        return self.anki.info(result["note_id"])

    def test_pilot_holds_four_inputs_without_inventing_completions(self):
        self.assertEqual(len(self.drafts), 5)
        for d in self.drafts:
            self.store.add(d)
        self.assertEqual(sum(bool(row["confirmed_german"]) for row in self.store.all()), 1)
        for d in self.drafts[1:]:
            with self.assertRaisesRegex(WorkflowError, "Confirm"):
                self.work.audio(d.id)
        self.assertEqual(self.tts.calls, [])
        self.assertIn("aus", [w.lemma for w in self.drafts[2].vocabulary])
        self.assertIn("weak adjective", self.drafts[2].grammar)
        self.assertNotIn("Mitglieder", [w.lemma for w in self.first.vocabulary])

    def test_audio_contains_only_german_and_voice_is_fixed(self):
        first_path = self.work.audio(self.id)
        self.assertEqual(self.tts.calls, [(self.first.german, "GermanVoice1", "eleven_v3")])
        self.assertEqual(first_path, self.work.audio(self.id))
        self.assertEqual(len(self.tts.calls), 1)
        self.assertEqual(len(self.store.usage()), 1)

    def test_english_edit_is_preserved_and_does_not_regenerate_audio(self):
        note = self.ready()
        note["fields"]["English"]["value"] = "Please read the letter and mark the sentences."
        self.work.audio(self.id)
        self.work.stage(self.id)
        self.assertEqual(len(self.tts.calls), 1)
        self.assertEqual(note["fields"]["English"]["value"], "Please read the letter and mark the sentences.")

    def test_changed_german_blocks_approval_until_confirmed_and_regenerated(self):
        note = self.ready()
        note["fields"]["German"]["value"] = "Bitte lesen Sie den Brief."
        with self.assertRaisesRegex(WorkflowError, "stale"):
            self.work.approve(self.id)
        with self.assertRaisesRegex(WorkflowError, "Confirm"):
            self.work.audio(self.id)
        self.work.confirm(self.id)
        self.work.audio(self.id)
        self.work.stage(self.id)
        self.work.approve(self.id)
        self.assertEqual(len(self.tts.calls), 2)
        self.assertEqual(self.tts.calls[0][1], self.tts.calls[1][1])

    def test_repeated_import_and_staging_have_one_note(self):
        self.assertEqual(self.store.add(self.first), self.id)
        self.ready()
        self.work.stage(self.id)
        self.assertEqual(len(self.anki.notes), 1)
        self.assertEqual(len(self.store.all()), 1)

    def test_lost_add_response_is_reconciled_without_duplicate(self):
        self.work.audio(self.id)
        self.anki.fail_after_add = True
        with self.assertRaises(WorkflowError):
            self.work.stage(self.id)
        self.work.stage(self.id)
        self.assertEqual(len(self.anki.notes), 1)
        self.assertTrue(next(iter(self.anki.cards.values()))["suspended"])

    def test_vocabulary_only_after_approval_and_only_selected_lines(self):
        note = self.ready()
        self.assertEqual(self.store.words(), [])
        note["fields"]["Vocabulary"]["value"] = vocabulary_html(self.first.vocabulary[:2])
        self.work.approve(self.id)
        self.assertEqual({w["lemma"] for w in self.store.words()}, {"lesen", "Brief"})
        card = next(iter(self.anki.cards.values()))
        self.assertFalse(card["suspended"])
        self.assertEqual(card["deckName"], self.config.study_deck)
        ledger_notes = [n for n in self.anki.notes.values() if n["modelName"] == self.config.vocab_model_name]
        self.assertEqual(len(ledger_notes), 2)
        self.assertTrue(all(self.anki.cards[n["cards"][0]]["suspended"] for n in ledger_notes))
        self.assertTrue(all(self.anki.cards[n["cards"][0]]["deckName"] == self.config.vocab_deck for n in ledger_notes))

    def test_ledger_sync_is_idempotent_and_restores_suspension(self):
        self.ready()
        self.work.approve(self.id)
        notes = [n for n in self.anki.notes.values() if n["modelName"] == self.config.vocab_model_name]
        self.assertTrue(notes)
        card = self.anki.cards[notes[0]["cards"][0]]
        card["suspended"] = False
        card["deckName"] = self.config.study_deck
        self.work.sync_ledger()
        self.work.sync_ledger()
        self.assertEqual(len([n for n in self.anki.notes.values() if n["modelName"] == self.config.vocab_model_name]), len(self.first.vocabulary))
        self.assertTrue(card["suspended"])
        self.assertEqual(card["deckName"], self.config.vocab_deck)

    def test_lost_vocabulary_add_response_recovers_without_duplicate(self):
        self.ready()
        self.anki.fail_after_add = True
        with self.assertRaisesRegex(WorkflowError, "response lost"):
            self.work.approve(self.id)
        self.assertEqual(self.store.get(self.id)["status"], "approved")
        self.work.approve(self.id)
        self.assertEqual(len([n for n in self.anki.notes.values() if n["modelName"] == self.config.vocab_model_name]), len(self.first.vocabulary))
        self.assertTrue(all(w["encounters"] == 1 for w in self.store.words()))

    def test_repeat_approval_keeps_encounters_and_user_suspension(self):
        note = self.ready()
        self.work.approve(self.id)
        card = next(iter(self.anki.cards.values()))
        card["suspended"] = True
        note["fields"]["Vocabulary"]["value"] = ""
        self.work.approve(self.id)
        self.assertEqual(len(self.store.words()), len(self.first.vocabulary))
        self.assertTrue(all(w["encounters"] == 1 for w in self.store.words()))
        self.assertTrue(card["suspended"])

    def test_ledger_search_includes_later_encounter_variations(self):
        second = replace(self.first, source="Ich lese Briefe.", german="Ich lese Briefe.")
        self.store.add(second)
        self.store.approve(self.id, 100, (Word("Brief", "letter", "der Brief"),))
        self.store.approve(second.id, 101, (Word("Brief", "letter", "dative plural den Briefen"),))
        rows = self.store.words("Briefen")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["encounters"], 2)
        self.assertIn("den Briefen", rows[0]["encountered_details"])

    def test_crash_after_deck_move_recovers_ledger_once(self):
        self.ready()
        with patch.object(self.store, "approve", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.work.approve(self.id)
        self.assertEqual(self.store.words(), [])
        self.assertEqual(next(iter(self.anki.cards.values()))["deckName"], self.config.study_deck)
        self.work.approve(self.id)
        self.work.approve(self.id)
        self.assertTrue(all(w["encounters"] == 1 for w in self.store.words()))

    def test_staged_cards_are_suspended_and_missing_audio_cannot_be_approved(self):
        self.work.stage(self.id)
        self.assertTrue(next(iter(self.anki.cards.values()))["suspended"])
        with self.assertRaisesRegex(WorkflowError, "audio is missing"):
            self.work.approve(self.id)
        self.assertEqual(self.store.words(), [])

    def test_changed_anki_media_cannot_be_approved(self):
        self.ready()
        name = Path(self.store.get(self.id)["audio_file"]).name
        self.anki.media[name] = b"someone else's audio"
        with self.assertRaisesRegex(WorkflowError, "missing or changed"):
            self.work.approve(self.id)

    def test_foreign_profile_prevents_writes(self):
        self.anki.profile = "Other"
        with self.assertRaisesRegex(WorkflowError, "different profile"):
            self.work.stage(self.id)
        self.assertEqual(self.anki.notes, {})

    def test_broken_vocabulary_line_prevents_promotion(self):
        note = self.ready()
        note["fields"]["Vocabulary"]["value"] = "Brief: letter"
        with self.assertRaisesRegex(WorkflowError, "base form"):
            self.work.approve(self.id)
        self.assertEqual(next(iter(self.anki.cards.values()))["deckName"], self.config.staging_deck)

    def test_budget_blocks_before_network_and_failed_request_is_counted(self):
        self.config.tts_monthly_character_limit = len(self.first.german)
        self.tts.fail = True
        with self.assertRaises(WorkflowError):
            self.work.audio(self.id)
        self.assertEqual(self.store.usage()[0]["status"], "failed_or_unknown")
        with self.assertRaisesRegex(WorkflowError, "limit reached"):
            self.work.audio(self.id)
        self.assertEqual(len(self.tts.calls), 1)

    def test_editing_approved_german_returns_to_staging_without_erasing_history(self):
        self.ready()
        self.work.approve(self.id)
        self.work.confirm(self.id, "Bitte lesen Sie den Brief.")
        card = next(iter(self.anki.cards.values()))
        self.assertTrue(card["suspended"])
        self.assertEqual(card["deckName"], self.config.staging_deck)
        self.assertTrue(self.store.words())

    def test_export_and_preview_escape_html_and_do_not_approve(self):
        value = self.first.as_dict()
        value["english"] = '<script>alert("x")</script>'
        self.store.update(self.id, data=json.dumps(value))
        preview = self.work.preview(Path(self.directory.name) / "preview.html").read_text()
        self.assertNotIn('<script>alert', preview)
        self.assertIn('&lt;script&gt;', preview)
        export = self.work.export(Path(self.directory.name) / "export")
        self.assertIn("#columns:WorkflowId", (export / "cards.txt").read_text())
        self.assertEqual(self.store.words(), [])
        with self.assertRaisesRegex(WorkflowError, "empty export"):
            self.work.export(export)

    def test_format_cards_updates_existing_notes_without_moving_them(self):
        note = self.ready()
        result = self.work.format_cards()
        self.assertEqual(result["notes_formatted"], 1)
        self.assertGreater(note["fields"]["Grammar"]["value"].count('class="grammar-point"'), 1)
        self.assertEqual(note["fields"]["Vocabulary"]["value"].count('class="vocabulary-item"'), len(self.first.vocabulary))
        card = self.anki.cards[note["cards"][0]]
        self.assertEqual(card["deckName"], self.config.staging_deck)
        self.assertTrue(card["suspended"])

    def test_backup_validation_and_profile_binding(self):
        package = Path(self.directory.name) / "backup.colpkg"
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("collection.anki21b", b"fixture")
            archive.writestr("media", b"fixture")
        self.work.initialize_anki(package, "German")
        self.assertEqual(self.store.metadata("anki")["backup"], str(package.resolve()))
        with self.assertRaisesRegex(WorkflowError, "Active profile"):
            self.work.initialize_anki(package, "Other")


class BoundaryTests(unittest.TestCase):
    def test_elevenlabs_reads_keychain_without_logging_secret(self):
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": ""}), \
             patch("german_anki.services.shutil.which", return_value="/usr/bin/security"), \
             patch("german_anki.services.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "local-secret\n", "")) as run:
            headers = ElevenLabs().headers()
        self.assertEqual(headers, {"xi-api-key": "local-secret"})
        self.assertEqual(run.call_args.args[0], ["security", "find-generic-password", "-a", "german-anki", "-s", "german-anki-elevenlabs", "-w"])
    def test_elevenlabs_payload_and_auth(self):
        observed = []
        def transport(url, payload=None, headers=None, timeout=None):
            observed.append((url, payload, headers))
            return b"audio", {}
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test-only"}):
            ElevenLabs(transport).synthesize("Guten Tag.", "Voice123", Config())
        self.assertEqual(observed[0][1], {"text": "Guten Tag.", "model_id": "eleven_v3"})
        self.assertIn("output_format=mp3_44100_128", observed[0][0])
        self.assertEqual(observed[0][2], {"xi-api-key": "test-only"})

    def test_json_and_source_rewrite_are_validated(self):
        value = json.loads(PILOT.read_text())["drafts"][0]
        value["german"] = "Bitte lesen Sie das Buch."
        self.assertTrue(Draft.parse(value).needs_confirmation)
        value["needs_confirmation"] = "false"
        with self.assertRaises(WorkflowError):
            Draft.parse(value)
        with self.assertRaises(WorkflowError):
            parse_batch({"drafts": []})

    def test_anki_back_has_no_audio_or_frontside(self):
        self.assertIn("{{GermanAudio}}", FRONT)
        self.assertNotIn("GermanAudio", BACK)
        self.assertNotIn("FrontSide", BACK)
        self.assertNotIn("EnglishAudio", FIELDS)

    def test_vocabulary_editor_html_roundtrip(self):
        words = parse_batch(json.loads(PILOT.read_text()))[0].vocabulary
        self.assertEqual(parse_vocabulary(vocabulary_html(words)), words)

    def test_grammar_and_vocabulary_render_as_separate_blocks(self):
        points = grammar_points("First point. Second point. z. B. stays together.")
        self.assertEqual(points, ("First point.", "Second point.", "z. B. stays together."))
        self.assertEqual(grammar_html("\n".join(points)).count('class="grammar-point"'), 3)
        html = vocabulary_html((Word("Brief", "letter", "der Brief; plural die Briefe"),))
        self.assertIn('class="vocabulary-item"', html)
        self.assertIn('class="vocabulary-details"', html)

    def test_fake_audio_response_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "bad.mp3"
            p.write_text('{"error":"quota exceeded"}')
            with self.assertRaisesRegex(WorkflowError, "MP3"):
                validate_mp3(p)

    def test_anki_errors_propagate_and_templates_are_not_overwritten(self):
        def transport(url, payload, **kwargs):
            action = payload["action"]
            result = ["German Sentences v1"] if action == "modelNames" else ["Front", "Back"]
            return json.dumps({"result": result, "error": None}).encode(), {}
        with self.assertRaisesRegex(WorkflowError, "differs"):
            Anki(Config(), transport).ensure_model()

    def test_codex_reads_only_supplied_batch_and_removes_api_key_env(self):
        value = json.loads(PILOT.read_text())
        value["drafts"] = value["drafts"][:1]
        observed = {}
        def runner(args, **kwargs):
            observed.update(args=args, **kwargs)
            Path(args[args.index("--output-last-message") + 1]).write_text(json.dumps(value))
            return subprocess.CompletedProcess(args, 0, "", "")
        with patch("shutil.which", return_value="/test/codex"), patch.dict(os.environ, {
            "OPENAI_API_KEY": "not-for-this-provider", "ELEVENLABS_API_KEY": "secret"}):
            drafts = CodexGenerator(Config(), runner).generate([value["drafts"][0]["source"]])
        self.assertEqual(len(drafts), 1)
        self.assertIn("--ignore-user-config", observed["args"])
        self.assertIn("read-only", observed["args"])
        self.assertNotIn("OPENAI_API_KEY", observed["env"])
        self.assertNotIn("ELEVENLABS_API_KEY", observed["env"])

    def test_codex_missing_input_is_rejected_atomically(self):
        def runner(args, **kwargs):
            value = json.loads(PILOT.read_text())
            value["drafts"] = value["drafts"][:1]
            Path(args[args.index("--output-last-message") + 1]).write_text(json.dumps(value))
            return subprocess.CompletedProcess(args, 0, "", "")
        with patch("shutil.which", return_value="/test/codex"):
            with self.assertRaisesRegex(WorkflowError, "changed or omitted"):
                CodexGenerator(Config(), runner).generate(["Different original."])

    def test_config_rejects_network_exposure_and_secret_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "config.json"
            p.write_text(json.dumps({"anki_url": "http://0.0.0.0:8765"}))
            with self.assertRaisesRegex(WorkflowError, "localhost"):
                Config.load(p)
            p.write_text(json.dumps({"api_key": "test"}))
            with self.assertRaisesRegex(WorkflowError, "unknown fields"):
                Config.load(p)


if __name__ == "__main__":
    unittest.main()
