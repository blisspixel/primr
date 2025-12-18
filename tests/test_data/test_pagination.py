"""
Tests for the pagination detection module.
"""

import pytest

from primr.data.pagination import (
    PaginationDetector,
    PaginationType,
    PaginationInfo,
    PaginationPattern,
    get_pagination_detector,
    reset_pagination_detector,
    detect_pagination,
    get_page_urls,
    extract_pagination_links,
    get_current_page_number,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton before each test."""
    reset_pagination_detector()
    yield
    reset_pagination_detector()


@pytest.fixture
def detector():
    """Create a fresh detector."""
    return PaginationDetector()


@pytest.fixture
def numbered_html():
    """HTML with numbered pagination."""
    return """
    <html>
    <body>
        <div class="pagination">
            <a href="/results?page=1">1</a>
            <a href="/results?page=2">2</a>
            <a href="/results?page=3">3</a>
            <a href="/results?page=4" rel="next">Next</a>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def path_pagination_html():
    """HTML with path-based pagination."""
    return """
    <html>
    <body>
        <div class="pagination">
            <a href="/blog/page/1">1</a>
            <a href="/blog/page/2">2</a>
            <a href="/blog/page/3" class="next">Next ›</a>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def load_more_html():
    """HTML with load more button."""
    return """
    <html>
    <body>
        <div class="results">
            <div class="item">Item 1</div>
            <div class="item">Item 2</div>
        </div>
        <button class="load-more">Load More</button>
    </body>
    </html>
    """


@pytest.fixture
def infinite_scroll_html():
    """HTML with infinite scroll."""
    return """
    <html>
    <body>
        <div class="results infinite-scroll" data-infinite="true">
            <div class="item">Item 1</div>
        </div>
        <script>
            const observer = new IntersectionObserver(callback);
        </script>
    </body>
    </html>
    """


# =============================================================================
# PAGINATION INFO TESTS
# =============================================================================

class TestPaginationInfo:
    """Tests for PaginationInfo dataclass."""
    
    def test_default_values(self):
        """Test default values."""
        info = PaginationInfo(pagination_type=PaginationType.NONE)
        assert info.current_page == 1
        assert info.total_pages is None
        assert info.has_next is False
        assert info.has_prev is False
    
    def test_with_values(self):
        """Test with custom values."""
        info = PaginationInfo(
            pagination_type=PaginationType.NUMBERED,
            current_page=3,
            total_pages=10,
            has_next=True,
            has_prev=True,
        )
        assert info.current_page == 3
        assert info.total_pages == 10


# =============================================================================
# NUMBERED PAGINATION TESTS
# =============================================================================

class TestNumberedPagination:
    """Tests for numbered pagination detection."""
    
    def test_detect_page_param(self, detector, numbered_html):
        """Test detection of ?page=N pagination."""
        url = "https://example.com/results?page=2"
        info = detector.detect(numbered_html, url)
        
        assert info.pagination_type == PaginationType.NUMBERED
        assert info.current_page == 2
        assert info.confidence >= 0.7
    
    def test_detect_p_param(self, detector):
        """Test detection of ?p=N pagination."""
        html = '<a href="/search?p=2" rel="next">Next</a>'
        url = "https://example.com/search?p=1"
        info = detector.detect(html, url)
        
        assert info.pagination_type == PaginationType.NUMBERED
        assert info.current_page == 1
    
    def test_detect_next_link(self, detector, numbered_html):
        """Test next link detection."""
        url = "https://example.com/results?page=2"
        info = detector.detect(numbered_html, url)
        
        assert info.has_next is True
        assert info.next_url is not None
    
    def test_extract_page_links(self, detector, numbered_html):
        """Test extraction of all page links."""
        links = detector.extract_page_links(numbered_html, "https://example.com")
        
        assert len(links) >= 3
        assert any("page=1" in link for link in links)
        assert any("page=2" in link for link in links)


# =============================================================================
# PATH PAGINATION TESTS
# =============================================================================

class TestPathPagination:
    """Tests for path-based pagination detection."""
    
    def test_detect_path_pagination(self, detector, path_pagination_html):
        """Test detection of /page/N pagination."""
        url = "https://example.com/blog/page/2"
        info = detector.detect(path_pagination_html, url)
        
        assert info.pagination_type == PaginationType.PATH
        assert info.current_page == 2
    
    def test_detect_path_links(self, detector, path_pagination_html):
        """Test detection of path pagination links."""
        url = "https://example.com/blog"
        info = detector.detect(path_pagination_html, url)
        
        assert info.pagination_type == PaginationType.PATH
        assert len(info.all_page_urls) >= 2


# =============================================================================
# OFFSET PAGINATION TESTS
# =============================================================================

class TestOffsetPagination:
    """Tests for offset-based pagination detection."""
    
    def test_detect_offset_param(self, detector):
        """Test detection of ?offset=N pagination."""
        html = '<a href="/api/items?offset=20" rel="next">Next</a>'
        url = "https://example.com/api/items?offset=10"
        info = detector.detect(html, url)
        
        assert info.pagination_type == PaginationType.OFFSET
        assert info.has_next is True
    
    def test_detect_start_param(self, detector):
        """Test detection of ?start=N pagination."""
        html = '<a href="/search?start=20">Next</a>'
        url = "https://example.com/search?start=0"
        info = detector.detect(html, url)
        
        assert info.pagination_type == PaginationType.OFFSET


# =============================================================================
# LOAD MORE TESTS
# =============================================================================

class TestLoadMore:
    """Tests for load more button detection."""
    
    def test_detect_load_more_button(self, detector, load_more_html):
        """Test detection of load more button."""
        url = "https://example.com/results"
        info = detector.detect(load_more_html, url)
        
        assert info.pagination_type == PaginationType.LOAD_MORE
        assert info.confidence >= 0.7
    
    def test_detect_show_more(self, detector):
        """Test detection of show more button."""
        html = '<button id="show-more">Show More</button>'
        url = "https://example.com/results"
        info = detector.detect(html, url)
        
        assert info.pagination_type == PaginationType.LOAD_MORE


# =============================================================================
# INFINITE SCROLL TESTS
# =============================================================================

class TestInfiniteScroll:
    """Tests for infinite scroll detection."""
    
    def test_detect_infinite_scroll_class(self, detector, infinite_scroll_html):
        """Test detection of infinite scroll class."""
        url = "https://example.com/feed"
        info = detector.detect(infinite_scroll_html, url)
        
        assert info.pagination_type == PaginationType.INFINITE_SCROLL
        assert info.confidence >= 0.7
    
    def test_detect_intersection_observer(self, detector):
        """Test detection of IntersectionObserver."""
        html = '<script>new IntersectionObserver(loadMore)</script>'
        url = "https://example.com/feed"
        info = detector.detect(html, url)
        
        assert info.pagination_type == PaginationType.INFINITE_SCROLL
    
    def test_detect_lazy_load(self, detector):
        """Test detection of lazy load."""
        html = '<div class="lazy-load" data-lazy="true"></div>'
        url = "https://example.com/feed"
        info = detector.detect(html, url)
        
        assert info.pagination_type == PaginationType.INFINITE_SCROLL


# =============================================================================
# URL GENERATION TESTS
# =============================================================================

class TestUrlGeneration:
    """Tests for URL generation."""
    
    def test_generate_numbered_urls(self, detector):
        """Test generating numbered page URLs."""
        pattern = PaginationPattern(
            pattern_type=PaginationType.NUMBERED,
            param_name="page",
            start_value=1,
        )
        urls = detector.generate_page_urls(
            "https://example.com/search",
            pattern,
            num_pages=5,
        )
        
        assert len(urls) == 5
        assert "page=1" in urls[0]
        assert "page=5" in urls[4]
    
    def test_generate_offset_urls(self, detector):
        """Test generating offset page URLs."""
        pattern = PaginationPattern(
            pattern_type=PaginationType.OFFSET,
            param_name="offset",
            start_value=0,
            increment=10,
        )
        urls = detector.generate_page_urls(
            "https://example.com/api/items",
            pattern,
            num_pages=3,
        )
        
        assert len(urls) == 3
        assert "offset=0" in urls[0]
        assert "offset=10" in urls[1]
        assert "offset=20" in urls[2]
    
    def test_generate_path_urls(self, detector):
        """Test generating path-based page URLs."""
        pattern = PaginationPattern(
            pattern_type=PaginationType.PATH,
            start_value=1,
        )
        urls = detector.generate_page_urls(
            "https://example.com/blog",
            pattern,
            num_pages=3,
        )
        
        assert len(urls) == 3
        assert "/page/1" in urls[0]
        assert "/page/2" in urls[1]
        assert "/page/3" in urls[2]
    
    def test_max_pages_limit(self, detector):
        """Test max pages limit is respected."""
        detector._max_pages = 5
        pattern = PaginationPattern(
            pattern_type=PaginationType.NUMBERED,
            param_name="page",
            start_value=1,
        )
        urls = detector.generate_page_urls(
            "https://example.com/search",
            pattern,
            num_pages=100,
        )
        
        assert len(urls) == 5


# =============================================================================
# CURRENT PAGE TESTS
# =============================================================================

class TestCurrentPage:
    """Tests for current page extraction."""
    
    def test_get_page_from_query(self, detector):
        """Test getting page from query parameter."""
        url = "https://example.com/search?page=5"
        page = detector.get_current_page(url)
        assert page == 5
    
    def test_get_page_from_path(self, detector):
        """Test getting page from path."""
        url = "https://example.com/blog/page/3"
        page = detector.get_current_page(url)
        assert page == 3
    
    def test_default_page_one(self, detector):
        """Test default page is 1."""
        url = "https://example.com/search"
        page = detector.get_current_page(url)
        assert page == 1
    
    def test_various_param_names(self, detector):
        """Test various parameter names."""
        assert detector.get_current_page("https://example.com?p=3") == 3
        assert detector.get_current_page("https://example.com?pg=7") == 7
        assert detector.get_current_page("https://example.com?pagenum=2") == 2


# =============================================================================
# SINGLETON TESTS
# =============================================================================

class TestSingleton:
    """Tests for singleton access."""
    
    def test_get_detector_returns_same(self):
        """Test get_pagination_detector returns same instance."""
        d1 = get_pagination_detector()
        d2 = get_pagination_detector()
        assert d1 is d2
    
    def test_reset_detector(self):
        """Test reset creates new instance."""
        d1 = get_pagination_detector()
        reset_pagination_detector()
        d2 = get_pagination_detector()
        assert d1 is not d2


# =============================================================================
# CONVENIENCE FUNCTION TESTS
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""
    
    def test_detect_pagination_function(self, numbered_html):
        """Test detect_pagination convenience function."""
        info = detect_pagination(numbered_html, "https://example.com/results?page=1")
        assert isinstance(info, PaginationInfo)
    
    def test_get_page_urls_function(self):
        """Test get_page_urls convenience function."""
        urls = get_page_urls(
            "https://example.com/search",
            pagination_type=PaginationType.NUMBERED,
            param_name="page",
            num_pages=3,
        )
        assert len(urls) == 3
    
    def test_extract_pagination_links_function(self, numbered_html):
        """Test extract_pagination_links convenience function."""
        links = extract_pagination_links(numbered_html, "https://example.com")
        assert isinstance(links, list)
    
    def test_get_current_page_number_function(self):
        """Test get_current_page_number convenience function."""
        page = get_current_page_number("https://example.com?page=5")
        assert page == 5


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_no_pagination(self, detector):
        """Test page with no pagination."""
        html = "<html><body><p>Just some content</p></body></html>"
        url = "https://example.com/about"
        info = detector.detect(html, url)
        
        assert info.pagination_type == PaginationType.NONE
    
    def test_empty_html(self, detector):
        """Test empty HTML."""
        info = detector.detect("", "https://example.com")
        assert info.pagination_type == PaginationType.NONE
    
    def test_malformed_page_param(self, detector):
        """Test malformed page parameter."""
        html = '<a href="/search?page=abc">Next</a>'
        url = "https://example.com/search?page=abc"
        info = detector.detect(html, url)
        
        # Should handle gracefully
        assert info is not None
    
    def test_relative_urls(self, detector):
        """Test relative URL handling."""
        html = '<a href="?page=2" rel="next">Next</a>'
        url = "https://example.com/search?page=1"
        info = detector.detect(html, url)
        
        if info.next_url:
            assert info.next_url.startswith("https://")
