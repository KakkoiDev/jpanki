"""CSV schema checks and build-freshness manifests.

Two independent jobs that both answer "is this deck safe to ship":

* :func:`check_columns` and friends validate the content itself.
* :func:`manifest` / :func:`check_fresh` detect a deck built from inputs that
  have since changed. minihongo had this (an ``.anki-manifest`` of input
  hashes, gating its deploy); nihongo-it-anki had nothing, and could silently
  publish a deck whose CSVs had moved on.
"""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Report:
    """Accumulated problems, separated by whether they should block a build."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def extend(self, other: "Report") -> "Report":
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        return self

    @property
    def ok(self) -> bool:
        return not self.errors

    def render(self) -> str:
        lines = [f"ERROR  {m}" for m in self.errors]
        lines += [f"WARN   {m}" for m in self.warnings]
        return "\n".join(lines) or "no problems found"

    def raise_if_failed(self) -> None:
        if self.errors:
            raise ValueError("validation failed:\n" + self.render())


def load_rows(path: Path) -> list[dict[str, str]]:
    """Read a CSV into dicts, preserving row order.

    Row order is load-bearing in one of the consumers — nihongo-it-anki derives
    audio filenames from row index — so this never sorts.
    """
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def check_columns(rows: list[dict[str, str]], expected: list[str], *, where: str) -> Report:
    """Assert the CSV has exactly the expected columns, in order."""
    report = Report()
    if not rows:
        report.error(f"{where}: no rows")
        return report
    actual = list(rows[0].keys())
    if actual != expected:
        missing = [c for c in expected if c not in actual]
        extra = [c for c in actual if c not in expected]
        detail = []
        if missing:
            detail.append(f"missing {missing}")
        if extra:
            detail.append(f"unexpected {extra}")
        if not detail:
            detail.append(f"wrong order: {actual}")
        report.error(f"{where}: columns {'; '.join(detail)}")
    return report


def check_required(
    rows: list[dict[str, str]],
    columns: list[str],
    *,
    where: str,
    id_column: str | None = None,
) -> Report:
    """Assert the given columns are non-empty in every row."""
    report = Report()
    for index, row in enumerate(rows, start=2):  # +2: header is line 1
        label = f"{where}:{index}"
        if id_column and row.get(id_column):
            label += f" ({row[id_column]})"
        for column in columns:
            if not (row.get(column) or "").strip():
                report.error(f"{label}: {column} is empty")
    return report


def check_unique(rows: list[dict[str, str]], column: str, *, where: str) -> Report:
    """Assert a column's values are distinct."""
    report = Report()
    seen: dict[str, int] = {}
    for index, row in enumerate(rows, start=2):
        value = row.get(column, "")
        if value in seen:
            report.error(f"{where}: {column}={value!r} duplicated (lines {seen[value]} and {index})")
        else:
            seen[value] = index
    return report


def check_media(
    rows: list[dict[str, str]],
    column: str,
    directory: Path,
    *,
    where: str,
    required: bool = False,
) -> Report:
    """Check that referenced audio files exist.

    ``required=False`` reports absences as warnings, which suits vocabulary
    cards that degrade gracefully to no audio. Pass ``required=True`` for card
    types whose front is the audio.
    """
    report = Report()
    for index, row in enumerate(rows, start=2):
        name = (row.get(column) or "").strip()
        if not name:
            continue
        if not (directory / name).exists():
            message = f"{where}:{index}: audio {name} not found in {directory}"
            report.error(message) if required else report.warn(message)
    return report


# ── freshness ───────────────────────────────────────────────────────


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(inputs: list[Path], *, extra: dict[str, str] | None = None) -> dict:
    """Hash every build input, for writing next to a released artifact."""
    missing = [p for p in inputs if not p.exists()]
    if missing:
        raise FileNotFoundError(f"cannot manifest missing inputs: {missing}")
    return {
        "inputs": {str(p): _hash_file(p) for p in sorted(inputs)},
        **({"extra": extra} if extra else {}),
    }


def write_manifest(inputs: list[Path], path: Path, *, extra: dict[str, str] | None = None) -> Path:
    """Write a manifest after a successful release."""
    path.write_text(json.dumps(manifest(inputs, extra=extra), indent=1) + "\n", encoding="utf-8")
    return path


def check_fresh(inputs: list[Path], path: Path, *, extra: dict[str, str] | None = None) -> Report:
    """Compare current inputs against a stored manifest.

    Catches the failure mode where content is edited, committed and deployed
    while the published deck still reflects the previous state — invisible
    without a check like this, because nothing about the site or the repo looks
    stale.

    ``extra`` should carry things that affect output but are not files, most
    importantly the library version: a jpanki upgrade can change rendering, and
    a manifest that only hashes CSVs would call the deck fresh regardless.
    """
    report = Report()
    if not path.exists():
        report.error(f"no manifest at {path}; run the release target to create it")
        return report

    stored = json.loads(path.read_text(encoding="utf-8"))
    current = manifest(inputs, extra=extra)

    stored_inputs, current_inputs = stored.get("inputs", {}), current["inputs"]
    for name in sorted(set(stored_inputs) | set(current_inputs)):
        if name not in stored_inputs:
            report.error(f"{name} is a new build input since the last release")
        elif name not in current_inputs:
            report.error(f"{name} was a build input at release time but is now gone")
        elif stored_inputs[name] != current_inputs[name]:
            report.error(f"{name} changed since the last release")

    if stored.get("extra") != current.get("extra"):
        report.error(
            f"build environment changed since release: "
            f"{stored.get('extra')} -> {current.get('extra')}"
        )
    return report
