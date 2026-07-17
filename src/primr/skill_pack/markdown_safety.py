"""Canonical CommonMark security surface shared by skill-pack boundaries.

Markdown parsers decode entities and hide link metadata from rendered prose.
Security checks therefore operate on one explicit parser configuration and
canonicalization policy before applying domain-specific instruction rules.
"""

from __future__ import annotations

import re
import unicodedata
from html import unescape as html_unescape
from typing import TYPE_CHECKING
from urllib.parse import unquote_to_bytes, urlsplit

from markdown_it import MarkdownIt

from primr.utils.content_sanitizer import (
    find_unsafe_instruction_unicode as find_unsafe_authored_unicode,
)
from primr.utils.url_security import non_public_host_block_reason

from . import command_grammar

if TYPE_CHECKING:
    from markdown_it.token import Token

SAFE_LINK_SCHEMES = frozenset({"", "http", "https"})
_RESIDUAL_PERCENT_ENCODING_RE = re.compile(r"%[0-9A-Fa-f]{2}")
_ENCODED_CONTROL_WHITESPACE_RE = re.compile(
    r"%(?:09|0[aAbBdD]|0[cC])|"
    r"&#(?:[xX]0*(?:9|[aAbBdD]|[cC])|0*(?:9|10|11|12|13));|"
    r"&(?:NewLine|Tab);",
    re.IGNORECASE,
)
_RAW_HTTP_URL_RE = re.compile(r"\bhttps?:[^\s<>{}\"']+", re.IGNORECASE)
_MAX_CANONICALIZATION_PASSES = 64
_LATIN_NAME_BASE_RE = re.compile(
    r"(?:LATIN (?:CAPITAL|SMALL) LETTER|LATIN LETTER SMALL CAPITAL) "
    r"(?:(?:DOTLESS|INSULAR|INVERTED|LONG|OPEN|REVERSED|SCRIPT|SIDEWAYS|TURNED) )?"
    r"(?P<base>[A-Z])(?: (?:BAR|ROTUNDA|WITHOUT HANDLE)| WITH .*)?$"
)
_LATIN_NAME_ALIAS_RE = re.compile(
    r"(?:LATIN (?:CAPITAL|SMALL) LETTER|LATIN LETTER SMALL CAPITAL) "
    r"(?P<alias>ALPHA|BETA|ESH|IOTA|UPSILON)(?: WITH .*)?$"
)
_LATIN_NAME_ALIASES = {
    "ALPHA": "A",
    "BETA": "B",
    "ESH": "S",
    "IOTA": "I",
    "UPSILON": "U",
}
_ASCII_CONFUSABLE_TRANSLATION = str.maketrans(
    {
        "Α": "A",
        "Β": "B",
        "Ε": "E",
        "Η": "H",
        "Ι": "I",
        "Κ": "K",
        "Μ": "M",
        "Ν": "N",
        "Ο": "O",
        "Ρ": "P",
        "Τ": "T",
        "Υ": "Y",
        "Χ": "X",
        "α": "a",
        "ι": "i",
        "κ": "k",
        "ο": "o",
        "ρ": "p",
        "τ": "t",
        "υ": "u",
        "χ": "x",
        "а": "a",
        "е": "e",
        "і": "i",
        "ј": "j",
        "о": "o",
        "р": "p",
        "с": "c",
        "х": "x",
        "у": "y",
        "ѕ": "s",
        "ɡ": "g",
        "ʟ": "l",
        "ᴜ": "u",
        "ո": "n",
    }
)


class SecurityBoundaryMarkdownIt(MarkdownIt):
    """Parse every link scheme so the local allowlist can inspect it."""

    def validateLink(self, url: str) -> bool:
        return True


SECURITY_COMMONMARK = SecurityBoundaryMarkdownIt("commonmark")


def visible_inline_text(token: Token) -> str:
    """Return decoded, formatting-free CommonMark inline text."""
    parts: list[str] = []
    for child in getattr(token, "children", None) or ():
        if child.type in {"text", "code_inline", "html_inline"}:
            parts.append(child.content)
        elif child.type in {"softbreak", "hardbreak"}:
            parts.append("\n")
    return "".join(parts)


def _decode_security_layer(text: str) -> str:
    try:
        percent_decoded = unquote_to_bytes(text).decode("utf-8", errors="strict")
    except UnicodeError:
        # Preserve the unsafe escape verbatim so residual-encoding checks fail
        # closed instead of replacing attacker-controlled bytes with U+FFFD.
        percent_decoded = text
    return unicodedata.normalize("NFKC", html_unescape(percent_decoded))


def canonicalize_security_text(text: str) -> str:
    """Decode nested entities, percent escapes, and compatibility characters.

    Sixty-four rounds cover realistic nested encodings without permitting an
    attacker to turn validation into quadratic work. Callers fail closed when
    :func:`has_residual_encoding` reports another encoded layer.
    """
    canonical = text
    for _ in range(_MAX_CANONICALIZATION_PASSES):
        decoded = _decode_security_layer(canonical)
        if decoded == canonical:
            return canonical
        canonical = decoded
    return canonical


