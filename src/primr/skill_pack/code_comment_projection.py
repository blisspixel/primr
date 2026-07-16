"""Language-aware comment projection for untrusted fenced code."""

from __future__ import annotations

import ast
import io
import re
import tokenize

_PYTHON_TRIPLE_STRING_RE = re.compile(r"^(?:[rubf]{0,3})(?P<quote>'''|\"\"\")", re.IGNORECASE)
_RUBY_PERCENT_QUOTE_RE = re.compile(r"%(?:q|Q)?(?P<delimiter>[{[(<])")
_PERL_QUOTE_RE = re.compile(r"(?<![A-Za-z0-9_])(?:q|qq|qw|qx)(?P<delimiter>[{[(<])")
_PAIRED_DELIMITERS = {"{": "}", "[": "]", "(": ")", "<": ">"}
_RUBY_BLOCK_START_RE = re.compile(r"^=begin\b")
_RUBY_BLOCK_END_RE = re.compile(r"^=end\b")
_PERL_POD_START_RE = re.compile(
    r"^=(?:begin|encoding|for|head[1-6]|item|over|pod)\b", re.IGNORECASE
)
_PERL_POD_END_RE = re.compile(r"^=cut\b", re.IGNORECASE)
CODE_FENCE_LANGUAGES = frozenset(
    {
        "bash",
        "bat",
        "c",
        "c#",
        "c++",
        "cmd",
        "cpp",
        "csharp",
        "css",
        "dockerfile",
        "fish",
        "go",
        "hcl",
        "html",
        "java",
        "javascript",
        "js",
        "json",
        "jsx",
        "kotlin",
        "lua",
        "makefile",
        "php",
        "perl",
        "powershell",
        "pwsh",
        "py",
        "python",
        "r",
        "rb",
        "ruby",
        "rust",
        "scss",
        "sh",
        "shell",
        "sql",
        "swift",
        "terraform",
        "tf",
        "toml",
        "ts",
        "tsx",
        "typescript",
        "xml",
        "yaml",
        "yml",
        "zsh",
    }
)
_ADJACENT_HASH_COMMENT_LANGUAGES = frozenset({"makefile", "perl", "r", "rb", "ruby", "toml"})
_CODE_COMMENT_LINE_RE = re.compile(r"^\s*(?:#|//|--|;)\s?(.*?)\s*$")
_CODE_BLOCK_COMMENT_RE = re.compile(
    r"/\*(.*?)(?:\*/|$)|<!--(.*?)(?:-->|$)|<#(.*?)(?:#>|$)",
    re.DOTALL,
)
_PYTHON_COMMENT_LANGUAGES = frozenset({"py", "python"})
_C_STYLE_COMMENT_LANGUAGES = frozenset(
    {
        "c",
        "c#",
        "c++",
        "cpp",
        "csharp",
        "css",
        "go",
        "java",
        "javascript",
        "js",
        "json",
        "jsx",
        "kotlin",
        "rust",
        "scss",
        "swift",
        "ts",
        "tsx",
        "typescript",
    }
)
_ECMASCRIPT_COMMENT_LANGUAGES = frozenset({"javascript", "js", "jsx", "ts", "tsx", "typescript"})
_SQL_COMMENT_LANGUAGES = frozenset({"sql"})
_HASH_COMMENT_LANGUAGES = frozenset(
    {
        "bash",
        "fish",
        "sh",
        "shell",
        "yaml",
        "yml",
        "zsh",
    }
)
_HASH_AND_C_STYLE_COMMENT_LANGUAGES = frozenset({"hcl", "php", "terraform", "tf"})
_CMD_COMMENT_LANGUAGES = frozenset({"bat", "cmd"})
_POWERSHELL_COMMENT_LANGUAGES = frozenset({"powershell", "pwsh"})
_ECMASCRIPT_REGEX_PREFIX_KEYWORDS = frozenset(
    {
        "await",
        "case",
        "delete",
        "instanceof",
        "in",
        "new",
        "return",
        "throw",
        "typeof",
        "void",
        "yield",
    }
)


