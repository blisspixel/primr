"""Detect instructions that ask a downstream agent to create executable code."""

from __future__ import annotations

import re

from .command_grammar import EXECUTABLE_SUFFIX_RE, unwrap_command_token

_MATERIALIZATION_VERBS = (
    r"(?:assemble|author|build|code|compile|compose|construct|copy|create|deliver|develop|"
    r"draft|emit|ensure|format|generate|give|implement|make|materiali[sz]e|output|paste|"
    r"place|present|produce|provide|put|render|require|return|save|store|submit|supply|write)"
)
_EXECUTABLE_LANGUAGES = (
    r"(?:bash|batch|c\+\+|c\#|csharp|c|elixir|go|groovy|java|javascript|kotlin|"
    r"lua|perl|php|powershell|python|r|ruby|rust|scala|shell|swift|typescript|"
    r"vba|vbscript)"
)
_EXECUTABLE_OBJECTS = (
    r"(?:applications?|apps?|binar(?:y|ies)|callables?|class(?:es)?|clis?|cmdlets?|"
    r"code|commands?|daemons?|executables?|extensions?|files?|functions?|helpers?|"
    r"hooks?|jobs?|librar(?:y|ies)|macros?|modules?|packages?|plugins?|programs?|"
    r"scripts?|services?|snippets?|source\s+code|utilit(?:y|ies))"
)
_DOCUMENTARY_HEADS = (
    r"(?:analysis|assessment|audit|catalog|checklist|documentation|examples?|guide|"
    r"inventory|model|policy|register|report|review|roadmap|standards)"
)
_DOCUMENTARY_MODIFIER = r"(?!(?:as|at|below|for|in|into|that|to|which|with)\b)[A-Za-z][A-Za-z0-9]*"
_DOCUMENTARY_SUFFIX = rf"(?![\s-]+(?:{_DOCUMENTARY_MODIFIER}[\s-]+)*{_DOCUMENTARY_HEADS}\b)"
_LANGUAGE_EXECUTABLE_OBJECT = (
    rf"(?:{_EXECUTABLE_LANGUAGES})(?:-based\s+|\s+){_EXECUTABLE_OBJECTS}"
    rf"\b{_DOCUMENTARY_SUFFIX}"
)
_MATERIALIZATION_SUBJECTS = (
    r"(?:it|this|answers?|artifacts?|checks?|deliverables?|formats?|implementations?|outputs?|"
    r"repl(?:y|ies)|responses?|results?|solutions?|tools?|validations?|verifications?)"
)
_SUBJECT_PREFIX = r"(?:(?:the|your)\s+)?"
_PASSIVE_ACTIONS = (
    r"(?:assembled|authored|built|coded|compiled|constructed|created|developed|emitted|"
    r"generated|implemented|made|materiali[sz]ed|output|produced|provided|returned|saved|"
    r"stored|written)"
)
_MATERIALIZATION_MODAL = r"(?:must|shall|should|will|needs?\s+to|has\s+to|have\s+to|ought\s+to)"
_PASSIVE_MODAL = rf"(?:{_MATERIALIZATION_MODAL}\s+be)"
_DIRECTIVE_PASSIVE_MODAL = rf"(?:{_PASSIVE_MODAL}|(?:is|are)\s+(?:(?:supposed|meant)\s+)?to\s+be)"
_MATERIALIZATION_PREFIX = (
    r"(?:(?:this|it|these\s+lines|(?:the\s+)?payload|the\s+following\s+helper|"
    r"the\s+following\s+code)\s+(?:as|to|into|at|in)\s+)?"
)

