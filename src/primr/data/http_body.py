"""Bound wire bytes and decompression before buffering untrusted HTTP bodies."""

from __future__ import annotations

import time
import zlib
from collections.abc import Iterable, Mapping

import httpx

DEFAULT_MAX_BODY_BYTES = 8 * 1024 * 1024


class BoundedHTTPTransport(httpx.HTTPTransport):
    """Read below Client's eager decoder, including redirect responses."""

    def __init__(self, deadline: float, limit: int = DEFAULT_MAX_BODY_BYTES) -> None:
        super().__init__(http2=True)
        self.deadline = deadline
        self.limit = limit

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if time.monotonic() >= self.deadline:
            raise httpx.TimeoutException("HTTP response deadline exceeded")
        response = super().handle_request(request)
        try:
            response._content = read_bounded_body(response, self.limit, self.deadline)
            return response
        except TimeoutError as exc:
            raise httpx.ReadTimeout(str(exc), request=request) from exc
        finally:
            response.close()


def read_bounded_body(response: httpx.Response, limit: int, deadline: float) -> bytes:
    """Read identity, gzip or deflate without HTTPX's unbounded decoder.

    Socket timeouts still apply to individual blocking operations. The deadline
    is checked at each raw read; OS DNS resolution has its own timeout policy.
    """
    _content_encoding(response.headers, limit)
    if response.is_stream_consumed:
        if len(response.content) > limit or time.monotonic() >= deadline:
            raise ValueError("Buffered HTTP response exceeds its budget")
        return response.content
    return read_bounded_chunks(response.iter_raw(), response.headers, limit, deadline)


def _content_encoding(headers: Mapping[str, str], limit: int) -> str:
    declared = headers.get("content-length")
    if declared is not None and (not declared.isascii() or not declared.isdecimal()):
        raise ValueError("Invalid response Content-Length")
    if declared is not None and int(declared) > limit:
        raise ValueError("HTTP response exceeds transfer limit")
    encoding = headers.get("content-encoding", "identity").strip().lower()
    if encoding not in {"identity", "gzip", "deflate"}:
        raise ValueError("Unsupported response content encoding")
    return encoding


def read_bounded_chunks(
    chunks: Iterable[bytes], headers: Mapping[str, str], limit: int, deadline: float
) -> bytes:
    """Decode raw transport or document chunks within wire and output limits.

    Callers own the transport and close it on success and failure. A chunk
    iterator must yield raw bytes without an SDK decoder or producer queue.
    """
    encoding = _content_encoding(headers, limit)
    body = bytearray()
    transferred = 0
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS) if encoding == "gzip" else None
    prefix = b""
    deflate_probe = bytearray()
    may_retry_raw = False
    for raw in chunks:
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