def _python_comment_prose(content: str) -> str:
    """Return comments and docstrings even when surrounding Python is invalid."""
    tokens: list[tokenize.TokenInfo] = []
    token_error_tail = ""
    try:
        for token in tokenize.generate_tokens(io.StringIO(content).readline):
            tokens.append(token)
    except (IndentationError, tokenize.TokenError):
        # Tokenization still yields every complete comment/string before the
        # malformed tail. Preserve those tokens and fail closed over the
        # unconsumed region without reclassifying earlier quoted literals.
        line_number, column = tokens[-1].end if tokens else (1, 0)
        lines = content.splitlines(keepends=True)
        if 1 <= line_number <= len(lines):
            token_error_tail = lines[line_number - 1][column:] + "".join(lines[line_number:])
    comments = [
        token.string.removeprefix("#").strip() for token in tokens if token.type == tokenize.COMMENT
    ]
    if token_error_tail:
        comments.append(token_error_tail)
    docstrings: list[str] = []
    try:
        tree = ast.parse(content)
    except (IndentationError, SyntaxError):
        triple_fstring = False
        for token in tokens:
            if token.type == getattr(tokenize, "FSTRING_START", -1):
                triple_fstring = _PYTHON_TRIPLE_STRING_RE.match(token.string) is not None
                continue
            if token.type == getattr(tokenize, "FSTRING_MIDDLE", -1) and triple_fstring:
                docstrings.append(token.string)
                continue
            if token.type == getattr(tokenize, "FSTRING_END", -1):
                triple_fstring = False
                continue
            if token.type != tokenize.STRING:
                continue
            triple_quote = _PYTHON_TRIPLE_STRING_RE.match(token.string)
            if triple_quote is None:
                continue
            try:
                value = ast.literal_eval(token.string)
            except (SyntaxError, ValueError):
                quote = triple_quote.group("quote")
                value = token.string[triple_quote.end() :]
                if value.endswith(quote):
                    value = value[: -len(quote)]
            if isinstance(value, str):
                docstrings.append(value)
    else:
        docstrings.extend(
            value
            for node in ast.walk(tree)
            if isinstance(node, (ast.AsyncFunctionDef, ast.ClassDef, ast.FunctionDef, ast.Module))
            and (value := ast.get_docstring(node, clean=False)) is not None
        )
    return "\n".join((*comments, *docstrings))


def _paired_literal_end(content: str, match: re.Match[str]) -> int:
    """Return the first index after one balanced Ruby/Perl quote literal."""
    opening = match.group("delimiter")
    closing = _PAIRED_DELIMITERS[opening]
    depth = 1
    index = match.end()
    while index < len(content):
        if content[index] == "\\":
            index += 2
            continue
        if content[index] == opening:
            depth += 1
        elif content[index] == closing:
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return len(content)


