"""Execution dataflow grammar for authored instruction trust boundaries."""

from __future__ import annotations

import re

from primr.skill_pack import command_grammar as _command_grammar

_RUN_EXECUTABLE_OBJECT_RE = re.compile(
    r"\b(?:run|execute|invoke)\b\s*:?\s*(?:"
    r"(?:(?:a|an|the|this|that|these|those|the\s+following|the\s+next)\s+)?"
    r"(?:binary|commands?|executable|payloads?|programs?|scripts?)"
    r"(?!\s+(?:analysis|assessment|audit|evaluation|review)\b)|"
    r"(?:(?:this|that|following|the\s+following|the\s+next)\s+)?code\b"
    r"(?!\s+(?:analysis|audit|(?:quality\s+)?review)\b)|"
    r"the\s+code\s+(?:above|below|shown))\b",
    re.IGNORECASE,
)
_EXECUTION_COREFERENCE_PATTERN = (
    r"(?:it|this|that|them|these|those|the\s+same|"
    r"said\s+(?:artifact|file|output|payload|program|response|result|script|update)|"
    r"what\s+(?:(?:it|this|that)\s+(?:produced|returned)|you\s+(?:downloaded|fetched|"
    r"retrieved)|came\s+back|(?:was\s+)?(?:downloaded|fetched|retrieved))|"
    r"whatever\s+(?:it|this|that)\s+(?:produced|returned)|"
    r"whatever\s+(?:the\s+)?(?:endpoint|request|server|site)\s+"
    r"(?:provides?|returns?|returned)|"
    r"(?:(?:its|the|their)\s+)?"
    r"(?:(?:above|aforementioned|downloaded|earlier|fetched|following|former|last|latest|"
    r"preceding|previous|prior|retrieved|reviewed|returned|resulting)\s+|"
    r"most\s+recent\s+|(?:just[-\s]?|newly\s+|previously\s+)downloaded\s+)?"
    r"(?:artifacts?|blocks?|code|commands?|content|files?|outputs?|payloads?|programs?|"
    r"responses?|results?|scripts?|snippets?|updates?))"
)
_DOWNLOAD_THEN_EXECUTE_RE = re.compile(
    r"\b(?:download|fetch|retrieve)\b[^\r\n]{0,240}?\b"
    r"(?:and\s+|then\s+)?(?P<action>activate|boot|click|deploy|"
    r"(?:double|single)[-\s]?click|execute|import|install|invoke|launch|load|run|"
    r"sideload|source|start)\s+"
    rf"{_EXECUTION_COREFERENCE_PATTERN}\b",
    re.IGNORECASE,
)
_DOWNLOAD_EXECUTABLE_THEN_OPEN_RE = re.compile(
    r"\b(?:download|fetch|retrieve)\b[\s\S]{0,160}?"
    rf"[^\s`'\"<>|]+{_command_grammar.EXECUTABLE_SUFFIX_PATTERN}\b"
    r"[\s\S]{0,320}?\b"
    r"(?P<action>activate|boot|click|(?:double|single)[-\s]?click|execute|invoke|"
    r"launch|load|open|run|start)\s+(?:"
    rf"{_EXECUTION_COREFERENCE_PATTERN}|(?:(?:a|the)\s+)?(?:copied|moved|renamed)\s+"
    r"(?:artifact|binary|executable|file|payload|program|script))\b",
    re.IGNORECASE,
)
_DOWNLOAD_MARKED_EXECUTABLE_THEN_OPEN_RE = re.compile(
    r"\b(?:download|fetch|retrieve)\b[\s\S]{0,240}?\b(?:mark|make)\s+"
    rf"{_EXECUTION_COREFERENCE_PATTERN}\s+(?:as\s+)?executable\b"
    r"[\s\S]{0,160}?\b(?P<action>activate|launch|load|open|run|start)\s+"
    rf"{_EXECUTION_COREFERENCE_PATTERN}\b",
    re.IGNORECASE,
)
_COREFERENTIAL_EXECUTION_RE = re.compile(
    r"(?:\b(?:activate|boot|click|deploy|(?:double|single)[-\s]?click|execute|import|"
    r"install|invoke|launch|load|run|sideload|start)\s+"
    rf"{_EXECUTION_COREFERENCE_PATTERN}\b|"
    rf"\bcarr(?:y|ies|ied|ying)\s+{_EXECUTION_COREFERENCE_PATTERN}\s+out\b)",
    re.IGNORECASE,
)
_SOURCE_COREFERENTIAL_EXECUTION_RE = re.compile(
    r"(?:^|[.!?;:]\s+|\b(?:and\s+then|next|now|please|then)\s+)source\s+"
    rf"{_EXECUTION_COREFERENCE_PATTERN}\b",
    re.IGNORECASE | re.MULTILINE,
)
_SOURCE_CITATION_OBJECT_RE = re.compile(
    r"^\s+(?:assertions?|citations?|claims?|conclusions?|evidence|facts?|figures?|"
    r"findings?|metrics?|statements?)\b",
    re.IGNORECASE,
)
_GENERIC_OPERATIONAL_COREFERENCE_RE = re.compile(
    r"\b(?:binary|code|command|executable|payload|program|script|snippet)\b"
    r"[^\r\n.!?]{0,160}?"
    r"\b(?:apply|enact|perform|use)\s+"
    rf"{_EXECUTION_COREFERENCE_PATTERN}\b",
    re.IGNORECASE,
)
_COREFERENTIAL_PERSISTENCE_RE = re.compile(
    rf"\b(?P<action>add|append|configur(?:e|es|ed|ing)|copy|enable|move|persist|place|put|"
    rf"register|save|schedule|set\s+up|write)\s+"
    rf"{_EXECUTION_COREFERENCE_PATTERN}\b"
    r"[^\r\n.!?]{0,64}?\b(?:as|at|for|in|into|on|to|via)\s+(?:(?:a|an|the)\s+)?"
    r"(?:autostart|boot|cron(?:\s+job)?|crontab|launch\s+(?:agent|daemon)|"
    r"(?:login|powershell|shell)\s+profile|login\s+item|scheduled\s+task|scheduler|service|"
    r"startup(?:\s+(?:folder|item|task))?|"
    r"~/\.(?:bash_profile|bashrc|profile|zprofile|zshrc))\b|"
    rf"\bmake\s+{_EXECUTION_COREFERENCE_PATTERN}\s+(?:(?:a|the)\s+)?"
    r"(?:autostart|launch\s+(?:agent|daemon)|login\s+item|scheduled\s+task|service|"
    r"startup\s+(?:item|task))\b",
    re.IGNORECASE,
)
_INTERPRETER_INPUT_PATTERN = (
    rf"(?P<input>[^\s\x60'\"<>|]+{_command_grammar.EXECUTABLE_SUFFIX_PATTERN}\b|"
    r"\b(?:artifact|content|download|file|it|output|payload|response|result|that|"
    r"them|these|this|those)\b)"
)
_INTERPRETER_SINK_RE = re.compile(
    r"\b(?:deliver|feed|forward|give|hand|inject|pass|pipe|provide|route|send|"
    r"submit|supply)\b[^\r\n.!?]{0,120}?"
    rf"{_INTERPRETER_INPUT_PATTERN}"
    r"[^\r\n.!?]{0,80}?\b(?:as\s+(?:the\s+)?input\s+)?(?:into|through|to)\s+"
    r"(?:the\s+)?"
    r"(?P<target>[A-Za-z][A-Za-z0-9_.+-]*)\b",
    re.IGNORECASE,
)
_INTERPRETER_PROCESS_RE = re.compile(
    r"\b(?:compile|evaluate|interpret|load|parse|process)\b[^\r\n.!?]{0,120}?"
    rf"{_INTERPRETER_INPUT_PATTERN}"
    r"[^\r\n.!?]{0,80}?\b(?:by|in|under|using|via|with)\s+(?:the\s+)?"
    r"(?P<target>[A-Za-z][A-Za-z0-9_.+-]*)\b",
    re.IGNORECASE,
)
_INTERPRETER_SPAWN_RE = re.compile(
    r"\bspawn\b\s+(?:the\s+)?(?P<target>[A-Za-z][A-Za-z0-9_.+-]*)\b"
    rf"[^\r\n.!?]{{0,120}}?{_INTERPRETER_INPUT_PATTERN}",
    re.IGNORECASE,
)
_INTERPRETER_TARGET_FIRST_RE = re.compile(
    r"\b(?:give|hand|provide|send|submit)\b\s+(?:the\s+)?"
    r"(?P<target>[A-Za-z][A-Za-z0-9_.+-]*)\b"
    rf"[^\r\n.!?]{{0,40}}?{_INTERPRETER_INPUT_PATTERN}",
    re.IGNORECASE,
)
_INTERPRETER_FOR_TARGET_RE = re.compile(
    r"\b(?:deliver|feed|give|hand|pass|provide|send|submit)\b[^\r\n.!?]{0,48}?"
    rf"{_INTERPRETER_INPUT_PATTERN}[^\r\n.!?]{{0,40}}?\bfor\s+(?:the\s+)?"
    r"(?P<target>[A-Za-z][A-Za-z0-9_.+-]*)\b[^\r\n.!?]{0,24}?\bto\s+"
    r"(?:consume|evaluate|execute|interpret|load|parse|process|run)\b",
    re.IGNORECASE,
)
_INTERPRETER_DIRECTIVE_RE = re.compile(
    r"\b(?:ask|have|let|make|tell)\b\s+(?:the\s+)?"
    r"(?P<target>[A-Za-z][A-Za-z0-9_.+-]*)\b"
    r"[^\r\n.!?]{0,32}?\b(?:consume|evaluate|execute|interpret|load|parse|process|run)\b"
    rf"[^\r\n.!?]{{0,80}}?{_INTERPRETER_INPUT_PATTERN}",
    re.IGNORECASE,
)
_INTERPRETER_ROLE_SUFFIX_RE = re.compile(
    r"^\s+(?:community|developers?|documentation|engineers?|engineering|experts?|"
    r"maintainers?|team|users?)\b",
    re.IGNORECASE,
)
_INTERPRETER_ANTECEDENT_RE = re.compile(
    r"\b(?P<target>bash|cmd|node|perl|php|powershell|pwsh|py|python(?:3(?:\.\d+)?)?|"
    r"ruby|sh|zsh)\b(?:\s+(?:interpreter|runtime))?"
    r"[^\r\n.!?]{0,32}\b(?:available|installed|ready)\b",
    re.IGNORECASE,
)
_INTERPRETER_DATA_SUFFIX_RE = re.compile(
    r"^\s+(?:analysis|documentation|findings|metrics|"
    r"records|report|schema|statistics|summary|telemetry)\b",
    re.IGNORECASE,
)
_OPERATIONAL_ARTIFACT_ACTION_RE = re.compile(
    r"\b(?:activat(?:e|es|ed|ing)|boot(?:s|ed|ing)?|"
    r"(?:click|(?:double|single)[-\s]?click)(?:s|ed|ing)?|"
    r"carr(?:y|ies|ied|ying)\s+out|"
    r"import(?:s|ed|ing)?|install(?:s|ed|ing)?|"
    r"load(?:s|ed|ing)?|open(?:s|ed|ing)?|sideload(?:s|ed|ing)?|"
    r"sourc(?:e|es|ed|ing))\b\s+"
    r"(?:(?:a|an|the|this|that)\s+)?"
    r"(?:(?:above|aforementioned|downloaded|earlier|following|former|last|latest|previous|"
    r"prior)\s+|most\s+recent\s+|"
    r"(?:just[-\s]?|newly\s+|previously\s+)downloaded\s+)?(?:"
    r"(?:artifact|binary|executable|file|package|payload|program|script|update)\b|"
    r"[^\s`'\"<>|]+\.(?:py|pyw|sh|bash|zsh|fish|ps1|bat|cmd|js|mjs|cjs|ts|"
    r"tsx|jsx|rb|pl|php|lua|r|vbs|exe|com|dll|scr|msi|jar|hta|wsf|msc|cpl|lnk|reg)\b)",
    re.IGNORECASE,
)
_NEGATED_EXECUTION_TAIL_RE = re.compile(
    r"\b(?:do\s+not(?:\s+ever)?|don't(?:\s+ever)?|must\s+not|"
    r"never(?:\s+ever)?|should\s+not|under\s+no\s+circumstances|without(?:\s+ever)?)"
    r"(?:[\s,]+(?:accidentally|inadvertently|intentionally|knowingly))*[\s,]*$",
    re.IGNORECASE,
)
_EXECUTION_NEGATION_EXCEPTION_RE = re.compile(
    r"\b(?:apart\s+from|except(?:\s+when)?|only\s+when|other\s+than|"
    r"provided\s+that|save\s+for|unless|with\s+the\s+exception\s+of)\b",
    re.IGNORECASE,
)
_EXECUTION_NEGATION_EXCEPTION_ACTION_RE = re.compile(
    r"\b(?:do\s+not|don't|must\s+not|never|should\s+not|"
    r"under\s+no\s+circumstances|without)\b"
    r"[^\r\n.!?]{0,48}?\b(?:activate|boot|carry\s+out|click|deploy|"
    r"(?:double|single)[-\s]?click|execute|"
    r"import|install|invoke|launch|load|open|run|sideload|source|start)\b"
    r"(?:[^\r\n.!?]|\.(?=[A-Za-z0-9])){0,160}?"
    r"\b(?:apart\s+from|except(?:\s+when)?|only\s+when|other\s+than|"
    r"provided\s+that|save\s+for|unless|with\s+the\s+exception\s+of)\b",
    re.IGNORECASE,
)
_INERT_OPERATIONAL_REVIEW_RE = re.compile(
    r"\b(?:analy[sz]e|assess|describe|document|evaluate|explain|review)\b"
    r"[^\r\n.!?]{0,60}\b(?:how|whether)\s+to\s*$",
    re.IGNORECASE,
)
_INERT_LANGUAGE_AUTHORING_RE = re.compile(
    r"^\s*use\s+(?:c\+\+|c#|go|java|javascript|python|ruby|rust|typescript)\s+to\s+"
    r"(?:author|build|create|develop|implement|write)\b"
    r"(?![^\r\n]*\b(?:and|then)\s+(?:execute|invoke|launch|run|start)\b)"
    r"[^\r\n]*[.!?]?\s*$",
    re.IGNORECASE,
)
_LANGUAGE_ARTIFACT_DESCRIPTION_RE = re.compile(
    r"^\s*(?:c\+\+|c#|go|java|javascript|python|ruby|rust|typescript)\s+"
    r"(?:application|class|code|function|library|module|package|program|script)\s+"
    r"(?:for|that|to|which)\b[^\r\n]*[.!?]?\s*$",
    re.IGNORECASE,
)


