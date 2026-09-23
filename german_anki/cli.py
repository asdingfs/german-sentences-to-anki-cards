"""Small command-line entry point; use `python3 -m german_anki --help`."""

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from .config import Config
from .domain import WorkflowError, digest, normalized, schema
from .services import Anki, CodexGenerator, ElevenLabs, GENERATION_PROMPT, keychain_key, parse_batch
from .storage import Store
from .workflow import Workflow


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def parser():
    root = argparse.ArgumentParser(description="German sentences → reviewed Anki cards. German-only ElevenLabs v3 audio.")
    root.add_argument("--config", help="JSON settings file; defaults to config.local.json")
    root.add_argument("--data-dir", help="Override local database/audio directory")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Write a local settings file, without secrets")
    commands.add_parser("doctor", help="Check Codex, Anki-Connect, and TTS setup without writing to Anki")
    p = commands.add_parser("init-anki", help="Create workflow decks/note type after verifying a collection backup")
    p.add_argument("--backup", required=True, help="Whole-collection .colpkg export including media")
    p.add_argument("--profile", required=True)
    for name in ("draft", "run"):
        p = commands.add_parser(name, help="Generate drafts using your ChatGPT/Codex login" if name == "draft" else "Paste → generate → German audio → Anki staging")
        source = p.add_mutually_exclusive_group()
        source.add_argument("--text", help="One German sentence")
        source.add_argument("--file", help="UTF-8 text file, one input per non-empty line")
        source.add_argument("--clipboard", action="store_true", help="Read pasted class sentences from the Mac clipboard")
    p = commands.add_parser("import-drafts", help="Import validated JSON drafts generated in this conversation")
    p.add_argument("file")
    commands.add_parser("list", help="Show local drafts and their states")
    p = commands.add_parser("show", help="Show the structured draft and confirmation state")
    p.add_argument("id")
    p = commands.add_parser("confirm", help="Confirm exact German; edited study cards return to staging for review")
    p.add_argument("id")
    p.add_argument("--german", help="Corrected exact German, or omit to confirm the current draft/Anki text")
    for name in ("audio", "stage", "approve"):
        p = commands.add_parser(name, help={"audio": "Generate/reuse German audio", "stage": "Attach drafts/audio to suspended Anki staging notes", "approve": "Promote reviewed Anki notes and record vocabulary"}[name])
        ids = p.add_mutually_exclusive_group(required=True)
        ids.add_argument("--id", help="Draft ID or unique prefix")
        if name == "approve":
            ids.add_argument("--selected", action="store_true", help="Approve notes selected in Anki Browse")
        else:
            ids.add_argument("--all", action="store_true", help="Process unapproved drafts")
    commands.add_parser("review", help="Open staging notes in Anki Browse")
    commands.add_parser("review-vocabulary", help="Open the searchable, suspended vocabulary deck in Anki Browse")
    commands.add_parser("sync-ledger", help="Reconcile approved base forms into suspended vocabulary notes")
    commands.add_parser("format-cards", help="Apply spaced grammar/vocabulary layout to sentence notes")
    commands.add_parser("sync", help="Ask Anki desktop to sync with your existing account")
    p = commands.add_parser("preview", help="Generate a local HTML front/back preview")
    p.add_argument("--output", default=".runtime/preview.html")
    p = commands.add_parser("export", help="Create a text-plus-media import fallback")
    p.add_argument("directory")
    p = commands.add_parser("vocabulary", help="Search approved base forms and their descriptions")
    p.add_argument("query", nargs="?", default="")
    commands.add_parser("voices", help="List account voices to audition (requires ElevenLabs key)")
    commands.add_parser("usage", help="Show TTS usage reservations and estimated cost")
    commands.add_parser("schema", help="Print the JSON schema for conversation-generated drafts")
    commands.add_parser("prompt", help="Print instructions for generating drafts in this conversation")
    return root


