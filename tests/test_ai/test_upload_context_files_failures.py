"""Edge-case tests for DeepResearchClient._upload_context_files: upload errors,
store-creation errors, missing-store-name response, MIME type detection."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from primr.ai.deep_research import DeepResearchClient
from primr.utils.errors import AIError


@pytest.fixture
def client(monkeypatch):
    import primr.ai.deep_research as dr

    mock_genai = MagicMock()
    mock_genai.Client.return_value = MagicMock()
    monkeypatch.setattr(dr, "genai", mock_genai)
    monkeypatch.setattr(dr, "_require_genai_dependency", lambda: None)
    monkeypatch.setattr(dr, "_orchestrator", None)
    monkeypatch.setattr(dr, "_client", None)
    return DeepResearchClient(api_key="fake-key-1234567890")


@pytest.fixture
def md_file(tmp_path):
    p = tmp_path / "context.md"
    p.write_text("# Heading\n\ncontent", encoding="utf-8")
    return str(p)


@pytest.fixture
def pdf_file(tmp_path):
    p = tmp_path / "doc.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    return str(p)


def test_missing_files_raises_before_api_call(client, tmp_path):
    bogus = str(tmp_path / "nope.txt")
    with pytest.raises(AIError) as exc_info:
        client._upload_context_files([bogus])
    assert "not found" in str(exc_info.value).lower()
    # API was never called
    client._client.file_search_stores.create.assert_not_called()


def test_store_creation_returns_empty_name_raises(client, md_file):
    store = MagicMock()
    store.name = ""
    client._client.file_search_stores.create.return_value = store
    with pytest.raises(AIError) as exc_info:
        client._upload_context_files([md_file])
    assert "no name returned" in str(exc_info.value).lower()


def test_store_creation_failure_raises_and_no_cleanup(client, md_file):
    client._client.file_search_stores.create.side_effect = RuntimeError("create failed")
    with pytest.raises(AIError) as exc_info:
        client._upload_context_files([md_file])
    assert "Failed to create file store" in str(exc_info.value)
    # No store created -> no cleanup attempted
    client._client.file_search_stores.delete.assert_not_called()


def test_upload_failure_cleans_up_store(client, md_file):
    store = MagicMock()
    store.name = "stores/abc"
    client._client.file_search_stores.create.return_value = store
    client._client.file_search_stores.upload_to_file_search_store.side_effect = RuntimeError(
        "upload failed"
    )
    # documents.list returns [] so cleanup proceeds to delete-store call
    client._client.file_search_stores.documents.list.return_value = []
    with pytest.raises(AIError) as exc_info:
        client._upload_context_files([md_file])
    assert "Failed to upload" in str(exc_info.value)
    # Cleanup happens
    client._client.file_search_stores.delete.assert_called_once()


def test_pdf_uses_pdf_mime_type(client, pdf_file):
    store = MagicMock()
    store.name = "stores/abc"
    client._client.file_search_stores.create.return_value = store
    client._upload_context_files([pdf_file])
    call_kwargs = client._client.file_search_stores.upload_to_file_search_store.call_args.kwargs
    assert call_kwargs["config"]["mime_type"] == "application/pdf"


def test_unknown_extension_passes_none_config(client, tmp_path):
    p = tmp_path / "weird.xyz"
    p.write_text("data", encoding="utf-8")
    store = MagicMock()
    store.name = "stores/abc"
    client._client.file_search_stores.create.return_value = store
    client._upload_context_files([str(p)])
    call_kwargs = client._client.file_search_stores.upload_to_file_search_store.call_args.kwargs
    assert call_kwargs["config"] is None
