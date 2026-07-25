"""The composed stylesheets must carry the same declarations as the originals.

Compared by declaration set rather than by bytes: reformatting, reordering and
regrouping rules is fine, but a changed colour, size or mask is a visual
regression on cards that are already in people's collections.
"""
import json
from pathlib import Path

import pytest

from jpanki import theme

GOLDEN = json.loads(
    (Path(__file__).parent / "fixtures" / "golden_css.json").read_text(encoding="utf-8")
)

# `.card` sets `text-align: center` and nothing between it and `.audio`
# overrides it, so declaring it again on `.audio` is provably inert. minihongo
# spelled it out; nihongo-it-anki relied on inheritance. The library spells it
# out for both.
INERT_ADDITIONS = {(".audio", "text-align")}


def minihongo_css() -> str:
    """How minihongo composes its stylesheet after migration."""
    return theme.compose(
        theme.base(),
        theme.headword(),
        theme.chip(".tags"),
        theme.ruby(),
        theme.replay(),
        theme.night(muted_selectors=(".card-type", ".hint")),
        extra=MINIHONGO_COMPONENTS,
    )


def nihongo_it_css() -> str:
    """How nihongo-it-anki composes its stylesheet after migration."""
    return theme.compose(
        theme.base(sentence_size="28px", sentence_margin="20px 0"),
        theme.chip(".category"),
        theme.ruby(),
        theme.replay(),
        theme.replay(scope=".listening-front", size="5rem", icon_size="2.5rem", radius="1.25rem"),
        theme.night(chip_selector=".category"),
        extra=NIHONGO_IT_COMPONENTS,
    )


# The project-specific component CSS that stays with each consumer. Reproduced
# here so the tests compare complete stylesheets; the real definitions live in
# each repo.
MINIHONGO_COMPONENTS = """
.explanation {
    font-size: 18px;
    margin: 15px 0;
    text-align: left;
    line-height: 1.6;
}
.grammar-name {
    font-size: 14px;
    color: #666666;
    margin-top: 10px;
}
.night_mode .grammar-name { color: #999999; }
"""

NIHONGO_IT_COMPONENTS = """
.pronunciation { font-size: 18px; margin: 15px 0; color: #666666; line-height: 1.8; }
.key-vocab { font-size: 16px; color: #666666; margin-top: 15px; }
.vocab { font-weight: bold; color: #2B70C9; }
.blank { display: inline-block; min-width: 4em; border-bottom: 2px solid #2B2B2B; color: transparent; }
.cloze-answer { color: #2B70C9; font-weight: bold; }
.listening-front { margin: 40px 0; }
.register {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 0.75rem;
    font-size: 11px;
    font-weight: bold;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-top: 6px;
    margin-left: 6px;
    vertical-align: middle;
    border: 1px solid #E5E5E5;
}
.register-casual  { background: #F7F7F7; color: #666666; }
.register-polite  { background: #e3f2fd; color: #1565c0; border-color: #bbdefb; }
.register-formal  { background: #fff3e0; color: #e65100; border-color: #ffe0b2; }
.register-keigo   { background: #f3e5f5; color: #6a1b9a; border-color: #e1bee7; }
.pitch-h { color: #4caf50; }
.pitch-l { color: #f44336; }
.night_mode .translation { color: #E8E8E8; }
.night_mode .pronunciation { color: #999999; }
.night_mode .key-vocab { color: #999999; }
.night_mode .vocab { color: #6DB3F2; }
.night_mode .cloze-answer { color: #6DB3F2; }
.night_mode .blank { border-bottom-color: #999999; }
.night_mode .register { border-color: #333333; }
.night_mode .register-casual  { background: #252525; color: #999999; }
.night_mode .register-polite  { background: #1a2a3a; color: #64b5f6; border-color: #1a2a3a; }
.night_mode .register-formal  { background: #2a1f0e; color: #ffb74d; border-color: #2a1f0e; }
.night_mode .register-keigo   { background: #2a1a2a; color: #ce93d8; border-color: #2a1a2a; }
.night_mode .pitch-h { color: #81c784; }
.night_mode .pitch-l { color: #e57373; }
"""

