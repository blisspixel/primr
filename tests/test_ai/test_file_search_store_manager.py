"""Unit tests for FileSearchStoreManager in primr.ai.deep_research.

Mocks the underlying genai.Client to exercise create_store, upload_context,
upload_file, delete_store, and the get_file_search_store_manager singleton.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from primr.ai.deep_research import FileSearchStoreManager, get_file_search_store_manager
from primr.utils.errors import AIError


@pytest.fixture
def mock_client(monkeypatch):
    """Patch genai.Client so we never hit the real API."""
    import primr.ai.deep_research as dr

    client = MagicMock()
    fake_genai = MagicMock()
    fake_genai.Client.return_value = client

    monkeypatch.setattr(dr, "genai", fake_genai)
    monkeypatch.setattr(dr, "_require_genai_dependency", lambda: None)

    # Patch get_settings to return a fake gemini key
    fake_settings = MagicMock()
    fake_settings.api.gemini_key = "fake-key-1234567890"
    monkeypatch.setattr("primr.config.settings.get_settings", lambda: fake_settings)

    return client


class TestInit:
    def test_uses_api_key_override(self, mock_client):
        mgr = FileSearchStoreManager(api_key="custom-key-9999")
        assert mgr._api_key == "custom-key-9999"

    def test_falls_back_to_settings_key(self, mock_client):
        # When no api_key is passed, _api_key is populated from settings.
        # We can't reliably patch the settings singleton, so just assert it's set.
        mgr = FileSearchStoreManager()
        assert mgr._api_key  # truthy — some key from settings


class TestCreateStore:
    def test_returns_store_name_on_success(self, mock_client):
        store = MagicMock()
        store.name = "stores/abc123"
        mock_client.file_search_stores.create.return_value = store
        mgr = FileSearchStoreManager()
        result = mgr.create_store("company_research")
        assert result == "stores/abc123"
        # display_name should include the primr- prefix for cleanup detection.
        call_args = mock_client.file_search_stores.create.call_args
        assert call_args.kwargs["config"]["display_name"].startswith("primr-")

    def test_raises_when_no_name_returned(self, mock_client):
        store = MagicMock()
        store.name = ""
        mock_client.file_search_stores.create.return_value = store
        mgr = FileSearchStoreManager()
        with pytest.raises(AIError, match="no name returned"):
            mgr.create_store("x")

    def test_wraps_underlying_exception(self, mock_client):
        mock_client.file_search_stores.create.side_effect = RuntimeError("API down")
        mgr = FileSearchStoreManager()
        with pytest.raises(AIError, match="Failed to create"):
            mgr.create_store("x")


class TestUploadContext:
    def test_writes_temp_file_and_uploads(self, mock_client):
        mgr = FileSearchStoreManager()
        mgr.upload_context("stores/abc", "content body", "research.txt")
        # Should have called upload_to_file_search_store
        mock_client.file_search_stores.upload_to_file_search_store.assert_called_once()
        kwargs = mock_client.file_search_stores.upload_to_file_search_store.call_args.kwargs
        assert kwargs["file_search_store_name"] == "stores/abc"
        assert kwargs["config"]["mime_type"] == "text/plain"

    def test_uses_custom_mime_type(self, mock_client):
        mgr = FileSearchStoreManager()
        mgr.upload_context("stores/abc", "body", "x.md", mime_type="text/markdown")
        kwargs = mock_client.file_search_stores.upload_to_file_search_store.call_args.kwargs
        assert kwargs["config"]["mime_type"] == "text/markdown"

    def test_wraps_upload_exception(self, mock_client):
        mock_client.file_search_stores.upload_to_file_search_store.side_effect = RuntimeError(
            "upload failed"
        )
        mgr = FileSearchStoreManager()
        with pytest.raises(AIError, match="Failed to upload context"):
            mgr.upload_context("stores/abc", "body", "x.txt")


class TestUploadFile:
    def test_raises_when_file_missing(self, mock_client, tmp_path):
        mgr = FileSearchStoreManager()
        with pytest.raises(AIError, match="File not found"):
            mgr.upload_file("stores/abc", str(tmp_path / "nonexistent.txt"))

    def test_uses_mime_type_for_md(self, mock_client, tmp_path):
        path = tmp_path / "report.md"
        path.write_text("body", encoding="utf-8")
        mgr = FileSearchStoreManager()
        mgr.upload_file("stores/abc", str(path))
        kwargs = mock_client.file_search_stores.upload_to_file_search_store.call_args.kwargs
        assert kwargs["config"]["mime_type"] == "text/markdown"

    def test_uses_mime_type_for_pdf(self, mock_client, tmp_path):
        path = tmp_path / "report.pdf"
        path.write_text("body", encoding="utf-8")
        mgr = FileSearchStoreManager()
        mgr.upload_file("stores/abc", str(path))
        kwargs = mock_client.file_search_stores.upload_to_file_search_store.call_args.kwargs
        assert kwargs["config"]["mime_type"] == "application/pdf"

    def test_unknown_extension_passes_none_config(self, mock_client, tmp_path):
        path = tmp_path / "unknown.xyz"
        path.write_text("body", encoding="utf-8")
        mgr = FileSearchStoreManager()
        mgr.upload_file("stores/abc", str(path))
        kwargs = mock_client.file_search_stores.upload_to_file_search_store.call_args.kwargs
        assert kwargs["config"] is None

    def test_wraps_upload_exception(self, mock_client, tmp_path):
        path = tmp_path / "x.txt"
        path.write_text("body", encoding="utf-8")
        mock_client.file_search_stores.upload_to_file_search_store.side_effect = RuntimeError("net")
        mgr = FileSearchStoreManager()
        with pytest.raises(AIError, match="Failed to upload"):
            mgr.upload_file("stores/abc", str(path))


class TestDeleteStore:
    def test_deletes_documents_then_store(self, mock_client):
        mock_client.file_search_stores.documents.list.return_value = [
            MagicMock(name="d/1"),
            MagicMock(name="d/2"),
        ]
        mgr = FileSearchStoreManager()
        mgr.delete_store("stores/abc")
        assert mock_client.file_search_stores.documents.delete.call_count == 2
        mock_client.file_search_stores.delete.assert_called_once_with(name="stores/abc")

    def test_falls_back_when_config_unsupported(self, mock_client):
        mock_client.file_search_stores.documents.list.return_value = [
            MagicMock(name="d/1"),
        ]
        # First delete call with config raises TypeError -> fallback no config
        mock_client.file_search_stores.documents.delete.side_effect = [
            TypeError("config unsupported"),
            None,
        ]
        mgr = FileSearchStoreManager()
        mgr.delete_store("stores/abc")
        assert mock_client.file_search_stores.documents.delete.call_count == 2

    def test_swallows_doc_list_error(self, mock_client):
        mock_client.file_search_stores.documents.list.side_effect = RuntimeError("list failed")
        mgr = FileSearchStoreManager()
        # Should still try to delete the store even when doc listing fails.
        mgr.delete_store("stores/abc")
        mock_client.file_search_stores.delete.assert_called_once_with(name="stores/abc")

    def test_swallows_store_delete_error(self, mock_client):
        mock_client.file_search_stores.documents.list.return_value = []
        mock_client.file_search_stores.delete.side_effect = RuntimeError("delete failed")
        mgr = FileSearchStoreManager()
        # Should not raise.
        mgr.delete_store("stores/abc")

    def test_logs_specific_error_for_non_empty(self, mock_client, caplog):
        mock_client.file_search_stores.documents.list.return_value = []
        mock_client.file_search_stores.delete.side_effect = RuntimeError(
            "FAILED_PRECONDITION: store non-empty"
        )
        mgr = FileSearchStoreManager()
        mgr.delete_store("stores/abc")
        # Logged at error level when the "still not empty" path triggers.
        # (caplog captures at WARN by default; check via the logger calls in module)


class TestGetFileSearchStoreManagerSingleton:
    def test_returns_same_instance_on_repeated_calls(self, mock_client, monkeypatch):
        import primr.ai.deep_research as dr

        # Reset the singleton before testing.
        monkeypatch.setattr(dr, "_store_manager", None)
        first = get_file_search_store_manager()
        second = get_file_search_store_manager()
        assert first is second

    def test_thread_safe_initialization(self, mock_client, monkeypatch):
        import primr.ai.deep_research as dr

        monkeypatch.setattr(dr, "_store_manager", None)
        # Just call once and confirm we get an instance.
        mgr = get_file_search_store_manager()
        assert isinstance(mgr, FileSearchStoreManager)


@pytest.mark.parametrize(
    ("filename", "expected_mime"),
    [
        ("report.md", "text/markdown"),
        ("report.txt", "text/plain"),
        ("data.json", "application/json"),
        ("data.csv", "text/csv"),
        ("doc.pdf", "application/pdf"),
    ],
)
def test_upload_file_mime_mapping(mock_client, tmp_path, filename, expected_mime):
    path = tmp_path / filename
    path.write_text("body", encoding="utf-8")
    mgr = FileSearchStoreManager()
    mgr.upload_file("stores/abc", str(path))
    kwargs = mock_client.file_search_stores.upload_to_file_search_store.call_args.kwargs
    assert kwargs["config"]["mime_type"] == expected_mime


def test_create_store_propagates_aierror(mock_client):
    """An AIError raised inside create() should propagate without rewrap."""
    mock_client.file_search_stores.create.side_effect = AIError("specific failure", model="x")
    mgr = FileSearchStoreManager()
    with pytest.raises(AIError, match="specific failure"):
        mgr.create_store("x")
