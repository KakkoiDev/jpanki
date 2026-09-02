"""Release guards for preserving existing Anki deck identities."""

import json
import sqlite3
import zipfile

import pytest

from jpanki.release import ReleaseError, assert_deck_names_compatible, deck_names


def package(tmp_path, filename: str, decks: dict[int, str]):
    database = tmp_path / f"{filename}.anki2"
    with sqlite3.connect(database) as connection:
        connection.execute("create table col (decks text not null)")
        payload = {str(deck_id): {"name": name} for deck_id, name in decks.items()}
        connection.execute("insert into col values (?)", (json.dumps(payload),))
    output = tmp_path / filename
    with zipfile.ZipFile(output, "w") as archive:
        archive.write(database, "collection.anki2")
    return output


def test_deck_names_reads_ids_and_names(tmp_path):
    built = package(tmp_path, "deck.apkg", {11: "Course::Tier 01 - Start"})
    assert deck_names(built) == {11: "Course::Tier 01 - Start"}


def test_compatible_release_may_add_decks(tmp_path):
    previous = package(tmp_path, "old.apkg", {11: "Course::Tier 01 - Start"})
    candidate = package(tmp_path, "new.apkg", {
        11: "Course::Tier 01 - Start",
        12: "Course::Tier 02 - Next",
    })
    assert_deck_names_compatible(previous, candidate)


def test_guard_rejects_the_duplicate_deck_regression(tmp_path):
    previous = package(
        tmp_path, "old.apkg", {11: "Agentic Path::Tier 01 - Survival"}
    )
    candidate = package(
        tmp_path, "new.apkg", {11: "Agentic Path::01 Survival"}
    )
    with pytest.raises(ReleaseError, match=r"renamed ID 11.*Tier 01.*01 Survival"):
        assert_deck_names_compatible(previous, candidate)


def test_guard_rejects_lost_published_deck_id(tmp_path):
    previous = package(tmp_path, "old.apkg", {11: "Course::Tier 01 - Start"})
    candidate = package(tmp_path, "new.apkg", {})
    with pytest.raises(ReleaseError, match="removed ID 11"):
        assert_deck_names_compatible(previous, candidate)
