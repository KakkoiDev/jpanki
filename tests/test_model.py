"""Model construction, and the GUID/ID policy that protects review history."""
from pathlib import Path

import genanki
import pytest

from jpanki import model


def spec(**overrides) -> model.NoteSpec:
    defaults = dict(
        name="Test",
        model_id=123456,
        fields=["Front", "Back"],
        templates=[{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}],
        css=".card { color: red; }",
    )
    return model.NoteSpec(**{**defaults, **overrides})


def test_build_model_maps_fields_and_templates():
    built = model.build_model(spec())
    assert built.name == "Test"
    assert [f["name"] for f in built.fields] == ["Front", "Back"]
    assert len(built.templates) == 1


def test_field_index_supports_safe_note_construction():
    assert spec(fields=["A", "B", "C"]).field_index("B") == 1


# ── GUID policy ─────────────────────────────────────────────────────


def test_note_guid_is_stable_across_content_edits():
    """The whole point: correcting a gloss must not orphan the note.

    genanki's default GUID hashes every field, so this is the behaviour the
    library exists to replace.
    """
    before = model.note_guid("bible", 1, "神")
    after = model.note_guid("bible", 1, "神")
    assert before == after


def test_note_guid_differs_per_note():
    assert model.note_guid("bible", 1, "神") != model.note_guid("bible", 1, "主")
    assert model.note_guid("bible", 1, "神") != model.note_guid("bible", 2, "神")


def test_note_guid_separator_prevents_ambiguity():
    """("a","b:c") and ("a:b","c") must not collide."""
    assert model.note_guid("a", "b:c") != model.note_guid("a:b", "c")
    assert model.note_guid("a", "b-c") != model.note_guid("a-b", "c")


def test_note_guid_requires_a_key():
    with pytest.raises(ValueError, match="at least one key part"):
        model.note_guid()


def test_note_guid_accepts_non_strings():
    assert model.note_guid("bible", 7) == model.note_guid("bible", "7")


# ── deck naming and IDs ─────────────────────────────────────────────


def test_subdeck_zero_pads_for_lexical_ordering():
    assert model.subdeck("Bible", 3, "Creation") == "Bible::03 Creation"
    assert model.subdeck("Bible", 12, "Fall") == "Bible::12 Fall"


def test_subdeck_ordering_is_actually_lexical():
    names = [model.subdeck("D", n, "x") for n in (1, 2, 9, 10, 11)]
    assert names == sorted(names), "zero-padding must make string sort match numeric"


def test_subdeck_width_follows_total_collection_size():
    assert model.subdeck("D", 3, "x", total=9) == "D::03 x"
    assert model.subdeck("D", 3, "x", total=99) == "D::03 x"
    assert model.subdeck("D", 3, "x", total=100) == "D::003 x"
    assert model.subdeck("D", 100, "x", total=100) == "D::100 x"


def test_subdeck_rejects_position_outside_collection():
    with pytest.raises(ValueError, match="exceeds total"):
        model.subdeck("D", 10, "x", total=9)


def test_subdeck_refuses_to_overflow_its_padding():
    with pytest.raises(ValueError, match="lexical"):
        model.subdeck("D", 100, "x", width=2)


def test_build_deck_requires_explicit_id():
    """Randomised deck IDs made rebuilds non-idempotent; there is no default."""
    with pytest.raises(TypeError):
        model.build_deck(name="no id")  # type: ignore[call-arg]


# ── media ───────────────────────────────────────────────────────────


def test_sound_ref_for_existing_file(tmp_path):
    clip = tmp_path / "w_kami.mp3"
    clip.write_bytes(b"x")
    value, media = model.sound_ref(clip)
    assert value == "[sound:w_kami.mp3]"
    assert media == clip


def test_sound_ref_degrades_when_optional(tmp_path):
    assert model.sound_ref(tmp_path / "missing.mp3") == ("", None)
    assert model.sound_ref(None) == ("", None)


def test_sound_ref_raises_when_required(tmp_path):
    """A listening card with no audio has a blank front — never ship one."""
    with pytest.raises(FileNotFoundError, match="cannot ship"):
        model.sound_ref(tmp_path / "missing.mp3", require=True)


# ── force_style ─────────────────────────────────────────────────────


def test_force_style_is_deterministic_in_the_css():
    assert model.force_style(1000, "a{}") == model.force_style(1000, "a{}")


def test_force_style_changes_with_the_css():
    assert model.force_style(1000, "a{}") != model.force_style(1000, "b{}")


def test_force_style_moves_the_id():
    assert model.force_style(1000, "a{}") != 1000


# ── packaging ───────────────────────────────────────────────────────


def build_package(tmp_path, media=()):
    package = model.Package()
    deck = package.add_deck(model.build_deck(9_999_001, "Test Deck"))
    built = model.build_model(spec())
    deck.add_note(genanki.Note(model=built, fields=["front", "back"],
                               guid=model.note_guid("test", 1)))
    for path in media:
        package.add_media(path)
    return package


def test_package_writes_apkg(tmp_path):
    out = build_package(tmp_path).write(tmp_path / "out.apkg")
    assert out.exists() and out.stat().st_size > 0


def test_package_creates_missing_output_directory(tmp_path):
    out = build_package(tmp_path).write(tmp_path / "nested" / "dir" / "out.apkg")
    assert out.exists()


def test_package_refuses_to_write_empty():
    with pytest.raises(ValueError, match="no decks"):
        model.Package().write(Path("unused.apkg"))


def test_package_deduplicates_media(tmp_path):
    clip = tmp_path / "a.mp3"
    clip.write_bytes(b"x")
    package = build_package(tmp_path, media=[clip, clip, clip])
    assert package.media_files == [str(clip)]


def test_package_rejects_conflicting_media_names(tmp_path):
    """Two files with one basename would silently overwrite inside the apkg."""
    (tmp_path / "x").mkdir()
    (tmp_path / "y").mkdir()
    first, second = tmp_path / "x" / "a.mp3", tmp_path / "y" / "a.mp3"
    first.write_bytes(b"1")
    second.write_bytes(b"2")
    package = model.Package()
    package.add_media(first)
    with pytest.raises(ValueError, match="claim the media name"):
        package.add_media(second)


def test_package_ignores_none_media():
    package = model.Package()
    package.add_media(None)
    assert package.media_files == []


def test_package_counts_notes(tmp_path):
    assert build_package(tmp_path).note_count() == 1
