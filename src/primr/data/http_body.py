"""Bound wire bytes and decompression before buffering untrusted HTTP bodies."""

from __future__ import annotations

import time
import zlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

DEFAULT_MAX_BODY_BYTES = 8 * 1024 * 1024


def read_bounded_body(response: httpx.Response, limit: int, deadline: float) -> bytes:
    """Read identity, gzip or deflate without HTTPX's unbounded decoder.

    Socket timeouts still apply to individual blocking operations. The deadline
    is checked at each raw read; OS DNS resolution has its own timeout policy.
    """
    declared = response.headers.get("content-length")
    if declared is not None and (not declared.isascii() or not declared.isdecimal()):
        raise ValueError("Invalid response Content-Length")
    if declared is not None and int(declared) > limit:
        raise ValueError("HTTP response exceeds transfer limit")
    encoding = response.headers.get("content-encoding", "identity").strip().lower()
    if encoding not in {"identity", "gzip", "deflate"}:
        raise ValueError("Unsupported response content encoding")
    if response.is_stream_consumed:
        # Injected/caching transports may supply an already decoded response.
        # Real HTTP responses remain unread until the bounded raw loop below.
        if len(response.content) > limit or time.monotonic() >= deadline:
            raise ValueError("Buffered HTTP response exceeds its budget")
        return response.content

    body = bytearray()
    transferred = 0
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS) if encoding == "gzip" else None
    prefix = b""
    deflate_probe = bytearray()
    may_retry_raw = False
    for raw in response.iter_raw():
        if time.monotonic() >= deadline:
            raise TimeoutError("HTTP response deadline exceeded")
        transferred += len(raw)
        if transferred > limit:
            raise ValueError("HTTP response exceeds transfer limit")
        if encoding == "deflate" and decoder is None:
            prefix += raw
            if len(prefix) < 2:
                continue
            # HTTP deflate exists both with and without a zlib wrapper.
            wrapped = prefix[0] & 15 == 8 and int.from_bytes(prefix[:2], "big") % 31 == 0
            decoder = zlib.decompressobj(zlib.MAX_WBITS if wrapped else -zlib.MAX_WBITS)
            may_retry_raw = wrapped
            raw, prefix = prefix, b""
        if may_retry_raw:
            deflate_probe.extend(raw)
        if decoder is None:
            decoded = raw
        else:
            try:
                decoded = decoder.decompress(raw, limit - len(body) + 1)
            except zlib.error:
                if not may_retry_raw:
                    raise
                # A valid raw stream can resemble a zlib header. Retain only
                # the already wire-bounded prefix until framing is established.
                decoder = zlib.decompressobj(-zlib.MAX_WBITS)
                decoded = decoder.decompress(bytes(deflate_probe), limit - len(body) + 1)
                may_retry_raw = False
        if decoded or (decoder is not None and decoder.eof):
            may_retry_raw = False
            deflate_probe.clear()
        if len(body) + len(decoded) > limit:
            raise ValueError("HTTP response exceeds decoded-body limit")
        body.extend(decoded)
        if decoder is not None and decoder.unused_data:
            # Reject extra members/trailing data instead of silently accepting
            # an unaudited second representation of the response body.
            raise ValueError("Trailing compressed response data")
    if time.monotonic() >= deadline:
        raise TimeoutError("HTTP response deadline exceeded")
    if encoding != "identity" and (decoder is None or not decoder.eof):
        raise ValueError("Incomplete compressed response")
    return bytes(body)
