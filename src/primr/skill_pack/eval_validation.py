"""Bounded schema and control-plane validation for behavioral eval artifacts."""

from __future__ import annotations

import json
import re
import unicodedata

from primr.skill_pack.code_comment_projection import CODE_FENCE_LANGUAGES, code_comment_prose
from primr.skill_pack.config import MAX_EVAL_CASES
from primr.skill_pack.markdown_safety import (
    SECURITY_COMMONMARK,
    canonicalize_security_text,
    decoded_reference_metadata,
    find_mixed_script_token,
    has_encoded_control_whitespace,
    has_invalid_percent_encoding,
    has_residual_encoding,
    raw_http_url_violation,
    security_text_candidates,
    visible_inline_text,
)
from primr.skill_pack.script_safety import scan_direct_execution_instruction
from primr.utils.content_sanitizer import (
    find_authored_agent_instruction,
    find_authored_prompt_control,
    find_sensitive_exfiltration_instruction,
)
from primr.utils.content_sanitizer import (
    find_unsafe_instruction_unicode as find_unsafe_authored_unicode,
)

_MAX_EVAL_JSON_CHARS = 256 * 1024
_MAX_EVAL_JSON_BYTES = 512 * 1024
_MAX_EVAL_ASSERTIONS = 25
_MAX_EVAL_TEXT_CHARS = 16 * 1024
_MAX_SKILL_NAME_CHARS = 64
_EVAL_TOP_LEVEL_KEYS = frozenset({"skill_name", "evals"})
_EVAL_CANONICAL_CASE_KEYS = frozenset({"id", "prompt", "expected_output", "expectations"})
_EVAL_LEGACY_CASE_KEYS = frozenset({"id", "prompt", "expected_output", "assertions"})
_REVIEW_CRITERION_PATTERN = (
    r"(?:accessibility|accuracy|best\s+practices|bugs?|code\s+quality|compatibility|"
    r"correctness|edge\s+cases|errors?|maintainability|performance|readability|"
    r"regressions?|requirements|safety|security|standards|style|testability|"
    r"type\s+safety|vulnerabilities?)"
)
_REVIEW_CRITERIA_PATTERN = (
    rf"{_REVIEW_CRITERION_PATTERN}(?:\s*,\s*{_REVIEW_CRITERION_PATTERN}){{0,3}}"
    rf"(?:\s*,?\s+and\s+{_REVIEW_CRITERION_PATTERN})?"
)
_INERT_REVIEW_FRAME_RE = re.compile(
    r"^\s*(?:please\s+)?(?:analy[sz]e|audit|compare|critique|evaluate|examine|"
    r"explain|inspect|review|summarize)\s+"
    r"(?:(?:a|an|the|this|following)\s+)?(?:[A-Za-z0-9_.+#-]+\s+){0,4}"
    r"(?:code|configuration|expression|file|function|query|script|snippet|template)"
    rf"(?:\s+(?:against|for)\s+{_REVIEW_CRITERIA_PATTERN})?"
    r"(?:\s+and\s+(?:do\s+not|never)\s+(?:deploy|execute|invoke|launch|run|use)"
    r"\s+(?:it|this|that))?\s*:?\s*$",
    re.IGNORECASE,
)
_REVIEW_FRAME_OPERATION_RE = re.compile(
    r"\b(?:activate|boot|carry\s+out|click|deploy|execute|import|install|invoke|launch|"
    r"load|open|run|sideload|source|start|use)\b",
    re.IGNORECASE,
)
_REVIEW_FRAME_NEGATION_TAIL_RE = re.compile(
    r"\b(?:do\s+not|never|under\s+no\s+circumstances)\s*$",
    re.IGNORECASE,
)
_UNSAFE_RAW_URI_RE = re.compile(
    r"\b(?:data|file|ftp|javascript|smb|vbscript):(?=\S)",
    re.IGNORECASE,
)
_FENCE_INFO_RE = re.compile(r"[A-Za-z0-9_+.-]{0,32}")