def has_download_then_execute(text: str) -> bool:
    """Return whether downloaded content is subsequently executed by reference."""
    return any(
        not _is_negated_execution_action(text, match.start("action"), match.end())
        for pattern in (
            _DOWNLOAD_THEN_EXECUTE_RE,
            _DOWNLOAD_EXECUTABLE_THEN_OPEN_RE,
            _DOWNLOAD_MARKED_EXECUTABLE_THEN_OPEN_RE,
        )
        for match in pattern.finditer(text)
    )


def _is_negated_execution_action(text: str, start: int, end: int) -> bool:
    """Return whether one execution action is unambiguously prohibited."""
    prefix = text[max(0, start - 80) : start]
    suffix = text[end : end + 96]
    return bool(
        _NEGATED_EXECUTION_TAIL_RE.search(prefix)
        and _EXECUTION_NEGATION_EXCEPTION_RE.search(suffix) is None
    )


def has_coreferential_execution(text: str) -> bool:
    """Return whether prose affirmatively executes referenced content."""
    matches = (
        *_COREFERENTIAL_EXECUTION_RE.finditer(text),
        *_SOURCE_COREFERENTIAL_EXECUTION_RE.finditer(text),
        *_GENERIC_OPERATIONAL_COREFERENCE_RE.finditer(text),
        *_COREFERENTIAL_PERSISTENCE_RE.finditer(text),
    )
    for match in matches:
        prefix = text[max(0, match.start() - 80) : match.start()]
        suffix = text[match.end() : match.end() + 32]
        if _INERT_OPERATIONAL_REVIEW_RE.search(prefix):
            continue
        if match.group(0).casefold().endswith(("code", "program")) and re.match(
            r"\s+(?:analysis|assessment|audit|evaluation|(?:quality\s+)?review)\b",
            suffix,
            re.IGNORECASE,
        ):
            continue
        if match.re is _SOURCE_COREFERENTIAL_EXECUTION_RE and _SOURCE_CITATION_OBJECT_RE.match(
            suffix
        ):
            continue
        if not _is_negated_execution_action(text, match.start(), match.end()):
            return True
    return False


