"""Kana → rōmaji, for audio filenames and reading cross-checks.

Ported from minihongo's ``generate_audio.py``, which grew this to derive stable,
content-addressed audio filenames (``w_hito.mp3``) instead of positional ones
(``tier1_001.mp3``). Content-derived names matter: with positional naming, CSV
row order becomes load-bearing and inserting a row silently reassigns every
later clip's audio.

The romanisation is wāpuro-style — the transliteration you would type on a
Japanese keyboard (``ou``, ``shi``, ``tsu``), not Hepburn with macrons (``ō``).
That is a deliberate choice for filenames, where ASCII is the point. It also
makes the output directly comparable to hand-written rōmaji in source data,
which tends to be wāpuro too.
"""
from __future__ import annotations

import re

# Digraphs, which must be matched before their component characters.
_DIGRAPHS = {
    "きゃ": "kya", "きゅ": "kyu", "きょ": "kyo",
    "しゃ": "sha", "しゅ": "shu", "しょ": "sho",
    "ちゃ": "cha", "ちゅ": "chu", "ちょ": "cho",
    "にゃ": "nya", "にゅ": "nyu", "にょ": "nyo",
    "ひゃ": "hya", "ひゅ": "hyu", "ひょ": "hyo",
    "みゃ": "mya", "みゅ": "myu", "みょ": "myo",
    "りゃ": "rya", "りゅ": "ryu", "りょ": "ryo",
    "ぎゃ": "gya", "ぎゅ": "gyu", "ぎょ": "gyo",
    "じゃ": "ja", "じゅ": "ju", "じょ": "jo",
    "びゃ": "bya", "びゅ": "byu", "びょ": "byo",
    "ぴゃ": "pya", "ぴゅ": "pyu", "ぴょ": "pyo",
}

# Digraphs that exist only in katakana, for transcribing loanwords. Without
# these, the small kana falls through unmapped: ソファ romanised as "sofuァ",
# which is how six such filenames ended up in minihongo's retired expressions
# deck. Katakana-only, so they are declared after the hiragana mirror below.
_KATAKANA_DIGRAPHS = {
    "ファ": "fa", "フィ": "fi", "フェ": "fe", "フォ": "fo", "フュ": "fyu",
    "ティ": "ti", "トゥ": "tu", "ディ": "di", "ドゥ": "du",
    "ウィ": "wi", "ウェ": "we", "ウォ": "wo",
    "シェ": "she", "ジェ": "je", "チェ": "che",
    "ツァ": "tsa", "ツィ": "tsi", "ツェ": "tse", "ツォ": "tso",
    "クァ": "kwa", "クィ": "kwi", "クェ": "kwe", "クォ": "kwo",
    "グァ": "gwa", "スィ": "si", "ズィ": "zi",
    "ヴァ": "va", "ヴィ": "vi", "ヴェ": "ve", "ヴォ": "vo", "ヴュ": "vyu",
    "テュ": "tyu", "デュ": "dyu", "ニュ": "nyu", "ヒュ": "hyu",
}

# Small vowels standing alone, once their digraph has had first refusal.
_SMALL_VOWELS = {"ァ": "a", "ィ": "i", "ゥ": "u", "ェ": "e", "ォ": "o", "ヮ": "wa"}

_MONOGRAPHS = {
    "あ": "a", "い": "i", "う": "u", "え": "e", "お": "o",
    "か": "ka", "き": "ki", "く": "ku", "け": "ke", "こ": "ko",
    "さ": "sa", "し": "shi", "す": "su", "せ": "se", "そ": "so",
    "た": "ta", "ち": "chi", "つ": "tsu", "て": "te", "と": "to",
    "な": "na", "に": "ni", "ぬ": "nu", "ね": "ne", "の": "no",
    "は": "ha", "ひ": "hi", "ふ": "fu", "へ": "he", "ほ": "ho",
    "ま": "ma", "み": "mi", "む": "mu", "め": "me", "も": "mo",
    "や": "ya", "ゆ": "yu", "よ": "yo",
    "ら": "ra", "り": "ri", "る": "ru", "れ": "re", "ろ": "ro",
    "わ": "wa", "を": "wo", "ん": "n",
    "が": "ga", "ぎ": "gi", "ぐ": "gu", "げ": "ge", "ご": "go",
    "ざ": "za", "じ": "ji", "ず": "zu", "ぜ": "ze", "ぞ": "zo",
    "だ": "da", "ぢ": "ji", "づ": "zu", "で": "de", "ど": "do",
    "ば": "ba", "び": "bi", "ぶ": "bu", "べ": "be", "ぼ": "bo",
    "ぱ": "pa", "ぴ": "pi", "ぷ": "pu", "ぺ": "pe", "ぽ": "po",
}

# Mirror every mapping onto katakana. Hiragana and katakana blocks are laid out
# in parallel, so a fixed codepoint offset converts between them.
_KATAKANA_OFFSET = ord("ア") - ord("あ")
for _kana, _rom in list(_MONOGRAPHS.items()):
    _MONOGRAPHS[chr(ord(_kana) + _KATAKANA_OFFSET)] = _rom
for _kana, _rom in list(_DIGRAPHS.items()):
    _DIGRAPHS["".join(chr(ord(c) + _KATAKANA_OFFSET) for c in _kana)] = _rom