CASES = [
    ("minihongo", "minihongo_shared_css", minihongo_css),
    ("nihongo-it", "nihongo_it_model_css", nihongo_it_css),
]


@pytest.mark.parametrize("label,golden_key,builder", CASES, ids=[c[0] for c in CASES])
def test_no_declaration_changes(label, golden_key, builder):
    old = theme.declarations(GOLDEN[golden_key])
    new = theme.declarations(builder())

    changed = []
    for selector in sorted(set(old) & set(new)):
        for prop, value in new[selector].items():
            if prop in old[selector]:
                if old[selector][prop] != value:
                    changed.append(f"{selector} {{{prop}}}: {old[selector][prop]!r} -> {value!r}")
            elif (selector, prop) not in INERT_ADDITIONS:
                changed.append(f"{selector} gained {{{prop}: {value}}}")
    assert not changed, f"{label} styling would change:\n  " + "\n  ".join(changed)


@pytest.mark.parametrize("label,golden_key,builder", CASES, ids=[c[0] for c in CASES])
def test_no_selector_dropped(label, golden_key, builder):
    """Every selector the original styled must still be styled."""
    old = set(theme.declarations(GOLDEN[golden_key]))
    new = set(theme.declarations(builder()))
    assert not (old - new), f"{label} would lose selectors: {sorted(old - new)}"


@pytest.mark.parametrize("label,golden_key,builder", CASES, ids=[c[0] for c in CASES])
def test_no_selector_invented(label, golden_key, builder):
    """And no dead selectors are introduced — layers must be opt-in."""
    old = set(theme.declarations(GOLDEN[golden_key]))
    new = set(theme.declarations(builder()))
    assert not (new - old), f"{label} would gain unused selectors: {sorted(new - old)}"


# ── layer behaviour ─────────────────────────────────────────────────


def test_scoped_replay_only_resizes():
    """A scoped replay must not re-declare the mask; it only overrides size."""
    scoped = theme.declarations(theme.replay(scope=".listening-front", size="5rem"))
    for props in scoped.values():
        assert "mask" not in props
        assert "-webkit-mask" not in props
        assert "background" not in props


def test_replay_masks_both_prefixed_and_unprefixed():
    """Anki's older clients need -webkit-mask; newer ones the standard property."""
    icon = theme.declarations(theme.replay())[".replay-button::before"]
    assert "mask" in icon and "-webkit-mask" in icon
    assert icon["mask"] == icon["-webkit-mask"]


def test_palette_override_propagates():
    css = theme.declarations(theme.base(palette=theme.PALETTE.but(rule="#123456")))
    assert css["hr#answer"]["border-top"] == "3px solid #123456"


def test_palette_but_does_not_mutate_shared_default():
    theme.PALETTE.but(accent="#000000")
    assert theme.PALETTE.accent == "#2B70C9"


def test_chip_selector_is_configurable():
    assert ".category" in theme.declarations(theme.chip(".category"))
    assert ".tags" not in theme.declarations(theme.chip(".category"))


def test_compose_appends_extra_last():
    """Consumer CSS must come after library layers to win ties at equal specificity."""
    out = theme.compose(theme.base(), extra=".card { padding: 0; }")
    assert out.rindex(".card { padding: 0; }") > out.rindex("line-height: 1.7")


def test_compose_skips_empty_layers():
    assert theme.compose("", "  ", ".a { b: c; }").strip() == ".a { b: c; }"


def test_declarations_merges_grouped_selectors():
    parsed = theme.declarations(".a, .b { color: red; } .a { size: 1px; }")
    assert parsed[".a"] == {"color": "red", "size": "1px"}
    assert parsed[".b"] == {"color": "red"}


def test_declarations_ignores_comments():
    assert theme.declarations("/* .x { color: red; } */ .y { color: blue; }") == {
        ".y": {"color": "blue"}
    }
