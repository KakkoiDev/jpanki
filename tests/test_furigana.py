"""Golden-file tests: extraction must not change how published cards render.

The fixtures were captured from the pre-extraction implementations by
capture_golden.py, over 4464 distinct bracketed values pulled from both repos'
real CSVs plus 21 hand-written edge cases. A failure here means jpanki would
alter the rendering of cards that are already in users' collections.

The one sanctioned divergence is documented in KNOWN_DIVERGENCE below.
"""
import json
from pathlib import Path

import pytest

from jpanki import furigana

GOLDEN = json.loads(
    (Path(__file__).parent / "fixtures" / "golden_furigana.json").read_text(encoding="utf-8")
)
ENTRIES = GOLDEN["entries"]

# minihongo's to_ruby_html omitted 々 from its character class, so a base form
# ending in the repetition mark kept its literal brackets instead of taking
# ruby. jpanki uses the superset, which fixes that. Verified safe: minihongo's
# only bracketed 々 is in comprehension.csv, which the Anki build never reads,
# so no published minihongo card changes. nihongo-it already had the superset.
KNOWN_DIVERGENCE = set(GOLDEN["_ruby_divergence"])

# Both source projects kept these lists at module scope; jpanki takes them as
# parameters. The captured values are pinned here so the tests exercise the same
# configuration the originals shipped with.
NIT_TTS_OVERRIDES = set(GOLDEN["_nit_tts_kanji_overrides"])
MH_KEEP_KANJI = set(GOLDEN["_mh_keep_kanji"])


def ids_for(entries):
    return [e["text"][:40] or "<empty>" for e in entries]


@pytest.mark.parametrize("entry", ENTRIES, ids=ids_for(ENTRIES))
def test_to_ruby_matches_nihongo_it(entry):
    """nihongo-it's renderer already used the superset class — match it exactly."""
    assert furigana.to_ruby(entry["text"]) == entry["nit_to_ruby_html"]


@pytest.mark.parametrize("entry", ENTRIES, ids=ids_for(ENTRIES))
def test_to_ruby_matches_minihongo_except_known_divergence(entry):
    text = entry["text"]
    got = furigana.to_ruby(text)
    if text in KNOWN_DIVERGENCE:
        # Diverges by design, and only by gaining ruby it should have had.
        assert got != entry["mh_to_ruby_html"]
        assert "々【" not in got, "the repetition mark should no longer leak brackets"
    else:
        assert got == entry["mh_to_ruby_html"]


@pytest.mark.parametrize("entry", ENTRIES, ids=ids_for(ENTRIES))
def test_strip_matches_minihongo(entry):
    assert furigana.strip(entry["text"]) == entry["mh_strip_furigana"]


@pytest.mark.parametrize("entry", ENTRIES, ids=ids_for(ENTRIES))
def test_to_reading_matches_minihongo(entry):
    """to_reading with no keep-list is minihongo's furigana_to_reading."""
    text = entry["text"]
    got = furigana.to_reading(text)
    if text in KNOWN_DIVERGENCE:
        pytest.skip("々 handling diverges by design; covered above")
    assert got == entry["mh_furigana_to_reading"]


@pytest.mark.parametrize("entry", ENTRIES, ids=ids_for(ENTRIES))
def test_keep_base_matches_nihongo_it_with_overrides(entry):
    """keep_base reproduces extract_furigana as nihongo-it actually configures it."""
    got = furigana.keep_base(entry["text"], overrides=NIT_TTS_OVERRIDES)
    assert got == entry["nit_extract_furigana"]


@pytest.mark.parametrize("entry", ENTRIES, ids=ids_for(ENTRIES))
def test_keep_base_matches_nihongo_it_without_overrides(entry):
    """And with the override set empty, isolating the base substitution."""
    got = furigana.keep_base(entry["text"])
    assert got == entry["nit_extract_furigana_no_overrides"]


# ── behaviour tests, independent of the fixtures ────────────────────


def test_parse_round_trips_to_strip():
    text = "あの人【ひと】は誰【だれ】？"
    assert "".join(t.base for t in furigana.parse(text)) == furigana.strip(text)


def test_parse_tokenises():
    assert furigana.parse("あの人【ひと】は") == [
        furigana.Token("あの"),
        furigana.Token("人", "ひと"),
        furigana.Token("は"),
    ]


def test_parse_empty():
    assert furigana.parse("") == []


@pytest.mark.parametrize("malformed", ["人【", "人【】", "【ひと】", "人", ""])
def test_malformed_never_raises(malformed):
    furigana.parse(malformed)
    furigana.to_ruby(malformed)
    furigana.strip(malformed)
    furigana.to_reading(malformed)
    furigana.keep_base(malformed)


def test_repetition_mark_takes_ruby():
    assert furigana.to_ruby("徐々【じょじょ】") == "<ruby>徐々<rt>じょじょ</rt></ruby>"


def test_only_the_kanji_run_takes_ruby():
    """Kana preceding a kanji run stays outside the <ruby> element."""
    assert furigana.to_ruby("ぶどう酒【ぶどうしゅ】") == "ぶどう<ruby>酒<rt>ぶどうしゅ</rt></ruby>"


def test_to_reading_keep_is_per_character():
    """A compound containing a kept character is kept whole (TTS mispronounces はは)."""
    assert furigana.to_reading("母【はは】", keep={"母"}) == "母"
    assert furigana.to_reading("人【ひと】", keep={"母"}) == "ひと"


def test_keep_base_overrides_match_whole_run():
    """Overriding 生 must not disturb 発生 — the reason this matches whole runs."""
    assert furigana.keep_base("生【なま】", overrides={"生"}) == "なま"
    assert furigana.keep_base("発生【はっせい】", overrides={"生"}) == "発生"


def test_to_reading_clean_drops_punctuation():
    assert furigana.to_reading("あの人【ひと】は誰【だれ】？", clean=True) == "あのひとはだれ"


@pytest.mark.parametrize(
    "text,expected",
    [("ひと", True), ("カタカナ", True), ("コーヒー", True), ("人", False), ("hito", False), ("", False)],
)
def test_is_kana(text, expected):
    assert furigana.is_kana(text) is expected


def test_annotations_extracts_pairs():
    assert furigana.annotations("あの人【ひと】は誰【だれ】？") == [("人", "ひと"), ("誰", "だれ")]
