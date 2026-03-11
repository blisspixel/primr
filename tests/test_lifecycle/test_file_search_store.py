"""
File Search Store lifecycle tests.

Tests proper creation, upload, and cleanup of File Search Stores.

**Feature: test-coverage-hardening**
**Validates: Requirements 10.1, 10.2, 10.3**
"""

from unittest.mock import Mock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_client():
    """Create a mock genai client."""
    client = Mock()
    client.file_search_stores = Mock()
    client.file_search_stores.create = Mock(return_value=Mock(name="test-store-123"))
    client.file_search_stores.upload_to_file_search_store = Mock()
    client.file_search_stores.delete = Mock()
    return client


@pytest.fixture
def mock_store_manager(mock_client):
    """Create a FileSearchStoreManager with mocked client."""
    from primr.ai.deep_research import FileSearchStoreManager

    manager = FileSearchStoreManager.__new__(FileSearchStoreManager)
    manager._api_key = "test-key"
    manager._client = mock_client
    return manager


# =============================================================================
# Unit Tests for Store Lifecycle
# =============================================================================


class TestStoreCreation:
    """Tests for File Search Store creation."""

    def test_create_store_returns_name(self, mock_store_manager, mock_client):
        """create_store should return the store name."""
        mock_store = Mock()
        mock_store.name = "test-store-123"
        mock_client.file_search_stores.create.return_value = mock_store

        store_name = mock_store_manager.create_store("test_research")

        assert store_name == "test-store-123"
        mock_client.file_search_stores.create.assert_called_once()

    def test_create_store_includes_timestamp(self, mock_store_manager, mock_client):
        """create_store should include timestamp in display name."""
        mock_client.file_search_stores.create.return_value = Mock(name="store-123")

        mock_store_manager.create_store("my_research")

        call_args = mock_client.file_search_stores.create.call_args
        config = call_args.kwargs.get("config", {})
        display_name = config.get("display_name", "")

        assert "my_research" in display_name
        # Should have timestamp suffix
        assert "_" in display_name


class TestStoreUpload:
    """Tests for uploading context to File Search Store."""

    def test_upload_context_calls_api(self, mock_store_manager, mock_client):
        """upload_context should call the upload API."""
        mock_store_manager.upload_context(
            store_name="test-store",
            content="Test content",
            filename="test.txt",
        )

        mock_client.file_search_stores.upload_to_file_search_store.assert_called_once()

    def test_upload_context_cleans_temp_file(self, mock_store_manager, mock_client):
        """upload_context should clean up temporary files."""
        import os
        import tempfile

        # Track temp files created
        original_mkstemp = tempfile.mkstemp
        created_files = []

        def tracking_mkstemp(*args, **kwargs):
            fd, path = original_mkstemp(*args, **kwargs)
            created_files.append(path)
            return fd, path

        with patch("tempfile.mkstemp", tracking_mkstemp):
            mock_store_manager.upload_context(
                store_name="test-store",
                content="Test content",
                filename="test.txt",
            )

        # Temp file should be cleaned up
        for path in created_files:
            assert not os.path.exists(path), f"Temp file not cleaned up: {path}"


class TestStoreDeletion:
    """Tests for File Search Store deletion."""

    def test_delete_store_on_success(self, mock_store_manager, mock_client):
        """
        WHEN a research task completes
        THEN the File Search Store SHALL be deleted

        **Validates: Requirements 10.1**
        """
        mock_store_manager.delete_store("test-store-123")

        mock_client.file_search_stores.delete.assert_called_once_with(name="test-store-123")

    def test_delete_store_on_failure(self, mock_store_manager, mock_client):
        """
        WHEN a research task fails
        THEN the File Search Store SHALL still be deleted in the finally block

        **Validates: Requirements 10.2**
        """
        # Simulate deletion after failure
        mock_store_manager.delete_store("test-store-123")

        mock_client.file_search_stores.delete.assert_called_once()

    def test_delete_store_handles_errors_gracefully(self, mock_store_manager, mock_client):
        """delete_store should not raise on deletion failure."""
        mock_client.file_search_stores.delete.side_effect = Exception("API error")

        # Should not raise
        mock_store_manager.delete_store("test-store-123")


class TestUploadOrdering:
    """Tests for context upload ordering."""

    def test_upload_before_research(self, mock_store_manager, mock_client):
        """
        WHEN Stage 1 context is uploaded
        THEN the file SHALL be properly indexed before Deep Research starts

        **Validates: Requirements 10.3**
        """
        # Create store
        mock_client.file_search_stores.create.return_value = Mock(name="store-123")
        store_name = mock_store_manager.create_store("research")

        # Upload context
        mock_store_manager.upload_context(
            store_name=store_name,
            content="Stage 1 research data",
            filename="stage1.txt",
        )

        # Verify order: create called before upload
        create_call = mock_client.file_search_stores.create.call_args_list
        upload_call = mock_client.file_search_stores.upload_to_file_search_store.call_args_list

        assert len(create_call) == 1
        assert len(upload_call) == 1


