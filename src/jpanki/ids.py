"""The model and deck ID registry.

Anki keys models and decks by integer ID, not by name. Two consequences drive
this module:

* Two decks sharing a deck ID **silently merge** in a user's collection. The
  second import does not error, does not warn — it lands the notes in the first
  deck's subdeck. This had already happened: ``accounting`` and ``jp-teaching``
  shipped with the same ``deck_base_id``.
* A model ID that changes **orphans** the notes using the old one, which is why
  ``--force-style`` is a deliberate, separate operation rather than automatic.

With one project minting IDs by hand, collisions were unlikely. With three,
they are a matter of time, so the IDs live in one checked-in file and
:func:`assert_unique` runs at build time.

The registry records history. Add to it; do not renumber a published entry.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

REGISTRY_PATH = Path(__file__).parent / "ids.toml"

#: How many deck IDs a registration reserves above its base, when the entry
#: doesn't say. Covers tiers plus the +100 female-voice offset.
DEFAULT_RESERVED = 200


class IdCollision(Exception):
    """Two registrations claim the same model ID or overlapping deck ID range."""


@dataclass(frozen=True)
class Registration:
    """One deck's reserved IDs."""

    slug: str
    model_ids: tuple[int, ...]
    deck_base_id: int
    reserved: int = DEFAULT_RESERVED
    previous_deck_base_id: int | None = None

    @property
    def model_id(self) -> int:
        """The single model ID, for the common case of one model per deck."""
        if len(self.model_ids) != 1:
            raise ValueError(
                f"{self.slug} registers {len(self.model_ids)} model IDs; "
                f"use .model_ids and index explicitly"
            )
        return self.model_ids[0]

    @property
    def deck_id_range(self) -> range:
        """Every deck ID this registration reserves."""
        return range(self.deck_base_id, self.deck_base_id + self.reserved + 1)

    def deck_id(self, offset: int) -> int:
        """A deck ID derived from the base — e.g. ``deck_id(tier)``.

        Deriving rather than randomising is what makes a build reproducible:
        rebuild the same content twice and Anki sees the same decks, so a
        re-import updates in place instead of duplicating.
        """
        if not 0 < offset <= self.reserved:
            raise ValueError(
                f"offset {offset} outside {self.slug}'s reserved range "
                f"(1..{self.reserved}); widen `reserved` in ids.toml"
            )
        return self.deck_base_id + offset


def load(path: Path | None = None) -> dict[str, Registration]:
    """Read the registry."""
    raw = tomllib.loads((path or REGISTRY_PATH).read_text(encoding="utf-8"))
    out: dict[str, Registration] = {}
    for slug, entry in raw.items():
        out[slug] = Registration(
            slug=slug,
            model_ids=tuple(entry["model_ids"]),
            deck_base_id=entry["deck_base_id"],
            reserved=entry.get("reserved", DEFAULT_RESERVED),
            previous_deck_base_id=entry.get("previous_deck_base_id"),
        )
    return out


def for_deck(slug: str, path: Path | None = None) -> Registration:
    """Look up one deck's IDs, failing loudly if it isn't registered."""
    registry = load(path)
    try:
        return registry[slug]
    except KeyError:
        raise KeyError(
            f"deck {slug!r} is not in {REGISTRY_PATH.name}; add it (with IDs no "
            f"other entry claims) before building. Registered: "
            f"{sorted(registry)}"
        ) from None


def assert_unique(registry: dict[str, Registration] | None = None) -> None:
    """Raise :class:`IdCollision` if any two registrations overlap.

    Call this from every consumer's build. It is cheap, and it is the only thing
    standing between a copy-pasted config and two decks merging in someone
    else's collection.
    """
    registry = registry if registry is not None else load()
    problems: list[str] = []

    seen_models: dict[int, str] = {}
    for reg in registry.values():
        for model_id in reg.model_ids:
            if model_id in seen_models:
                problems.append(
                    f"model_id {model_id} claimed by both "
                    f"{seen_models[model_id]!r} and {reg.slug!r}"
                )
            seen_models[model_id] = reg.slug

    entries = sorted(registry.values(), key=lambda r: r.deck_base_id)
    for earlier, later in zip(entries, entries[1:]):
        end = earlier.deck_base_id + earlier.reserved
        if later.deck_base_id <= end:
            problems.append(
                f"deck ID ranges overlap: {earlier.slug!r} reserves "
                f"{earlier.deck_base_id}..{end} but {later.slug!r} starts at "
                f"{later.deck_base_id}"
            )

    # A model ID doubling as a deck ID is legal in Anki (separate namespaces)
    # but almost always signals a copy-paste, so flag it too.
    deck_ids = {i for reg in registry.values() for i in reg.deck_id_range}
    for model_id, slug in seen_models.items():
        if model_id in deck_ids:
            owner = next(r.slug for r in registry.values() if model_id in r.deck_id_range)
            problems.append(
                f"model_id {model_id} ({slug!r}) falls inside {owner!r}'s "
                f"reserved deck ID range — probably a copy-paste"
            )

    if problems:
        raise IdCollision(
            "ID registry is inconsistent:\n  " + "\n  ".join(problems)
        )