def resolve(store, prefix):
    matches = [r["id"] for r in store.all() if r["id"].startswith(prefix)]
    if len(matches) != 1:
        raise WorkflowError("Draft ID must match exactly one record. Use list to find it.")
    return matches[0]


def inputs(args):
    if args.text is not None:
        return [args.text.strip()]
    if args.file:
        raw = Path(args.file).read_text(encoding="utf-8")
    elif args.clipboard:
        if not shutil.which("pbpaste"):
            raise WorkflowError("Clipboard input needs macOS; use --text or --file instead.")
        raw = subprocess.run(["pbpaste"], capture_output=True, text=True, check=True).stdout
    elif sys.stdin.isatty():
        print("Paste one German input per line. Finish with an empty line:", file=sys.stderr)
        lines = []
        while True:
            try:
                line = input()
            except EOFError:
                break
            if not line.strip():
                break
            lines.append(line)
        raw = "\n".join(lines)
    else:
        raw = sys.stdin.read()
    return [line.strip() for line in raw.splitlines() if line.strip()]


def generate(args, config, store):
    sentences = inputs(args)
    if not sentences:
        raise WorkflowError("No German text supplied.")
    existing = {r["id"] for r in store.all()}
    pending = list(dict.fromkeys(s for s in sentences if digest(normalized(s))[:24] not in existing))
    if pending:
        print(f"Generating {len(pending)} drafts through your ChatGPT/Codex login…", file=sys.stderr)
        drafts = CodexGenerator(config).generate(pending, [w["lemma"] for w in store.words()])
        for draft in drafts:
            store.add(draft)
    return list(dict.fromkeys(digest(normalized(s))[:24] for s in sentences))


def doctor(config):
    checks = {"python": sys.version.split()[0], "codex": shutil.which(config.codex_command),
              "elevenlabs_key_configured": bool(os.environ.get("ELEVENLABS_API_KEY") or keychain_key()),
              "voice_ids_configured": len(config.voice_ids), "tts_model": config.tts_model,
              "monthly_tts_character_limit": config.tts_monthly_character_limit,
              "audio_decoder": shutil.which("ffprobe") or shutil.which("afinfo")}
    if checks["codex"]:
        status = subprocess.run([config.codex_command, "login", "status"], capture_output=True, text=True, timeout=20)
        message = status.stdout + status.stderr
        checks["codex_chatgpt_login"] = status.returncode == 0 and "ChatGPT" in message
    try:
        anki = Anki(config)
        checks["anki_version"] = anki.call("version")
        checks["anki_profile"] = anki.call("getActiveProfile")
    except WorkflowError as exc:
        checks["anki_error"] = str(exc)
    emit(checks)
    return 0 if "anki_version" in checks and checks.get("codex_chatgpt_login") and checks["elevenlabs_key_configured"] and checks["voice_ids_configured"] else 1


