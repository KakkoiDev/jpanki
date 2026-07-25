#!/usr/bin/env python3
"""One-shot: snapshot both projects' card CSS before extraction.

Companion to capture_golden.py. Writes tests/fixtures/golden_css.json so
test_theme.py can assert that jpanki's composed stylesheets carry the same
declarations the originals shipped — rule by rule, not byte by byte, since
reformatting is fine but a changed colour or size is not.

    python3 tests/capture_css.py
"""
import argparse
import json
import re
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from capture_golden import load_module  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def extract_nit_css(path: Path) -> str:
    """Pull the css=''' ... ''' literal out of create_deck.create_model().

    Importing the module and calling create_model() would need a real genanki
    plus a DeckConfig, so read the literal straight out of the source instead.
    """
    source = path.read_text(encoding="utf-8")
    match = re.search(r"css=(?:r?)'''(.*?)'''", source, re.S)
    if not match:
        raise SystemExit(f"no css=''' literal found in {path}")
    return match.group(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minihongo", type=Path, default=Path("/Users/cyril/Code/minihongo"))
    ap.add_argument("--nihongo-it", type=Path, default=Path("/Users/cyril/Code/nihongo-it-anki"))
    args = ap.parse_args()

    sys.path.insert(0, str(args.minihongo))
    mh_anki = load_module(args.minihongo / "generate_anki.py", "mh_generate_anki_css",
                          stub_deps=["genanki"])

    out = {
        "_note": (
            "Card CSS as shipped before extraction. test_theme.py compares "
            "declaration sets, so whitespace and rule order may change freely "
            "but values may not."
        ),
        "minihongo_shared_css": mh_anki.SHARED_CSS,
        "nihongo_it_model_css": extract_nit_css(args.nihongo_it / "scripts" / "create_deck.py"),
    }

    FIXTURES.mkdir(parents=True, exist_ok=True)
    dest = FIXTURES / "golden_css.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for key in ("minihongo_shared_css", "nihongo_it_model_css"):
        print(f"{key}: {len(out[key])} chars, {out[key].count('{')} rules")
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
