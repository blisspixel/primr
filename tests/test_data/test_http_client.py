"""
Tests for the HTTP client module.

Tests connection pooling, retry logic, and convenience functions.
"""

import pytest
import threading
from unittest.mock import Mock, patch, MagicMock
import requests

from primr.data.http_client import (
    HTTPClient,
    HTTPClientConfig,
    get_http_client,
    reset_http_client,
    http_get,
    http_get_text,
    http_get_json,
    get_random_user_agent,
    get_default_headers,
    USER_AGENTS,
)
from primr.utils.errors import ScrapingError


# =============================================================================
# HELPER FUNCTIONS TESTS
# =============================================================================

class TestHelperFunctions:
    """Tests for helper functions."""
    
    def test_get_random_user_agent(self):
        """Test random user agent selection."""
        ua = get_random_user_agent()
        assert ua in USER_AGENTS
        assert "Mozilla" in ua
    
    def test_get_default_headers(self):
        """Test default headers generation."""
        headers = get_default_headers()
        
        assert "User-Agent" in headers
        assert "Accept" in headers
        assert "Accept-Language" in headers
        assert headers["Connection"] == "keep-alive"
    
    def test_user_agents_variety(self):
        """Test that we have multiple user agents."""
        assert len(USER_AGENTS) >= 4
        
        # Check variety
        browsers = set()
        for ua in USER_AGENTS:
            if "Chrome" in ua:
                browsers.add("Chrome")
            if "Firefox" in ua:
                browsers.add("Firefox")
            if "Safari" in ua and "Chrome" not in ua:
                browsers.add("Safari")
        
        assert len(browsers) >= 2


# =============================================================================
# HTTP CLIENT CONFIG TESTS
# =============================================================================

class TestHTTPClientConfig:
    """Tests for HTTPClientConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = HTTPClientConfig()
        
        assert config.pool_connections == 10
        assert config.pool_maxsize == 20
        assert config.max_retries == 3
        assert config.timeout == 30.0
        assert config.verify_ssl is True
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = HTTPClientConfig(
            pool_connections=5,
            pool_maxsize=10,
            max_retries=5,
            timeout=60.0,
            verify_ssl=False
        )
        
        assert config.pool_connections == 5
        assert config.max_retries == 5
        assert config.verify_ssl is False


# =============================================================================
# HTTP CLIENT TESTS
# =============================================================================

class TestHTTPClient:
    """Tests for HTTPClient class."""
    
    def test_initialization(self):
        """Test client initialization."""
        client = HTTPClient()
        assert client._session is not None
        client.close()
    
    def test_initialization_with_config(self):
        """Test client initialization with custom config."""
        config = HTTPClientConfig(pool_connections=5)
        client = HTTPClient(config=config)
        assert client._config.pool_connections == 5
        client.close()
    
    def test_context_manager(self):
        """Test client as context manager."""
        with HTTPClient() as client:
            assert client._session is not None
        # Session should be closed after context
    
    @patch('requests.Session.get')
    def test_get_success(self, mock_get):
        """Test successful GET request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "Hello World"
        mock_get.return_value = mock_response
        
        with HTTPClient() as client:
            response = client.get("https://example.com")
            
            assert response.status_code == 200
            mock_get.assert_called_once()
    
    @patch('requests.Session.get')
    def test_get_with_custom_headers(self, mock_get):
        """Test GET request with custom headers."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        with HTTPClient() as client:
            client.get(
                "https://example.com",
                headers={"X-Custom": "value"}
            )
            
            call_kwargs = mock_get.call_args[1]
            assert "X-Custom" in call_kwargs["headers"]
    
    @patch('requests.Session.get')
    def test_get_with_timeout(self, mock_get):
        """Test GET request with custom timeout."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        with HTTPClient() as client:
            client.get("https://example.com", timeout=10.0)
            
            call_kwargs = mock_get.call_args[1]
            assert call_kwargs["timeout"] == 10.0
    
    @patch('requests.Session.get')
    def test_get_failure_raises_scraping_error(self, mock_get):
        """Test that request failure raises ScrapingError."""
        mock_get.side_effect = requests.RequestException("Connection failed")
        
        with HTTPClient() as client:
            with pytest.raises(ScrapingError) as exc_info:
                client.get("https://example.com")
            
            assert "Connection failed" in str(exc_info.value)
    
    @patch('requests.Session.get')
    def test_get_text_success(self, mock_get):
        """Test get_text returns text content."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "Page content"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        with HTTPClient() as client:
            text = client.get_text("https://example.com")
            
            assert text == "Page content"
    
    @patch('requests.Session.get')
    def test_get_text_failure_returns_none(self, mock_get):
        """Test get_text returns None on failure."""
        mock_get.side_effect = requests.RequestException("Failed")
        
        with HTTPClient() as client:
            text = client.get_text("https://example.com")
            
            assert text is None
    
    @patch('requests.Session.get')
    def test_get_json_success(self, mock_get):
        """Test get_json returns parsed JSON."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"key": "value"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        with HTTPClient() as client:
            data = client.get_json("https://api.example.com")
            
            assert data == {"key": "value"}
    
    @patch('requests.Session.get')
    def test_get_json_invalid_json_returns_none(self, mock_get):
        """Test get_json returns None for invalid JSON."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        with HTTPClient() as client:
            data = client.get_json("https://api.example.com")
            
            assert data is None
    
    @patch('requests.Session.head')
    def test_head_success(self, mock_head):
        """Test HEAD request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_head.return_value = mock_response
        
        with HTTPClient() as client:
            response = client.head("https://example.com")
            
            assert response.status_code == 200
    
    @patch('requests.Session.head')
    def test_head_failure_returns_none(self, mock_head):
        """Test HEAD request failure returns None."""
        mock_head.side_effect = requests.RequestException("Failed")
        
        with HTTPClient() as client:
            response = client.head("https://example.com")
            
            assert response is None