def main(argv=None):
    args = parser().parse_args(argv)
    store = None
    try:
        if args.command == "init":
            target = Path(args.config or "config.local.json")
            if target.exists():
                raise WorkflowError(f"Settings already exist: {target}")
            target.write_text(json.dumps(asdict(Config()), indent=2) + "\n", encoding="utf-8")
            print(f"Created {target.resolve()}. Add voice IDs; keep API keys in macOS Keychain or a session-only environment variable.")
            return 0
        if args.command == "schema":
            emit(schema())
            return 0
        if args.command == "prompt":
            print(GENERATION_PROMPT)
            return 0
        config = Config.load(args.config)
        if args.data_dir:
            config.data_dir = args.data_dir
        if args.command == "doctor":
            return doctor(config)
        if args.command == "voices":
            raw = ElevenLabs().voices()
            emit({"voices": [{"voice_id": v["voice_id"], "name": v.get("name"),
                               "category": v.get("category"), "labels": v.get("labels"),
                               "preview_url": v.get("preview_url")} for v in raw.get("voices", [])],
                  "has_more": raw.get("has_more", False)})
            return 0
        store = Store(config.data_dir)
        work = Workflow(config, store)
        with store.lock():
            if args.command == "init-anki":
                emit(work.initialize_anki(args.backup, args.profile))
            elif args.command == "import-drafts":
                drafts = parse_batch(json.loads(Path(args.file).read_text(encoding="utf-8")))
                emit([{"id": store.add(d), "german": d.german, "needs_confirmation": d.needs_confirmation or bool(d.warnings)} for d in drafts])
            elif args.command in {"draft", "run"}:
                ids = generate(args, config, store)
                if args.command == "draft":
                    emit([{"id": i, "german": store.draft(i).german,
                           "needs_confirmation": not bool(store.get(i)["confirmed_german"])} for i in ids])
                else:
                    errors = False
                    for draft_id in ids:
                        try:
                            if store.get(draft_id)["status"] != "approved":
                                try:
                                    work.audio(draft_id)
                                except WorkflowError as exc:
                                    print(f"{draft_id}: {exc}", file=sys.stderr)
                                    errors = True
                            emit(work.stage(draft_id))
                        except WorkflowError as exc:
                            print(f"{draft_id}: {exc}", file=sys.stderr)
                            errors = True
                    return int(errors)
            elif args.command == "list":
                emit([{"id": r["id"], "status": r["status"], "german": store.draft(r["id"]).german,
                       "german_confirmed": bool(r["confirmed_german"]), "note_id": r["note_id"]} for r in store.all()])
            elif args.command == "show":
                draft_id = resolve(store, args.id)
                emit({"draft": store.draft(draft_id).as_dict(), "state": {k: v for k, v in store.get(draft_id).items() if k != "data"}})
            elif args.command == "confirm":
                emit(work.confirm(resolve(store, args.id), args.german).as_dict())
            elif args.command in {"audio", "stage", "approve"}:
                if args.id:
                    ids = [resolve(store, args.id)]
                elif getattr(args, "selected", False):
                    ids = work.selected_ids()
                else:
                    ids = [r["id"] for r in store.all() if r["status"] != "approved"]
                errors = False
                for draft_id in ids:
                    try:
                        value = getattr(work, args.command)(draft_id)
                        emit(str(value) if isinstance(value, Path) else value)
                    except WorkflowError as exc:
                        print(f"{draft_id}: {exc}", file=sys.stderr)
                        errors = True
                return int(errors)
            elif args.command == "review":
                work.check_anki()
                deck = config.staging_deck.replace('"', '\\"')
                emit(work.anki.call("guiBrowse", query=f'deck:"{deck}"'))
            elif args.command == "review-vocabulary":
                work.check_anki()
                deck = config.vocab_deck.replace('"', '\\"')
                emit(work.anki.call("guiBrowse", query=f'deck:"{deck}"'))
            elif args.command == "sync-ledger":
                emit(work.sync_ledger())
            elif args.command == "format-cards":
                emit(work.format_cards())
            elif args.command == "sync":
                work.check_anki()
                work.anki.call("sync")
                print("Desktop sync requested. Open AnkiMobile and sync there, including media.")
            elif args.command == "preview":
                print(work.preview(args.output))
            elif args.command == "export":
                print(work.export(args.directory))
            elif args.command == "vocabulary":
                emit(store.words(args.query))
            elif args.command == "usage":
                usage = store.usage()
                emit({"requests": usage, "total_characters_reserved": sum(u["characters"] for u in usage),
                      "estimated_usd": round(sum(u["estimated_usd"] for u in usage), 4),
                      "note": "Estimates exclude plan fees, taxes, and voice multipliers. Failed/unknown requests retain their reservation."})
        return 0
    except (WorkflowError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted. Completed drafts and audio remain saved; rerun to continue.", file=sys.stderr)
        return 130
    finally:
        if store:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