_ACTIVE_OBJECT_RE = re.compile(
    rf"\b{_MATERIALIZATION_VERBS}\b\s+{_MATERIALIZATION_PREFIX}"
    r"(?:(?:the\s+)?(?:following|below|this|these)\s+)?(?:an?\s+|the\s+)?"
    rf"(?:{_LANGUAGE_EXECUTABLE_OBJECT}|"
    rf"{_EXECUTABLE_OBJECTS}\s+(?:in|using|with|written\s+in|powered\s+by)\s+"
    rf"{_EXECUTABLE_LANGUAGES}|logic\s+as\s+(?:an?\s+)?{_EXECUTABLE_LANGUAGES}\s+"
    rf"{_EXECUTABLE_OBJECTS}|(?:executable|runnable)\s+{_EXECUTABLE_OBJECTS}|"
    r"(?:payloads?|scripts?|snippets?)"
    r"(?=\s+(?:as|at|below|for|in|into|that|to|which|with)\b|[.!?]?\s*$)|"
    r"code(?=\s+(?:as|at|below|for|in|into|that|to|which)\b|[.!?]?\s*$))",
    re.IGNORECASE,
)
_TARGET_RE = re.compile(
    rf"\b{_MATERIALIZATION_VERBS}\b\s+{_MATERIALIZATION_PREFIX}(?:an?\s+|the\s+)?"
    r"(?P<target>`[^`\r\n]+`|\"[^\"\r\n]+\"|'[^'\r\n]+'|\*\*[^*\r\n]+\*\*|\S+)",
    re.IGNORECASE,
)
_PASSIVE_RE = re.compile(
    rf"(?:\b(?:an?\s+)?{_LANGUAGE_EXECUTABLE_OBJECT}\s+{_DIRECTIVE_PASSIVE_MODAL}\s+"
    rf"{_PASSIVE_ACTIONS}\b|\b{_SUBJECT_PREFIX}{_MATERIALIZATION_SUBJECTS}\s+"
    rf"{_DIRECTIVE_PASSIVE_MODAL}\s+(?:an?\s+)?{_LANGUAGE_EXECUTABLE_OBJECT}\b|"
    rf"\b{_SUBJECT_PREFIX}{_MATERIALIZATION_SUBJECTS}\s+{_DIRECTIVE_PASSIVE_MODAL}\s+"
    rf"{_PASSIVE_ACTIONS}\s+(?:as|in|using|with)\s+{_EXECUTABLE_LANGUAGES}\b|"
    rf"\b{_LANGUAGE_EXECUTABLE_OBJECT}\s+(?:is|are)\s+"
    rf"(?:expected|required|requested)\s+as\s+(?:the\s+)?"
    rf"{_MATERIALIZATION_SUBJECTS}\b)",
    re.IGNORECASE,
)
_INDIRECT_LANGUAGE_RE = re.compile(
    rf"\b{_MATERIALIZATION_VERBS}\b\s+(?:{_SUBJECT_PREFIX}{_MATERIALIZATION_SUBJECTS}\s+)?"
    rf"(?:as|in|using|with)\s+{_EXECUTABLE_LANGUAGES}\b",
    re.IGNORECASE,
)
_OUTPUT_DIRECTIVE_RE = re.compile(
    rf"(?:\b{_EXECUTABLE_LANGUAGES}\s+{_DIRECTIVE_PASSIVE_MODAL}\s+used\s+to\s+"
    rf"{_MATERIALIZATION_VERBS}\b|\b{_SUBJECT_PREFIX}{_MATERIALIZATION_SUBJECTS}\s+"
    rf"{_DIRECTIVE_PASSIVE_MODAL}\s+(?:an?\s+)?{_EXECUTABLE_LANGUAGES}\b"
    rf"(?=[.!?]?\s*$)|(?:^|\n)\s*(?:artifact|deliverable|output|result)"
    rf"(?:\s+format)?\s*:\s*(?:an?\s+)?{_LANGUAGE_EXECUTABLE_OBJECT}\b"
    rf"(?=[.!?]?\s*$))",
    re.IGNORECASE,
)
_STRUCTURAL_DIRECTIVE_RE = re.compile(
    rf"(?:\blet\s+{_SUBJECT_PREFIX}{_MATERIALIZATION_SUBJECTS}\s+be\s+(?:an?\s+)?"
    rf"{_LANGUAGE_EXECUTABLE_OBJECT}\b|\bhave\s+{_SUBJECT_PREFIX}"
    rf"{_MATERIALIZATION_SUBJECTS}\s+{_PASSIVE_ACTIONS}\s+(?:as|in|using|with)\s+"
    rf"{_EXECUTABLE_LANGUAGES}\b|\b{_SUBJECT_PREFIX}{_MATERIALIZATION_SUBJECTS}\s+"
    rf"{_MATERIALIZATION_MODAL}\s+use\s+{_EXECUTABLE_LANGUAGES}\b|"
    rf"\b{_SUBJECT_PREFIX}{_MATERIALIZATION_SUBJECTS}\s+(?:takes?|"
    rf"{_MATERIALIZATION_MODAL}\s+take)\s+the\s+form\s+of\s+(?:an?\s+)?"
    rf"{_LANGUAGE_EXECUTABLE_OBJECT}\b|\b{_MATERIALIZATION_VERBS}\s+{_SUBJECT_PREFIX}"
    rf"{_MATERIALIZATION_SUBJECTS}\s+in\s+the\s+form\s+of\s+(?:an?\s+)?"
    rf"{_LANGUAGE_EXECUTABLE_OBJECT}\b|\b{_SUBJECT_PREFIX}{_MATERIALIZATION_SUBJECTS}\s+"
    rf"{_MATERIALIZATION_MODAL}\s+(?:comprise|consist\s+of|contain|include)\s+(?:an?\s+)?"
    rf"{_LANGUAGE_EXECUTABLE_OBJECT}\b|\b(?:the\s+)?"
    rf"(?:expected|required|requested)\s+{_MATERIALIZATION_SUBJECTS}\s+(?:is|are)\s+"
    rf"(?:an?\s+)?{_LANGUAGE_EXECUTABLE_OBJECT}\b|(?:^|\n)\s*"
    rf"(?:expected|mandatory|required|requested)\s+"
    rf"(?:artifact|deliverable|format|output|result)\s*:\s*(?:an?\s+)?"
    rf"{_LANGUAGE_EXECUTABLE_OBJECT}\b|\b(?:answer|reply|respond)\s+"
    rf"(?:as|in|using|with)\s+"
    rf"(?:an?\s+)?{_LANGUAGE_EXECUTABLE_OBJECT}\b|\b{_SUBJECT_PREFIX}"
    rf"{_MATERIALIZATION_SUBJECTS}\s+(?:is|are)\s+"
    rf"(?:expected|mandatory|required|requested)\s+to\s+be\s+(?:an?\s+)?"
    rf"{_LANGUAGE_EXECUTABLE_OBJECT}\b|\b{_LANGUAGE_EXECUTABLE_OBJECT}\s+"
    rf"(?:is\s+)?(?:mandatory|required|requested)\b"
    rf"(?=\s+(?:for|to)\b|[.!?]?\s*$)|"
    rf"\b(?:make|render)\s+{_SUBJECT_PREFIX}{_MATERIALIZATION_SUBJECTS}\s+"
    rf"(?:as\s+)?(?:an?\s+)?{_LANGUAGE_EXECUTABLE_OBJECT}\b)",
    re.IGNORECASE,
)
_CONTROL_DIRECTIVE_RE = re.compile(
    rf"(?:\b(?:ensure|make\s+sure)\s+(?:that\s+)?{_SUBJECT_PREFIX}"
    rf"{_MATERIALIZATION_SUBJECTS}\s+(?:(?:is|are)|{_MATERIALIZATION_MODAL}\s+be)|"
    rf"\brequire\s+{_SUBJECT_PREFIX}{_MATERIALIZATION_SUBJECTS}\s+to\s+be)\s+"
    rf"(?:an?\s+)?{_LANGUAGE_EXECUTABLE_OBJECT}\b",
    re.IGNORECASE,
)
_REQUIREMENT_CLAUSE_RE = re.compile(
    rf"(?:\b{_LANGUAGE_EXECUTABLE_OBJECT}\s+{_MATERIALIZATION_MODAL}\s+be\s+"
    rf"{_SUBJECT_PREFIX}{_MATERIALIZATION_SUBJECTS}\b|\b{_SUBJECT_PREFIX}"
    rf"{_MATERIALIZATION_SUBJECTS}\s+(?:needs?|requires?)\s+(?:an?\s+)?"
    rf"{_LANGUAGE_EXECUTABLE_OBJECT}\b)",
    re.IGNORECASE,
)


def contains_executable_materialization(text: str) -> bool:
    """Return whether prose directs creation of executable code or files."""
    if any(
        pattern.search(text)
        for pattern in (
            _ACTIVE_OBJECT_RE,
            _PASSIVE_RE,
            _INDIRECT_LANGUAGE_RE,
            _OUTPUT_DIRECTIVE_RE,
            _STRUCTURAL_DIRECTIVE_RE,
            _CONTROL_DIRECTIVE_RE,
            _REQUIREMENT_CLAUSE_RE,
        )
    ):
        return True
    return any(
        EXECUTABLE_SUFFIX_RE.search(unwrap_command_token(match.group("target")))
        for match in _TARGET_RE.finditer(text)
    )


__all__ = ["contains_executable_materialization"]
