"""The `漢字【かんじ】` furigana notation: one parser, several renderers.

Both source projects annotate readings inline, writing a base form immediately
followed by its reading in lenticular brackets:

    あの人【ひと】は誰【だれ】？

and then render that per target — ruby HTML for cards, bare kanji for display,
all-kana for text-to-speech. Between them they had four regexes doing this,
with three *different* character classes:

    minihongo to_ruby_html         kanji + ext-A
    minihongo furigana_to_reading  kanji + ext-A
    minihongo text_for_tts         kanji + ext-A + 々
    nihongo-it to_ruby_html        kanji + ext-A + 々
    nihongo-it extract_furigana    kanji + 々          (+ leading digits)

The practical consequence: `徐々【じょじょ】` rendered correctly in some paths
and leaked literal brackets onto the card in others. This module parses the
notation once, into tokens, and renders from those — so a base form is either
annotatable everywhere or nowhere.

The canonical class is the superset (`BASE_CHARS`). Adopting it was verified
against both corpora: it changes nothing in minihongo's Anki-consumed CSVs
(their only bracketed 々 lives in comprehension.csv, which the deck build does
not read) and reproduces nihongo-it's ruby output exactly.
"""
from __future__ import annotations

import re
from typing import Iterable, NamedTuple

# CJK ideographs, CJK ext-A, and 々 (the repetition mark, U+3005, as in 徐々).
# 々 belongs here because it is part of the *written* base form even though it
# is not itself an ideograph.
BASE_CHARS = r"一-鿿㐀-䶿々"

#: A base run followed by its bracketed reading.
NOTATION_RE = re.compile(rf"([{BASE_CHARS}]+)【([^】]+)】")

#: A bracketed annotation on its own, wherever it appears. Used by :func:`strip`,
#: which historically removed brackets without caring what preceded them.
_BRACKET_RE = re.compile(r"【[^】]+】")

_KANA_RE = re.compile(r"^[぀-ゟ゠-ヿー]+$")


class Token(NamedTuple):
    """A run of text, optionally carrying a reading.

    ``reading`` is ``None`` for plain text (kana, punctuation, latin, digits)
    and a kana string for an annotated base form.
    """

    base: str
    reading: str | None = None

    @property
    def annotated(self) -> bool:
        return self.reading is not None


def parse(text: str) -> list[Token]:
    """Split furigana notation into tokens.

    >>> parse("あの人【ひと】は")
    [Token(base='あの', reading=None), Token(base='人', reading='ひと'), Token(base='は', reading=None)]

    Malformed input degrades to plain text rather than raising: an unclosed
    bracket, an empty annotation, or a reading with no base form are all
    returned verbatim in a single unannotated token.
    """
    if not text:
        return []
    tokens: list[Token] = []
    pos = 0
    for match in NOTATION_RE.finditer(text):
        if match.start() > pos:
            tokens.append(Token(text[pos:match.start()]))
        tokens.append(Token(match.group(1), match.group(2)))
        pos = match.end()
    if pos < len(text):
        tokens.append(Token(text[pos:]))
    return tokens


def to_ruby(text: str) -> str:
    """Render as ruby HTML for an Anki card.

    >>> to_ruby("人【ひと】")
    '<ruby>人<rt>ひと</rt></ruby>'
    """
    return NOTATION_RE.sub(r"<ruby>\1<rt>\2</rt></ruby>", text)


def strip(text: str) -> str:
    """Remove the reading annotations, keeping the base forms.

    >>> strip("人【ひと】です")
    '人です'
    """
    if not text:
        return ""
    return _BRACKET_RE.sub("", text)


def to_reading(
    text: str,
    *,
    keep: Iterable[str] = (),
    clean: bool = False,
) -> str:
    """Replace annotated base forms with their readings.

    >>> to_reading("あの人【ひと】は誰【だれ】？")
    'あのひとはだれ？'

    ``keep`` names base forms that should stay as written instead of becoming
    kana. Text-to-speech engines need this: Edge TTS reads 母【はは】 correctly
    as kanji but turns the kana はは into "wawa", because it treats the leading
    は as the topic particle. A base run is kept if *any* of its characters is
    in ``keep`` — matching the original behaviour, which deliberately protected
    compounds containing a problem character.

    ``clean=True`` additionally drops punctuation and whitespace, for when the
    result is used as a sort key or a filename rather than spoken.
    """
    keep_set = set(keep)

    def render(match: re.Match) -> str:
        base, reading = match.group(1), match.group(2)
        if keep_set and any(c in keep_set for c in base):
            return base
        return reading

    out = NOTATION_RE.sub(render, text)
    if clean:
        out = re.sub(r"[、。！？・\s/]", "", out)
    return out


def keep_base(text: str, *, overrides: Iterable[str] = ()) -> str:
    """Drop the annotations but keep the base forms — the inverse of :func:`to_reading`.

    This is the other text-to-speech strategy, and the one nihongo-it-anki
    settled on: feed the engine kanji, because a good engine gets standard
    readings right and kanji carries pitch information that bare kana loses.

    ``overrides`` names base forms the engine demonstrably misreads, which fall
    back to their kana reading. Unlike :func:`to_reading`'s ``keep``, matching
    here is on the *whole* base run, not per-character, so overriding 生 does
    not disturb 発生 or 厚生.

    >>> keep_base("昼食【ちゅうしょく】前【まえ】に")
    '昼食前に'
    >>> keep_base("提出【ていしゅつ】", overrides={"提出"})
    'ていしゅつ'
    """
    override_set = set(overrides)

    def render(match: re.Match) -> str:
        base, reading = match.group(1), match.group(2)
        return reading if base in override_set else base

    return NOTATION_RE.sub(render, text)


def is_kana(text: str) -> bool:
    """True if ``text`` is entirely hiragana/katakana (plus the ー lengthener).

    Used to validate that a reading column really contains a reading.
    """
    return bool(text) and bool(_KANA_RE.match(text))


def annotations(text: str) -> list[tuple[str, str]]:
    """Every ``(base, reading)`` pair, for validation and vocabulary extraction."""
    return [(t.base, t.reading) for t in parse(text) if t.reading is not None]
