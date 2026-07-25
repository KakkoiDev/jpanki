"""The card CSS design system, as composable layers.

Both projects had arrived at the same visual language independently — Noto Sans
JP with system fallbacks, a `#BC002D` answer divider in Japanese-flag red, a
`#2B70C9` blue accent, chip-styled category labels, centred ruby with small grey
readings, a full `.night_mode` counterpart, and a replay button restyled by
masking an inline SVG. Two stylesheets, ~2.9 KB and ~4.8 KB, maintained
separately.

They are layers here rather than one blob because the projects legitimately
disagree in places. The clearest case is the replay button: minihongo wants it
at 2.5 rem, while nihongo-it-anki's listening card wants a 5 rem button as the
dominant element on an otherwise empty front. That is a real design difference,
so :func:`replay` is parameterised instead of forked.

Composition is explicit — nothing is applied unless a consumer asks for it:

    css = theme.compose(
        theme.base(),
        theme.ruby(),
        theme.chip(".tags"),
        theme.replay(),
        theme.night(),
        extra=MY_COMPONENT_CSS,
    )

Component styling specific to one project's card types — register badges, pitch
accent colours, cloze blanks, grammar pattern names — stays with that project.
This module owns the shared foundation only.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class Palette:
    """The colour and type tokens both projects share.

    Override any of these to re-skin a deck without rewriting rules:

        theme.base(palette=theme.PALETTE.but(accent="#2E7D32"))
    """

    text: str = "#2B2B2B"
    background: str = "#FFFFFF"
    muted: str = "#666666"
    border: str = "#E5E5E5"
    surface: str = "#F7F7F7"
    #: Japanese-flag red, used for the question/answer divider.
    rule: str = "#BC002D"
    #: Interactive blue, used for the replay icon and highlighted vocabulary.
    accent: str = "#2B70C9"

    # Night-mode counterparts. Anki toggles these via its own .night_mode class.
    night_text: str = "#E8E8E8"
    night_background: str = "#1A1A1A"
    night_muted: str = "#999999"
    night_border: str = "#333333"
    night_surface: str = "#252525"
    night_accent: str = "#6DB3F2"

    font_stack: str = '"Noto Sans JP", "Hiragino Sans", "Yu Gothic", system-ui, sans-serif'
    radius: str = "0.75rem"

    def but(self, **overrides) -> "Palette":
        """A copy with some tokens replaced."""
        return replace(self, **overrides)


PALETTE = Palette()

# The speaker icon used for the replay button, as a data URI. Kept as one
# constant because it is repeated in both the -webkit- and unprefixed mask
# properties, and Anki's desktop and mobile clients need different ones.
_SPEAKER_SVG = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'"
    "%3E%3Cpath d='M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0014 8.5v7a4.47 4.47 0 002.5"
    "-3.5zM14 3.23v2.06a6.51 6.51 0 010 13.42v2.06A8.51 8.51 0 0014 3.23z'/%3E%3C/svg%3E"
)


def base(
    *,
    palette: Palette = PALETTE,
    font_size: str = "20px",
    sentence_size: str = "22px",
    sentence_margin: str = "15px 0",
) -> str:
    """The card surface, the classes every card type uses, and the answer divider.

    ``sentence_size`` is a parameter because the projects disagree: minihongo
    sets 22px, nihongo-it-anki 28px, because the latter's cards put a single
    sentence at the centre of attention while the former's pair it with a
    headword. Both are right for their layout.
    """
    p = palette
    return f"""
.card {{
    font-family: {p.font_stack};
    font-size: {font_size};
    text-align: center;
    color: {p.text};
    background: {p.background};
    padding: 24px;
    line-height: 1.7;
}}
.card-type {{
    font-size: 12px;
    color: {p.muted};
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 15px;
}}
.sentence {{
    font-size: {sentence_size};
    margin: {sentence_margin};
    line-height: 1.8;
}}
.translation {{
    font-size: 22px;
    margin: 15px 0;
    line-height: 1.6;
}}
.audio {{ margin: 10px 0; text-align: center; }}
hr#answer {{ border: none; border-top: 3px solid {p.rule}; margin: 20px 0; }}
"""


def headword(*, palette: Palette = PALETTE) -> str:
    """A large headword plus an italic hint, for vocabulary-style cards.

    Opt-in, because sentence-based decks have no headword and would otherwise
    carry dead selectors.
    """
    return f"""
.word {{
    font-size: 32px;
    font-weight: bold;
    margin: 20px 0 15px;
    line-height: 2;
}}
.hint {{
    font-size: 18px;
    font-style: italic;
    margin: 10px 0;
    color: {palette.muted};
}}
"""


def ruby(*, palette: Palette = PALETTE, size: str = "12px") -> str:
    """Centred ruby with small, de-emphasised readings."""
    return f"""
