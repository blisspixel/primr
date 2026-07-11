import pytest

from primr.output.artifact_inventory import (
    classify_artifact,
    inventory_explicit,
    inventory_explicit_result,
    scan_artifact_roots,
)


def test_explicit_inventory_preserves_missing_and_expands_exact_siblings(tmp_path):
    md = tmp_path / "Acme_Strategic_Overview.md"
    docx = md.with_suffix(".docx")
    manifest = tmp_path / "run_manifest.json"
    md.write_text("report", encoding="utf-8")
    docx.write_bytes(b"docx")
    manifest.write_text("{}", encoding="utf-8")
    missing = tmp_path / "missing.txt"

    records = inventory_explicit([md, missing], expand_adjacent=True, include_hash=True)

    by_name = {record.path.name: record for record in records}
    assert by_name["missing.txt"].exists is False
    assert by_name[docx.name].source == "adjacent"
    assert manifest.name not in by_name
    assert by_name[md.name].content_hash.startswith("sha256:")


def test_bounded_scan_finds_deliverables_qa_and_fallbacks(tmp_path):
    (tmp_path / "report.md").write_text("body", encoding="utf-8")
    (tmp_path / "report.docx").write_bytes(b"docx")
    (tmp_path / "report_QA.json").write_text("{}", encoding="utf-8")
    (tmp_path / "recovered_deep_research_abcd.txt").write_text("body", encoding="utf-8")
    (tmp_path / "README.md").write_text("not an output", encoding="utf-8")

    result = scan_artifact_roots([tmp_path])
    names = {record.path.name for record in result["artifacts"]}
    assert {
        "report.md",
        "report.docx",
        "report_QA.json",
        "recovered_deep_research_abcd.txt",
    } <= names


def test_classification_covers_manifest_and_verification(tmp_path):
    assert classify_artifact(tmp_path / "run_manifest.json") == "run_manifest"
    assert classify_artifact(tmp_path / "verification.json") == "verification_summary"


def test_scan_keeps_newest_matches_and_reports_limits(tmp_path):
    import os

    for index in range(6):
        path = tmp_path / f"report_{index}.md"
        path.write_text(str(index), encoding="utf-8")
        os.utime(path, (index + 1, index + 1))

    result = scan_artifact_roots([tmp_path], max_paths=3, max_entries=20)
    assert [record.path.name for record in result["artifacts"]] == [
        "report_5.md",
        "report_4.md",
        "report_3.md",
    ]
    assert result["matched_count"] == 6
    assert result["truncated"] is True


def test_scan_stops_at_entry_budget(tmp_path):
    for index in range(8):
        (tmp_path / f"report_{index}.md").write_text("body", encoding="utf-8")

    result = scan_artifact_roots([tmp_path], max_entries=3)
    assert result["visited_entries"] == 3
    assert result["truncated"] is True


def test_scan_does_not_follow_nested_directory_symlink(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "secret.md").write_text("body", encoding="utf-8")
    link = tmp_path / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")

    result = scan_artifact_roots([tmp_path])
    assert "secret.md" not in {record.path.name for record in result["artifacts"]}


def test_explicit_inventory_reports_total_path_cap(tmp_path):
    paths = [tmp_path / f"missing_{index}.md" for index in range(5)]
    result = inventory_explicit_result(paths, expand_adjacent=True, max_paths=2)
    assert [record.path for record in result.records] == paths[:2]
    assert result.truncated is True


def test_exact_adjacent_expansion_preserves_dotted_stem(tmp_path):
    markdown = tmp_path / "report.v2.md"
    docx = tmp_path / "report.v2.docx"
    markdown.write_text("body", encoding="utf-8")
    docx.write_bytes(b"docx")

    records = inventory_explicit([markdown], expand_adjacent=True)
    assert {record.path.name for record in records} == {markdown.name, docx.name}
