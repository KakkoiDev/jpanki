"""Publishing `.apkg` files as GitHub release assets, via the `gh` CLI.

The two projects had arrived at different, and both reasonable, tag strategies:

* minihongo uses one **rolling** tag (``anki``) whose assets are replaced in
  place, because its site downloads the current decks at build time and only
  ever wants the latest.
* nihongo-it-anki uses **namespaced version** tags (``it-vocab/v5.1``), because
  its four decks are released independently and users may want an older one.

Both are supported. Neither is converted to the other: the tags are already
published, and rewriting release history to unify a naming convention would
break existing download URLs for no benefit.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class ReleaseError(RuntimeError):
    """A `gh` invocation failed."""


def _gh(*args: str, dry_run: bool = False) -> str:
    command = ["gh", *args]
    if dry_run:
        print("  would run:", " ".join(command))
        return ""
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        raise ReleaseError(
            "gh not found on PATH. Install the GitHub CLI and authenticate with "
            "`gh auth login` to publish releases."
        ) from None
    except subprocess.CalledProcessError as error:
        raise ReleaseError(f"gh {' '.join(args)} failed:\n{error.stderr.strip()}") from None
    return result.stdout.strip()


def tag_exists(tag: str) -> bool:
    try:
        _gh("release", "view", tag, "--json", "tagName")
        return True
    except ReleaseError:
        return False


@dataclass
class Release:
    """A release to publish.

    ``tag`` is the whole strategy: pass a constant like ``"anki"`` for a rolling
    release, or ``f"{slug}/{version}"`` for a namespaced one.
    """

    tag: str
    title: str
    assets: list[Path]
    notes: str | None = None
    notes_file: Path | None = None
    draft: bool = False

    def validate(self) -> None:
        if not self.assets:
            raise ReleaseError("no assets to upload")
        missing = [p for p in self.assets if not p.exists()]
        if missing:
            raise ReleaseError(f"assets missing — build them first: {missing}")
        if self.notes and self.notes_file:
            raise ReleaseError("pass notes or notes_file, not both")
        if self.notes_file and not self.notes_file.exists():
            raise ReleaseError(f"notes file not found: {self.notes_file}")

    def _notes_args(self) -> list[str]:
        if self.notes_file:
            return ["--notes-file", str(self.notes_file)]
        if self.notes:
            return ["--notes", self.notes]
        return ["--notes", ""]


def publish(release: Release, *, dry_run: bool = False) -> None:
    """Create the release, or update it in place if the tag already exists.

    Updating rather than recreating is deliberate: deleting and recreating a
    release breaks any link to it and, for a rolling tag, would briefly leave
    users with no deck to download.
    """
    release.validate()
    assets = [str(p) for p in release.assets]

    if tag_exists(release.tag):
        print(f"updating existing release {release.tag}")
        _gh("release", "upload", release.tag, *assets, "--clobber", dry_run=dry_run)
        _gh("release", "edit", release.tag, "--title", release.title,
            *release._notes_args(), dry_run=dry_run)
    else:
        print(f"creating release {release.tag}")
        args = ["release", "create", release.tag, *assets,
                "--title", release.title, *release._notes_args()]
        if release.draft:
            args.append("--draft")
        _gh(*args, dry_run=dry_run)

    for asset in release.assets:
        size_mb = asset.stat().st_size / 1_000_000
        print(f"  {asset.name}  ({size_mb:.1f} MB)")


def download(tag: str, pattern: str, destination: Path, *, dry_run: bool = False) -> None:
    """Fetch release assets, overwriting local copies.

    Used by minihongo's site build, which treats the release as the source of
    truth for decks rather than building them in CI.
    """
    destination.mkdir(parents=True, exist_ok=True)
    _gh("release", "download", tag, "--pattern", pattern,
        "--dir", str(destination), "--clobber", dry_run=dry_run)