ruby {{ ruby-align: center; }}
ruby rt {{ font-size: {size}; font-weight: normal; color: {palette.muted}; }}
"""


def chip(selector: str = ".tags", *, palette: Palette = PALETTE) -> str:
    """A pill-shaped label, for category and lesson names.

    ``selector`` exists because the two projects named this differently —
    minihongo calls it ``.tags``, nihongo-it-anki calls it ``.category`` — for
    visually identical output. Pass whichever the card templates already use;
    renaming published templates is not worth the churn.
    """
    p = palette
    return f"""
{selector} {{
    display: inline-block;
    background: {p.surface};
    padding: 4px 12px;
    border-radius: {p.radius};
    font-size: 12px;
    color: {p.muted};
    border: 1px solid {p.border};
    margin-top: 10px;
}}
"""


def replay(
    *,
    palette: Palette = PALETTE,
    size: str = "2.5rem",
    icon_size: str = "1.2rem",
    radius: str | None = None,
    scope: str = "",
) -> str:
    """Restyle Anki's replay button to match the projects' play button.

    Anki renders audio as a link containing its own markup, which cannot be
    styled directly. The approach both projects landed on: hide the children,
    then draw the icon as a masked block on ``::before``. A mask rather than a
    background so the icon takes ``accent`` as its colour.

    ``scope`` prefixes the selectors, which is how a single card type gets an
    outsized button without affecting the rest of the deck:

        replay() + replay(scope=".listening-front", size="5rem", icon_size="2.5rem")
    """
    p = palette
    prefix = f"{scope} " if scope else ""
    button = f"{prefix}.replay-button, {prefix}.replaybutton"
    icon = f"{prefix}.replay-button::before, {prefix}.replaybutton::before"
    radius = radius or p.radius

    if scope:
        # A scoped call only resizes the button the unscoped call already drew.
        # Re-declaring the mask and colours here would be redundant.
        return f"""
{button} {{
    width: {size};
    height: {size};
    border-radius: {radius};
}}
{icon} {{
    width: {icon_size};
    height: {icon_size};
}}
"""

    return f"""
{button} {{
    display: flex !important;
    align-items: center;
    justify-content: center;
    width: {size};
    height: {size};
    margin: 0 auto;
    border: 2px solid {p.border};
    border-radius: {radius};
    background: {p.background};
    cursor: pointer;
    text-decoration: none;
}}
.replay-button *, .replaybutton * {{ display: none !important; }}
{icon} {{
    content: "";
    flex-shrink: 0;
    width: {icon_size};
    height: {icon_size};
    background: {p.accent};
    -webkit-mask: url("{_SPEAKER_SVG}") center / contain no-repeat;
    mask: url("{_SPEAKER_SVG}") center / contain no-repeat;
}}
"""


def night(
    *,
    palette: Palette = PALETTE,
    chip_selector: str = ".tags",
    muted_selectors: tuple[str, ...] = (".card-type",),
) -> str:
    """Night-mode counterparts for everything the other layers define.

    Anki adds ``.night_mode`` to the body, so this is plain CSS specificity
    rather than a media query — which matters, because a reviewer's Anki theme
    is independent of their OS theme.

    ``muted_selectors`` lists project-specific classes that should follow the
    muted colour into dark mode, so consumers do not have to hand-write the
    parallel rules for their own components.
    """
    p = palette
    muted = ",\n".join(f".night_mode {s}" for s in muted_selectors)
    return f"""
.night_mode .card {{
    color: {p.night_text};
    background: {p.night_background};
}}
{muted} {{ color: {p.night_muted}; }}
.night_mode {chip_selector} {{
    background: {p.night_surface};
    border-color: {p.night_border};
    color: {p.night_muted};
}}
.night_mode ruby rt {{ color: {p.night_muted}; }}
.night_mode hr#answer {{ border-top-color: {p.rule}; }}
.night_mode .replay-button, .night_mode .replaybutton {{
    border-color: {p.night_border};
    background: {p.night_background};
}}
"""


def compose(*layers: str, extra: str = "") -> str:
    """Join layers into one stylesheet, trimming incidental blank lines.

    ``extra`` is appended last so a consumer's own component CSS wins any tie
    with a library layer at equal specificity.
    """
    parts = [layer.strip("\n") for layer in (*layers, extra) if layer and layer.strip()]
    return "\n" + "\n\n".join(parts) + "\n"


def declarations(css: str) -> dict[str, dict[str, str]]:
    """Parse a stylesheet into ``{selector: {property: value}}``.

    A comparison helper, not a real parser — it exists so tests can assert two
    stylesheets carry the same declarations regardless of formatting, rule
    order, or how the rules were grouped. Handles only flat rule sets, which is
    all Anki card CSS needs (no nesting, no at-rules).
    """
    import re

    out: dict[str, dict[str, str]] = {}
    # Strip comments, then walk `selector { body }` pairs.
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selectors, body = match.group(1), match.group(2)
        props: dict[str, str] = {}
        for decl in body.split(";"):
            if ":" not in decl:
                continue
            prop, _, value = decl.partition(":")
            props[prop.strip()] = " ".join(value.split())
        for selector in selectors.split(","):
            key = " ".join(selector.split())
            if key:
                out.setdefault(key, {}).update(props)
    return out
