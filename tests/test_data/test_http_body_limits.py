"""Exercise the lazy transport boundary before body buffering or decoding."""

import gzip
import zlib

import httpx
import pytest

from primr.data.safe_http import safe_http_get
from tests.test_data.test_safe_http import _allow_all


class LazyBody(httpx.SyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.reads = 0
        self.closed = False

    def __iter__(self):
        for chunk in self.chunks:
            self.reads += 1
            yield chunk

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def allow_public_url(monkeypatch):
    monkeypatch.setattr("primr.data.safe_http.resolve_safe_url_for_connect", _allow_all)


def fetch(stream, *, headers=None, limit=8):
    return safe_http_get(
        "https://example.com/page",
        max_body_bytes=limit,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, stream=stream, headers=headers)
        ),
    )


def test_exact_limit_and_next_byte():
    accepted = LazyBody([b"abcd", b"efgh"])
    assert fetch(accepted)[1] == b"abcdefgh"
    rejected = LazyBody([b"abcdefgh", b"i", b"never-read"])
    assert fetch(rejected) == (None, None, None)
    assert rejected.reads == 2
    assert accepted.closed
    assert rejected.closed


def test_declared_oversize_is_closed_without_reading():
    stream = LazyBody([b"never-read"])
    assert fetch(stream, headers={"content-length": "9"}) == (None, None, None)
    assert stream.reads == 0
    assert stream.closed


def test_dishonest_declared_size_does_not_remove_cap():
    stream = LazyBody([b"abcdefgh", b"i"])
    assert fetch(stream, headers={"content-length": "1"}) == (None, None, None)
    assert stream.closed


@pytest.mark.parametrize("encoding", ["gzip", "deflate", "raw-deflate"])
def test_compressed_data_has_bounded_expansion(encoding):
    def encode(body):
        if encoding == "gzip":
            return gzip.compress(body)
        if encoding == "raw-deflate":
            compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
            return compressor.compress(body) + compressor.flush()
        return zlib.compress(body)

    headers = {"content-encoding": "gzip" if encoding == "gzip" else "deflate"}
    encoded = encode(b"a" * 128)
    stream = LazyBody([encoded[:1], encoded[1:]])
    assert fetch(stream, headers=headers, limit=128)[1] == b"a" * 128
    bomb = LazyBody([encode(b"a" * 100_000), b"never-read"])
    assert fetch(bomb, headers=headers, limit=256) == (None, None, None)
    assert bomb.reads == 1
    assert bomb.closed


@pytest.mark.parametrize("encoding", ["br", "zstd", "gzip, gzip"])
def test_unsupported_decoders_are_not_invoked(encoding):
    stream = LazyBody([b"never-read"])
    assert fetch(stream, headers={"content-encoding": encoding}) == (None, None, None)
    assert stream.reads == 0


def test_redirect_body_is_never_consumed():
    stream = LazyBody([b"never-read"])

    def handler(request):
        if request.url.path == "/page":
            return httpx.Response(302, headers={"location": "/final"}, stream=stream)
        return httpx.Response(200, stream=LazyBody([b"ok"]))

    assert (
        safe_http_get("https://example.com/page", transport=httpx.MockTransport(handler))[1]
        == b"ok"
    )
    assert stream.reads == 0
    assert stream.closed


def test_progressing_stream_stops_at_request_deadline(monkeypatch):
    now = [0.0]
    monkeypatch.setattr("primr.data.safe_http.time.monotonic", lambda: now[0])

    def chunks():
        for _ in range(100):
            now[0] += 1
            yield b"x"

    stream = LazyBody(chunks())
    assert safe_http_get(
        "https://example.com/page",
        timeout=3,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=stream)),
    ) == (None, None, None)
    assert stream.reads == 3
    assert stream.closed


@pytest.mark.parametrize("split", [1, 2, 5, 166])
def test_raw_deflate_with_a_zlib_looking_prefix_remains_supported(split):
    prefix = b"\x78\x9c\x00\x63\xff" + b"A" * 156
    raw = prefix + b"\x01\x00\x00\xff\xff"
    assert zlib.decompress(raw, -zlib.MAX_WBITS) == b"A" * 156
    stream = LazyBody([raw[:split], raw[split:]])
    assert fetch(stream, headers={"content-encoding": "deflate"}, limit=1000)[1] == b"A" * 156
    assert stream.closed


def test_raw_deflate_framing_fallback_keeps_the_expansion_limit():
    compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    raw = (
        b"\x78\x9c\x00\x63\xff"
        + b"A" * 156
        + compressor.compress(b"B" * 100_000)
        + compressor.flush()
    )
    stream = LazyBody([raw])
    assert fetch(stream, headers={"content-encoding": "deflate"}, limit=1000) == (None, None, None)
    assert stream.closed
