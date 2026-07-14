"""Trust boundary for executable files shipped in generated skill packs.

Python is not safely sandboxed by inspecting its syntax. Generated or
caller-supplied helpers therefore never cross the packaging boundary. Primr
ships only exact, reviewed first-party helpers registered in this module.
"""

from __future__ import annotations

import ast
import codeop
import re
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt

from . import command_grammar as _command_grammar
from .code_fragment_safety import (
    contains_non_python_executable_fragment,
    find_non_python_executable_fragment,
)
from .materialization_safety import contains_executable_materialization
from .process_spec_safety import (
    contains_machine_execution_instruction,
    is_inert_run_declaration,
)
from .verifier_asset import (
    VERIFY_ARTIFACT_INVOCATION,
    VERIFY_ARTIFACT_SCRIPT,
    VERIFY_ARTIFACT_SCRIPT_PATH,
)

if TYPE_CHECKING:
    from markdown_it.token import Token

_VERIFICATION_SKILL_NAME_MARKERS = ("validat", "review", "check", "verif")


class _SecurityBoundaryMarkdownIt(MarkdownIt):
    """Parse every link scheme so the local allowlist can inspect it."""

    def validateLink(self, url: str) -> bool:
        return True


_COMMONMARK = _SecurityBoundaryMarkdownIt("commonmark")
_EXECUTABLE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9._/\\-])"
    r"(?:[A-Za-z]:[/\\]|[/\\]|(?:(?:\.{1,2})[/\\])*)"
    r"scripts[/\\][A-Za-z0-9._/\\-]*[A-Za-z0-9_-]"
    r"(?![A-Za-z0-9_-]|\.[A-Za-z0-9])",
    re.IGNORECASE,
)
_COMMAND_BOUNDARY_PATTERN = (
    r"(?:^|[.!?]\s+|[;:,]\s*|[(\[]\s*|\s+(?:->|=>|[-/=])\s*|"
    r"[\u2013\u2014]\s*|^\s*(?:[-*+]|\d+[.)])\s*)"
)
_INSTRUCTION_PREFIX_PATTERN = rf"(?:{_command_grammar.COMMAND_INSTRUCTION_PREFIX_PATTERN})?"
_COMMAND_START_RE = re.compile(
    rf"{_COMMAND_BOUNDARY_PATTERN}{_INSTRUCTION_PREFIX_PATTERN}"
    r"(?P<instruction>(?P<verb>run|execute|invoke)\b(?=\s|:)\s*:?\s*"
    r"(?P<command>[^\r\n]{1,400}))",
    re.IGNORECASE | re.MULTILINE,
)
_SECONDARY_COMMAND_RE = re.compile(
    rf"{_COMMAND_BOUNDARY_PATTERN}{_INSTRUCTION_PREFIX_PATTERN}"
    r"(?:use|launch|start|open|call)\b\s*:?\s*(?P<command>[^\r\n]{1,400})",
    re.IGNORECASE | re.MULTILINE,
)
_EXECUTABLE_COMMAND_OBJECTS = frozenset(
    {"binary", "executable", "interpreter", "program", "utility"}
)
_INLINE_COMMAND_CONTEXT_RE = re.compile(
    r"\b(?:use|run|execute|invoke|launch|call|start|open)\s+(?:the\s+)?$",
    re.IGNORECASE,
)
_TERMINAL_INSTRUCTION_RE = re.compile(
    r"(?:\b(?:in|at)\s+(?:the\s+|a\s+)?(?:terminal|shell|powershell|command\s+prompt)"
    r"[^\r\n]{0,160}\b(?:type|enter|paste)\b|"
    r"\b(?:type|enter|paste)\b[^\r\n]{0,160}"
    r"\b(?:terminal|shell|powershell|command\s+prompt)\b|"
    r"\b(?:shell|terminal|powershell|command\s+prompt)\s+step\s*:)",
    re.IGNORECASE,
)
_DEFINITION_LINE_RE = re.compile(
    r"^(?!https?:)(?![^:\r\n]*\bhttps?:)"
    r"(?![^:\r\n]*\b[A-Za-z][A-Za-z0-9+.-]*:[/\\])"
    r"(?P<key>`[^`\r\n]+`|\"[^\"\r\n]+\"|'[^'\r\n]+'|"
    r"[A-Za-z0-9][A-Za-z0-9._-]*"
    r"(?: [A-Za-z0-9][A-Za-z0-9._-]*){0,3})\s*:\s*(?P<value>.+)$",
    re.IGNORECASE,
)
_OPERATIONAL_DEFINITION_KEYS = frozenset(
    {
        "bash",
        "cli",
        "cmd",
        "command",
        "command line",
        "console",
        "powershell",
        "shell",
        "terminal",
    }
)
_SAFE_LINK_SCHEMES = frozenset({"", "http", "https"})
_RAW_MARKDOWN_LINK_SCHEME_RE = re.compile(
    r"\]\(\s*(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*):",
    re.IGNORECASE,
)
_SAFE_NAMED_SKILL_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)+")
_SAFE_REFERENCE_INLINE_RE = re.compile(
    r"(?:references|evals)/[A-Za-z0-9][A-Za-z0-9._-]{0,127}\."
    r"(?:md|txt|json|csv|ya?ml)",
    re.IGNORECASE,
)
_PROGRESSIVE_PATH_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9._/\\-])(?:references|evals)[/\\][^\s`'\"<>|]+",
    re.IGNORECASE,
)
_USE_EXECUTABLE_HELPER_RE = re.compile(
    r"\b(?:run|execute|invoke|use)\b\s+(?:the\s+|this\s+)?"
    r"(?:scripts?|helpers?|programs?|modules?)\s+(?:named\s+)?"
    r"(?<![A-Za-z0-9._/\\-])(?P<path>[A-Za-z0-9._/\\-]+\."
    r"(?:py|pyw|sh|bash|zsh|fish|ps1|bat|cmd|js|mjs|cjs|ts|tsx|jsx|rb|pl|"
    r"php|lua|exe|dll|scr|msi|jar))\b",
    re.IGNORECASE,
)
_INTERPRETER_COMMAND_RE = re.compile(
    r"\b(?:(?:py|python(?:3(?:\.\d+)?)?)(?:\.exe)?\s+-(?:c|m)\b|"
    r"node(?:\.exe)?\s+(?:-e|--eval)\b|(?:ruby|perl)(?:\.exe)?\s+-e\b|"
    r"php(?:\.exe)?\s+-r\b|(?:ba|z|fi)?sh(?:\.exe)?\s+-c\b|"
    r"(?:powershell|pwsh)(?:\.exe)?\s+-(?:command|encodedcommand|file)\b|"
    r"cmd(?:\.exe)?\s+/(?:c|k)\b)",
    re.IGNORECASE,
)
_MAX_RECONSTRUCTED_CODE_CHARS = 16 * 1024
_MAX_RECONSTRUCTION_ATTEMPTS = 1_024
_HTML_ENTITY_PREFIX_RE = re.compile(r"^&(?:#[0-9]+|#x[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]+);")


def is_verification_skill_name(name: str) -> bool:
    """Return whether a skill name declares the verification role contract."""
    tokens = name.casefold().split("-")
    return any(
        token.startswith(marker) for token in tokens for marker in _VERIFICATION_SKILL_NAME_MARKERS
    )


def registered_verifier_path_count(text: str) -> int:
    """Count raw or CommonMark-decoded helper-path mentions.

    ``max`` avoids double-counting ordinary visible references while still
    detecting entity-encoded text and path mentions hidden in Markdown syntax.
    """
    raw_count = text.casefold().count(VERIFY_ARTIFACT_SCRIPT_PATH.casefold())
    decoded_count = (
        commonmark_security_text(text).casefold().count(VERIFY_ARTIFACT_SCRIPT_PATH.casefold())
    )
    return max(raw_count, decoded_count)


def _contextual_command_violation(
    text: str,
    *,
    allow_registered: bool = True,
) -> str | None:
    """Reserve imperative run commands for the one registered verifier.

    Run, execute, and invoke at an instruction boundary are operational verbs
    consumed by downstream agents. Trying to infer whether their arguments are
    prose or an executable creates an open-ended command allowlist, so only the
    exact reviewed verifier invocation crosses this boundary.
    """
    for command_match in _COMMAND_START_RE.finditer(text):
        if is_inert_run_declaration(command_match.group("instruction").strip()):
            continue
        if (
            allow_registered
            and command_match.group("instruction").strip() == VERIFY_ARTIFACT_INVOCATION
        ):
            continue
        if command_match.group(
            "verb"
        ).casefold() == "run" and _command_grammar.is_declarative_run_noun_compound(
            command_match.group("command")
        ):
            continue
        return "unregistered run, execute, or invoke instruction"
    return None


def _secondary_command_violation(text: str) -> str | None:
    """Reject explicit launchers and executable paths under other verbs."""
    for command_match in _SECONDARY_COMMAND_RE.finditer(text):
        tokens = [
            token
            for raw_token in _command_grammar.FIRST_COMMAND_TOKEN_RE.findall(
                command_match.group("command")
            )
            if (token := _command_grammar.unwrap_command_token(raw_token))
        ]
        while tokens and tokens[0].casefold() in _command_grammar.COMMAND_DETERMINERS:
            tokens.pop(0)
        if not tokens:
            continue
        first = tokens[0]
        if first.casefold() == "when":
            continue
        initial_objects = {token.casefold() for token in tokens[:4]}
        if object_name := next(
            (token for token in initial_objects if token in _EXECUTABLE_COMMAND_OBJECTS),
            None,
        ):
            return f"explicit executable object: {object_name}"
        if first.casefold() == "helper" and any(
            token.replace("\\", "/").casefold().startswith("scripts/") for token in tokens[1:4]
        ):
            # The exact registered helper path is adjudicated below together
            # with all other scripts/ references, preserving its precise error.
            continue
        command = " ".join(tokens)
        if _command_grammar.looks_like_standalone_shell_command(
            command,
            case_sensitive_generic=False,
        ):
            return f"direct executable instruction: {first}"
    return None


def _visible_inline_text(token: Token) -> str:
    """Return decoded, formatting-free CommonMark inline text."""
    children = getattr(token, "children", None) or ()
    parts: list[str] = []
    for child in children:
        if child.type in {"text", "code_inline", "html_inline"}:
            parts.append(child.content)
        elif child.type in {"softbreak", "hardbreak"}:
            parts.append("\n")
    return "".join(parts)


def _decode_link_destination(destination: str) -> str:
    """Decode bounded percent-encoding layers in a CommonMark link target."""
    decoded = destination
    for _ in range(3):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    return decoded


def _decoded_link_destinations(token: Token) -> list[str]:
    """Return normalized destinations from an inline CommonMark token."""
    destinations: list[str] = []
    for child in token.children or ():
        if child.type != "link_open":
            continue
        destination = child.attrGet("href")
        if isinstance(destination, str) and destination:
            destinations.append(_decode_link_destination(destination))
    return destinations


def _decoded_link_titles(token: Token) -> list[str]:
    """Return decoded title metadata from an inline CommonMark token."""
    titles: list[str] = []
    for child in token.children or ():
        if child.type != "link_open":
            continue
        title = child.attrGet("title")
        if isinstance(title, str) and title:
            titles.append(_decode_link_destination(title))
    return titles


def _decoded_reference_metadata(env: dict[str, object]) -> list[tuple[str, str]]:
    """Return every CommonMark reference destination and title, used or not."""
    references = env.get("references")
    if not isinstance(references, dict):
        return []
    metadata: list[tuple[str, str]] = []
    for reference in references.values():
        if not isinstance(reference, dict):
            continue
        raw_destination = reference.get("href", "")
        raw_title = reference.get("title", "")
        destination = (
            _decode_link_destination(raw_destination) if isinstance(raw_destination, str) else ""
        )
        title = _decode_link_destination(raw_title) if isinstance(raw_title, str) else ""
        metadata.append((destination, title))
    return metadata


def commonmark_security_text(text: str) -> str:
    """Render decoded visible text and link metadata for security checks."""
    env: dict[str, object] = {}
    parts: list[str] = []
    for token in _COMMONMARK.parse(text, env):
        if token.type != "inline":
            continue
        parts.append(_visible_inline_text(token))
        parts.extend(_decoded_link_destinations(token))
        parts.extend(_decoded_link_titles(token))
    for destination, title in _decoded_reference_metadata(env):
        parts.extend(value for value in (destination, title) if value)
    return "\n".join(parts)


def _link_destination_value_violation(destination: str) -> str | None:
    """Reject one executable artifact or active URI destination."""
    try:
        parsed = urlsplit(destination)
    except ValueError:
        return "invalid Markdown link destination"
    if parsed.scheme.casefold() not in _SAFE_LINK_SCHEMES:
        return "only relative, HTTP, and HTTPS authored links are allowed"
    path = parsed.path.replace("\\", "/").rstrip("/")
    leaf = path.rsplit("/", 1)[-1]
    if _command_grammar.EXECUTABLE_SUFFIX_RE.search(leaf):
        return "executable Markdown link destination is not allowed"
    if ".." in path.split("/"):
        return f"unsafe progressive-disclosure path: {destination}"
    return None


def _link_destination_violation(token: Token) -> str | None:
    """Reject executable artifacts and active URI schemes in authored links."""
    for destination in _decoded_link_destinations(token):
        if violation := _link_destination_value_violation(destination):
            return violation
    return None


def _visible_command_candidates(text: str) -> list[str]:
    """Split decoded block text into normalized command-bearing cells."""
    raw_candidates = [text]
    if "|" in text:
        raw_candidates.extend(text.split("|"))
    candidates: list[str] = []
    for raw_candidate in raw_candidates:
        for sentence_candidate in re.split(r"(?<=[.!?;])\s+", raw_candidate):
            structural_candidate = sentence_candidate.lstrip(" \t#>*+-(")
            if not structural_candidate:
                continue
            candidates.append(structural_candidate)
            unquoted_candidate = structural_candidate.lstrip("\"'")
            if (
                unquoted_candidate != structural_candidate
                and _DEFINITION_LINE_RE.fullmatch(structural_candidate) is None
            ):
                candidates.append(unquoted_candidate)
    return list(dict.fromkeys(candidates))


def _looks_like_executable_code(fragment: str) -> bool:
    """Return whether a structurally isolated fragment contains active code."""
    candidate = fragment.strip()
    if not candidate:
        return False
    if contains_non_python_executable_fragment(candidate):
        return True
    try:
        tree = ast.parse(candidate, mode="exec")
    except (SyntaxError, ValueError, MemoryError):
        return False
    active_expression_nodes = (
        ast.Await,
        ast.Call,
        ast.DictComp,
        ast.GeneratorExp,
        ast.Lambda,
        ast.ListComp,
        ast.NamedExpr,
        ast.SetComp,
        ast.Yield,
        ast.YieldFrom,
    )
    if tree.body and all(
        isinstance(statement, ast.AnnAssign)
        and statement.value is None
        and isinstance(statement.target, ast.Name)
        and not any(
            isinstance(node, active_expression_nodes) for node in ast.walk(statement.annotation)
        )
        for statement in tree.body
    ):
        # Markdown labels such as ``Company: ExampleCo`` and
        # ``URL: not provided`` are syntactically valid Python annotations but
        # contain no active expression or assignment.
        return False
    if any(not isinstance(statement, ast.Expr) for statement in tree.body):
        return True
    return any(isinstance(node, active_expression_nodes) for node in ast.walk(tree))


def _plain_text_executable_fragment(text: str) -> str | None:
    """Detect code hidden in plain lines or Markdown table cells."""
    if fragment := find_non_python_executable_fragment(text):
        return fragment
    logical_lines: list[tuple[str, bool]] = []
    continued = ""
    used_shell_continuation = False
    for raw_line in text.splitlines():
        stripped_right = raw_line.rstrip()
        trailing_carets = len(stripped_right) - len(stripped_right.rstrip("^"))
        shell_continuation = (
            stripped_right.endswith("\\")
            or (stripped_right.endswith("`") and stripped_right.count("`") % 2 == 1)
            or trailing_carets % 2 == 1
        )
        if shell_continuation:
            continued += stripped_right[:-1] + " "
            used_shell_continuation = True
            if len(continued) > _MAX_RECONSTRUCTED_CODE_CHARS:
                return continued[:80]
            continue
        logical_lines.append(
            (continued + raw_line.lstrip() if continued else raw_line, used_shell_continuation)
        )
        continued = ""
        used_shell_continuation = False
    if continued:
        return continued[:80]

    for raw_line, reconstructed_shell_line in logical_lines:
        line = raw_line.strip()
        if _command_grammar.SHELL_OPERATOR_COMMAND_RE.match(line):
            return line
        if reconstructed_shell_line and _command_grammar.looks_like_standalone_shell_command(
            line, case_sensitive_generic=False
        ):
            return line
        for candidate in _visible_command_candidates(line):
            if candidate.strip() == VERIFY_ARTIFACT_INVOCATION:
                continue
            definition = _DEFINITION_LINE_RE.match(candidate)
            shell_candidate = definition.group("value") if definition else candidate
            if contains_machine_execution_instruction(candidate.strip()) or (
                definition
                and contains_machine_execution_instruction(definition.group("value").strip())
            ):
                return candidate
            operational_definition = bool(
                definition
                and _command_grammar.unwrap_command_token(definition.group("key")).casefold()
                in _OPERATIONAL_DEFINITION_KEYS
            )
            if _command_grammar.looks_like_standalone_shell_command(
                shell_candidate,
                case_sensitive_generic=not operational_definition,
                allow_path_command=definition is None or operational_definition,
            ):
                return candidate
        if _looks_like_executable_code(line):
            return line
        if "|" not in line:
            continue
        for cell in line.split("|"):
            if contains_machine_execution_instruction(cell.strip()):
                return cell.strip()
            if _looks_like_executable_code(cell):
                return cell.strip()
    return None


def _multiline_executable_fragment(text: str) -> str | None:
    """Reconstruct active code split across decoded CommonMark blocks.

    ``compile_command`` distinguishes an incomplete Python construct from a
    permanently invalid prose line. Each start position therefore advances
    only while syntax is incomplete, avoiding the former cubic window search.
    """
    lines = text.splitlines()
    if len(lines) < 2:
        return None
    attempts = 0
    for start, line in enumerate(lines[:-1]):
        stripped = line.strip()
        if not stripped:
            continue
        candidate_lines: list[str] = []
        candidate_chars = 0
        for end in range(start, len(lines)):
            candidate_chars += len(lines[end]) + 1
            if candidate_chars > _MAX_RECONSTRUCTED_CODE_CHARS:
                return stripped
            candidate_lines.append(lines[end])
            candidate = "\n".join(candidate_lines).strip()
            attempts += 1
            if attempts > _MAX_RECONSTRUCTION_ATTEMPTS:
                return stripped
            try:
                compiled = codeop.compile_command(candidate, symbol="exec")
            except (OverflowError, SyntaxError, ValueError):
                break
            if compiled is None:
                continue
            if _looks_like_executable_code(candidate):
                return candidate
            break
    return None


def _unsafe_progressive_path(text: str) -> str | None:
    """Return a non-canonical authored reference/eval path, if present."""
    for match in _PROGRESSIVE_PATH_TOKEN_RE.finditer(text):
        candidate = match.group(0).rstrip(".,;:!?)]}")
        if _SAFE_REFERENCE_INLINE_RE.fullmatch(candidate) is None:
            return candidate
    return None


def _scan_textual_executable_patterns(text: str) -> str | None:
    """Apply semantic-free text checks to raw or CommonMark-decoded prose."""
    machine_text = "\n".join(
        line for line in text.splitlines() if line.strip() != VERIFY_ARTIFACT_INVOCATION
    )
    if contains_machine_execution_instruction(machine_text.strip()):
        return "machine-readable execution instruction"
    if _TERMINAL_INSTRUCTION_RE.search(text):
        return "explicit terminal or shell instruction"
    if fragment := _plain_text_executable_fragment(text):
        return f"executable code fragment: {fragment[:80]}"
    if interpreter_command := _INTERPRETER_COMMAND_RE.search(text):
        return f"direct interpreter command: {interpreter_command.group(0)}"

    if contains_executable_materialization(text):
        return "instruction to materialize model-authored executable code"

    if unsafe_path := _unsafe_progressive_path(text):
        return f"unsafe progressive-disclosure path: {unsafe_path}"
    candidates = [match.group(0) for match in _EXECUTABLE_PATH_RE.finditer(text)]
    if command_violation := _contextual_command_violation(text):
        return command_violation
    if command_violation := _secondary_command_violation(text):
        return command_violation
    candidates.extend(match.group("path") for match in _USE_EXECUTABLE_HELPER_RE.finditer(text))
    for candidate in candidates:
        if candidate.casefold() != VERIFY_ARTIFACT_SCRIPT_PATH.casefold():
            return f"unregistered executable path: {candidate}"
    return None


def _inline_children_violation(
    children: list[Token],
    *,
    registered_top_level: bool,
) -> str | None:
    """Validate raw HTML, images, and inline-code children."""
    for index, child in enumerate(children):
        if child.type == "image":
            return "images are not allowed in authored instruction prose"
        if child.type == "html_inline" and (
            child.content != "<artifact>" or not registered_top_level
        ):
            return "raw inline HTML is allowed only in the registered verifier invocation"
        if child.type != "code_inline":
            continue
        previous = (
            children[index - 1].content if index and children[index - 1].type == "text" else ""
        )
        following = (
            children[index + 1].content
            if index + 1 < len(children) and children[index + 1].type == "text"
            else ""
        )
        named_skill = bool(
            _SAFE_NAMED_SKILL_RE.fullmatch(child.content)
            and re.match(r"^\s+skill\b", following, re.IGNORECASE)
        )
        safe_reference = _SAFE_REFERENCE_INLINE_RE.fullmatch(child.content) is not None
        if named_skill or safe_reference:
            continue
        if any(character.isspace() for character in child.content):
            return "multi-token inline code is not allowed in authored prose"
        if _command_grammar.SHELL_METACHAR_RE.search(child.content) or _looks_like_executable_code(
            child.content
        ):
            return "executable inline code is not allowed in authored prose"
        if _INLINE_COMMAND_CONTEXT_RE.search(previous):
            return "inline token in executable command context"
    return None


def scan_authored_executable_instructions(text: str) -> str | None:
    """Reject executable payloads or helper materialization in authored prose.

    Skill bodies and references are instructions consumed by another agent.
    Allowing a model to place executable code there would bypass the exact
    first-party helper registry even when no ``scripts/*.py`` companion is
    present. Runtime artifact generation remains supported, but generated
    skill prose cannot contain executable-language fences, direct an agent to
    materialize an inline payload, or name an unregistered executable file.
    """
    if not text:
        return None
    for match in _RAW_MARKDOWN_LINK_SCHEME_RE.finditer(text):
        if match.group("scheme").casefold() not in _SAFE_LINK_SCHEMES:
            return "only relative, HTTP, and HTTPS authored links are allowed"
    for raw_line in text.splitlines():
        stripped_line = raw_line.strip()
        if _command_grammar.SHELL_OPERATOR_COMMAND_RE.match(
            stripped_line
        ) and not _HTML_ENTITY_PREFIX_RE.match(stripped_line):
            return f"executable code fragment: {stripped_line[:80]}"
    raw_machine_text = "\n".join(
        line for line in text.splitlines() if line.strip() != VERIFY_ARTIFACT_INVOCATION
    )
    if contains_machine_execution_instruction(raw_machine_text):
        return "machine-readable execution instruction"
    env: dict[str, object] = {}
    tokens = _COMMONMARK.parse(text, env)
    rendered_blocks: list[str] = []
    for destination, title in _decoded_reference_metadata(env):
        if destination and (reference_violation := _link_destination_value_violation(destination)):
            return reference_violation
        if title:
            rendered_blocks.append(title)
    for token_index, token in enumerate(tokens):
        if token.type == "fence":
            return "fenced code block is not allowed in authored prose"
        if token.type == "code_block":
            return "indented code block is not allowed in authored prose"
        if token.type == "html_block":
            return "raw HTML block is not allowed in authored prose"
        if token.type == "inline":
            visible_text = _visible_inline_text(token)
            rendered_blocks.append(visible_text)
            rendered_blocks.extend(_decoded_link_titles(token))
            if link_violation := _link_destination_violation(token):
                return link_violation
            previous_token = tokens[token_index - 1] if token_index else None
            registered_top_level = bool(
                token.level == 1
                and previous_token is not None
                and previous_token.type == "paragraph_open"
                and previous_token.level == 0
                and token.content == VERIFY_ARTIFACT_INVOCATION
            )
            if "<artifact>" in visible_text.casefold() and not registered_top_level:
                return "artifact placeholder is allowed only in the registered verifier invocation"
            for candidate in _visible_command_candidates(visible_text):
                if command_violation := _contextual_command_violation(
                    candidate,
                    allow_registered=(
                        registered_top_level and candidate == VERIFY_ARTIFACT_INVOCATION
                    ),
                ):
                    return command_violation
            for inline_text in dict.fromkeys((token.content, visible_text)):
                if fragment := _multiline_executable_fragment(inline_text):
                    return f"multiline executable code fragment: {fragment[:80]}"
            if child_violation := _inline_children_violation(
                list(token.children or ()),
                registered_top_level=registered_top_level,
            ):
                return child_violation
    rendered_text = "\n".join(rendered_blocks)
    if fragment := _multiline_executable_fragment(rendered_text):
        return f"multiline executable code fragment: {fragment[:80]}"
    if violation := _scan_textual_executable_patterns(rendered_text):
        return violation
    return None


def _top_level_block_line_indices(
    text: str,
    *,
    token_type: str,
    raw_line: str,
    tag: str | None = None,
) -> list[int]:
    """Locate exact, visible CommonMark blocks at document level.

    Token levels distinguish ordinary top-level blocks from visually similar
    content nested in lists or block quotes. Requiring the exact source line
    also excludes alternate Markdown syntax and inline markup that happens to
    render to the same text.
    """
    lines = text.splitlines()
    indices: list[int] = []
    for token in _COMMONMARK.parse(text):
        if token.type != token_type or token.level != 0 or token.map is None:
            continue
        if tag is not None and token.tag != tag:
            continue
        start, end = token.map
        if end != start + 1 or start >= len(lines) or lines[start].strip() != raw_line:
            continue
        indices.append(start)
    return indices


def has_registered_verifier_invocation(body: str) -> bool:
    """Return whether the exact invocation appears once in unfenced workflow prose."""
    lines = body.splitlines()
    if sum(line.strip() == VERIFY_ARTIFACT_INVOCATION for line in lines) != 1:
        return False
    if registered_verifier_path_count(body) != 1:
        return False
    workflow_indices = _top_level_block_line_indices(
        body,
        token_type="heading_open",
        tag="h2",
        raw_line="## Workflow",
    )
    invocation_indices = _top_level_block_line_indices(
        body,
        token_type="paragraph_open",
        raw_line=VERIFY_ARTIFACT_INVOCATION,
    )
    output_indices = _top_level_block_line_indices(
        body,
        token_type="heading_open",
        tag="h2",
        raw_line="## Output Format",
    )
    if not (len(workflow_indices) == len(invocation_indices) == len(output_indices) == 1):
        return False
    workflow_index = workflow_indices[0]
    invocation_index = invocation_indices[0]
    output_index = output_indices[0]
    return workflow_index < invocation_index < output_index


def insert_registered_verifier_invocation(body: str) -> str:
    """Insert the registered invocation before the unfenced output heading."""
    lines = [line for line in body.splitlines() if line.strip() != VERIFY_ARTIFACT_INVOCATION]
    body_without_invocation = "\n".join(lines)
    workflow_indices = _top_level_block_line_indices(
        body_without_invocation,
        token_type="heading_open",
        tag="h2",
        raw_line="## Workflow",
    )
    output_indices = _top_level_block_line_indices(
        body_without_invocation,
        token_type="heading_open",
        tag="h2",
        raw_line="## Output Format",
    )
    if len(workflow_indices) != 1 or len(output_indices) != 1:
        raise ValueError("verification body must have one unfenced workflow and output section")
    if workflow_indices[0] >= output_indices[0]:
        raise ValueError("verification body sections are out of order")
    output_index = output_indices[0]
    lines[output_index:output_index] = [VERIFY_ARTIFACT_INVOCATION, ""]
    result = "\n".join(lines)
    if not has_registered_verifier_invocation(result):
        raise ValueError("verification invocation could not be inserted safely")
    return result


def scan_python_script(relpath: str, content: str) -> str | None:
    """Reject every helper except an exact registered first-party artifact."""
    if relpath != VERIFY_ARTIFACT_SCRIPT_PATH:
        return "path is not registered as a first-party helper"
    if content != VERIFY_ARTIFACT_SCRIPT:
        return "content does not match the registered first-party helper"
    return None


__all__ = [
    "VERIFY_ARTIFACT_INVOCATION",
    "VERIFY_ARTIFACT_SCRIPT",
    "VERIFY_ARTIFACT_SCRIPT_PATH",
    "commonmark_security_text",
    "has_registered_verifier_invocation",
    "insert_registered_verifier_invocation",
    "is_verification_skill_name",
    "registered_verifier_path_count",
    "scan_authored_executable_instructions",
    "scan_python_script",
]