def _fenced_data_violation(content: str, language: str) -> str | None:
    """Reject control prose hidden inside canonical inert review data."""
    canonical_content = canonicalize_security_text(content)
    try:
        canonical_authored_prose = (
            code_comment_prose(canonical_content, language)
            if language.casefold() in CODE_FENCE_LANGUAGES
            else canonical_content
        )
    except (MemoryError, RecursionError, SystemError):
        return "review data exceeds parser complexity limits"
    if mixed_script := find_mixed_script_token(canonical_authored_prose):
        return f"mixed-script token in review data: {mixed_script}"
    for candidate in security_text_candidates(content):
        if unsafe_unicode := find_unsafe_authored_unicode(candidate):
            return f"unsafe Unicode in review data: {unsafe_unicode}"
        if prompt_control := find_authored_prompt_control(candidate):
            return f"control instruction in review data: {prompt_control}"
        try:
            authored_prose = (
                code_comment_prose(candidate, language)
                if language.casefold() in CODE_FENCE_LANGUAGES
                else candidate
            )
        except (MemoryError, RecursionError, SystemError):
            return "review data exceeds parser complexity limits"
        if exfiltration := find_sensitive_exfiltration_instruction(authored_prose):
            return f"sensitive-data instruction in review data: {exfiltration}"
        if instruction := find_authored_agent_instruction(authored_prose):
            return f"agent instruction in review data: {instruction}"
        if direct_execution := scan_direct_execution_instruction(authored_prose):
            return f"execution instruction in review data: {direct_execution}"
    return None


def _fence_info_violation(info: str) -> str | None:
    """Reject control instructions in a canonical fence language identifier."""
    canonical = canonicalize_security_text(info)
    if _FENCE_INFO_RE.fullmatch(canonical) is None:
        return "fenced review language identifier is invalid"
    if canonical.casefold() in CODE_FENCE_LANGUAGES:
        return None
    semantic_surface = re.sub(r"[_-]+", " ", canonical)
    if mixed_script := find_mixed_script_token(semantic_surface):
        return f"mixed-script fenced review language identifier: {mixed_script}"
    for candidate in security_text_candidates(semantic_surface):
        if prompt_control := find_authored_prompt_control(candidate):
            return f"control instruction in fenced review language identifier: {prompt_control}"
        if instruction := find_authored_agent_instruction(candidate):
            return f"agent instruction in fenced review language identifier: {instruction}"
        if direct_execution := scan_direct_execution_instruction(candidate):
            return f"execution instruction in fenced review language identifier: {direct_execution}"
    return None


def _is_inert_review_frame(frame: str) -> bool:
    if _INERT_REVIEW_FRAME_RE.fullmatch(frame) is None:
        return False
    return all(
        _REVIEW_FRAME_NEGATION_TAIL_RE.search(frame[max(0, match.start() - 40) : match.start()])
        is not None
        for match in _REVIEW_FRAME_OPERATION_RE.finditer(frame)
    )


