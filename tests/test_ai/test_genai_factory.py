"""Tests for the genai HTTP-timeout defaults (finite timeout everywhere).

Pins the fix for a real production hang: the google-genai SDK has no default
HTTP timeout, and a live run blocked in ssl.read for 3.5 hours when the
endpoint went quiet mid-response. Every client construction must carry a
finite request timeout.
"""

import pytest

from primr.ai.genai_factory import (
    DEFAULT_GENAI_HTTP_TIMEOUT_MS,
    default_genai_http_options,
    get_genai_http_timeout_ms,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("PRIMR_GEMINI_HTTP_TIMEOUT_MS", raising=False)


class TestTimeoutResolution:
    def test_default_is_five_minutes(self):
        assert DEFAULT_GENAI_HTTP_TIMEOUT_MS == 300_000
        assert get_genai_http_timeout_ms() == 300_000

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("PRIMR_GEMINI_HTTP_TIMEOUT_MS", "60000")
        assert get_genai_http_timeout_ms() == 60_000

    @pytest.mark.parametrize("bad", ["0", "-5", "soon", ""])
    def test_invalid_values_fall_back(self, monkeypatch, bad):
        monkeypatch.setenv("PRIMR_GEMINI_HTTP_TIMEOUT_MS", bad)
        assert get_genai_http_timeout_ms() == DEFAULT_GENAI_HTTP_TIMEOUT_MS


class TestHttpOptions:
    def test_options_carry_finite_timeout(self):
        options = default_genai_http_options()
        assert options.timeout == DEFAULT_GENAI_HTTP_TIMEOUT_MS

    def test_env_override_applies(self, monkeypatch):
        monkeypatch.setenv("PRIMR_GEMINI_HTTP_TIMEOUT_MS", "120000")
        assert default_genai_http_options().timeout == 120_000


class TestNoUnguardedConstructionsRemain:
    def test_every_genai_client_carries_http_options(self):
        """Repo invariant: every genai Client(api_key=...) passes http_options.

        A new construction without it would reintroduce the unbounded-hang
        class (no default HTTP timeout in the SDK) this module exists to
        prevent.
        """
        import re
        from pathlib import Path

        import primr

        src_root = Path(primr.__file__).parent
        offenders: list[str] = []
        pattern = re.compile(r"\w[\w.]*\.Client\(api_key=")
        for path in src_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(text.splitlines(), 1):
                if pattern.search(line) and "http_options=" not in line:
                    offenders.append(f"{path.relative_to(src_root)}:{i}: {line.strip()}")
        assert not offenders, (
            "genai Client constructions without http_options "
            "(pass http_options=default_genai_http_options()):\n" + "\n".join(offenders)
        )