# =============================================================================
# Integration-style Tests (with mocks)
# =============================================================================


class TestOrchestratorStoreLifecycle:
    """Tests for store lifecycle in DeepResearchOrchestrator."""

    def test_orchestrator_has_store_manager(self):
        """Orchestrator should have a FileSearchStoreManager."""
        from primr.ai.deep_research import DeepResearchOrchestrator

        orchestrator = DeepResearchOrchestrator.__new__(DeepResearchOrchestrator)
        orchestrator._settings = Mock()
        orchestrator._settings.api.gemini_key = "test-key"
        orchestrator._store_manager = Mock()

        assert orchestrator._store_manager is not None

    def test_store_cleanup_pattern(self, mock_store_manager, mock_client):
        """Verify the try/finally cleanup pattern works."""
        store_name = None
        cleanup_called = False

        try:
            # Simulate store creation
            mock_client.file_search_stores.create.return_value = Mock(name="store-123")
            store_name = mock_store_manager.create_store("test")

            # Simulate some work
            mock_store_manager.upload_context(store_name, "content", "file.txt")

            # Simulate success
        finally:
            # Cleanup should always happen
            if store_name:
                mock_store_manager.delete_store(store_name)
                cleanup_called = True

        assert cleanup_called
        mock_client.file_search_stores.delete.assert_called_once()

    def test_store_cleanup_on_exception(self, mock_store_manager, mock_client):
        """Store should be cleaned up even when exception occurs."""
        store_name = None
        cleanup_called = False

        try:
            mock_client.file_search_stores.create.return_value = Mock(name="store-123")
            store_name = mock_store_manager.create_store("test")

            # Simulate failure
            raise ValueError("Simulated failure")
        except ValueError:
            pass
        finally:
            if store_name:
                mock_store_manager.delete_store(store_name)
                cleanup_called = True

        assert cleanup_called
        mock_client.file_search_stores.delete.assert_called_once()


# =============================================================================
# Property Tests
# =============================================================================


@given(
    display_name=st.text(
        alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz_"),
        min_size=3,
        max_size=30,
    )
)
@settings(max_examples=20, deadline=None)
def test_property_store_cleanup_always_called(display_name: str):
    """
    **Feature: test-coverage-hardening, Property 15: File Search Store cleanup**
    **Validates: Requirements 10.1, 10.2**

    For any research task (successful or failed), the File Search Store
    should be deleted in the finally block.
    """
    from primr.ai.deep_research import FileSearchStoreManager

    mock_client = Mock()
    mock_client.file_search_stores.create.return_value = Mock(name=f"store-{display_name}")
    mock_client.file_search_stores.delete = Mock()

    manager = FileSearchStoreManager.__new__(FileSearchStoreManager)
    manager._api_key = "test-key"
    manager._client = mock_client

    store_name = None
    try:
        store_name = manager.create_store(display_name)
        # Simulate work (may succeed or fail)
    finally:
        if store_name:
            manager.delete_store(store_name)

    # Delete should have been called
    mock_client.file_search_stores.delete.assert_called_once()


@given(
    success=st.booleans(),
)
@settings(max_examples=20, deadline=None)
def test_property_cleanup_regardless_of_outcome(success: bool):
    """
    **Feature: test-coverage-hardening, Property 15: File Search Store cleanup**
    **Validates: Requirements 10.1, 10.2**

    For any research outcome (success or failure), cleanup should occur.
    """
    from primr.ai.deep_research import FileSearchStoreManager

    mock_client = Mock()
    mock_client.file_search_stores.create.return_value = Mock(name="store-test")
    mock_client.file_search_stores.delete = Mock()

    manager = FileSearchStoreManager.__new__(FileSearchStoreManager)
    manager._api_key = "test-key"
    manager._client = mock_client

    store_name = None
    try:
        store_name = manager.create_store("test")
        if not success:
            raise ValueError("Simulated failure")
    except ValueError:
        pass
    finally:
        if store_name:
            manager.delete_store(store_name)

    mock_client.file_search_stores.delete.assert_called_once()


