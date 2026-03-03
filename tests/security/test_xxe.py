"""
XXE (XML External Entity) protection tests.

Tests that verify XML parsing is secure against external entity attacks.
"""

import xml.etree.ElementTree as ET

import pytest


class TestXXEProtection:
    """Test XXE (XML External Entity) protection."""

    def test_xml_parser_safe_parsing(self):
        """Test that XML parser handles normal XML correctly."""
        safe_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>https://example.com/page1</loc>
    </url>
    <url>
        <loc>https://example.com/page2</loc>
    </url>
</urlset>"""

        try:
            root = ET.fromstring(safe_xml)
            assert root is not None
            urls = [
                elem.text
                for elem in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
            ]
            assert len(urls) == 2
            assert "https://example.com/page1" in urls
            assert "https://example.com/page2" in urls
        except ET.ParseError:
            pytest.fail("Failed to parse valid XML")

    def test_xml_parser_blocks_external_entities(self):
        """Test that XML parser blocks external entity expansion."""
        xxe_payload = b"""<?xml version="1.0"?>
<!DOCTYPE foo [
    <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>&xxe;</loc>
    </url>
</urlset>"""

        try:
            parser = ET.XMLParser()
            try:
                parser.entity = {}
                parser.parser.SetParamEntityParsing(0)
                root = ET.fromstring(xxe_payload, parser=parser)
            except AttributeError:
                root = ET.fromstring(xxe_payload)

            urls = [
                elem.text
                for elem in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
                if elem.text
            ]
            for url in urls:
                assert "root:" not in url, "XXE attack succeeded - read /etc/passwd"
                assert "/bin/bash" not in url, "XXE attack succeeded - read /etc/passwd"
                assert "xxe" not in url.lower() or url == "&xxe;", "Entity should not be expanded"
        except ET.ParseError:
            # It's acceptable (and preferred) to reject malicious XML
            pass

    def test_xml_parser_handles_entity_reference_safely(self):
        """Test that internal entity references are handled safely."""
        xml_with_entity = b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE urlset [
    <!ENTITY internal "https://example.com/internal">
]>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>&internal;</loc>
    </url>
</urlset>"""

        try:
            parser = ET.XMLParser()
            try:
                parser.entity = {}
                parser.parser.SetParamEntityParsing(0)
                root = ET.fromstring(xml_with_entity, parser=parser)
            except AttributeError:
                root = ET.fromstring(xml_with_entity)

            assert root is not None
            urls = [
                elem.text
                for elem in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
                if elem.text
            ]
            assert isinstance(urls, list)
        except ET.ParseError:
            # It's acceptable to reject XML with entities
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
