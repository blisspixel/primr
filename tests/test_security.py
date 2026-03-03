"""
Security tests for Primr.

This module re-exports all security tests from the tests/security/ package
for backward compatibility. New tests should be added to the appropriate
file in tests/security/:

- test_ssrf.py: SSRF protection tests
- test_xxe.py: XXE protection tests
- test_path_traversal.py: Path traversal protection tests
- test_input_validation.py: Input validation and sanitization tests
"""

# Re-export all test classes for backward compatibility
