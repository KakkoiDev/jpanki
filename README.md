# jpanki compatibility package

The authoritative implementation has moved to
[JP Core](https://github.com/KakkoiDev/jp-core). This repository preserves the
published `jpanki` import paths while existing projects migrate.

New projects should depend on JP Core and use `import jp_core`. Existing code
can continue to use `import jpanki`; its public modules are aliases of the JP
Core modules rather than copied implementations.

The remainder of this README documents the inherited API.

Shared mechanics for generating Japanese-language Anki decks.

Extracted from two projects that had independently converged on the same
solutions: [minihongo](https://github.com/KakkoiDev/minihongo) and
[nihongo-it-anki](https://github.com/KakkoiDev/nihongo-it-anki). Both used
genanki, the same `漢字【かな】` furigana notation, the same Edge TTS voices, the
same card CSS (Noto Sans JP, `#BC002D` answer rule, night mode, a
`-webkit-mask` replay-button restyle), and even the same trick for forcing Anki
to pick up new styling — with zero code in common.

This library owns that shared machinery. It deliberately does **not** own
content schemas or card templates: those are pedagogy, and each consumer keeps
its own.

## What's here

| Module | Owns |
|---|---|
| `furigana` | The `漢字【かな】` notation — one parser, several renderers |
| `romaji` | kana → rōmaji, for filenames and reading cross-checks |
| `theme` | The card CSS design system, as composable layers |
| `model` | genanki model/deck/package construction, media refs |
| `ids` | The deck/model ID registry that keeps consumers from colliding |
| `tts` | Edge TTS primitives: synthesise, normalise, merge |
| `validate` | CSV schema checks and build-freshness manifests |
| `release` | Publishing `.apkg` files as GitHub release assets |

## Install

```bash
uv add jpanki --git https://github.com/KakkoiDev/jpanki
```

Audio generation needs the extra and `ffmpeg` on `PATH`:

```bash
uv add "jpanki[audio]" --git https://github.com/KakkoiDev/jpanki
```

## The two rules that matter

**Note GUIDs are derived from a stable business key, never from content.**
`genanki`'s default hashes every field, so correcting one typo in a gloss
creates a *new* note and silently resets that card's review history for
everyone who re-imports the deck. Pass a key that identifies the note
independently of what it says:

```python
guid = jpanki.note_guid("bible", lesson, japanese)   # not the English gloss
```

**Deck and model IDs are registered, not invented.** An ID collision between
two decks silently merges them inside a user's collection. `ids.toml` records
every ID already published; `assert_unique()` fails the build on a clash. IDs
in that file are historical fact — record them, never renumber them.

## Development

```bash
uv sync
uv run pytest
```

The furigana tests are golden-file tests captured from the two original
implementations. They exist so that extraction cannot silently change how
hundreds of already-published cards render. Treat a diff there as a bug in the
library, not a stale fixture.