def _delimited_comment_prose(
    content: str,
    *,
    line_marker: str,
    block_comments: bool,
    block_start: str = "/*",
    block_end: str = "*/",
    backtick_strings: bool = False,
    marker_requires_boundary: bool = False,
    marker_boundary_chars: str = "",
    marker_requires_line_start: bool = False,
    marker_requires_suffix_boundary: bool = False,
    marker_case_insensitive: bool = False,
    escape_character: str = "\\",
    single_quote_escapes: bool = True,
    doubled_quote_escapes: bool = False,
    nested_block_comments: bool = False,
    paired_quote_re: re.Pattern[str] | None = None,
    quote_terminates_at_newline: bool = False,
) -> str:
    """Extract comments outside quoted literals for C-family and SQL data."""
    comments: list[str] = []
    index = 0
    quote: str | None = None
    while index < len(content):
        character = content[index]
        if quote is not None:
            if quote_terminates_at_newline and quote != "`" and character in "\r\n":
                quote = None
                index += 1
                continue
            if character == escape_character and (quote != "'" or single_quote_escapes):
                index += 2
                continue
            if character == quote:
                if (
                    doubled_quote_escapes
                    and index + 1 < len(content)
                    and content[index + 1] == quote
                ):
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if paired_quote_re is not None and (paired_quote := paired_quote_re.match(content, index)):
            index = _paired_literal_end(content, paired_quote)
            continue
        if character in ({"'", '"', "`"} if backtick_strings else {"'", '"'}):
            quote = character
            index += 1
            continue
        if block_comments and content.startswith(block_start, index):
            content_start = index + len(block_start)
            if not nested_block_comments:
                end = content.find(block_end, content_start)
                if end < 0:
                    comments.append(content[content_start:].strip())
                    break
                comments.append(content[content_start:end].strip())
                index = end + len(block_end)
                continue
            depth = 1
            cursor = content_start
            while depth:
                next_start = content.find(block_start, cursor)
                next_end = content.find(block_end, cursor)
                if next_end < 0:
                    comments.append(content[content_start:].strip())
                    return "\n".join(comments)
                if 0 <= next_start < next_end:
                    depth += 1
                    cursor = next_start + len(block_start)
                    continue
                depth -= 1
                cursor = next_end + len(block_end)
            comments.append(content[content_start:next_end].strip())
            index = cursor
            continue
        marker_text = content[index : index + len(line_marker)]
        marker_matches = (
            marker_text.casefold() == line_marker.casefold()
            if marker_case_insensitive
            else marker_text == line_marker
        )
        marker_suffix_index = index + len(line_marker)
        if (
            marker_matches
            and (
                not marker_requires_boundary
                or index == 0
                or content[index - 1].isspace()
                or content[index - 1] in marker_boundary_chars
            )
            and (
                not marker_requires_line_start
                or not content[content.rfind("\n", 0, index) + 1 : index].strip()
            )
            and (
                not marker_requires_suffix_boundary
                or marker_suffix_index == len(content)
                or content[marker_suffix_index].isspace()
            )
        ):
            end = content.find("\n", index + len(line_marker))
            end = len(content) if end < 0 else end
            comments.append(content[index + len(line_marker) : end].strip())
            index = end
            continue
        index += 1
    return "\n".join(comments)


def _ecmascript_regex_literal_start(content: str, slash_index: int) -> bool:
    """Distinguish a regex literal opener from a division operator."""
    cursor = slash_index - 1
    while cursor >= 0 and content[cursor].isspace():
        cursor -= 1
    if cursor < 0:
        return True
    if content[cursor] in "([{:;,=!?&|+-*%^~<>":
        return True
    if not (content[cursor].isalnum() or content[cursor] in "_$"):
        return False
    end = cursor + 1
    while cursor >= 0 and (content[cursor].isalnum() or content[cursor] in "_$"):
        cursor -= 1
    return content[cursor + 1 : end].casefold() in _ECMASCRIPT_REGEX_PREFIX_KEYWORDS


def _project_ecmascript_template(
    content: str,
    projection: list[str],
    contexts: list[tuple[str, int]],
    index: int,
) -> int:
    character = content[index]
    if character == "\\":
        projection[index] = " "
        if index + 1 < len(content):
            index += 1
            if content[index] not in "\r\n":
                projection[index] = " "
        return index + 1
    if content.startswith("${", index):
        projection[index : index + 2] = [" ", " "]
        contexts.append(("interpolation", 1))
        return index + 2
    if character == "`":
        projection[index] = " "
        contexts.pop()
    elif character not in "\r\n":
        projection[index] = " "
    return index + 1


def _advance_ecmascript_quote(
    content: str,
    contexts: list[tuple[str, int]],
    index: int,
) -> int:
    kind, _ = contexts[-1]
    character = content[index]
    if character in "\r\n":
        contexts.pop()
        return index
    if character == "\\":
        return min(index + 2, len(content))
    if (kind == "single_quote" and character == "'") or (
        kind == "double_quote" and character == '"'
    ):
        contexts.pop()
    return index + 1


def _project_ecmascript_regex(
    content: str,
    projection: list[str],
    contexts: list[tuple[str, int]],
    index: int,
) -> int:
    kind, depth = contexts[-1]
    character = content[index]
    if character in "\r\n":
        contexts.pop()
        return index
    projection[index] = " "
    if character == "\\":
        if index + 1 < len(content):
            index += 1
            if content[index] not in "\r\n":
                projection[index] = " "
        return index + 1
    if character == "[":
        contexts[-1] = (kind, 1)
    elif character == "]" and depth:
        contexts[-1] = (kind, 0)
    elif character == "/" and not depth:
        contexts.pop()
    return index + 1