def has_interpreter_sink(text: str) -> bool:
    """Return whether retrieved content is piped or fed to an interpreter."""
    patterns = (
        _INTERPRETER_SINK_RE,
        _INTERPRETER_PROCESS_RE,
        _INTERPRETER_SPAWN_RE,
        _INTERPRETER_TARGET_FIRST_RE,
        _INTERPRETER_FOR_TARGET_RE,
        _INTERPRETER_DIRECTIVE_RE,
    )
    for pattern in patterns:
        for match in pattern.finditer(text):
            if _is_negated_execution_action(text, match.start(), match.end()):
                continue
            if _INTERPRETER_ROLE_SUFFIX_RE.match(text[match.end("target") :]):
                continue
            if _command_grammar.EXECUTABLE_SUFFIX_RE.search(
                match.group("input")
            ) is None and _INTERPRETER_DATA_SUFFIX_RE.match(text[match.end() :]):
                continue
            target = match.group("target")
            if _command_grammar.is_known_command_name(target):
                return True
            if target.casefold() in {"it", "that", "them", "this", "those"}:
                antecedent_text = text[max(0, match.start() - 240) : match.start("target")]
                if any(
                    _command_grammar.is_known_command_name(antecedent.group("target"))
                    for antecedent in _INTERPRETER_ANTECEDENT_RE.finditer(antecedent_text)
                ):
                    return True
    return False