def _confusable_skeleton(canonical: str) -> str:
    decomposed = "".join(
        character
        for character in unicodedata.normalize("NFKD", canonical)
        if not unicodedata.category(character).startswith("M")
    ).translate(_ASCII_CONFUSABLE_TRANSLATION)
    skeleton_parts: list[str] = []
    for character in decomposed:
        if character.isascii():
            skeleton_parts.append(character)
            continue
        name = unicodedata.name(character, "")
        match = _LATIN_NAME_BASE_RE.fullmatch(name)
        if match:
            skeleton_parts.append(match.group("base"))
            continue
        alias = _LATIN_NAME_ALIAS_RE.fullmatch(name)
        skeleton_parts.append(_LATIN_NAME_ALIASES[alias.group("alias")] if alias else character)
    return "".join(skeleton_parts)


def confusable_security_text_candidates(text: str) -> tuple[str, ...]:
    """Return canonical and confusable-resistant views without layout rewrites."""
    canonical = canonicalize_security_text(text)
    return tuple(dict.fromkeys((canonical, _confusable_skeleton(canonical))))


def security_text_candidates(text: str) -> tuple[str, ...]:
    """Return canonical, flattened, and confusable-resistant security views."""
    candidates = (text, *confusable_security_text_candidates(text))
    flattened = tuple(re.sub(r"[\r\n]+", " ", candidate) for candidate in candidates)
    control_whitespace_stripped = tuple(
        re.sub(r"[\t\f\v]+", "", candidate) for candidate in candidates
    )
    return tuple(dict.fromkeys((*candidates, *flattened, *control_whitespace_stripped)))


def find_mixed_script_token(text: str) -> str | None:
    """Return a token that mixes Latin letters with another Unicode script.

    Security-sensitive command words are short enough that mixing scripts is
    not legitimate natural-language typography. Pure non-Latin words and
    ordinary Latin words with diacritics remain valid.
    """
    token: list[str] = []

    def mixed(candidate: list[str]) -> bool:
        scripts: set[str] = set()
        for character in candidate:
            if not character.isalpha():
                continue
            name = unicodedata.name(character, "")
            scripts.add("LATIN" if character.isascii() or "LATIN" in name else "OTHER")
        return len(scripts) > 1

    for character in text:
        if character.isalpha() or unicodedata.category(character).startswith("M"):
            token.append(character)
            continue
        if token and mixed(token):
            return "".join(token)
        token.clear()
    if token and mixed(token):
        return "".join(token)
    return None


def has_residual_encoding(text: str) -> bool:
    """Return whether bounded canonicalization left another encoded layer."""
    return bool(_RESIDUAL_PERCENT_ENCODING_RE.search(text) or html_unescape(text) != text)


def has_invalid_percent_encoding(text: str) -> bool:
    """Return whether any bounded percent-decoding layer is invalid UTF-8."""
    candidate = text
    for _ in range(_MAX_CANONICALIZATION_PASSES + 1):
        try:
            percent_decoded = unquote_to_bytes(candidate).decode("utf-8", errors="strict")
        except UnicodeError:
            return True
        decoded = unicodedata.normalize("NFKC", html_unescape(percent_decoded))
        if decoded == candidate:
            return False
        candidate = decoded
    return False


def has_encoded_control_whitespace(text: str) -> bool:
    """Return whether an encoded layer introduces line or tab controls."""
    candidate = text
    for _ in range(_MAX_CANONICALIZATION_PASSES):
        if _ENCODED_CONTROL_WHITESPACE_RE.search(candidate):
            return True
        decoded = _decode_security_layer(candidate)
        if decoded == candidate:
            return False
        candidate = decoded
    return _ENCODED_CONTROL_WHITESPACE_RE.search(candidate) is not None


def decoded_link_destinations(token: Token) -> list[str]:
    """Return canonical destinations from an inline CommonMark token."""
    destinations: list[str] = []
    for child in token.children or ():
        if child.type != "link_open":
            continue
        destination = child.attrGet("href")
        if isinstance(destination, str) and destination:
            destinations.append(canonicalize_security_text(destination))
    return destinations


def decoded_link_titles(token: Token) -> list[str]:
    """Return canonical title metadata from an inline CommonMark token."""
    titles: list[str] = []
    for child in token.children or ():
        if child.type != "link_open":
            continue
        title = child.attrGet("title")
        if isinstance(title, str) and title:
            titles.append(canonicalize_security_text(title))
    return titles


def decoded_reference_metadata(env: dict[str, object]) -> list[tuple[str, str, str]]:
    """Return labels, destinations, and titles for every link definition."""
    references = env.get("references")
    if not isinstance(references, dict):
        return []
    metadata: list[tuple[str, str, str]] = []
    for raw_label, reference in references.items():
        if not isinstance(reference, dict):
            continue
        raw_destination = reference.get("href", "")
        raw_title = reference.get("title", "")
        label = canonicalize_security_text(str(raw_label))
        destination = (
            canonicalize_security_text(raw_destination) if isinstance(raw_destination, str) else ""
        )
        title = canonicalize_security_text(raw_title) if isinstance(raw_title, str) else ""
        metadata.append((label, destination, title))
    return metadata