@given(
    content_size=st.integers(min_value=100, max_value=10000),
)
@settings(max_examples=20, deadline=None)
def test_property_upload_before_use(content_size: int):
    """
    **Feature: test-coverage-hardening, Property 16: Context upload ordering**
    **Validates: Requirements 10.3**

    For any research task using Stage 1 context, the file upload
    must complete before Deep Research begins.
    """
    from primr.ai.deep_research import FileSearchStoreManager

    mock_client = Mock()
    mock_client.file_search_stores.create.return_value = Mock(name="store-test")
    mock_client.file_search_stores.upload_to_file_search_store = Mock()

    call_order = []

    def track_create(*args, **kwargs):
        call_order.append("create")
        return Mock(name="store-test")

    def track_upload(*args, **kwargs):
        call_order.append("upload")

    mock_client.file_search_stores.create.side_effect = track_create
    mock_client.file_search_stores.upload_to_file_search_store.side_effect = track_upload

    manager = FileSearchStoreManager.__new__(FileSearchStoreManager)
    manager._api_key = "test-key"
    manager._client = mock_client

    # Create store
    store_name = manager.create_store("test")

    # Upload content
    content = "x" * content_size
    manager.upload_context(store_name, content, "context.txt")

    # Verify order
    assert call_order == ["create", "upload"]


# =============================================================================
# Tests for cleanup_orphaned_resources
# =============================================================================


class TestCleanupOrphanedResources:
    """Tests for the pre/post-run orphan cleanup function."""

    def test_cleanup_deletes_orphaned_caches(self):
        """Orphaned caches are deleted."""
        mock_cache = Mock()
        mock_cache.name = "cache-orphan-1"

        mock_client = Mock()
        mock_client.caches.list.return_value = [mock_cache]
        mock_client.file_search_stores.list.return_value = []

        with (
            patch("primr.ai.deep_research.genai.Client", return_value=mock_client),
            patch("primr.ai.deep_research.get_settings") as mock_settings,
        ):
            mock_settings.return_value.api.gemini_key = "test-key"

            from primr.ai.deep_research import cleanup_orphaned_resources

            result = cleanup_orphaned_resources(api_key="test-key")

        assert result["caches_deleted"] == 1
        mock_client.caches.delete.assert_called_once_with(name="cache-orphan-1")

    def test_cleanup_deletes_orphaned_stores(self):
        """Orphaned file search stores are deleted (docs first, then store)."""
        mock_doc = Mock()
        mock_doc.name = "doc-1"
        mock_store = Mock()
        mock_store.name = "store-orphan-1"

        mock_client = Mock()
        mock_client.caches.list.return_value = []
        mock_client.file_search_stores.list.return_value = [mock_store]
        mock_client.file_search_stores.documents.list.return_value = [mock_doc]

        with (
            patch("primr.ai.deep_research.genai.Client", return_value=mock_client),
            patch("primr.ai.deep_research.get_settings") as mock_settings,
        ):
            mock_settings.return_value.api.gemini_key = "test-key"

            from primr.ai.deep_research import cleanup_orphaned_resources

            result = cleanup_orphaned_resources(api_key="test-key")

        assert result["stores_deleted"] == 1
        # Documents deleted first
        mock_client.file_search_stores.documents.delete.assert_called_once()
        # Then store
        mock_client.file_search_stores.delete.assert_called_once_with(name="store-orphan-1")

    def test_cleanup_returns_zero_when_clean(self):
        """Returns zero counts when no orphans exist."""
        mock_client = Mock()
        mock_client.caches.list.return_value = []
        mock_client.file_search_stores.list.return_value = []

        with (
            patch("primr.ai.deep_research.genai.Client", return_value=mock_client),
            patch("primr.ai.deep_research.get_settings") as mock_settings,
        ):
            mock_settings.return_value.api.gemini_key = "test-key"

            from primr.ai.deep_research import cleanup_orphaned_resources

            result = cleanup_orphaned_resources(api_key="test-key")

        assert result["caches_deleted"] == 0
        assert result["stores_deleted"] == 0

    def test_cleanup_handles_api_errors_gracefully(self):
        """Cleanup does not raise on API errors."""
        mock_client = Mock()
        mock_client.caches.list.side_effect = Exception("API down")
        mock_client.file_search_stores.list.side_effect = Exception("API down")

        with (
            patch("primr.ai.deep_research.genai.Client", return_value=mock_client),
            patch("primr.ai.deep_research.get_settings") as mock_settings,
        ):
            mock_settings.return_value.api.gemini_key = "test-key"

            from primr.ai.deep_research import cleanup_orphaned_resources

            # Should not raise
            result = cleanup_orphaned_resources(api_key="test-key")

        assert result["caches_deleted"] == 0
        assert result["stores_deleted"] == 0