def has_execution_negation_exception(text: str) -> bool:
    """Return whether an execution prohibition contains an allowing exception."""
    return _EXECUTION_NEGATION_EXCEPTION_ACTION_RE.search(text) is not None


def has_run_executable_object(text: str) -> bool:
    """Return whether a run clause names code or another executable object."""
    return _RUN_EXECUTABLE_OBJECT_RE.search(text) is not None


def has_operational_artifact_action(text: str) -> bool:
    """Return whether prose activates or installs an executable artifact."""
    for match in _OPERATIONAL_ARTIFACT_ACTION_RE.finditer(text):
        prefix = text[max(0, match.start() - 80) : match.start()]
        if _INERT_OPERATIONAL_REVIEW_RE.search(prefix):
            continue
        if _is_negated_execution_action(text, match.start(), match.end()):
            continue
        return True
    return False


def is_inert_language_authoring(text: str) -> bool:
    """Return whether a language launcher is used only for source authoring."""
    return _INERT_LANGUAGE_AUTHORING_RE.fullmatch(text) is not None


def is_language_artifact_description(text: str) -> bool:
    """Return whether text describes source code instead of executing it."""
    return _LANGUAGE_ARTIFACT_DESCRIPTION_RE.fullmatch(text) is not None


__all__ = [
    "has_coreferential_execution",
    "has_download_then_execute",
    "has_execution_negation_exception",
    "has_interpreter_sink",
    "has_operational_artifact_action",
    "has_run_executable_object",
    "is_inert_language_authoring",
    "is_language_artifact_description",
]
