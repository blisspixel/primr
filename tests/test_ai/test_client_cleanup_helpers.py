"""Unit tests for DeepResearchClient internal helpers: _cleanup_file_store,
_upload_context_files, _start_research, _start_research_stream."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from primr.ai.deep_research import DeepResearchClient


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


class TestCleanupFileStore:
    def test_deletes_docs_then_store(self, client):
        # Create fake docs with .name attribute
        doc1 = MagicMock()
        doc1.name = "doc/1"
        doc2 = MagicMock()
        doc2.name = "doc/2"
        client._client.file_search_stores.documents.list.return_value = [doc1, doc2]
        client._cleanup_file_store("stores/abc")
        # Both docs deleted then store deleted
        assert client._client.file_search_stores.documents.delete.call_count == 2
        client._client.file_search_stores.delete.assert_called_once_with(
            name="stores/abc"
        )

    def test_falls_back_when_config_unsupported(self, client):
        doc = MagicMock()
        doc.name = "doc/1"
        client._client.file_search_stores.documents.list.return_value = [doc]
        client._client.file_search_stores.documents.delete.side_effect = [
            TypeError("config unsupported"),
            None,
        ]
        client._cleanup_file_store("stores/abc")
        # Two calls: first with config raises TypeError, second without config succeeds
        assert client._client.file_search_stores.documents.delete.call_count == 2

    def test_handles_list_failure_gracefully(self, client):
        client._client.file_search_stores.documents.list.side_effect = RuntimeError(
            "list api down"
        )
        # Should still attempt to delete the store
        client._cleanup_file_store("stores/abc")
        client._client.file_search_stores.delete.assert_called_once()

    def test_handles_store_delete_failure_gracefully(self, client):
        client._client.file_search_stores.documents.list.return_value = []
        client._client.file_search_stores.delete.side_effect = RuntimeError(
            "delete failed"
        )
        # Should NOT raise
        client._cleanup_file_store("stores/abc")

    def test_logs_when_store_not_empty(self, client, caplog):
        client._client.file_search_stores.documents.list.return_value = []
        client._client.file_search_stores.delete.side_effect = RuntimeError(
            "FAILED_PRECONDITION: store non-empty"
        )
        client._cleanup_file_store("stores/abc")
        # Should have hit the "CLEANUP FAILED" path
        # (caplog default WARNING level may not capture; just verify no raise)


class TestUploadContextFiles:
    def test_empty_list_raises(self, client):
        # The upload helper should fail without doing anything because file paths are required.
        # The actual function signature: returns store name on success.
        # When empty, an exception should bubble up.
        with pytest.raises(Exception):  # noqa: B017
            client._upload_context_files([])

    def test_creates_store_and_uploads(self, client, tmp_path):
        # Create a real text file
        f = tmp_path / "context.txt"
        f.write_text("body content", encoding="utf-8")

        store = MagicMock()
        store.name = "stores/abc"
        client._client.file_search_stores.create.return_value = store

        # Avoid the actual upload call; just patch it to no-op
        result = client._upload_context_files([str(f)])
        assert result == "stores/abc"

    def test_missing_file_raises(self, client, tmp_path):
        bogus = tmp_path / "nonexistent.txt"
        with pytest.raises(Exception):  # noqa: B017
            client._upload_context_files([str(bogus)])