def _eval_commonmark_projection(text: str) -> tuple[str, str | None]:
    """Project eval prose while admitting only explicitly framed review data."""
    env: dict[str, object] = {}
    tokens = SECURITY_COMMONMARK.parse(text, env)
    source_lines = text.splitlines()
    parts: list[str] = []
    last_visible_prose = ""
    if decoded_reference_metadata(env):
        return "", "Markdown link definitions are not supported in behavioral eval fields"
    for token in tokens:
        if token.type in {"fence", "code_block"}:
            if token.type == "fence" and token.map:
                final_line = source_lines[token.map[1] - 1]
                closing_candidate = re.sub(r"^(?:[ ]{0,3}>[ \t]?)+", "", final_line).strip()
                closing_pattern = rf"{re.escape(token.markup[0])}{{{len(token.markup)},}}"
                if re.fullmatch(closing_pattern, closing_candidate) is None:
                    return "", "code fence is not closed or has an ambiguous closing line"
            canonical_frame = unicodedata.normalize("NFKC", last_visible_prose)
            if not _is_inert_review_frame(canonical_frame):
                return "", "code block requires explicit inert review framing"
            if token.type == "fence" and (
                info_violation := _fence_info_violation(token.info.strip())
            ):
                return "", info_violation
            language = token.info.strip() if token.type == "fence" else ""
            if violation := _fenced_data_violation(token.content, language):
                return "", violation
            continue
        if token.type == "html_block":
            return "", "raw HTML outside a fenced review block"
        if token.type != "inline":
            continue
        children = list(token.children or ())
        if any(child.type == "image" for child in children):
            return "", "images are not supported in behavioral eval fields"
        if any(child.type == "html_inline" for child in children):
            return "", "raw HTML outside a fenced review block"
        if any(child.type == "link_open" for child in children):
            return "", "Markdown links are not supported in behavioral eval fields"
        visible_text = visible_inline_text(token)
        if visible_text.strip():
            last_visible_prose = visible_text
        parts.append(visible_text)
    return "\n".join(parts), None


def find_eval_control_instruction(text: str) -> str | None:
    """Return unsafe control-plane prose from a behavioral-eval field.

    Fenced examples remain review data. Visible CommonMark prose, link metadata,
    Unicode controls, prompt overrides, executable launch directions, and
    affirmative credential-transfer instructions remain ship blockers.
    """
    if unsafe_unicode := find_unsafe_authored_unicode(text):
        return f"unsafe Unicode: {unsafe_unicode}"
    if has_invalid_percent_encoding(text):
        return "invalid UTF-8 percent encoding"
    if has_encoded_control_whitespace(text):
        return "encoded control whitespace"
    canonical_text = canonicalize_security_text(text)
    if has_residual_encoding(canonical_text):
        return "excessive or residual encoded control text"
    if raw_url_violation := raw_http_url_violation(text):
        return raw_url_violation
    rendered, markdown_violation = _eval_commonmark_projection(canonical_text)
    if markdown_violation:
        return markdown_violation
    canonical_rendered = canonicalize_security_text(rendered)
    if has_residual_encoding(canonical_rendered):
        return "excessive or residual encoded control text"
    if mixed_script := find_mixed_script_token(canonical_rendered):
        return f"mixed-script token: {mixed_script}"
    for candidate in security_text_candidates(rendered):
        if unsafe_unicode := find_unsafe_authored_unicode(candidate):
            return f"unsafe Unicode: {unsafe_unicode}"
        if prompt_control := find_authored_prompt_control(candidate):
            return prompt_control
        if raw_url_violation := raw_http_url_violation(candidate):
            return raw_url_violation
        if unsafe_uri := _UNSAFE_RAW_URI_RE.search(candidate):
            return f"unsafe URI scheme: {unsafe_uri.group(0)}"
        if exfiltration := find_sensitive_exfiltration_instruction(candidate):
            return exfiltration
        if authored_instruction := find_authored_agent_instruction(candidate):
            return authored_instruction
        if direct_execution := scan_direct_execution_instruction(candidate):
            return direct_execution
    return None


def _scan_eval_text(label: str, value: str) -> str | None:
    if not value.strip():
        return f"eval {label} must be non-empty"
    if len(value) > _MAX_EVAL_TEXT_CHARS:
        return f"eval {label} exceeds {_MAX_EVAL_TEXT_CHARS} characters"
    if hit := find_eval_control_instruction(value):
        return f"control instruction in eval {label}: {hit[:80]}"
    return None


def _scan_eval_files(value: object) -> str | None:
    if not isinstance(value, list):
        return "eval files must be a list"
    if value:
        return "eval input files are not supported by Primr packaging"
    return None


