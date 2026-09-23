"""Validated card data, stable identities, and editable Anki field rendering."""

from dataclasses import asdict, dataclass
from hashlib import sha256
from html import escape
from html.parser import HTMLParser
import json
import re
import unicodedata


class WorkflowError(Exception):
    """An actionable input, setup, or service error safe to show to the user."""


def normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split())


def digest(value) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def text(value, name: str, *, empty=False, limit=12000) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise WorkflowError(f"{name} must be {'a string' if empty else 'non-empty text'}.")
    if len(value) > limit or "\x00" in value:
        raise WorkflowError(f"{name} is too long or contains invalid characters.")
    return value.strip()


@dataclass(frozen=True)
class Word:
    lemma: str
    meaning: str
    details: str

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict) or set(value) != {"lemma", "meaning", "details"}:
            raise WorkflowError("Each vocabulary item needs lemma, meaning, and details.")
        parts = {k: text(v, f"vocabulary.{k}", empty=k == "details", limit=2000)
                 for k, v in value.items()}
        if any("|" in v or "\n" in v for v in parts.values()):
            raise WorkflowError("Vocabulary fields must be single lines without the | separator.")
        return cls(**parts)

    @property
    def key(self):
        return normalized(self.lemma).casefold()


@dataclass(frozen=True)
class Draft:
    source: str
    german: str
    english: str
    grammar: str
    vocabulary: tuple[Word, ...]
    needs_confirmation: bool
    warnings: tuple[str, ...]

    @classmethod
    def parse(cls, value):
        fields = {"source", "german", "english", "grammar", "vocabulary",
                  "needs_confirmation", "warnings"}
        if not isinstance(value, dict) or set(value) != fields:
            raise WorkflowError("Draft fields do not match the card schema.")
        if type(value["needs_confirmation"]) is not bool:
            raise WorkflowError("needs_confirmation must be true or false.")
        if not isinstance(value["warnings"], list) or len(value["warnings"]) > 20:
            raise WorkflowError("warnings must be a short list.")
        if not isinstance(value["vocabulary"], list) or len(value["vocabulary"]) > 30:
            raise WorkflowError("vocabulary must contain at most 30 items.")
        words = tuple(Word.parse(v) for v in value["vocabulary"])
        if len({w.key for w in words}) != len(words):
            raise WorkflowError("Use one vocabulary entry per base form.")
        draft = cls(
            source=text(value["source"], "source", limit=5000),
            german=text(value["german"], "german", limit=5000),
            english=text(value["english"], "english", empty=True),
            grammar=text(value["grammar"], "grammar", empty=True),
            vocabulary=words,
            needs_confirmation=value["needs_confirmation"],
            warnings=tuple(text(w, "warning") for w in value["warnings"]),
        )
        # A model cannot silently authorize its own rewrite, even if it says it is safe.
        if normalized(draft.source) != normalized(draft.german) and not draft.needs_confirmation:
            draft = cls(**{**draft.__dict__, "needs_confirmation": True,
                           "warnings": (*draft.warnings, "The German differs from the source; confirm the exact front.")})
        if "[sound:" in draft.german or "<" in draft.german or ">" in draft.german:
            raise WorkflowError("German must be plain sentence text, without markup or audio tags.")
        return draft

    @property
    def id(self):
        return digest(normalized(self.source))[:24]

    def as_dict(self):
        value = asdict(self)
        value["vocabulary"] = [asdict(w) for w in self.vocabulary]
        value["warnings"] = list(self.warnings)
        return value


class _Plain(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"br", "div", "p", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"div", "p", "li"}:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def plain(value: str) -> str:
    parser = _Plain()
    parser.feed(value)
    return "\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip())


def rich(value: str) -> str:
    return escape(value).replace("\n", "<br>")


def grammar_points(value: str) -> tuple[str, ...]:
    """Turn prose into stable display points while preserving authored newlines."""
    points = []
    for paragraph in value.splitlines() or [value]:
        paragraph = normalized(paragraph)
        if not paragraph:
            continue
        protected = paragraph
        abbreviations = {"z. B.": "z.§B.§", "d. h.": "d.§h.§", "e.g.": "e§g§",
                         "i.e.": "i§e§", "Mr.": "Mr§", "Dr.": "Dr§"}
        for source, placeholder in abbreviations.items():
            protected = protected.replace(source, placeholder)
        for point in re.split(r"(?<=[.!?])\s+(?=(?:[A-ZÄÖÜ]|z\.§B\.§|d\.§h\.§))", protected):
            for source, placeholder in abbreviations.items():
                point = point.replace(placeholder, source)
            if point.strip():
                points.append(point.strip())
    return tuple(points)