def commonmark_security_text(text: str) -> str:
    """Render visible text plus hidden link metadata for security checks."""
    env: dict[str, object] = {}
    parts: list[str] = []
    for token in SECURITY_COMMONMARK.parse(text, env):
        if token.type != "inline":
            continue
        parts.append(visible_inline_text(token))
        parts.extend(decoded_link_destinations(token))
        parts.extend(decoded_link_titles(token))
    for label, destination, title in decoded_reference_metadata(env):
        parts.extend(value for value in (label, destination, title) if value)
    return "\n".join(parts)


def link_destination_violation(
    destination: str,
    *,
    allow_root_relative: bool = True,
    allow_local_relative: bool = True,
) -> str | None:
    """Reject one executable artifact or active URI destination."""
    if has_invalid_percent_encoding(destination):
        return "invalid UTF-8 percent encoding in Markdown link destination"
    if re.match(r"^https?:", destination, re.IGNORECASE) and (
        raw_http_violation := _http_target_violation(
            destination,
            target_name="HTTP Markdown link destination",
        )
    ):
        return raw_http_violation
    destination = canonicalize_security_text(destination)
    if has_residual_encoding(destination):
        return "excessive or residual encoding in Markdown link destination"
    if unsafe_unicode := find_unsafe_authored_unicode(destination):
        return f"unsafe Unicode in Markdown link destination: {unsafe_unicode}"
    try:
        parsed = urlsplit(destination)
    except ValueError:
        return "invalid Markdown link destination"
    if parsed.scheme.casefold() not in SAFE_LINK_SCHEMES:
        return "only relative, HTTP, and HTTPS authored links are allowed"
    if parsed.username is not None or parsed.password is not None:
        return "userinfo is not allowed in authored links"
    if parsed.scheme:
        if canonical_http_violation := _http_target_violation(
            destination,
            target_name="HTTP Markdown link destination",
        ):
            return canonical_http_violation
    if not parsed.scheme and (
        parsed.netloc
        or destination.startswith("\\")
        or (not allow_root_relative and destination.startswith("/"))
        or (
            not allow_local_relative
            and destination.casefold().startswith(("./", ".\\", "~/", "~\\"))
        )
    ):
        return "absolute local and scheme-relative authored links are not allowed"
    path = parsed.path.replace("\\", "/").rstrip("/")
    leaf = path.rsplit("/", 1)[-1]
    if command_grammar.EXECUTABLE_SUFFIX_RE.search(leaf):
        return "executable Markdown link destination is not allowed"
    if ".." in path.split("/"):
        return f"unsafe progressive-disclosure path: {destination}"
    return None


def _http_target_violation(candidate: str, *, target_name: str) -> str | None:
    """Validate one HTTP representation without changing its authority."""
    if has_invalid_percent_encoding(candidate):
        return f"invalid UTF-8 percent encoding in {target_name}"
    if "\\" in candidate or re.match(r"^https?://", candidate, re.IGNORECASE) is None:
        return f"malformed {target_name}"
    authority = re.split(r"[/?#]", candidate.split("://", 1)[1], maxsplit=1)[0]
    if _RESIDUAL_PERCENT_ENCODING_RE.search(authority):
        return f"encoded authority delimiter or hostname in {target_name}"
    try:
        parsed = urlsplit(candidate)
        _ = parsed.port
    except ValueError:
        return f"invalid {target_name}"
    if not parsed.netloc or parsed.hostname is None:
        return f"{target_name} requires a host"
    if parsed.username is not None or parsed.password is not None:
        return f"userinfo is not allowed in {target_name}"
    if reason := non_public_host_block_reason(parsed.hostname):
        return f"non-public {target_name}: {reason}"
    return None


def raw_http_url_violation(text: str) -> str | None:
    """Reject malformed or lexically non-public HTTP targets in prose."""
    for surface in dict.fromkeys((text, canonicalize_security_text(text))):
        for match in _RAW_HTTP_URL_RE.finditer(surface):
            candidate = match.group(0).rstrip(".,;!?")
            while candidate.endswith(")") and candidate.count(")") > candidate.count("("):
                candidate = candidate[:-1]
            if violation := _http_target_violation(candidate, target_name="HTTP target"):
                return violation
    return None


def token_link_destination_violation(token: Token) -> str | None:
    """Reject executable artifacts and active URI schemes in authored links."""
    for destination in decoded_link_destinations(token):
        if violation := link_destination_violation(destination):
            return violation
    return None


__all__ = [
    "SAFE_LINK_SCHEMES",
    "SECURITY_COMMONMARK",
    "canonicalize_security_text",
    "commonmark_security_text",
    "confusable_security_text_candidates",
    "decoded_link_destinations",
    "decoded_link_titles",
    "decoded_reference_metadata",
    "find_mixed_script_token",
    "has_encoded_control_whitespace",
    "has_invalid_percent_encoding",
    "has_residual_encoding",
    "link_destination_violation",
    "raw_http_url_violation",
    "security_text_candidates",
    "token_link_destination_violation",
    "visible_inline_text",
]