def scan_eval_case_fields(
    prompt: str,
    expected_output: str,
    assertions: list[str],
) -> str | None:
    """Validate agent-consumed text in one behavioral evaluation case."""
    if not assertions:
        return "eval assertions must be a non-empty list"
    if len(assertions) > _MAX_EVAL_ASSERTIONS:
        return f"eval assertions exceed {_MAX_EVAL_ASSERTIONS}"
    fields = [("prompt", prompt), ("expected_output", expected_output)]
    fields.extend((f"assertions[{index}]", assertion) for index, assertion in enumerate(assertions))
    for label, value in fields:
        if not isinstance(value, str):
            return f"eval {label} must be a string"
        if unsafe := _scan_eval_text(label, value):
            return unsafe
    return None


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key!r}")
        result[key] = value
    return result


def scan_eval_json(content: str, *, expected_skill_name: str | None = None) -> str | None:
    """Validate Primr's bounded form of Anthropic's current evals schema."""
    if len(content) > _MAX_EVAL_JSON_CHARS:
        return f"eval JSON exceeds {_MAX_EVAL_JSON_CHARS} characters"
    try:
        content_bytes = content.encode("utf-8")
    except UnicodeEncodeError as exc:
        return f"invalid eval JSON: {type(exc).__name__}"
    if len(content_bytes) > _MAX_EVAL_JSON_BYTES:
        return f"eval JSON exceeds {_MAX_EVAL_JSON_BYTES} bytes"
    try:
        payload = json.loads(content, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, UnicodeError, ValueError, RecursionError) as exc:
        return f"invalid eval JSON: {type(exc).__name__}"
    if not isinstance(payload, dict) or set(payload) != _EVAL_TOP_LEVEL_KEYS:
        return "eval JSON must contain exactly skill_name and evals"
    skill_name = payload["skill_name"]
    if (
        not isinstance(skill_name, str)
        or not skill_name.strip()
        or len(skill_name) > _MAX_SKILL_NAME_CHARS
    ):
        return "eval skill_name must be a non-empty bounded string"
    if unsafe := _scan_eval_text("skill_name", skill_name):
        return unsafe
    if expected_skill_name is not None and skill_name != expected_skill_name:
        return "eval skill_name does not match the containing skill"
    evals = payload["evals"]
    if not isinstance(evals, list) or not evals or len(evals) > MAX_EVAL_CASES:
        return f"evals must contain between 1 and {MAX_EVAL_CASES} cases"
    seen_ids: set[int] = set()
    for index, case in enumerate(evals, start=1):
        if not isinstance(case, dict):
            return f"eval case {index} has an invalid structure"
        case_keys = set(case)
        if case_keys in (_EVAL_CANONICAL_CASE_KEYS, _EVAL_CANONICAL_CASE_KEYS | {"files"}):
            assertions_key = "expectations"
        elif case_keys == _EVAL_LEGACY_CASE_KEYS:
            assertions_key = "assertions"
        else:
            return f"eval case {index} has an invalid structure"
        case_id = case["id"]
        if type(case_id) is not int or case_id <= 0 or case_id in seen_ids:
            return f"eval case {index} id must be a unique positive integer"
        seen_ids.add(case_id)
        prompt = case["prompt"]
        expected_output = case["expected_output"]
        assertions = case[assertions_key]
        if not isinstance(prompt, str) or not isinstance(expected_output, str):
            return f"eval case {index} prompt and expected_output must be strings"
        if not isinstance(assertions, list) or not all(
            isinstance(assertion, str) for assertion in assertions
        ):
            return f"eval case {index} assertions must be a list of strings"
        if unsafe := scan_eval_case_fields(prompt, expected_output, assertions):
            return f"eval case {index}: {unsafe}"
        if "files" in case and (unsafe := _scan_eval_files(case["files"])):
            return f"eval case {index}: {unsafe}"
    return None


__all__ = ["find_eval_control_instruction", "scan_eval_case_fields", "scan_eval_json"]