_DIGRAPHS.update(_KATAKANA_DIGRAPHS)
# ...and mirror the extended digraphs back into hiragana. Loanwords are
# conventionally katakana, but hand-written readings often spell them in
# hiragana (とぅ, てぃ, ふぇ), and those readings must romanise too.
for _kana, _rom in list(_KATAKANA_DIGRAPHS.items()):
    _hira = "".join(
        chr(ord(c) - _KATAKANA_OFFSET) if "ァ" <= c <= "ヶ" else c for c in _kana
    )
    _DIGRAPHS.setdefault(_hira, _rom)

_MONOGRAPHS.update(_SMALL_VOWELS)
# Hiragana small vowels, for the same reason.
for _kana, _rom in list(_SMALL_VOWELS.items()):
    if "ァ" <= _kana <= "ヶ":
        _MONOGRAPHS.setdefault(chr(ord(_kana) - _KATAKANA_OFFSET), _rom)
_MONOGRAPHS["ヴ"] = "vu"
_MONOGRAPHS["ゔ"] = "vu"

_SOKUON = ("っ", "ッ")      # gemination: doubles the next consonant
_CHOONPU = ("ー", "-")      # long vowel: repeats the previous vowel

_VOWELS = "aiueo"


def from_kana(text: str, *, space: str = "_") -> str:
    """Transliterate kana to wāpuro rōmaji.

    >>> from_kana("ひと")
    'hito'
    >>> from_kana("がっこう")
    'gakkou'
    >>> from_kana("コーヒー")
    'koohii'

    Punctuation is dropped and whitespace becomes ``space``. Other alphanumeric
    characters pass through lowercased — and note that Python considers kanji
    alphanumeric, so ``from_kana("人") == "人"``. That is inherited from the
    original implementation and kept deliberately: minihongo's audio filenames
    are derived through this function, and tightening the rule here would
    rename existing clips and orphan them. Use :func:`filename` when the result
    must be ASCII; it sanitises.
    """
    out: list[str] = []
    i = 0
    while i < len(text):
        pair = text[i:i + 2]
        if pair in _DIGRAPHS:
            out.append(_DIGRAPHS[pair])
            i += 2
            continue

        char = text[i]
        if char in _SOKUON:
            # Double the initial consonant of whatever follows.
            following = _MONOGRAPHS.get(text[i + 1:i + 2]) or _DIGRAPHS.get(text[i + 1:i + 3])
            if following and following[0].isalpha():
                out.append(following[0])
            i += 1
        elif char in _CHOONPU:
            if out and out[-1] and out[-1][-1] in _VOWELS:
                out.append(out[-1][-1])
            i += 1
        elif char in _MONOGRAPHS:
            out.append(_MONOGRAPHS[char])
            i += 1
        else:
            if char.isspace():
                out.append(space)
            elif char.isalnum():
                out.append(char.lower())
            i += 1
    return "".join(out)


def filename(text: str, *, prefix: str = "", max_length: int = 40) -> str:
    """Derive a stable, filesystem-safe basename from Japanese text.

    >>> filename("人【ひと】", prefix="w")
    'w_hito'

    Furigana annotations are read for their kana, so the name reflects the
    reading rather than the kanji. The result is truncated to ``max_length``
    because some source entries are whole phrases, not words.
    """
    from jpanki import furigana  # local import: furigana has no romaji dependency

    stem = from_kana(furigana.to_reading(text, clean=True))
    stem = re.sub(r"[^a-z0-9_]+", "", stem).strip("_")
    if not stem:
        raise ValueError(f"no romanisable content in {text!r}")
    stem = stem[:max_length].rstrip("_")
    return f"{prefix}_{stem}" if prefix else stem


def matches(reading: str, claimed: str) -> bool:
    """Whether hand-written rōmaji is consistent with a kana reading.

    Source data romanises inconsistently by hand — ``hukuin``/``fukuin``,
    ``jyuujika``/``jūjika``, ``kouyu``/``kōyu`` — so this compares loosely:
    macrons are expanded, common alternative spellings are folded together, and
    everything non-alphabetic is dropped. Use it to *flag* mismatches for
    review, not to reject data.
    """
    return _fold(reading, from_kana) == _fold(claimed, None)


def same_romanisation(first: str, second: str) -> bool:
    """Whether two rōmaji strings are the same word spelled differently.

    Source data often offers both forms side by side (``ou, ō``;
    ``seinaru kata, sēnaru kata``), and a card should show one.
    """
    return _fold(first, None) == _fold(second, None)


def _is_kana(text: str) -> bool:
    from jpanki import furigana

    return furigana.is_kana(text)


_MACRONS = {"ā": "aa", "ī": "ii", "ū": "uu", "ē": "ee", "ō": "ou"}
# Spelling variants that mean the same sound. Left side folds to right side.
_FOLDS = [
    ("hu", "fu"), ("jy", "j"), ("sy", "sh"), ("ty", "ch"), ("cy", "ch"),
    ("shi", "si"), ("chi", "ti"), ("tsu", "tu"), ("wo", "o"),
    ("oo", "ou"), ("ee", "ei"),
]


def _fold(text: str, transform) -> str:
    if transform is not None:
        text = transform(text)
    text = text.lower()
    for macron, expansion in _MACRONS.items():
        text = text.replace(macron, expansion)
    text = re.sub(r"[^a-z]", "", text)
    for variant, canonical in _FOLDS:
        text = text.replace(variant, canonical)
    return text