def _advance_ecmascript_code(
    content: str,
    projection: list[str],
    contexts: list[tuple[str, int]],
    index: int,
) -> int:
    kind, depth = contexts[-1]
    character = content[index]
    if content.startswith("//", index):
        contexts.append(("line_comment", 0))
        return index + 2
    if content.startswith("/*", index):
        contexts.append(("block_comment", 0))
        return index + 2
    if character == "/" and _ecmascript_regex_literal_start(content, index):
        projection[index] = " "
        contexts.append(("regex", 0))
    elif character == "'":
        contexts.append(("single_quote", 0))
    elif character == '"':
        contexts.append(("double_quote", 0))
    elif character == "`":
        projection[index] = " "
        contexts.append(("template", 0))
    elif kind == "interpolation" and character == "{":
        contexts[-1] = (kind, depth + 1)
    elif kind == "interpolation" and character == "}":
        if depth == 1:
            projection[index] = " "
            contexts.pop()
        else:
            contexts[-1] = (kind, depth - 1)
    return index + 1


def _ecmascript_code_projection(content: str) -> str:
    """Blank literals while preserving comments and interpolation code."""
    projection = list(content)
    contexts: list[tuple[str, int]] = [("code", 0)]
    index = 0
    while index < len(content):
        kind, _ = contexts[-1]
        if kind == "template":
            index = _project_ecmascript_template(content, projection, contexts, index)
        elif kind in {"single_quote", "double_quote"}:
            index = _advance_ecmascript_quote(content, contexts, index)
        elif kind == "line_comment":
            if content[index] in "\r\n":
                contexts.pop()
            else:
                index += 1
        elif kind == "block_comment":
            if content.startswith("*/", index):
                contexts.pop()
                index += 2
            else:
                index += 1
        elif kind == "regex":
            index = _project_ecmascript_regex(content, projection, contexts, index)
        else:
            index = _advance_ecmascript_code(content, projection, contexts, index)
    return "".join(projection)


def _ecmascript_comment_prose(content: str) -> str:
    return _delimited_comment_prose(
        _ecmascript_code_projection(content),
        line_marker="//",
        block_comments=True,
        quote_terminates_at_newline=True,
    )


def _combine_comment_prose(*projections: str) -> str:
    return "\n".join(value for value in projections if value)


def _directive_block_comment_prose(
    content: str,
    *,
    start_re: re.Pattern[str],
    end_re: re.Pattern[str],
) -> str:
    """Extract line-oriented Ruby or Perl documentation comments."""
    comments: list[str] = []
    in_comment = False
    for line in content.splitlines():
        if not in_comment:
            if start := start_re.match(line):
                in_comment = True
                comments.append(line[start.end() :].strip())
            continue
        if end_re.match(line):
            in_comment = False
            continue
        comments.append(line.strip())
    return "\n".join(comments)


def _cmd_comment_prose(content: str) -> str:
    comments: list[str] = []
    for line in content.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("::"):
            comments.append(stripped[2:].strip())
            continue
        quoted = False
        for index, character in enumerate(line):
            if character == '"' and (index == 0 or line[index - 1] != "^"):
                quoted = not quoted
                continue
            if quoted or line[index : index + 3].casefold() != "rem":
                continue
            prefix = line[:index].rstrip()
            if prefix.endswith("@"):
                prefix = prefix[:-1].rstrip()
            suffix = line[index + 3 :]
            command_prefix = re.sub(
                r"^(?:(?:\d*>>?|<)\s*(?:\"[^\"\r\n]*\"|\S+)\s*)+",
                "",
                prefix.casefold(),
            )
            conditional_prefix = bool(
                re.match(r"^(?:if\b.{0,192}|(?:for\b.{0,192}\bdo)|else)\s*$", command_prefix)
            )
            if (not command_prefix or prefix.endswith(("&", "|")) or conditional_prefix) and (
                not suffix or suffix[0].isspace() or suffix[0] in ".:/;=,"
            ):
                comments.append(suffix[1:].strip() if suffix[:1] in ".:/;=," else suffix.strip())
                break
    return "\n".join(comments)


