"""genanki construction: models, decks, media references, and the ID policy.

The thin part of this module wraps genanki. The load-bearing part is the GUID
policy, which fixes a real defect in one of the source projects.

**Why GUIDs matter.** Anki matches an incoming note against an existing one by
GUID. genanki's default GUID is a hash of *every field value*, so correcting a
single typo in an English gloss produces a note Anki has never seen. On
re-import it is added alongside the old one, and the review history — the
scheduling a learner has built up over months — stays attached to the note they
can no longer see. minihongo shipped with default GUIDs. nihongo-it-anki keyed
on its sentence text, which is better but still content, and it had to build
``migrate_guids.py`` and a 293-row migration map the first time it edited
sentences in bulk.

So :func:`note_guid` takes a *business key*: whatever identifies the note
independently of what it currently says. A row ID, or a
``(deck, lesson, headword)`` tuple. Get this right once and content is free to
be corrected forever.

**Why deck IDs matter.** minihongo minted them with ``random.randint`` on every
build, so no two builds produced the same decks and rebuild-twice was never
idempotent. Derive them from a registered base instead — see :mod:`jpanki.ids`.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import genanki


@dataclass
class NoteSpec:
    """Everything needed to build one genanki model.

    ``templates`` is passed to genanki unchanged: a list of dicts with ``name``,
    ``qfmt`` and ``afmt``. Card templates are pedagogy, so the library carries
    them rather than generating them.
    """

    name: str
    model_id: int
    fields: list[str]
    templates: list[dict]
    css: str = ""
    #: genanki's model type. The default (0) is the standard front/back model;
    #: cloze models are type 1. Both source projects use 0 — nihongo-it-anki
    #: implements cloze in template JavaScript instead, to keep one note type.
    model_type: int = 0

    def field_index(self, name: str) -> int:
        """Position of a field, for building note value lists safely."""
        return self.fields.index(name)


def build_model(spec: NoteSpec) -> genanki.Model:
    """Construct the genanki model described by ``spec``."""
    return genanki.Model(
        spec.model_id,
        spec.name,
        fields=[{"name": name} for name in spec.fields],
        templates=spec.templates,
        css=spec.css,
        model_type=spec.model_type,
    )


def build_deck(deck_id: int, name: str) -> genanki.Deck:
    """Construct a deck with an explicit, reproducible ID.

    There is deliberately no default for ``deck_id``: randomising it is the bug
    this signature exists to prevent. Get one from
    :meth:`jpanki.ids.Registration.deck_id`.
    """
    return genanki.Deck(deck_id, name)


def subdeck(
    parent: str,
    position: int,
    label: str,
    *,
    total: int | None = None,
    width: int | None = None,
    number_prefix: str = "",
    separator: str = " ",
) -> str:
    """Build a ``Parent::NN Label`` subdeck name.

    Anki sorts the deck sidebar lexically, with no way to specify an order, so
    both projects independently arrived at zero-padded numeric prefixes to make
    the sidebar follow curriculum order. The width is at least two digits and,
    when ``total`` is supplied, grows automatically with the collection:
    1-99 subdecks use ``01`` and 100-999 use ``001``.

    ``width`` remains available for callers with a fixed external naming
    contract. New collection builders should pass ``total`` instead.

    ``number_prefix`` and ``separator`` preserve an established public naming
    scheme while centralising the padding. For example, ``number_prefix="Tier "``
    and ``separator=" - "`` produces ``Parent::Tier 01 - Label``.
    """
    if position < 1:
        raise ValueError("subdeck position must be positive")
    if total is not None:
        if total < 1:
            raise ValueError("subdeck total must be positive")
        if position > total:
            raise ValueError(f"position {position} exceeds total {total}")
        automatic_width = max(2, len(str(total)))
        if width is not None and width != automatic_width:
            raise ValueError("pass either total or width, not conflicting values")
        width = automatic_width
    elif width is None:
        width = 2

    if position >= 10 ** width:
        raise ValueError(
            f"position {position} needs more than {width} digits, which would "
            f"break Anki's lexical sidebar ordering; pass a wider `width`"
        )
    return (
        f"{parent}::{number_prefix}{position:0{width}d}"
        f"{separator}{label}"
    )


def note_guid(*key_parts: object) -> str:
    """A stable GUID from a business key.

    Pass parts that identify the note but do not change when its content is
    corrected:

        note_guid("bible", lesson, japanese)     # good
        note_guid("bible", english_translation)  # bad: editing the gloss orphans it

    Parts are stringified and joined with a separator that cannot appear in a
    slug, so ``("a", "b:c")`` and ``("a:b", "c")`` do not collide.
    """
    if not key_parts:
        raise ValueError("note_guid needs at least one key part")
    key = "\x1f".join(str(part) for part in key_parts)
    return genanki.guid_for(key)


def sound_ref(path: Path | None, *, require: bool = False) -> tuple[str, Path | None]:
    """Build an Anki ``[sound:...]`` reference, tolerating a missing file.

    Returns the field value and the media path to register, or ``("", None)``
    when the clip is absent.

    ``require=True`` raises instead. Use it for card types whose front is the
    audio: a listening card with no clip has a blank front and is unreviewable,
    so shipping one is worse than failing the build. minihongo already refused
    to build its listening deck without audio; that check lives here now.
    """
    if path is None or not path.exists():
        if require:
            raise FileNotFoundError(
                f"required audio missing: {path}. A card whose front is audio "
                f"cannot ship without it — generate audio before building."
            )
        return "", None
    return f"[sound:{path.name}]", path


def force_style(model_id: int, css: str) -> int:
    """Offset a model ID by a hash of its CSS, so Anki re-reads the styling.

    Anki keeps the model definition — including CSS — from the first import and
    ignores changes on later imports of the same model ID. The only way to push
    restyled cards to existing users is to present a new model, which means
    **resetting review history for every note using it**.

    Both projects independently invented this exact trick and both put it behind
    a separate ``--force-style`` flag rather than applying it automatically.
    Keep it that way: it is a deliberate, occasional, destructive operation.

    Deterministic in the CSS, so the same stylesheet always yields the same ID.
    """
    digest = hashlib.sha256(css.encode("utf-8")).hexdigest()[:6]
    return model_id + int(digest, 16)


@dataclass
class Package:
    """A deck package under construction.

    Collects decks and deduplicates media paths, because the same clip is often
    referenced by several notes and genanki would otherwise store it twice.
    """

    decks: list[genanki.Deck] = field(default_factory=list)
    _media: dict[str, Path] = field(default_factory=dict)

    def add_deck(self, deck: genanki.Deck) -> genanki.Deck:
        self.decks.append(deck)
        return deck

    def add_media(self, path: Path | None) -> None:
        if path is not None:
            # Key on filename: that is what the [sound:] reference resolves,
            # so two different paths with one basename are a genuine conflict.
            existing = self._media.get(path.name)
            if existing is not None and existing != path:
                raise ValueError(
                    f"two different files claim the media name {path.name!r}: "
                    f"{existing} and {path}"
                )
            self._media[path.name] = path

    @property
    def media_files(self) -> list[str]:
        return [str(p) for _, p in sorted(self._media.items())]

    def write(self, output: Path) -> Path:
        """Write the ``.apkg``, returning the path."""
        if not self.decks:
            raise ValueError("refusing to write a package with no decks")
        package = genanki.Package(self.decks)
        package.media_files = self.media_files
        output.parent.mkdir(parents=True, exist_ok=True)
        package.write_to_file(str(output))
        return output

    def note_count(self) -> int:
        return sum(len(deck.notes) for deck in self.decks)
