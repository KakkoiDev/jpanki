"""CSV checks and the freshness manifest."""
import json

import pytest

from jpanki import validate


def write_csv(path, header, rows):
    lines = [",".join(header)] + [",".join(r) for r in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_load_rows_preserves_order(tmp_path):
    csv_path = write_csv(tmp_path / "a.csv", ["id", "v"], [["3", "c"], ["1", "a"], ["2", "b"]])
    assert [r["id"] for r in validate.load_rows(csv_path)] == ["3", "1", "2"]


def test_check_columns_accepts_exact_match():
    rows = [{"a": "1", "b": "2"}]
    assert validate.check_columns(rows, ["a", "b"], where="t").ok


def test_check_columns_reports_missing_and_extra():
    report = validate.check_columns([{"a": "1", "c": "2"}], ["a", "b"], where="t")
    assert not report.ok
    assert "missing ['b']" in report.errors[0] and "unexpected ['c']" in report.errors[0]


def test_check_columns_reports_wrong_order():
    report = validate.check_columns([{"b": "", "a": ""}], ["a", "b"], where="t")
    assert "wrong order" in report.errors[0]


def test_check_columns_rejects_empty_file():
    assert "no rows" in validate.check_columns([], ["a"], where="t").errors[0]


def test_check_required_flags_blank_and_whitespace():
    rows = [{"id": "1", "v": "x"}, {"id": "2", "v": ""}, {"id": "3", "v": "   "}]
    report = validate.check_required(rows, ["v"], where="t", id_column="id")
    assert len(report.errors) == 2
    assert "(2)" in report.errors[0] and "(3)" in report.errors[1]


def test_check_required_line_numbers_account_for_header():
    report = validate.check_required([{"v": ""}], ["v"], where="t")
    assert "t:2" in report.errors[0], "first data row is file line 2"


def test_check_unique_detects_duplicates():
    report = validate.check_unique([{"id": "a"}, {"id": "b"}, {"id": "a"}], "id", where="t")
    assert len(report.errors) == 1
    assert "lines 2 and 4" in report.errors[0]


def test_check_media_warns_when_optional(tmp_path):
    report = validate.check_media([{"a": "x.mp3"}], "a", tmp_path, where="t")
    assert report.ok and len(report.warnings) == 1


def test_check_media_errors_when_required(tmp_path):
    report = validate.check_media([{"a": "x.mp3"}], "a", tmp_path, where="t", required=True)
    assert not report.ok


def test_check_media_accepts_present_file(tmp_path):
    (tmp_path / "x.mp3").write_bytes(b"x")
    report = validate.check_media([{"a": "x.mp3"}], "a", tmp_path, where="t", required=True)
    assert report.ok and not report.warnings


def test_check_media_skips_blank_references(tmp_path):
    report = validate.check_media([{"a": ""}], "a", tmp_path, where="t", required=True)
    assert report.ok


def test_report_accumulates_and_renders():
    report = validate.Report()
    report.error("bad")
    report.warn("iffy")
    assert not report.ok
    assert "ERROR  bad" in report.render() and "WARN   iffy" in report.render()


def test_report_extend_merges():
    a, b = validate.Report(), validate.Report()
    a.error("one")
    b.warn("two")
    a.extend(b)
    assert a.errors == ["one"] and a.warnings == ["two"]


def test_report_raise_if_failed():
    report = validate.Report()
    report.warn("only a warning")
    report.raise_if_failed()  # warnings alone must not block
    report.error("now blocking")
    with pytest.raises(ValueError, match="validation failed"):
        report.raise_if_failed()


# ── freshness ───────────────────────────────────────────────────────


def test_manifest_hashes_inputs(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("x", encoding="utf-8")
    assert list(validate.manifest([f])["inputs"]) == [str(f)]


def test_manifest_rejects_missing_input(tmp_path):
    with pytest.raises(FileNotFoundError):
        validate.manifest([tmp_path / "nope.csv"])


def test_check_fresh_passes_when_unchanged(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("x", encoding="utf-8")
    m = tmp_path / "m.json"
    validate.write_manifest([f], m)
    assert validate.check_fresh([f], m).ok


def test_check_fresh_detects_edited_input(tmp_path):
    """The failure mode this exists for: deck released, then content edited."""
    f = tmp_path / "a.csv"
    f.write_text("x", encoding="utf-8")
    m = tmp_path / "m.json"
    validate.write_manifest([f], m)
    f.write_text("y", encoding="utf-8")
    report = validate.check_fresh([f], m)
    assert not report.ok and "changed since the last release" in report.errors[0]


def test_check_fresh_detects_new_input(tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    a.write_text("x", encoding="utf-8")
    b.write_text("y", encoding="utf-8")
    m = tmp_path / "m.json"
    validate.write_manifest([a], m)
    assert "new build input" in validate.check_fresh([a, b], m).errors[0]


def test_check_fresh_detects_removed_input(tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    a.write_text("x", encoding="utf-8")
    b.write_text("y", encoding="utf-8")
    m = tmp_path / "m.json"
    validate.write_manifest([a, b], m)
    assert "now gone" in validate.check_fresh([a], m).errors[0]


def test_check_fresh_detects_library_version_change(tmp_path):
    """A jpanki upgrade can change rendering, so it must invalidate freshness."""
    f = tmp_path / "a.csv"
    f.write_text("x", encoding="utf-8")
    m = tmp_path / "m.json"
    validate.write_manifest([f], m, extra={"jpanki": "0.1.0"})
    report = validate.check_fresh([f], m, extra={"jpanki": "0.2.0"})
    assert not report.ok and "build environment changed" in report.errors[0]


def test_check_fresh_requires_a_manifest(tmp_path):
    report = validate.check_fresh([], tmp_path / "absent.json")
    assert "no manifest" in report.errors[0]


def test_manifest_is_stable_across_input_order(tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    a.write_text("x", encoding="utf-8")
    b.write_text("y", encoding="utf-8")
    assert validate.manifest([a, b]) == validate.manifest([b, a])
