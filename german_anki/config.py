from dataclasses import dataclass, field, fields
import json
import math
from pathlib import Path
from urllib.parse import urlparse

from .domain import WorkflowError


@dataclass
class Config:
    data_dir: str = ".runtime"
    anki_url: str = "http://127.0.0.1:8765"
    model_name: str = "German Sentences v1"
    staging_deck: str = "German Sentences::Staging"
    study_deck: str = "German Sentences::Study"
    vocab_model_name: str = "German Vocabulary Ledger v1"
    vocab_deck: str = "German Vocabulary Ledger"
    codex_command: str = "codex"
    codex_model: str = ""
    voice_ids: list[str] = field(default_factory=list)
    tts_model: str = "eleven_v3"
    tts_output_format: str = "mp3_44100_128"
    tts_monthly_character_limit: int = 30000
    tts_usd_per_1000_characters: float = 0.10

    @classmethod
    def load(cls, path=None):
        target = Path(path or "config.local.json")
        if not target.exists():
            if path:
                raise WorkflowError(f"Configuration does not exist: {target}")
            return cls()
        data = json.loads(target.read_text())
        if not isinstance(data, dict) or set(data) - {f.name for f in fields(cls)}:
            raise WorkflowError("Configuration contains unknown fields. API keys belong in environment variables.")
        obj = cls(**data)
        obj.data_dir = str((target.resolve().parent / obj.data_dir).resolve())
        url = urlparse(obj.anki_url)
        if url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise WorkflowError("Anki-Connect must use an HTTP localhost address.")
        if obj.tts_model != "eleven_v3" or obj.tts_output_format != "mp3_44100_128":
            raise WorkflowError("This version supports eleven_v3 and mp3_44100_128 only.")
        if type(obj.tts_monthly_character_limit) is not int or obj.tts_monthly_character_limit <= 0:
            raise WorkflowError("Set a positive monthly TTS character limit.")
        if not isinstance(obj.voice_ids, list) or any(not isinstance(v, str) or not v.isalnum() for v in obj.voice_ids):
            raise WorkflowError("voice_ids must contain ElevenLabs voice IDs, not voice names.")
        if not isinstance(obj.tts_usd_per_1000_characters, (int, float)) or not math.isfinite(obj.tts_usd_per_1000_characters) or obj.tts_usd_per_1000_characters <= 0:
            raise WorkflowError("The estimated TTS character price must be positive.")
        if len({obj.staging_deck, obj.study_deck, obj.vocab_deck}) != 3 or obj.model_name == obj.vocab_model_name:
            raise WorkflowError("Sentence/vocabulary decks and note types must be distinct.")
        return obj
