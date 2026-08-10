"""The registry must stay internally consistent, and must catch collisions."""
import pytest

from jpanki import ids


def test_shipped_registry_is_consistent():
    """The checked-in registry must never be in a colliding state."""
    ids.assert_unique()


def test_every_registered_deck_resolves():
    for slug in ids.load():
        assert ids.for_deck(slug).slug == slug


def test_unregistered_deck_raises_with_guidance():
    with pytest.raises(KeyError, match="not in ids.toml"):
        ids.for_deck("no-such-deck")


def test_detects_duplicate_model_id():
    registry = {
        "a": ids.Registration("a", (111,), 1_000, reserved=100),
        "b": ids.Registration("b", (111,), 2_000, reserved=100),
    }
    with pytest.raises(ids.IdCollision, match="model_id 111"):
        ids.assert_unique(registry)


def test_detects_overlapping_deck_ranges():
    """The exact failure that shipped: two decks sharing a deck_base_id."""
    registry = {
        "accounting": ids.Registration("accounting", (1,), 2261602312, reserved=200),
        "jp-teaching": ids.Registration("jp-teaching", (2,), 2261602312, reserved=200),
    }
    with pytest.raises(ids.IdCollision, match="overlap"):
        ids.assert_unique(registry)


def test_detects_adjacent_ranges_that_touch():
    """A range ending exactly where the next begins is still a collision."""
    registry = {
        "a": ids.Registration("a", (1,), 1_000, reserved=100),
        "b": ids.Registration("b", (2,), 1_100, reserved=100),
    }
    with pytest.raises(ids.IdCollision, match="overlap"):
        ids.assert_unique(registry)


def test_allows_ranges_with_a_gap():
    registry = {
        "a": ids.Registration("a", (1,), 1_000, reserved=100),
        "b": ids.Registration("b", (2,), 1_101, reserved=100),
    }
    ids.assert_unique(registry)


def test_detects_model_id_inside_a_deck_range():
    registry = {
        "a": ids.Registration("a", (1_050,), 5_000, reserved=100),
        "b": ids.Registration("b", (2,), 1_000, reserved=100),
    }
    with pytest.raises(ids.IdCollision, match="copy-paste"):
        ids.assert_unique(registry)


def test_jp_teaching_was_renumbered_away_from_accounting():
    """Regression guard for the collision this module was written to catch."""
    accounting = ids.for_deck("accounting")
    jp_teaching = ids.for_deck("jp-teaching")
    assert jp_teaching.deck_base_id != accounting.deck_base_id
    assert jp_teaching.previous_deck_base_id == accounting.deck_base_id, (
        "the old, colliding base must stay recorded so the migration is traceable"
    )
    assert not set(accounting.deck_id_range) & set(jp_teaching.deck_id_range)


def test_deck_id_is_derived_not_random():
    reg = ids.for_deck("bible")
    assert reg.deck_id(1) == reg.deck_base_id + 1
    assert reg.deck_id(1) == reg.deck_id(1)  # reproducible across calls


def test_deck_id_rejects_offset_outside_reservation():
    reg = ids.for_deck("bible")
    for bad in (0, -1, reg.reserved + 1):
        with pytest.raises(ValueError, match="reserved range"):
            reg.deck_id(bad)


def test_model_id_shortcut_rejects_ambiguity():
    """minihongo registers nine models, so `.model_id` must refuse to guess."""
    with pytest.raises(ValueError, match="9 model IDs"):
        _ = ids.for_deck("minihongo").model_id
    assert len(ids.for_deck("minihongo").model_ids) == 9


def test_minihongo_keeps_its_published_model_ids():
    """These are in the wild; renumbering them would orphan every note."""
    assert set(ids.for_deck("minihongo").model_ids) == {
        2007390001, 2007390002, 2007390003,
        2007390011, 2007390012, 2007390013,
        2007390021, 2007390022, 2007390023,
    }


def test_agentic_lab_keeps_the_ids_it_shipped_with():
    """agentic-lab shipped from nihongo-it-anki before it was registered here."""
    reg = ids.for_deck("agentic-lab")
    assert reg.model_id == 2011796738
    assert reg.deck_base_id == 2564905615
    assert reg.reserved == 200
    claimed = set(reg.deck_id_range)
    for other in ids.load().values():
        if other.slug == reg.slug:
            continue
        assert not claimed & set(other.deck_id_range)
        if other.previous_deck_base_id is not None:
            previous = range(
                other.previous_deck_base_id,
                other.previous_deck_base_id + other.reserved + 1,
            )
            assert not claimed & set(previous)


@pytest.mark.parametrize(
    "slug,model_id",
    [("it-vocab", 1607392323), ("it-kundoku", 1708493424), ("accounting", 1809594535),
     ("jp-teaching", 1809594536)],
)
def test_nihongo_it_keeps_its_published_model_ids(slug, model_id):
    assert ids.for_deck(slug).model_id == model_id
