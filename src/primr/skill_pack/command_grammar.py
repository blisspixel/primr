"""Conservative command-line grammar for generated instruction prose.

This module recognizes concrete executable shapes without treating ordinary
business prose as a command merely because its first word is also a utility,
language, or PowerShell-like compound.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

FIRST_COMMAND_TOKEN_RE = re.compile(r"`[^`\r\n]*`|\"[^\"\r\n]*\"|'[^'\r\n]*'|\S+")
COMMAND_DETERMINERS = frozenset({"a", "an", "our", "the", "their", "this", "those", "your"})
_PREFIX_SEPARATOR = r"(?:\s*(?:,|->|=>|:|-|\u2013|\u2014|\()\s*|\s+)"
COMMAND_INSTRUCTION_PREFIX_PATTERN = (
    rf"(?:(?:please|then|next|now|finally|always|first)\b{_PREFIX_SEPARATOR}|"
    rf"after\s+that\b{_PREFIX_SEPARATOR}|be\s+sure\s+to\s+|can\s+you\s+|"
    r"(?:could|would)\s+you\s+|kindly\s+|"
    r"(?:you|it|the\s+agent|agents?)\s+"
    r"(?:can|must|shall|should|will|need(?:s)?\s+to)\s+(?:always\s+)?|"
    r"(?:ask|direct|have|instruct|tell)\s+(?:the\s+)?agent\s+(?:to\s+)?|"
    r"we\s+need\s+you\s+to\s+|"
    rf"to\s+continue\b{_PREFIX_SEPARATOR}|proceed\s+with\s+|"
    r"download(?:\s+the\s+payload)?\s+(?:with|using)\s+)"
)
EXECUTABLE_SUFFIX_RE = re.compile(
    r"\.(?:py|pyw|sh|bash|zsh|fish|ps1|bat|cmd|js|mjs|cjs|ts|tsx|jsx|rb|pl|"
    r"php|lua|r|vbs|exe|dll|scr|msi|jar)$",
    re.IGNORECASE,
)
SHELL_METACHAR_RE = re.compile(
    r"(?:\|\||&&|[|;]|\$\(|(?<![=-])>{1,2}(?!=)|(?<![=-])<(?![=-])|\r|\n)"
)
SHELL_OPERATOR_COMMAND_RE = re.compile(r"^(?:&\s*(?:\{|\S)|\.\s+|\$\(|<\(|>{1,2}(?=\S)|:\s*>{1,2})")
KNOWN_EXECUTION_LAUNCHER_RE = re.compile(
    r"^(?:py|python(?:3(?:\.\d+)?)?|node|deno|bun|ruby|perl|php|java|dotnet|"
    r"cmd|cscript|wscript|rscript|pwsh|powershell|bash|csh|dash|ksh|tcsh|zsh|fish|sh|"
    r"go|groovy|julia|lua|luajit|r|swift|mshta|"
    r"osascript|rundll32|regsvr32|certutil|bitsadmin|env|uv|npx|pnpx|pnpm|"
    r"yarn|pipx)(?:\.exe)?$",
    re.IGNORECASE,
)
PATH_SHAPED_COMMAND_RE = re.compile(r"^(?:[A-Za-z]:[/\\]|[/\\]{1,2}|\.{1,2}[/\\])")

_SHELL_COMMAND_NAMES = frozenset(
    {
        "base64",
        "call",
        "cat",
        "chmod",
        "chown",
        "copy",
        "cp",
        "curl",
        "del",
        "echo",
        "erase",
        "eval",
        "exec",
        "iex",
        "irm",
        "iwr",
        "kill",
        "killall",
        "ln",
        "md",
        "mkdir",
        "move",
        "mv",
        "nc",
        "ncat",
        "nice",
        "nohup",
        "printf",
        "rd",
        "ren",
        "rm",
        "rmdir",
        "robocopy",
        "reboot",
        "rsync",
        "scp",
        "setsid",
        "shutdown",
        "socat",
        "ssh",
        "saps",
        "start",
        "tee",
        "touch",
        "type",
        "timeout",
        "wget",
        "xcopy",
        "xargs",
    }
)
_POSITIONAL_COMMAND_NAMES = frozenset(
    {
        "aws",
        "apt",
        "apt-get",
        "az",
        "brew",
        "bundle",
        "cargo",
        "cd",
        "choco",
        "composer",
        "dir",
        "dnf",
        "docker",
        "gcloud",
        "gh",
        "git",
        "gradle",
        "helm",
        "kubectl",
        "make",
        "mvn",
        "net",
        "npm",
        "oc",
        "pip",
        "podman",
        "poetry",
        "reg",
        "scoop",
        "service",
        "systemctl",
        "terraform",
        "winget",
        "yum",
    }
)
_NO_ARGUMENT_COMMAND_NAMES = frozenset(
    {"dir", "hostname", "id", "ipconfig", "ls", "pwd", "uname", "ver", "whoami"}
)
_CASE_INSENSITIVE_COMMAND_NAMES = frozenset(
    {
        "call",
        "copy",
        "del",
        "echo",
        "erase",
        "iex",
        "irm",
        "iwr",
        "md",
        "mkdir",
        "move",
        "rd",
        "ren",
        "rmdir",
        "robocopy",
        "saps",
        "start",
        "type",
        "xcopy",
    }
)
_ARGUMENT_SHAPE_REQUIRED_COMMAND_NAMES = frozenset({"curl", "wget"})
_COMMAND_WRAPPERS = frozenset({"command", "doas", "sudo"})
_INSTRUCTION_PREFIX_RE = re.compile(rf"^{COMMAND_INSTRUCTION_PREFIX_PATTERN}", re.IGNORECASE)
_POWERSHELL_VERBS = frozenset(
    {
        "add",
        "clear",
        "connect",
        "convert",
        "copy",
        "disable",
        "disconnect",
        "enable",
        "enter",
        "exit",
        "export",
        "find",
        "format",
        "get",
        "grant",
        "import",
        "initialize",
        "install",
        "invoke",
        "join",
        "measure",
        "mount",
        "move",
        "new",
        "open",
        "out",
        "protect",
        "publish",
        "read",
        "receive",
        "register",
        "remove",
        "rename",
        "repair",
        "request",
        "reset",
        "resolve",
        "restart",
        "restore",
        "resume",
        "revoke",
        "save",
        "search",
        "select",
        "send",
        "set",
        "show",
        "split",
        "start",
        "stop",
        "submit",
        "suspend",
        "sync",
        "test",
        "trace",
        "unblock",
        "uninstall",
        "unprotect",
        "unpublish",
        "unregister",
        "update",
        "use",
        "wait",
        "write",
    }
)
_GO_RUN_RE = re.compile(r"^go\s+run\b")
_COMMAND_OPTION_RE = re.compile(r"^(?:--?[A-Za-z]|/[A-Za-z])")
_COMMAND_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S+$")
_FILE_ARGUMENT_RE = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z][A-Za-z0-9]{0,15}(?:,\S+)?$")
_RUN_NOUN_COMPOUNDS = frozenset({"rate", "time"})
_IMPERATIVE_PROSE_CONNECTORS = frozenset(
    {"by", "for", "from", "in", "into", "of", "on", "to", "with"}
)
_BUSINESS_ACTION_OBJECTS = frozenset(
    {"account", "evidence", "findings", "intake", "owner", "questions", "requirements", "scope"}
)
_DECLARATIVE_PREDICATES = frozenset(
    {
        "are",
        "can",
        "define",
        "defines",
        "depend",
        "depends",
        "drive",
        "drives",
        "favor",
        "favors",
        "guide",
        "guides",
        "handle",
        "handles",
        "improve",
        "improves",
        "inform",
        "informs",
        "integrate",
        "integrates",
        "is",
        "may",
        "must",
        "read",
        "reads",
        "reduce",
        "reduces",
        "remain",
        "remains",
        "require",
        "requires",
        "should",
        "support",
        "supports",
        "use",
        "uses",
        "vary",
        "varies",
        "will",
        "run",
        "runs",
    }
)


def unwrap_command_token(token: str) -> str:
    """Remove ordinary Markdown/shell quoting and sentence punctuation."""
    if token.strip() in {".", ".."}:
        return token.strip()
    token = token.strip().rstrip(".,;:!?)]}")
    wrappers = (("**", "**"), ("__", "__"), ("*", "*"), ("_", "_"))
    changed = True
    while changed and token:
        changed = False
        if len(token) >= 2 and token[0] == token[-1] and token[0] in {'"', "'", "`"}:
            token = token[1:-1]
            changed = True
        for opening, closing in wrappers:
            if (
                len(token) > len(opening) + len(closing)
                and token.startswith(opening)
                and token.endswith(closing)
            ):
                token = token[len(opening) : -len(closing)]
                changed = True
                break
    return token.rstrip(".,;:!?)]}")


def _has_command_shaped_argument(tokens: list[str], candidate: str) -> bool:
    if SHELL_METACHAR_RE.search(candidate):
        return True
    for token in tokens[1:]:
        if (
            _COMMAND_OPTION_RE.match(token)
            or PATH_SHAPED_COMMAND_RE.match(token)
            or EXECUTABLE_SUFFIX_RE.search(token)
            or _FILE_ARGUMENT_RE.fullmatch(token)
            or _COMMAND_ASSIGNMENT_RE.fullmatch(token)
        ):
            return True
        try:
            if urlsplit(token).scheme.casefold() in {"http", "https"}:
                return True
        except ValueError:
            return True
    return False


def _is_powershell_cmdlet(token: str) -> bool:
    verb, separator, noun = token.partition("-")
    return bool(
        separator
        and verb.casefold() in _POWERSHELL_VERBS
        and noun
        and noun[0].isupper()
        and noun.replace("-", "").isalnum()
    )


def _decode_ansi_c_escape(candidate: str, index: int) -> tuple[str, int]:
    """Decode one bounded Bash ANSI-C escape beginning at ``index``."""
    if index + 1 >= len(candidate):
        return "\\", index
    escape = candidate[index + 1]
    simple = {
        "a": "\a",
        "b": "\b",
        "e": "\x1b",
        "E": "\x1b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "t": "\t",
        "v": "\v",
        "\\": "\\",
        "'": "'",
        '"': '"',
    }
    if escape in simple:
        return simple[escape], index + 1
    if escape in "01234567":
        end = index + 2
        while end < len(candidate) and end < index + 4 and candidate[end] in "01234567":
            end += 1
        return chr(int(candidate[index + 1 : end], 8)), end - 1
    hexadecimal_width = {"x": 2, "u": 4, "U": 8}.get(escape)
    if hexadecimal_width is not None:
        start = index + 2
        end = start
        while (
            end < len(candidate)
            and end < start + hexadecimal_width
            and candidate[end] in "0123456789abcdefABCDEF"
        ):
            end += 1
        if end > start:
            try:
                return chr(int(candidate[start:end], 16)), end - 1
            except ValueError:
                return "", end - 1
    return escape, index + 1


def _decode_shell_command_word(candidate: str) -> tuple[str, bool] | None:
    """Decode standard shell quoting and report obfuscating command syntax."""
    decoded: list[str] = []
    quote: str | None = None
    ansi_c_quote = False
    changed = False
    shell_syntax = False
    index = 0
    while index < len(candidate):
        character = candidate[index]
        if quote is not None:
            if character == quote:
                quote = None
                ansi_c_quote = False
                changed = True
                if index + 1 < len(candidate) and not candidate[index + 1].isspace():
                    shell_syntax = True
            elif ansi_c_quote and character == "\\":
                escaped, index = _decode_ansi_c_escape(candidate, index)
                decoded.append(escaped)
                changed = True
            elif quote == '"' and character == "\\" and index + 1 < len(candidate):
                index += 1
                decoded.append(candidate[index])
                changed = True
            else:
                decoded.append(character)
            index += 1
            continue
        if character.isspace():
            break
        if character == "$" and index + 1 < len(candidate) and candidate[index + 1] in {'"', "'"}:
            changed = True
            shell_syntax = True
            index += 1
            quote = candidate[index]
            ansi_c_quote = quote == "'"
        elif character in {'"', "'"}:
            quote = character
            changed = True
            shell_syntax = shell_syntax or bool(decoded)
        elif (
            character in {"\\", "^"}
            or (
                character == "`"
                and index + 1 < len(candidate)
                and not candidate[index + 1].isspace()
                and (index > 0 or "`" not in candidate[index + 1 :].split(maxsplit=1)[0])
            )
        ) and index + 1 < len(candidate):
            index += 1
            escaped = candidate[index]
            if escaped == "\r" and index + 1 < len(candidate) and candidate[index + 1] == "\n":
                index += 1
            elif escaped != "\n":
                decoded.append(escaped)
            changed = True
            shell_syntax = True
        else:
            decoded.append(character)
        index += 1
    if quote is not None or not changed:
        return None
    return "".join(decoded), shell_syntax


def _is_known_command_name(token: str) -> bool:
    token_casefold = token.casefold()
    return bool(
        token_casefold in _SHELL_COMMAND_NAMES
        or token_casefold in _POSITIONAL_COMMAND_NAMES
        or token_casefold in _NO_ARGUMENT_COMMAND_NAMES
        or token_casefold in _COMMAND_WRAPPERS
        or KNOWN_EXECUTION_LAUNCHER_RE.fullmatch(token)
        or _is_powershell_cmdlet(token)
    )


def _is_sentence_case_command_prose(
    first: str,
    tokens: list[str],
    candidate: str,
    *,
    argument_shape: bool,
) -> bool:
    """Recognize declarative prose headed by an ambiguous product or utility."""
    if not first or not first[0].isupper():
        return False
    powershell_cmdlet = _is_powershell_cmdlet(first)
    first_casefold = first.casefold()
    if not (
        first_casefold == "node.js"
        or first_casefold in _SHELL_COMMAND_NAMES
        or KNOWN_EXECUTION_LAUNCHER_RE.fullmatch(first)
        or powershell_cmdlet
    ):
        return False
    if first_casefold == "node.js" and len(tokens) > 1 and tokens[1].casefold() == "with":
        return True
    following_words = [
        word for token in tokens[1:5] for word in re.findall(r"[A-Za-z]+", token.casefold())
    ]
    leading_argument_shape = _has_command_shaped_argument(
        tokens[:2],
        " ".join(tokens[:2]),
    )
    if argument_shape and (
        first_casefold in _CASE_INSENSITIVE_COMMAND_NAMES
        or powershell_cmdlet
        or leading_argument_shape
    ):
        return False
    if first_casefold not in _CASE_INSENSITIVE_COMMAND_NAMES and any(
        word in _DECLARATIVE_PREDICATES for word in following_words
    ):
        return True
    if argument_shape:
        return False
    if (
        first_casefold in _CASE_INSENSITIVE_COMMAND_NAMES
        and len(tokens) >= 4
        and any(word in _IMPERATIVE_PROSE_CONNECTORS for word in following_words)
    ):
        return True
    if (
        first_casefold in _CASE_INSENSITIVE_COMMAND_NAMES
        and candidate.rstrip().endswith((".", "!", "?"))
        and (
            (len(tokens) > 1 and tokens[1].casefold() in COMMAND_DETERMINERS)
            or any(word in _BUSINESS_ACTION_OBJECTS for word in following_words)
        )
    ):
        return True
    return any(word in _DECLARATIVE_PREDICATES for word in following_words)


def is_declarative_run_noun_compound(command: str) -> bool:
    """Distinguish business noun compounds such as run rate and run time."""
    tokens = [
        token
        for raw_token in FIRST_COMMAND_TOKEN_RE.findall(command)
        if (token := unwrap_command_token(raw_token))
    ]
    if (
        not tokens
        or tokens[0].casefold() not in _RUN_NOUN_COMPOUNDS
        or _has_command_shaped_argument(tokens, command)
    ):
        return False
    words = re.findall(r"[A-Za-z]+", command.casefold())
    return any(word in _DECLARATIVE_PREDICATES for word in words[1:])


def looks_like_standalone_shell_command(
    candidate: str,
    *,
    case_sensitive_generic: bool = True,
    allow_path_command: bool = True,
) -> bool:
    """Recognize high-signal standalone shell command grammar."""
    candidate = candidate.strip()
    instruction_prefix = False
    for _ in range(4):
        prefix_match = _INSTRUCTION_PREFIX_RE.match(candidate)
        if prefix_match is None:
            break
        instruction_prefix = True
        candidate = candidate[prefix_match.end() :].lstrip()
    if instruction_prefix:
        case_sensitive_generic = False
    tokens = [
        token
        for raw_token in FIRST_COMMAND_TOKEN_RE.findall(candidate)
        if (token := unwrap_command_token(raw_token))
    ]
    if not tokens:
        return False
    shell_escaped_command = False
    decoded_first = _decode_shell_command_word(candidate)
    if decoded_first is not None and _is_known_command_name(decoded_first[0]):
        tokens[0] = decoded_first[0]
        shell_escaped_command = decoded_first[1]
    wrapped = False
    while (
        len(tokens) > 1
        and tokens[0].casefold() in _COMMAND_WRAPPERS
        and (tokens[0] == tokens[0].casefold() or not case_sensitive_generic)
    ):
        wrapped = True
        tokens.pop(0)
    first = tokens[0]
    try:
        if urlsplit(first).scheme.casefold() in {"http", "https"}:
            return False
    except ValueError:
        pass
    command_text = " ".join(tokens)
    if wrapped:
        return True
    if shell_escaped_command:
        return True
    argument_shape = _has_command_shaped_argument(tokens, command_text)
    if _is_sentence_case_command_prose(
        first,
        tokens,
        candidate,
        argument_shape=argument_shape,
    ):
        return False
    if KNOWN_EXECUTION_LAUNCHER_RE.fullmatch(first) and len(tokens) == 1:
        return True
    if (
        _GO_RUN_RE.match(command_text)
        or SHELL_OPERATOR_COMMAND_RE.match(command_text)
        or _is_powershell_cmdlet(first)
        or EXECUTABLE_SUFFIX_RE.search(first)
        or (allow_path_command and PATH_SHAPED_COMMAND_RE.match(first))
    ):
        return True
    if KNOWN_EXECUTION_LAUNCHER_RE.fullmatch(first):
        return bool(
            argument_shape or wrapped or not case_sensitive_generic or first == first.casefold()
        )
    first_casefold = first.casefold()
    if first_casefold in _NO_ARGUMENT_COMMAND_NAMES and len(tokens) == 1:
        return bool(not case_sensitive_generic or first == first_casefold)
    if first_casefold in _POSITIONAL_COMMAND_NAMES and len(tokens) > 1:
        return bool(not case_sensitive_generic or first == first_casefold)
    if first_casefold in _SHELL_COMMAND_NAMES:
        if first_casefold in _ARGUMENT_SHAPE_REQUIRED_COMMAND_NAMES:
            return bool(argument_shape or wrapped or not case_sensitive_generic)
        return bool(
            argument_shape
            or wrapped
            or not case_sensitive_generic
            or first == first_casefold
            or first_casefold in _CASE_INSENSITIVE_COMMAND_NAMES
        )
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", first):
        return False
    if (
        case_sensitive_generic and first != first.casefold()
    ) or first.casefold() in COMMAND_DETERMINERS:
        return False
    return argument_shape


__all__ = [
    "COMMAND_DETERMINERS",
    "COMMAND_INSTRUCTION_PREFIX_PATTERN",
    "EXECUTABLE_SUFFIX_RE",
    "FIRST_COMMAND_TOKEN_RE",
    "KNOWN_EXECUTION_LAUNCHER_RE",
    "PATH_SHAPED_COMMAND_RE",
    "SHELL_METACHAR_RE",
    "SHELL_OPERATOR_COMMAND_RE",
    "is_declarative_run_noun_compound",
    "looks_like_standalone_shell_command",
    "unwrap_command_token",
]
