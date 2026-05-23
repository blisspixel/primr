"""Regression test for ResearchMemory.list_companies robustness.

yaml.safe_load can return non-mapping values (a bare scalar or list) for a
malformed or planted *.yaml file in the memory directory. The listing must skip
those instead of raising TypeError on `"company_name" in data` (or later when
the CLI sorts the returned values).
"""

from __future__ import annotations

from primr.agentic.memory import ResearchMemory


def test_list_companies_skips_non_mapping_and_non_string(tmp_path):
    mem = ResearchMemory(storage_path=tmp_path)

    # Valid entry — a mapping with a string company_name.
    (tmp_path / "acme.yaml").write_text("company_name: Acme Corp\n", encoding="utf-8")
    # Bare scalar — safe_load returns an int.
    (tmp_path / "scalar.yaml").write_text("42\n", encoding="utf-8")
    # Bare sequence — safe_load returns a list.
    (tmp_path / "list.yaml").write_text("- a\n- b\n", encoding="utf-8")
    # Mapping, but company_name is not a string.
    (tmp_path / "weird.yaml").write_text("company_name: 123\n", encoding="utf-8")
    # Mapping without a company_name at all.
    (tmp_path / "nokey.yaml").write_text("other: value\n", encoding="utf-8")

    # Must not raise despite the malformed files.
    companies = mem.list_companies()

    assert "Acme Corp" in companies
    # Only well-formed string names survive — the non-mapping/non-string
    # entries are dropped, and sorted() on the result can't blow up.
    assert all(isinstance(c, str) and c for c in companies)
    assert 123 not in companies
    sorted(companies)  # exercises the CLI's downstream sort path