def grammar_html(value: str) -> str:
    return "".join(f'<div class="grammar-point">{rich(point)}</div>'
                   for point in grammar_points(value))


def vocabulary_html(words) -> str:
    return "".join(
        '<div class="vocabulary-item">'
        f'<span class="vocabulary-term">{rich(w.lemma)}</span>'
        f'<span class="vocabulary-separator"> | </span>'
        f'<span class="vocabulary-meaning">{rich(w.meaning)}</span>'
        f'<span class="vocabulary-separator vocabulary-details-separator"> | </span>'
        f'<span class="vocabulary-details">{rich(w.details)}</span>'
        '</div>' for w in words)


def parse_vocabulary(value: str) -> tuple[Word, ...]:
    words = []
    for line in plain(value).splitlines():
        parts = line.split("|", 2)
        if len(parts) != 3:
            raise WorkflowError("Vocabulary lines must use: base form | meaning | details. Delete a whole line to omit it.")
        words.append(Word.parse(dict(zip(("lemma", "meaning", "details"), parts))))
    if len({w.key for w in words}) != len(words):
        raise WorkflowError("Vocabulary contains duplicate base forms.")
    return tuple(words)


FIELDS = ["WorkflowId", "German", "GermanAudio", "English", "Grammar", "Vocabulary",
          "BaseForms", "Source", "VoiceId", "Status"]
VOCAB_FIELDS = ["LedgerId", "BaseForm", "Meaning", "Details", "Encounters", "SourceSentences"]
VOCAB_FRONT = '<div class="label">VOCABULARY LEDGER</div><div class="sentence">{{BaseForm}}</div>'
VOCAB_BACK = '<div class="meaning">{{Meaning}}</div><hr><div class="explanation">{{Details}}</div><hr><div class="explanation">{{SourceSentences}}</div>'


def ledger_id(lemma_key):
    return digest({"vocabulary_lemma": lemma_key})[:24]
FRONT = '<div class="label">DEUTSCH</div><div class="sentence">{{German}}</div>{{GermanAudio}}'
BACK = '''<div class="label">MEANING</div><div class="meaning">{{English}}</div>
<hr><div class="label">GRAMMAR</div><div class="grammar-list">{{Grammar}}</div>
{{#Vocabulary}}<hr><div class="label">WORDS</div><div class="vocabulary">{{Vocabulary}}</div>{{/Vocabulary}}'''
CSS = '''.card { font-family: -apple-system, Arial, sans-serif; font-size: 20px;
text-align: left; color: #20312d; background: #f5f4ee; max-width: 760px;
margin: 0 auto; padding: 28px; line-height: 1.65; }
.label { font-size: 11px; letter-spacing: .16em; color: #678077; margin: 14px 0; }
.sentence { font-size: 30px; line-height: 1.45; margin-bottom: 20px; }
.meaning { font-size: 26px; } .explanation, .grammar-list, .vocabulary { font-size: 18px; }
.grammar-point { display: block; margin: 0 0 14px; }
.grammar-point:last-child { margin-bottom: 0; }
.vocabulary-item { display: block; margin: 0 0 18px; }
.vocabulary-item:last-child { margin-bottom: 0; }
.vocabulary-term { font-weight: 700; }
.vocabulary-meaning { font-weight: 600; }
.vocabulary-details { display: block; margin-top: 3px; color: #4f625a; }
.vocabulary-details-separator { display: none; }
hr { border: 0; border-top: 1px solid #ccd4cd; margin: 24px 0; }
.nightMode.card { color: #e5ebe7; background: #17221e; }
.nightMode .label { color: #a0b6ab; }
.nightMode .vocabulary-details { color: #c6d2cc; }'''


def note_fields(draft: Draft, *, audio="", voice="", status="draft"):
    return dict(zip(FIELDS, [draft.id, rich(draft.german), audio, rich(draft.english),
                            grammar_html(draft.grammar), vocabulary_html(draft.vocabulary),
                            rich("; ".join(w.lemma for w in draft.vocabulary)), rich(draft.source),
                            voice, rich(status)]))


def schema():
    string = {"type": "string"}
    word = {"type": "object", "additionalProperties": False,
            "properties": {k: string for k in ("lemma", "meaning", "details")},
            "required": ["lemma", "meaning", "details"]}
    props = {k: string for k in ("source", "german", "english", "grammar")}
    props.update(vocabulary={"type": "array", "items": word},
                 needs_confirmation={"type": "boolean"},
                 warnings={"type": "array", "items": string})
    return {"type": "object", "additionalProperties": False,
            "properties": {"drafts": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "properties": props, "required": list(props)}}}, "required": ["drafts"]}
