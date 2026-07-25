#!/usr/bin/env python3
"""One-shot: snapshot the pre-extraction behaviour of both source repos.

Run this BEFORE jpanki replaces anything. It imports the live functions out of
minihongo and nihongo-it-anki, runs them over a corpus drawn from those repos'
real CSVs plus hand-written edge cases, and writes the results to
tests/fixtures/golden_furigana.json.

test_furigana.py then asserts jpanki reproduces every entry. The point is that
extraction cannot silently change how already-published cards render.

Kept in the repo for provenance — it documents exactly where each golden value
came from. It does not need to run again unless a source repo is re-snapshotted.

    python3 tests/capture_golden.py [--minihongo PATH] [--nihongo-it PATH]
"""
import argparse
import csv
import importlib.util
import json
import re
import sys
import types
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


class _PermissiveStub(types.ModuleType):
    """A module whose every attribute resolves to a harmless placeholder.

    Needed because create_deck.py evaluates `genanki.Model` in a function
    annotation at import time, so a bare empty module isn't enough.
    """

    def __getattr__(self, attr):
        return type(attr, (), {})


def load_module(path: Path, name: str, stub_deps=()):
    """Import a standalone .py file, stubbing imports it doesn't need for us.

    generate_anki.py imports genanki at module scope; we only want its
    to_ruby_html, so a stub module is enough to get past the import.
    """
    for dep in stub_deps:
        sys.modules.setdefault(dep, _PermissiveStub(dep))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def corpus_from_csvs(*globs):
    """Every distinct field value containing furigana brackets."""
    found = set()
    for pattern in globs:
        for path in sorted(Path("/").glob(pattern.lstrip("/"))):
            try:
                rows = list(csv.DictReader(path.open(encoding="utf-8")))
            except (OSError, csv.Error):
                continue
            for row in rows:
                for value in row.values():
                    if value and "【" in value:
                        found.add(value)
    return found


# Edge cases worth pinning down regardless of whether the corpora contain them.
# Several of these are the exact points where the two repos disagreed.
SYNTHETIC = [
    "",
    "人【ひと】",
    "私【わたし】は人【ひと】だ。",
    "あの人【ひと】は誰【だれ】？",
    # 々 repetition mark: nihongo-it's regex includes 々, minihongo's does not.
    "少々【しょうしょう】",
    "徐々【じょじょ】に",
    "度々【たびたび】",
    # Digits before kanji: pronunciation.extract_furigana preserves them.
    "5分間【ふんかん】",
    "第2章【しょう】",
    # Kana attached to a kanji run — only the kanji run should take ruby.
    "ぶどう酒【ぶどうしゅ】",
    "生【い】き物【もの】",
    "読【よ】む",
    # Katakana and latin left alone.
    "コンピュータ",
    "API【エーピーアイ】",
    # No furigana at all.
    "これは本です。",
    "1234",
    # Pathological / malformed input: unclosed and empty brackets.
    "人【",
    "人【】",
    "【ひと】",
    "人【ひと】【ふたり】",
    # Full-width space inside a sentence.
    "私【わたし】は　本【ほん】を　読【よ】む。",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minihongo", type=Path, default=Path("/Users/cyril/Code/minihongo"))
    ap.add_argument("--nihongo-it", type=Path, default=Path("/Users/cyril/Code/nihongo-it-anki"))
    args = ap.parse_args()

    mh, nit = args.minihongo, args.nihongo_it

    # --- import the live implementations -------------------------------
    sys.path.insert(0, str(mh))
    mh_common = load_module(mh / "mh_common.py", "mh_common")
    mh_anki = load_module(mh / "generate_anki.py", "mh_generate_anki", stub_deps=["genanki"])
    mh_audio = load_module(mh / "generate_audio.py", "mh_generate_audio")

    sys.path.insert(0, str(nit / "scripts"))
    nit_pron = load_module(nit / "scripts" / "pronunciation.py", "nit_pronunciation")
    # create_deck.py imports genanki and config; we only want to_ruby_html, and
    # a stub genanki plus the real config on sys.path is enough.
    nit_deck = load_module(nit / "scripts" / "create_deck.py", "nit_create_deck", stub_deps=["genanki"])

    # --- build the corpus ---------------------------------------------
    corpus = corpus_from_csvs(
        str(mh / "data" / "*.csv"),
        str(nit / "decks" / "*" / "tier*.csv"),
    )
    print(f"corpus: {len(corpus)} distinct bracketed values from CSVs "
          f"+ {len(SYNTHETIC)} synthetic")

    # nihongo-it's extract_furigana consults a module-level override set rather
    # than taking it as an argument, so capture both the configured behaviour and
    # a clean no-override baseline. jpanki takes the set as a parameter, and must
    # reproduce each.
    nit_overrides = set(nit_pron.TTS_KANJI_OVERRIDES)
    # minihongo's text_for_tts has the mirror-image arrangement: a module-level
    # keep-list of kanji that TTS mispronounces as kana.
    mh_keep = set(mh_audio._KEEP_KANJI)

    entries = []
    for text in SYNTHETIC + sorted(corpus):
        nit_pron.TTS_KANJI_OVERRIDES = nit_overrides
        with_overrides = nit_pron.extract_furigana(text)
        nit_pron.TTS_KANJI_OVERRIDES = set()
        without_overrides = nit_pron.extract_furigana(text)
        nit_pron.TTS_KANJI_OVERRIDES = nit_overrides

        entries.append({
            "text": text,
            # minihongo's renderers
            "mh_to_ruby_html": mh_anki.to_ruby_html(text),
            "mh_strip_furigana": mh_common.strip_furigana(text),
            "mh_furigana_to_reading": mh_audio.furigana_to_reading(text),
            "mh_text_for_tts": mh_audio.text_for_tts(text),
            # nihongo-it-anki's renderers
            "nit_to_ruby_html": nit_deck.to_ruby_html(text),
            "nit_extract_furigana": with_overrides,
            "nit_extract_furigana_no_overrides": without_overrides,
        })

    # Where the two ruby renderers disagree, record it explicitly so the
    # divergence is documented rather than discovered later.
    divergent = [e["text"] for e in entries
                 if e["mh_to_ruby_html"] != e["nit_to_ruby_html"]]

    out = {
        "_note": (
            "Captured from the pre-extraction implementations. jpanki must "
            "reproduce mh_to_ruby_html for minihongo inputs and "
            "nit_to_ruby_html for nihongo-it inputs. Where they diverge, "
            "jpanki takes the superset (nihongo-it's, which includes \\u3005 "
            "々) -- verified to change zero rows in minihongo's Anki-consumed "
            "CSVs."
        ),
        "_sources": {
            "minihongo": {
                "to_ruby_html": "generate_anki.py:98",
                "strip_furigana": "mh_common.py:27",
                "furigana_to_reading": "generate_audio.py:156",
                "text_for_tts": "generate_audio.py:173",
            },
            "nihongo-it-anki": {
                "to_ruby_html": "scripts/create_deck.py:47",
                "extract_furigana": "scripts/pronunciation.py:472",
            },
        },
        "_ruby_divergence": divergent,
        "_nit_tts_kanji_overrides": sorted(nit_overrides),
        "_mh_keep_kanji": sorted(mh_keep),
        "entries": entries,
    }

    FIXTURES.mkdir(parents=True, exist_ok=True)
    dest = FIXTURES / "golden_furigana.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {dest} ({len(entries)} entries)")
    print(f"ruby renderers diverge on {len(divergent)} input(s): {divergent}")


if __name__ == "__main__":
    main()
