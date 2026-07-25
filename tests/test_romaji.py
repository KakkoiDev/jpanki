"""Kana → rōmaji, and the loose comparison used to audit hand-written rōmaji."""
import pytest

from jpanki import romaji


@pytest.mark.parametrize(
    "kana,expected",
    [
        ("ひと", "hito"),
        ("わたし", "watashi"),
        ("かみ", "kami"),
        # Digraphs must beat their component characters.
        ("きょうかい", "kyoukai"),
        ("しょうしょう", "shoushou"),
        ("じょじょ", "jojo"),
        # Gemination: っ doubles the following consonant.
        ("がっこう", "gakkou"),
        ("いっぱい", "ippai"),
        ("まっちゃ", "maccha"),  # wāpuro, not Hepburn
        # Long vowels repeat the preceding vowel.
        ("コーヒー", "koohii"),
        ("ラーメン", "raamen"),
        # Katakana is mirrored from hiragana.
        ("カタカナ", "katakana"),
        ("イエス", "iesu"),
        # Punctuation is dropped, spaces become the separator.
        ("あの ひと", "ano_hito"),
        ("ひと。", "hito"),
        ("", ""),
    ],
)
def test_from_kana(kana, expected):
    assert romaji.from_kana(kana) == expected


def test_trailing_sokuon_is_dropped():
    """A sokuon with nothing after it has no consonant to double."""
    assert romaji.from_kana("あっ") == "a"


def test_leading_choonpu_has_no_vowel_to_repeat():
    assert romaji.from_kana("ーあ") == "a"


def test_space_separator_is_configurable():
    assert romaji.from_kana("あの ひと", space="-") == "ano-hito"


def test_kanji_passes_through_unromanised():
    """Python calls kanji alphanumeric, so it survives from_kana unchanged.

    Inherited from minihongo, whose audio filenames are derived through this
    function; tightening it would rename existing clips. filename() sanitises.
    """
    assert romaji.from_kana("人") == "人"
    assert romaji.filename("人【ひと】") == "hito"


@pytest.mark.parametrize(
    "text,prefix,expected",
    [
        ("人【ひと】", "w", "w_hito"),
        ("十字架【じゅうじか】", "w", "w_juujika"),
        ("神【かみ】", "", "kami"),
        # Furigana is read for its kana, so the name reflects the reading.
        ("あの人【ひと】は誰【だれ】？", "s", "s_anohitohadare"),
    ],
)
def test_filename(text, prefix, expected):
    assert romaji.filename(text, prefix=prefix) == expected


def test_filename_truncates_long_phrases():
    long_phrase = "あ" * 100
    assert len(romaji.filename(long_phrase, max_length=20)) == 20


def test_filename_rejects_unromanisable_input():
    with pytest.raises(ValueError):
        romaji.filename("人")


def test_filename_is_filesystem_safe():
    name = romaji.filename("あの人【ひと】は誰【だれ】？", prefix="s")
    assert all(c.isalnum() or c == "_" for c in name)


@pytest.mark.parametrize(
    "kana,claimed",
    [
        # Real inconsistencies from the Bible playlist's own wordlists.
        ("ふくいん", "hukuin"),
        ("ふくいん", "fukuin"),
        ("じゅうじか", "jyuujika"),
        ("じゅうじか", "jūjika"),
        ("こうゆ", "kouyu"),
        ("こうゆ", "kōyu"),
        ("かみ", "kami"),
        ("せいれい", "seirei"),
    ],
)
def test_matches_accepts_spelling_variants(kana, claimed):
    assert romaji.matches(kana, claimed) is True


@pytest.mark.parametrize(
    "kana,claimed", [("かみ", "tanaka"), ("ひと", "kami"), ("あい", "koi")]
)
def test_matches_rejects_genuinely_different_readings(kana, claimed):
    assert romaji.matches(kana, claimed) is False


@pytest.mark.parametrize(
    "kana,expected",
    [
        # Loanword digraphs, which the original table lacked entirely.
        ("ソファ", "sofa"),
        ("フィルム", "firumu"),
        ("パーティ", "paati"),
        ("ミーティング", "miitingu"),
        ("カフェ", "kafe"),
        ("オフィス", "ofisu"),
        ("ヴァイオリン", "vaiorin"),
        ("チェック", "chekku"),
    ],
)
def test_katakana_loanword_digraphs(kana, expected):
    """Small kana must not fall through unmapped (ソファ was becoming 'sofuァ')."""
    assert romaji.from_kana(kana) == expected