def _generic_comment_prose(content: str) -> str:
    comments: list[str] = []
    for line in content.splitlines():
        if match := _CODE_COMMENT_LINE_RE.search(line):
            comments.append(match.group(1))
    for match in _CODE_BLOCK_COMMENT_RE.finditer(content):
        comments.append(next(group for group in match.groups() if group is not None))
    return "\n".join(comments)


def code_comment_prose(content: str, language: str) -> str:
    """Project language comments without treating literals as instructions."""
    language = language.casefold()
    if language in _PYTHON_COMMENT_LANGUAGES:
        return _python_comment_prose(content)
    if language in _C_STYLE_COMMENT_LANGUAGES:
        projection = (
            _ecmascript_comment_prose(content)
            if language in _ECMASCRIPT_COMMENT_LANGUAGES
            else _delimited_comment_prose(
                content,
                line_marker="//",
                block_comments=True,
                backtick_strings=language == "go",
                quote_terminates_at_newline=True,
            )
        )
        if language in _ECMASCRIPT_COMMENT_LANGUAGES and content.startswith("#!"):
            end = content.find("\n")
            hashbang = content[2 : len(content) if end < 0 else end].strip()
            return _combine_comment_prose(hashbang, projection)
        return projection
    if language in _SQL_COMMENT_LANGUAGES:
        return _combine_comment_prose(
            _delimited_comment_prose(
                content,
                line_marker="--",
                block_comments=True,
                single_quote_escapes=False,
                doubled_quote_escapes=True,
            ),
            _delimited_comment_prose(
                content,
                line_marker="#",
                block_comments=False,
                single_quote_escapes=False,
                doubled_quote_escapes=True,
            ),
            _delimited_comment_prose(
                content,
                line_marker="rem",
                block_comments=False,
                marker_requires_line_start=True,
                marker_requires_suffix_boundary=True,
                marker_case_insensitive=True,
                single_quote_escapes=False,
                doubled_quote_escapes=True,
            ),
        )
    if language in _POWERSHELL_COMMENT_LANGUAGES:
        return _delimited_comment_prose(
            content,
            line_marker="#",
            block_comments=True,
            block_start="<#",
            block_end="#>",
            escape_character="`",
            single_quote_escapes=False,
            doubled_quote_escapes=True,
            nested_block_comments=True,
        )
    if language in {"rb", "ruby"}:
        return _combine_comment_prose(
            _delimited_comment_prose(
                content,
                line_marker="#",
                block_comments=False,
                paired_quote_re=_RUBY_PERCENT_QUOTE_RE,
            ),
            _directive_block_comment_prose(
                content,
                start_re=_RUBY_BLOCK_START_RE,
                end_re=_RUBY_BLOCK_END_RE,
            ),
        )
    if language == "perl":
        return _combine_comment_prose(
            _delimited_comment_prose(
                content,
                line_marker="#",
                block_comments=False,
                paired_quote_re=_PERL_QUOTE_RE,
            ),
            _directive_block_comment_prose(
                content,
                start_re=_PERL_POD_START_RE,
                end_re=_PERL_POD_END_RE,
            ),
        )
    if language == "r":
        return _delimited_comment_prose(
            content,
            line_marker="#",
            block_comments=False,
            backtick_strings=True,
        )
    if language in _ADJACENT_HASH_COMMENT_LANGUAGES:
        return _delimited_comment_prose(content, line_marker="#", block_comments=False)
    if language in _HASH_COMMENT_LANGUAGES:
        return _delimited_comment_prose(
            content,
            line_marker="#",
            block_comments=False,
            marker_requires_boundary=True,
            marker_boundary_chars=";|&()<>",
            single_quote_escapes=False,
        )
    if language in _HASH_AND_C_STYLE_COMMENT_LANGUAGES:
        return _combine_comment_prose(
            _delimited_comment_prose(
                content,
                line_marker="#",
                block_comments=False,
            ),
            _delimited_comment_prose(content, line_marker="//", block_comments=True),
        )
    if language == "lua":
        return _delimited_comment_prose(
            content,
            line_marker="--",
            block_comments=True,
            block_start="--[[",
            block_end="]]",
        )
    if language in _CMD_COMMENT_LANGUAGES:
        return _cmd_comment_prose(content)
    return _generic_comment_prose(content)


__all__ = ["CODE_FENCE_LANGUAGES", "code_comment_prose"]