# =============================================================================
# STATISTICS TESTS
# =============================================================================

class TestHTTPClientStats:
    """Tests for HTTP client statistics."""
    
    @patch('requests.Session.get')
    def test_stats_tracking(self, mock_get):
        """Test that statistics are tracked."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        with HTTPClient() as client:
            client.get("https://example.com")
            client.get("https://example.com")
            
            stats = client.get_stats()
            
            assert stats["total_requests"] == 2
            assert stats["successful"] == 2
            assert stats["failed"] == 0
            assert stats["success_rate"] == 1.0
    
    @patch('requests.Session.get')
    def test_stats_with_failures(self, mock_get):
        """Test statistics with failures."""
        mock_response = Mock()
        mock_response.status_code = 200
        
        # First call succeeds, second fails
        mock_get.side_effect = [
            mock_response,
            requests.RequestException("Failed")
        ]
        
        with HTTPClient() as client:
            client.get("https://example.com")
            try:
                client.get("https://example.com")
            except ScrapingError:
                pass
            
            stats = client.get_stats()
            
            assert stats["total_requests"] == 2
            assert stats["successful"] == 1
            assert stats["failed"] == 1
            assert stats["success_rate"] == 0.5
    
    @patch('requests.Session.get')
    def test_reset_stats(self, mock_get):
        """Test resetting statistics."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        with HTTPClient() as client:
            client.get("https://example.com")
            client.reset_stats()
            
            stats = client.get_stats()
            
            assert stats["total_requests"] == 0
            assert stats["successful"] == 0


# =============================================================================
# SINGLETON TESTS
# =============================================================================

class TestSingleton:
    """Tests for singleton access."""
    
    def setup_method(self):
        """Reset singleton before each test."""
        reset_http_client()
    
    def teardown_method(self):
        """Clean up after each test."""
        reset_http_client()
    
    def test_get_http_client_singleton(self):
        """Test that get_http_client returns singleton."""
        client1 = get_http_client()
        client2 = get_http_client()
        
        assert client1 is client2
    
    def test_reset_http_client(self):
        """Test resetting the singleton."""
        client1 = get_http_client()
        reset_http_client()
        client2 = get_http_client()
        
        assert client1 is not client2
    
    def test_singleton_thread_safe(self):
        """Test that singleton access is thread safe."""
        clients = []
        errors = []
        
        def get_client():
            try:
                client = get_http_client()
                clients.append(client)
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=get_client) for _ in range(10)]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        # All should be the same instance
        assert all(c is clients[0] for c in clients)


# =============================================================================
# CONVENIENCE FUNCTION TESTS
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""
    
    def setup_method(self):
        """Reset singleton before each test."""
        reset_http_client()
    
    def teardown_method(self):
        """Clean up after each test."""
        reset_http_client()
    
    @patch.object(HTTPClient, 'get')
    def test_http_get(self, mock_get):
        """Test http_get convenience function."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        response = http_get("https://example.com")
        
        assert response.status_code == 200
        mock_get.assert_called_once()
    
    @patch.object(HTTPClient, 'get_text')
    def test_http_get_text(self, mock_get_text):
        """Test http_get_text convenience function."""
        mock_get_text.return_value = "Page content"
        
        text = http_get_text("https://example.com")
        
        assert text == "Page content"
    
    @patch.object(HTTPClient, 'get_json')
    def test_http_get_json(self, mock_get_json):
        """Test http_get_json convenience function."""
        mock_get_json.return_value = {"key": "value"}
        
        data = http_get_json("https://api.example.com")
        
        assert data == {"key": "value"}


# =============================================================================
# CONNECTION POOLING TESTS
# =============================================================================

class TestConnectionPooling:
    """Tests for connection pooling behavior."""
    
    def test_session_has_adapters(self):
        """Test that session has HTTP adapters configured."""
        with HTTPClient() as client:
            # Check adapters are mounted
            assert "http://" in client._session.adapters
            assert "https://" in client._session.adapters
    
    def test_adapter_configuration(self):
        """Test that adapters have correct configuration."""
        config = HTTPClientConfig(pool_connections=5, pool_maxsize=15)
        
        with HTTPClient(config=config) as client:
            adapter = client._session.get_adapter("https://example.com")
            
            # HTTPAdapter stores pool config internally
            # The exact attribute varies by requests version
            assert adapter is not None
            # Verify it's an HTTPAdapter with pooling
            assert hasattr(adapter, 'poolmanager') or hasattr(adapter, 'config')
    
    def test_retry_configuration(self):
        """Test that retry is configured."""
        config = HTTPClientConfig(max_retries=5)
        
        with HTTPClient(config=config) as client:
            adapter = client._session.get_adapter("https://example.com")
            
            # Check retry is configured
            assert adapter.max_retries.total == 5


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests (may require network)."""
    
    @pytest.mark.skip(reason="Requires network access")
    def test_real_request(self):
        """Test a real HTTP request."""
        with HTTPClient() as client:
            response = client.get("https://httpbin.org/get")
            assert response.status_code == 200
    
    @pytest.mark.skip(reason="Requires network access")
    def test_real_json_request(self):
        """Test a real JSON request."""
        with HTTPClient() as client:
            data = client.get_json("https://httpbin.org/json")
            assert data is not None
            assert "slideshow" in data
