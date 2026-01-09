# HTML Test Fixtures

This directory contains HTML samples for testing soft block detection and content extraction.

## Fixtures

| File | Description | Expected Detection |
|------|-------------|-------------------|
| `cloudflare_challenge.html` | Cloudflare "Just a moment" challenge page | CHALLENGE |
| `akamai_blocked.html` | Akamai access denied page | HARD_BLOCK |
| `cookie_consent_wall.html` | Cookie consent wall blocking content | CONSENT_WALL |
| `empty_search_results.html` | Legitimate empty search results | NOT blocked (false positive test) |
| `spa_skeleton.html` | SPA skeleton with "enable JavaScript" | SOFT_BLOCK (no content rendered) |
| `normal_content.html` | Normal company about page | NOT blocked |
| `wirewall_blocked.html` | WireWall bot protection page | SOFT_BLOCK |

## Usage

These fixtures are used by `test_detection.py` to verify soft block detection accuracy.

```python
from pathlib import Path

fixtures_dir = Path(__file__).parent / "fixtures" / "html"
cloudflare_html = (fixtures_dir / "cloudflare_challenge.html").read_bytes()
```

## Updating Fixtures

When adding new fixtures:
1. Capture real HTML from blocked pages (anonymize if needed)
2. Add entry to this README
3. Add corresponding test case in `test_detection.py`

## Sources

- Cloudflare: Captured from real Cloudflare challenge (anonymized)
- Akamai: Synthetic based on common Akamai block patterns
- WireWall: Based on patterns seen on torexgold.com
- Normal content: Synthetic example company page
