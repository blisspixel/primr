"""Bounded detection of machine-readable process specifications.

Generated skill prose may contain ordinary JSON examples and glossary-style
YAML labels. This module rejects only structural execution keys, non-empty
argument vectors, executable tool values, or correlated process file and
argument fields. Parsing is bounded and never constructs application objects.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping

import yaml
from yaml.tokens import AliasToken, AnchorToken, TagToken

from .command_grammar import (
    EXECUTABLE_SUFFIX_RE,
    KNOWN_EXECUTION_LAUNCHER_RE,
    looks_like_standalone_shell_command,
)

_MAX_JSON_DECODE_ATTEMPTS = 1_024
_MAX_MACHINE_TEXT_CHARS = 64 * 1024
_MAX_YAML_TOKENS = 4_096
_COMMAND_EXECUTION_KEYS = frozenset({"cmd", "command", "run"})
_STRICT_COMMAND_EXECUTION_KEYS = frozenset({"cmd", "command"})
_ENTRYPOINT_EXECUTION_KEYS = frozenset({"executable"})
_SHELL_EXECUTION_KEYS = frozenset({"shell"})
_VECTOR_EXECUTION_KEYS = frozenset({"argv", "command_line", "commandline"})
_PROCESS_FILE_KEYS = frozenset(
    {
        "binary",
        "executable_path",
        "executablepath",
        "file",
        "file_name",
        "filename",
        "path",
        "program",
    }
)
_PROCESS_ARGUMENT_KEYS = frozenset({"args", "argument_list", "argumentlist", "arguments"})
_PROCESS_CONTAINER_KEYS = frozenset({"process"})
_TOOL_KEYS = frozenset({"runner", "tool"})
_OPERATIONAL_TOOL_VALUES = frozenset(
    {"bash", "cli", "cmd", "command", "console", "powershell", "shell", "terminal"}
)
_INERT_DOCUMENT_SUFFIX_RE = re.compile(
    r"\.(?:csv|docx?|json|md|pdf|pptx?|txt|xlsx?|ya?ml)$", re.IGNORECASE
)
_YAML_MAPPING_LINE_RE = re.compile(
    r"^\s*(?:-\s*)?(?P<key>`[^`\r\n]+`|\"[^\"\r\n]+\"|'[^'\r\n]+'|"
    r"[A-Za-z0-9][A-Za-z0-9._-]*)\s*:\s*(?P<value>.*)$"
)
_SINGLE_TOKEN_RE = re.compile(r"[A-Za-z0-9._/\\-]+")
_INERT_PROCESS_VALUES = frozenset({"manual", "manual review"})


def _normalize_key(key: object) -> str:
    normalized = str(key).strip().strip("`\"'").casefold().replace("-", "_")
    return normalized


def _has_value(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return value is not None and value is not False


def _is_executable_value(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    candidate = value.strip()
    return bool(
        EXECUTABLE_SUFFIX_RE.search(candidate)
        or looks_like_standalone_shell_command(candidate, case_sensitive_generic=False)
    )


def _is_process_file_value(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    return _INERT_DOCUMENT_SUFFIX_RE.search(value.strip()) is None


def _is_entrypoint_value(value: object) -> bool:
    if not _has_value(value):
        return False
    if isinstance(value, (list, dict)):
        return True
    if not isinstance(value, str):
        return False
    candidate = value.strip()
    return bool(_is_executable_value(candidate) or _SINGLE_TOKEN_RE.fullmatch(candidate))


def _is_contextual_command_scalar(value: object) -> bool:
    """Recognize commands inside fields that explicitly declare a process."""
    if not isinstance(value, str) or not value.strip():
        return False
    candidate = value.strip()
    if candidate.casefold() in _INERT_PROCESS_VALUES:
        return False
    if _is_executable_value(candidate):
        return True
    tokens = candidate.split()
    return bool(
        len(tokens) > 1
        and tokens[0] == tokens[0].casefold()
        and _SINGLE_TOKEN_RE.fullmatch(tokens[0])
    )


def _is_process_scalar(value: object) -> bool:
    """Treat nonempty explicit process fields as operational, except reviewed metadata."""
    return bool(
        isinstance(value, str)
        and value.strip()
        and value.strip().casefold() not in _INERT_PROCESS_VALUES
    )


def _is_command_value(value: object, *, allow_inert_single_token: bool) -> bool:
    """Return whether a scalar or vector is shaped as an executable command."""
    if isinstance(value, str):
        candidate = value.strip()
        if _is_contextual_command_scalar(candidate):
            return True
        return bool(
            not allow_inert_single_token
            and candidate == candidate.casefold()
            and _SINGLE_TOKEN_RE.fullmatch(candidate)
        )
    if isinstance(value, (list, dict)):
        return bool(value)
    return False


def _contains_process_arguments(value: object, *, depth: int = 0) -> bool:
    if depth > 64:
        return True
    if isinstance(value, dict):
        items = {_normalize_key(key): child for key, child in value.items()}
        if any(key in _PROCESS_ARGUMENT_KEYS and _has_value(child) for key, child in items.items()):
            return True
        return any(_contains_process_arguments(child, depth=depth + 1) for child in items.values())
    if isinstance(value, list):
        return any(_contains_process_arguments(child, depth=depth + 1) for child in value)
    return False


def _collect_process_file_values(value: object, *, depth: int = 0) -> tuple[list[object], bool]:
    """Collect nested process-file values and report a traversal-limit breach."""
    if depth > 64:
        return [], True
    if isinstance(value, dict):
        items = {_normalize_key(key): child for key, child in value.items()}
        values = [child for key, child in items.items() if key in _PROCESS_FILE_KEYS]
        exceeded = False
        for child in items.values():
            nested_values, nested_exceeded = _collect_process_file_values(child, depth=depth + 1)
            values.extend(nested_values)
            exceeded = exceeded or nested_exceeded
        return values, exceeded
    if isinstance(value, list):
        list_values: list[object] = []
        exceeded = False
        for child in value:
            nested_values, nested_exceeded = _collect_process_file_values(child, depth=depth + 1)
            list_values.extend(nested_values)
            exceeded = exceeded or nested_exceeded
        return list_values, exceeded
    return [], False


def _mapping_declares_execution(mapping: Mapping[str, object]) -> bool:
    items = {_normalize_key(raw_key): value for raw_key, value in mapping.items()}
    command_values = [value for key, value in items.items() if key in _COMMAND_EXECUTION_KEYS]
    if any(
        key in _COMMAND_EXECUTION_KEYS
        and _is_command_value(
            value,
            allow_inert_single_token=key not in _STRICT_COMMAND_EXECUTION_KEYS,
        )
        for key, value in items.items()
    ):
        return True
    if any(
        key in _ENTRYPOINT_EXECUTION_KEYS and _is_entrypoint_value(value)
        for key, value in items.items()
    ):
        return True
    if any(
        key in _SHELL_EXECUTION_KEYS
        and (
            _is_executable_value(value)
            or value is True
            or (isinstance(value, str) and value.strip().casefold() in _OPERATIONAL_TOOL_VALUES)
        )
        for key, value in items.items()
    ):
        return True
    if any(key in _VECTOR_EXECUTION_KEYS and _has_value(value) for key, value in items.items()):
        return True
    if "script" in items and _is_executable_value(items["script"]):
        return True
    if "entrypoint" in items and _is_entrypoint_value(items["entrypoint"]):
        return True
    if "spawn" in items and _has_value(items["spawn"]):
        return True
    if any(
        key in _TOOL_KEYS
        and isinstance(value, str)
        and (value.strip().casefold() in _OPERATIONAL_TOOL_VALUES or _is_executable_value(value))
        for key, value in items.items()
    ):
        return True
    file_values, file_scan_exceeded = _collect_process_file_values(items)
    if file_scan_exceeded:
        return True
    if any(_is_executable_value(value) for value in file_values):
        return True
    has_arguments = _contains_process_arguments(items)
    return has_arguments and (
        any(_is_process_file_value(value) for value in file_values)
        or any(_is_process_file_value(value) for value in command_values)
    )


def _is_process_vector(value: list[object], *, allow_executable_inventory: bool) -> bool:
    """Return whether a sequence has an executable argv-style first element."""
    if not value or not isinstance(value[0], str):
        return False
    string_values = [element for element in value if isinstance(element, str)]
    if len(string_values) != len(value):
        return False
    if (
        allow_executable_inventory
        and len(string_values) > 1
        and all(KNOWN_EXECUTION_LAUNCHER_RE.fullmatch(element.strip()) for element in string_values)
    ):
        return False
    joined = " ".join(string_values)
    if not allow_executable_inventory:
        return joined.strip().casefold() not in _INERT_PROCESS_VALUES
    executable = _is_executable_value(value[0]) or looks_like_standalone_shell_command(
        joined, case_sensitive_generic=False
    )
    return executable


def _visit_json(
    value: object,
    *,
    depth: int = 0,
    process_context: bool = False,
    bare_vector: bool = False,
) -> bool:
    if depth > 64:
        return True
    if isinstance(value, dict):
        if _mapping_declares_execution(value):
            return True
        return any(
            _visit_json(
                child,
                depth=depth + 1,
                process_context=_normalize_key(key) in _PROCESS_CONTAINER_KEYS,
                bare_vector=bare_vector,
            )
            for key, child in value.items()
        )
    if isinstance(value, list):
        if (process_context and _is_process_vector(value, allow_executable_inventory=False)) or (
            bare_vector and _is_process_vector(value, allow_executable_inventory=True)
        ):
            return True
        if process_context and all(isinstance(child, str) for child in value):
            return False
        return any(
            _visit_json(
                child,
                depth=depth + 1,
                process_context=process_context,
                bare_vector=bare_vector,
            )
            for child in value
        )
    if process_context and isinstance(value, str):
        return _is_process_scalar(value)
    return False


def _contains_json_execution_instruction(text: str) -> bool:
    decoder = json.JSONDecoder()
    position = 0
    attempts = 0
    while position < len(text):
        object_start = text.find("{", position)
        array_start = text.find("[", position)
        starts = [start for start in (object_start, array_start) if start >= 0]
        if not starts:
            return False
        start = min(starts)
        next_nonspace = start + 1
        while next_nonspace < len(text) and text[next_nonspace].isspace():
            next_nonspace += 1
        following = text[next_nonspace : next_nonspace + 1]
        plausible = (
            following in {'"', "}"}
            if text[start] == "{"
            else following in {'"', "{", "[", "]", "-", "t", "f", "n"} or following.isdigit()
        )
        if not plausible:
            position = start + 1
            continue
        attempts += 1
        if attempts > _MAX_JSON_DECODE_ATTEMPTS:
            return True
        try:
            value, end = decoder.raw_decode(text, start)
        except (json.JSONDecodeError, RecursionError):
            position = start + 1
            continue
        try:
            if _visit_json(value, bare_vector=True):
                return True
        except RecursionError:
            return True
        position = max(end, start + 1)
    return False


def _yaml_scalar(value: str) -> object:
    candidate = value.strip()
    casefolded = candidate.casefold()
    if (
        casefolded in {"", "false", "no", "null", "off", "~"}
        or re.fullmatch(r"\[\s*]", candidate)
        or re.fullmatch(r"\{\s*}", candidate)
    ):
        return ""
    if len(candidate) >= 2 and candidate[0] == candidate[-1] and candidate[0] in {'"', "'", "`"}:
        return candidate[1:-1]
    return candidate


def _load_bounded_yaml(text: str) -> tuple[list[object], bool]:
    """Load basic YAML values after explicit size, token, and alias bounds."""
    if len(text) > _MAX_MACHINE_TEXT_CHARS:
        return [], True
    try:
        for token_count, token in enumerate(yaml.scan(text, Loader=yaml.SafeLoader), start=1):
            if token_count > _MAX_YAML_TOKENS or isinstance(
                token, (AliasToken, AnchorToken, TagToken)
            ):
                return [], True
        return list(yaml.safe_load_all(text)), False
    except RecursionError:
        return [], True
    except yaml.YAMLError:
        return [], False


def _contains_line_yaml_execution_instruction(text: str) -> bool:
    """Fallback for mapping fragments embedded in otherwise invalid YAML."""
    current: dict[str, object] = {}
    for raw_line in text.splitlines():
        match = _YAML_MAPPING_LINE_RE.match(raw_line)
        if match is None:
            if current and _mapping_declares_execution(current):
                return True
            current = {}
            continue
        current[_normalize_key(match.group("key"))] = _yaml_scalar(match.group("value"))
        if _mapping_declares_execution(current):
            return True
    return bool(current and _mapping_declares_execution(current))


def _contains_yaml_execution_instruction(text: str) -> bool:
    documents, fail_closed = _load_bounded_yaml(text)
    if fail_closed:
        return True
    if any(_visit_json(document) for document in documents):
        return True
    return _contains_line_yaml_execution_instruction(text)


def is_inert_run_declaration(text: str) -> bool:
    """Return whether text is exactly one non-executable ``run`` metadata key."""
    documents, fail_closed = _load_bounded_yaml(text)
    if fail_closed or len(documents) != 1 or not isinstance(documents[0], dict):
        return False
    items = {_normalize_key(key): value for key, value in documents[0].items()}
    return set(items) == {"run"} and not _mapping_declares_execution(items)


def contains_machine_execution_instruction(text: str) -> bool:
    """Return whether bounded JSON or YAML-like text declares execution."""
    if len(text) > _MAX_MACHINE_TEXT_CHARS:
        return True
    return _contains_json_execution_instruction(text) or _contains_yaml_execution_instruction(text)


__all__ = ["contains_machine_execution_instruction", "is_inert_run_declaration"]
