"""Detect affirmative instructions to access or disclose sensitive material.

This module owns the credential grammar used at authored-agent trust
boundaries. It deliberately distinguishes raw values from governance metadata
and distinguishes affirmative actions from prohibitions and review questions.
"""

from __future__ import annotations

import re

_SENSITIVE_MATERIAL_PATTERN = (
    r"(?:~/\.ssh\b|\.aws[/\\]credentials\b|\.docker[/\\]config\.json\b|\.env\b|"
    r"\.kube[/\\]config\b|\.netrc\b|\.npmrc\b|\.pypirc\b|credentials\.json\b|"
    r"/etc/(?:gshadow|shadow)\b|/proc/(?:self|\d+)/environ\b|"
    r"id_(?:ed25519|rsa)\b|kubeconfigs?\b|"
    r"(?:aws_shared_credentials_file|google_application_credentials|azure_client_secret|"
    r"github_token|gitlab_token|npm_token|pypi_token)\b|"
    r"aws[_-]+(?:access[_-]+key[_-]+id|secret[_-]+access[_-]+key|session[_-]+token)\b|"
    r"(?:[a-z][a-z0-9]*[_-]+){0,3}api[_-]+keys?\b|"
    r"access\s+tokens?\b|api\s+keys?\b|auth(?:entication|orization)?\s+tokens?\b|"
    r"(?:oauth\s+)?client\s+secrets?\b|github\s+pats?\b|personal\s+access\s+tokens?\b|"
    r"recovery\s+codes?\b|refresh\s+tokens?\b|service\s+account\s+keys?\b|"
    r"session\s+tokens?\b|(?:browser\s+)?session\s+cookies?\b|ssh_auth_sock\b|"
    r"ssh[\s_-]+agent(?:[\s_-]+(?:credentials?|identit(?:y|ies)|keys?|socket))?\b|"
    r"wallet\s+seed\s+phrases?\b|"
    r"(?:anthropic|aws|azure|bearer|gcp|gemini|github|gitlab|google|hf|huggingface|"
    r"npm|openai|pypi|service(?:[\s_-]+account)?|slack|xai)"
    r"[\s_-]+(?:access[\s_-]+)?tokens?\b|database[_-]+url\b|pgpassword\b|"
    r"credential\s+values?\b|credentials?\b|"
    r"passwords?\b|private\s+keys?\b|secrets\b|"
    r"(?:(?:actual|application|deployment|my|our|raw|service|stored|the|their|your)\s+"
    r"secret|secret\s+(?:key|token|value))s?\b|system\s+prompt\b)"
)
_SENSITIVE_MATERIAL_RE = re.compile(_SENSITIVE_MATERIAL_PATTERN, re.IGNORECASE)
_SENSITIVE_TRANSFER_ACTION_PATTERN = (
    r"answer(?:s|ed|ing)?|attach(?:es|ed|ing)?|backup|backed\s+up|backing\s+up|"
    r"beacon(?:s|ed|ing)?|"
    r"announc(?:e|es|ed|ing)|broadcast(?:s|ed|ing)?|contain(?:s|ed|ing)?|"
    r"cop(?:y|ies|ied|ying)|deliver(?:s|ed|ing)?|dictat(?:e|es|ed|ing)|"
    r"disclos(?:e|es|ed|ing)|"
    r"echo(?:es|ed|ing)?|email(?:s|ed|ing)?|emit(?:s|ted|ting)?|"
    r"enumerat(?:e|es|ed|ing)|"
    r"exfiltrat(?:e|es|ed|ing)|exfil(?:s|ed|ing)?|forward(?:s|ed|ing)?|"
    r"expos(?:e|es|ed|ing)|export(?:s|ed|ing)?|includ(?:e|es|ed|ing)|"
    r"giv(?:e|es|en|ing)|hand(?:s|ed|ing)?(?:\s+over)?|"
    r"leak(?:s|ed|ing)?|mirr(?:or|ors|ored|oring)|mov(?:e|es|ed|ing)|"
    r"past(?:e|es|ed|ing)|plac(?:e|es|ed|ing)|post(?:s|ed|ing)?|"
    r"provid(?:e|es|ed|ing)|publish(?:es|ed|ing)?|push(?:es|ed|ing)?|put(?:s|ting)?|"
    r"quot(?:e|es|ed|ing)|recit(?:e|es|ed|ing)|relay(?:s|ed|ing)?|"
    r"return(?:s|ed|ing)?|"
    r"render(?:s|ed|ing)?|reproduc(?:e|es|ed|ing)|"
    r"repl(?:y|ies|ied|ying)|respond(?:s|ed|ing)?|"
    r"sa(?:y|ys|id|ying)|sav(?:e|es|ed|ing)|"
    r"send(?:s|ing)?|sent|shar(?:e|es|ed|ing)|spell(?:s|ed|ing)?(?:\s+out)?|"
    r"stat(?:e|es|ed|ing)|stream(?:s|ed|ing)?|submit(?:s|ted|ting)?|"
    r"summari[sz](?:e|es|ed|ing)|sync(?:s|ed|ing)?|"
    r"transcrib(?:e|es|ed|ing)|transmit(?:s|ted|ting)?|"
    r"transfer(?:s|red|ring)?|upload(?:s|ed|ing)?|"
    r"verbali[sz](?:e|es|ed|ing)|writ(?:e|es|ten|ing)"
)
_SENSITIVE_VALUE_TRANSFER_ACTION_PATTERN = (
    rf"{_SENSITIVE_TRANSFER_ACTION_PATTERN}|display(?:s|ed|ing)?|"
    r"dump(?:s|ed|ing)?|list(?:s|ed|ing)?|output(?:s|ted|ting)?|"
    r"print(?:s|ed|ing)?|read(?:s|ing)?(?:\s+(?:aloud|out))?|"
    r"repeat(?:s|ed|ing)?|report(?:s|ed|ing)?|reveal(?:s|ed|ing)?|"
    r"show(?:s|ed|ing)?|surfac(?:e|es|ed|ing)|tell(?:s|ing)?|told"
)
_SENSITIVE_DIRECT_VALUE_OUTPUT_RE = re.compile(
    r"\b(?:repeat(?:s|ed|ing)?|report(?:s|ed|ing)?|tell(?:s|ing)?|told)\b"
    rf"[^\r\n.!?]{{0,80}}?{_SENSITIVE_MATERIAL_PATTERN}",
    re.IGNORECASE,
)
_SENSITIVE_TRANSFER_RE = re.compile(
    rf"\b(?:{_SENSITIVE_TRANSFER_ACTION_PATTERN})\b"
    rf"(?:(?!\b(?:{_SENSITIVE_TRANSFER_ACTION_PATTERN}|but|except|however|instead|then)\b)"
    rf"[^\r\n.!?]){{0,80}}?{_SENSITIVE_MATERIAL_PATTERN}",
    re.IGNORECASE,
)
_SENSITIVE_RELOCATION_RE = re.compile(
    rf"\b(?:copy|move)\b[^\r\n.!?]{{0,60}}?{_SENSITIVE_MATERIAL_PATTERN}"
    r"[^\r\n.!?]{0,40}\bto\b[^\r\n.!?]{0,30}"
    r"(?:https?://|another\s+(?:host|machine|system)|external|remote|third[-\s]?party)",
    re.IGNORECASE,
)
_SENSITIVE_ACCESS_RE = re.compile(
    rf"\b(?:access(?:es|ed|ing)?|cat(?:s|ted|ting)?|displays?|displayed|displaying|"
    rf"captur(?:e|es|ed|ing)|collect(?:s|ed|ing)?|gather(?:s|ed|ing)?|"
    rf"dump(?:s|ed|ing)?|harvest(?:s|ed|ing)?|scrap(?:e|es|ed|ing)|"
    rf"extract(?:s|ed|ing)?|fetch(?:es|ed|ing)?|find(?:s|ing)?|found|"
    rf"get(?:s|ting)?|got|inspect(?:s|ed|ing)?|list(?:s|ed|ing)?|load(?:s|ed|ing)?|"
    rf"locat(?:e|es|ed|ing)|obtain(?:s|ed|ing)?|open(?:s|ed|ing)?|read(?:s|ing)?|"
    rf"reveal(?:s|ed|ing)?|show(?:s|ed|ing)?|retriev(?:e|es|ed|ing)|"
    rf"print(?:s|ed|ing)?|steal(?:s|ing)?|stole|stolen|view(?:s|ed|ing)?)\b"
    rf"[^\r\n.!?]{{0,80}}?{_SENSITIVE_MATERIAL_PATTERN}",
    re.IGNORECASE,
)
_SENSITIVE_PASSIVE_TRANSFER_RE = re.compile(
    rf"{_SENSITIVE_MATERIAL_PATTERN}[^\r\n.!?]{{0,48}}?\b(?:must|shall|should)\b"
    r"(?:(?!\b(?:never|not)\b)[^\r\n.!?]){0,32}?"
    rf"\b(?:{_SENSITIVE_TRANSFER_ACTION_PATTERN})\b",
    re.IGNORECASE,
)
_SENSITIVE_VALUE_COREFERENCE_RE = re.compile(
    rf"{_SENSITIVE_MATERIAL_PATTERN}"
    r"[^\r\n.!?;]{0,160}?(?:[.!?;]\s*|\r?\n\s*)[^\r\n.!?]{0,48}?"
    rf"\b(?P<action>{_SENSITIVE_VALUE_TRANSFER_ACTION_PATTERN})\b"
    r"[^\r\n.!?]{0,32}?(?:(?:their|its|the|these|those|corresponding)\s+){0,2}"
    r"(?:(?:actual|raw|secret)\s+)?(?:contents?|keys?|plaintext|tokens?|values?)\b",
    re.IGNORECASE,
)
_SENSITIVE_COREFERENCE_SEPARATOR_PATTERN = (
    r"(?:[.!?;]\s*|,\s*(?:but|however|instead|nevertheless|then|yet)\s+|\r?\n\s*)"
)
_SENSITIVE_PRONOUN_TRANSFER_RE = re.compile(
    rf"(?P<material>{_SENSITIVE_MATERIAL_PATTERN})"
    rf"(?P<antecedent>[^\r\n.!?;]{{0,160}}?){_SENSITIVE_COREFERENCE_SEPARATOR_PATTERN}"
    r"[^\r\n.!?]{0,48}?"
    rf"\b(?P<action>{_SENSITIVE_VALUE_TRANSFER_ACTION_PATTERN})\b"
    r"[^\r\n.!?]{0,48}?\b(?:it|them|these|those|"
    r"the\s+(?:archive|backup|bundle|copy|encoding|export|file|package|screenshot))\b",
    re.IGNORECASE,
)
_SENSITIVE_TRANSFORMED_TRANSFER_RE = re.compile(
    r"\b(?:archiv(?:e|es|ed|ing)|base64[-\s]?encod(?:e|es|ed|ing)|"
    r"captur(?:e|es|ed|ing)|compress(?:es|ed|ing)?|encod(?:e|es|ed|ing)|"
    r"encrypt(?:s|ed|ing)?|hex[-\s]?encod(?:e|es|ed|ing)|"
    r"photograph(?:s|ed|ing)?|renam(?:e|es|ed|ing)|"
    r"screenshot(?:s|ed|ing)?)\b"
    rf"[^\r\n.!?]{{0,64}}?{_SENSITIVE_MATERIAL_PATTERN}"
    r"[^\r\n.!?]{0,48}?(?P<continuation>\b(?:and|then)\b[^\r\n.!?]{0,32}?"
    rf"\b(?P<action>{_SENSITIVE_VALUE_TRANSFER_ACTION_PATTERN})\b"
    r"[^\r\n.!?]{0,48}?\b(?:it|them|these|those|the\s+"
    r"(?:archive|backup|base64|bundle|ciphertext|copy|encoded\s+value|encoding|"
    r"export|file|package|result|screenshot))\b)",
    re.IGNORECASE,
)
_SENSITIVE_PRONOUN_USE_RE = re.compile(
    rf"(?P<material>{_SENSITIVE_MATERIAL_PATTERN})"
    rf"(?P<antecedent>[^\r\n.!?;]{{0,160}}?){_SENSITIVE_COREFERENCE_SEPARATOR_PATTERN}"
    r"[^\r\n.!?]{0,48}?"
    r"\b(?P<action>use|apply|enter|provide|supply)\b"
    r"[^\r\n.!?]{0,32}?\b(?:it|them|these|those)\b"
    r"[^\r\n.!?]{0,24}?\b(?:for|to)\s+"
    r"(?:authenticat(?:e|ion)|log\s+(?:in|on)|sign\s+in|access)\b",
    re.IGNORECASE,
)
_SENSITIVE_PRONOUN_AUTH_RE = re.compile(
    rf"(?P<material>{_SENSITIVE_MATERIAL_PATTERN})"
    rf"(?P<antecedent>[^\r\n.!?;]{{0,160}}?){_SENSITIVE_COREFERENCE_SEPARATOR_PATTERN}"
    r"[^\r\n.!?]{0,48}?"
    r"\b(?P<action>authenticate|log\s+(?:in|on)|sign\s+in|access)\b"
    r"[^\r\n.!?]{0,32}?\b(?:using|with)\s+(?:it|them|these|those)\b",
    re.IGNORECASE,
)
_SENSITIVE_PRONOUN_ENTRY_RE = re.compile(
    rf"(?P<material>{_SENSITIVE_MATERIAL_PATTERN})"
    rf"(?P<antecedent>[^\r\n.!?;]{{0,160}}?){_SENSITIVE_COREFERENCE_SEPARATOR_PATTERN}"
    r"[^\r\n.!?]{0,48}?"
    r"\b(?P<action>enter|input|submit|type)\b"
    r"[^\r\n.!?]{0,32}?\b(?:it|them|these|those)\b"
    r"[^\r\n.!?]{0,24}?\b(?:in|into|to)\b"
    r"[^\r\n.!?]{0,24}?\b(?:authentication|login|sign[-\s]?in)\b"
    r"[^\r\n.!?]{0,16}?\b(?:field|form)\b",
    re.IGNORECASE,
)
_SENSITIVE_ENTRY_TRANSFER_RE = re.compile(
    r"\b(?P<action>add(?:s|ed|ing)?|enter(?:s|ed|ing)?|input(?:s|ted|ting)?|"
    r"insert(?:s|ed|ing)?|record(?:s|ed|ing)?|submit(?:s|ted|ting)?|"
    r"typ(?:e|es|ed|ing))\b"
    rf"[^\r\n.!?]{{0,64}}?{_SENSITIVE_MATERIAL_PATTERN}"
    r"[^\r\n.!?]{0,64}?\b(?:in|into|to)\b[^\r\n.!?]{0,32}?"
    r"\b(?:answer|chat|document|field|file|form|message|output|report|response|ticket)\b",
    re.IGNORECASE,
)
_SENSITIVE_DEFINITE_USE_RE = re.compile(
    r"\b(?:use|apply|enter|provide|supply)\b[^\r\n.!?]{0,24}?"
    r"\b(?:the|this|that|your|my|our|its|their|provided|supplied|actual|raw)\s+"
    rf"{_SENSITIVE_MATERIAL_PATTERN}(?:\s+(?:itself|value))?\s+(?:for|to)\s+"
    r"(?:authenticat(?:e|ion)|log\s+(?:in|on)|sign\s+in|access)\b",
    re.IGNORECASE,
)
_SENSITIVE_DEFINITE_AUTH_RE = re.compile(
    r"\b(?:authenticate|log\s+(?:in|on)|sign\s+in|access)\b"
    r"[^\r\n.!?]{0,40}?\b(?:using|with)\s+"
    r"(?:(?:the|this|that|your|my|our|its|their|provided|supplied|actual|raw)\s+)?"
    rf"{_SENSITIVE_MATERIAL_PATTERN}"
    r"(?!\s+(?:authentication|authorization|design|flow|guidance|management|"
    r"policy|rotation|status)\b)",
    re.IGNORECASE,
)
_SENSITIVE_TRANSFER_EXCEPTION_RE = re.compile(
    rf"\b(?:{_SENSITIVE_TRANSFER_ACTION_PATTERN})\b[^\r\n.!?]{{0,60}}?"
    r"\b(?:apart\s+from|except|other\s+than|save\s+for|with\s+the\s+exception\s+of)\b"
    rf"[^\r\n.!?]{{0,32}}?{_SENSITIVE_MATERIAL_PATTERN}",
    re.IGNORECASE,
)
_TRANSFER_NEGATION_PATTERN = (
    r"(?:never|do\s+not|don't|must\s+not|should\s+not|"
    r"under\s+no\s+circumstances|(?:abstain|refrain)\s+from)"
)
_TRANSFER_NEGATION_RE = re.compile(rf"\b{_TRANSFER_NEGATION_PATTERN}\b", re.IGNORECASE)
_DIRECT_NEGATION_TAIL_RE = re.compile(
    r"^[\s,]*(?:(?:accidentally|ever|inadvertently|intentionally|knowingly|publicly)"
    r"[\s,]*)*(?:(?:under\s+(?:any|no)\s+circumstances|at\s+any\s+time)[\s,]*)?$",
    re.IGNORECASE,
)
_COORDINATED_NEGATION_TAIL_RE = re.compile(r"\b(?:and|or)\s*$", re.IGNORECASE)
_NEGATION_CANCELLER_RE = re.compile(
    r"^[\s,]*(?:ever\s+)?(?:(?:avoid|fail|forget|hesitate|neglect|refuse)\s+to|"
    r"(?:abstain|refrain)\s+from)\b",
    re.IGNORECASE,
)
_NEGATION_REVERSAL_RE = re.compile(
    r"\b(?:but|except|however|instead|nevertheless|then|yet)\b",
    re.IGNORECASE,
)
_DESCRIPTIVE_ACTION_TAIL_RE = re.compile(
    r"(?:\b(?:analy[sz]e|assess|audit|check|determine|document|evaluate|explain|"
    r"investigate|measure|review|summarize|test)\s+"
    r"(?:if|whether)\s+(?:[A-Za-z][\w-]*\s+){0,6}|"
    r"\b(?:analy[sz]e|assess|audit|check|debug|evaluate|examine|inspect|review|test)\s+"
    r"(?:the\s+|this\s+)?(?:code|function|module|program|script|service|system)\s+"
    r"(?:that|which)\s+|"
    r"\b(?:describe|document|explain|summarize)\s+how\s+(?!to\b)"
    r"(?:[A-Za-z][\w-]*\s+){1,8})$",
    re.IGNORECASE,
)
_SENSITIVE_METADATA_PREFIX_RE = re.compile(
    r"\b(?:age|counts?|expiration|expiry|inventory|metadata|names?|numbers?|owners?|"
    r"rotation|status)\s+(?:of\s+)?(?:active\s+|expired\s+|managed\s+|rotated\s+)?$",
    re.IGNORECASE,
)
_SENSITIVE_METADATA_SUFFIX_RE = re.compile(
    r"^[-\s]+(?:(?:are|is)\s+stored|(?:by\s+)?(?:age|algorithm|complexity|counts?|design|"
    r"documentation|docs?|expiration|expiry|guidance|handling|hygiene|injection|lifetime|"
    r"locations?|management|metadata|names?|owners?|pages?|polic(?:y|ies)|requirements?|"
    r"reset|risks?|rotation|rules?|security|status|storage(?:\s+locations?)?))"
    r"\b[^\r\n.!?]{0,120}$",
    re.IGNORECASE,
)
_SENSITIVE_VALUE_DETAIL_PATTERN = (
    r"(?:contents?|plaintext|raw\s+data|(?:full\s+)?values?|"
    r"(?:actual|raw|secret)\s+(?:keys?|tokens?)|"
    r"(?:keys?|tokens?)\s+(?:itself|themselves)|the\s+(?:key|token)\s+itself)"
)
_NEGATED_VALUE_DETAIL_RE = re.compile(
    rf"(?:\bbut\s+never\b[^\r\n.!?]{{0,16}}\b{_SENSITIVE_VALUE_DETAIL_PATTERN}\b|"
    rf"(?:^|[\s,])not\s+(?:the(?:ir)?\s+)?\b{_SENSITIVE_VALUE_DETAIL_PATTERN}\b|"
    rf"\bwithout\b\s+(?:(?:exposing|including|providing|revealing|returning|sharing|"
    rf"showing)\s+)?(?:their\s+)?\b{_SENSITIVE_VALUE_DETAIL_PATTERN}\b|"
    rf"\b(?:do\s+not|never|not)\b\s+(?:expose|include|provide|reveal|return|share|show)"
    rf"[^\r\n.!?]{{0,16}}\b{_SENSITIVE_VALUE_DETAIL_PATTERN}\b)",
    re.IGNORECASE,
)
_SENSITIVE_VALUE_DETAIL_RE = re.compile(rf"\b{_SENSITIVE_VALUE_DETAIL_PATTERN}\b", re.IGNORECASE)
_SENSITIVE_METADATA_ACTION_RE = re.compile(
    rf"\b(?:{_SENSITIVE_TRANSFER_ACTION_PATTERN})\b", re.IGNORECASE
)
_SENSITIVE_METADATA_DESTINATION_RE = re.compile(
    r"\b(?:in|into|to)\s+(?:the\s+)?"
    r"(?:answer|chat|document|field|file|form|message|output|report|response|ticket)\b",
    re.IGNORECASE,
)
_PASSIVE_METADATA_ACTION_RE = re.compile(
    rf"\b(?:must|shall|should)\b[^\r\n.!?]{{0,32}}?"
    rf"\b(?:{_SENSITIVE_TRANSFER_ACTION_PATTERN})\b",
    re.IGNORECASE,
)
_META_PROHIBITION_TAIL_RE = re.compile(
    r"\b(?:advise|instruct|remind|tell|warn)\s+"
    r"(?:[A-Za-z][\w-]*\s+){0,5}(?:never|not)\s+to\s*$",
    re.IGNORECASE,
)
_NEGATION_SUFFIX_EXCEPTION_RE = re.compile(
    r"\b(?:apart\s+from|except(?:\s+when)?|only\s+when|other\s+than|"
    r"provided\s+that|save\s+for|unless|with\s+the\s+exception\s+of)\b",
    re.IGNORECASE,
)
_AFFIRMATIVE_CONTINUATION_RE = re.compile(
    r"\b(?:and\s+)?(?:nevertheless|then|yet)\b[^\r\n.!?]{0,40}"
    r"\b(?:do\s+(?:it|so|that)|proceed|perform|repeat|"
    rf"{_SENSITIVE_TRANSFER_ACTION_PATTERN})\b",
    re.IGNORECASE,
)
_DOUBLE_NEGATION_RE = re.compile(
    rf"\b{_TRANSFER_NEGATION_PATTERN}\b[\s,]*(?:ever[\s,]*)?"
    rf"\b{_TRANSFER_NEGATION_PATTERN}\b",
    re.IGNORECASE,
)
_SENTENCE_BOUNDARY_RE = re.compile(
    r"[!?;]|(?<!\be\.g)(?<!\bi\.e)(?<!\betc)\.(?=\s|$)|\r?\n",
    re.IGNORECASE,
)


def _is_nonaffirmative_sensitive_action(text: str, match_start: int, match_end: int) -> bool:
    prefix = text[:match_start]
    boundaries = list(_SENTENCE_BOUNDARY_RE.finditer(prefix))
    clause = prefix[boundaries[-1].end() :] if boundaries else prefix
    if _DOUBLE_NEGATION_RE.search(clause):
        return False
    if _DESCRIPTIVE_ACTION_TAIL_RE.search(clause) or _META_PROHIBITION_TAIL_RE.search(clause):
        suffix = text[match_end:]
        if boundary := _SENTENCE_BOUNDARY_RE.search(suffix):
            suffix = suffix[: boundary.start()]
        return _AFFIRMATIVE_CONTINUATION_RE.search(suffix) is None
    negations = list(_TRANSFER_NEGATION_RE.finditer(clause))
    if not negations:
        return False
    suffix = text[match_end:]
    if boundary := _SENTENCE_BOUNDARY_RE.search(suffix):
        suffix = suffix[: boundary.start()]
    if _NEGATION_SUFFIX_EXCEPTION_RE.search(suffix):
        return False
    tail = clause[negations[-1].end() :]
    if _NEGATION_CANCELLER_RE.search(tail) or _NEGATION_REVERSAL_RE.search(tail):
        return False
    return bool(
        _DIRECT_NEGATION_TAIL_RE.fullmatch(tail) or _COORDINATED_NEGATION_TAIL_RE.search(tail)
    )


def _is_metadata_only_sensitive_action(text: str, match_start: int, match_end: int) -> bool:
    matched_text = text[match_start:match_end]
    material = _SENSITIVE_MATERIAL_RE.search(matched_text)
    if material is None:
        return False
    suffix = text[match_end:]
    if boundary := _SENTENCE_BOUNDARY_RE.search(suffix):
        suffix = suffix[: boundary.start()]
    if _SENSITIVE_METADATA_PREFIX_RE.search(matched_text[: material.start()]) is not None:
        return not suffix.strip(" \t,.")
    material_suffix = matched_text[material.end() :] + suffix
    if _SENSITIVE_METADATA_SUFFIX_RE.fullmatch(material_suffix) is None:
        return False
    affirmative_suffix = _NEGATED_VALUE_DETAIL_RE.sub("", material_suffix)
    affirmative_suffix = _PASSIVE_METADATA_ACTION_RE.sub("", affirmative_suffix, count=1)
    affirmative_suffix = _SENSITIVE_METADATA_DESTINATION_RE.sub("", affirmative_suffix)
    return not (
        _SENSITIVE_VALUE_DETAIL_RE.search(affirmative_suffix)
        or _SENSITIVE_MATERIAL_RE.search(affirmative_suffix)
        or _SENSITIVE_METADATA_ACTION_RE.search(affirmative_suffix)
    )


def _is_metadata_only_sensitive_antecedent(antecedent: str) -> bool:
    material = _SENSITIVE_MATERIAL_RE.search(antecedent)
    if material is None:
        return False
    prefix = antecedent[: material.start()]
    suffix = antecedent[material.end() :]
    metadata_shape = bool(
        _SENSITIVE_METADATA_PREFIX_RE.search(prefix)
        or _SENSITIVE_METADATA_SUFFIX_RE.fullmatch(suffix)
    )
    return metadata_shape and _SENSITIVE_VALUE_DETAIL_RE.search(suffix) is None


def find_sensitive_exfiltration_instruction(text: str) -> str | None:
    """Return an affirmative instruction to access or transfer secrets."""
    text = re.sub(r"[\r\n]+", " ", text)
    for transformed in _SENSITIVE_TRANSFORMED_TRANSFER_RE.finditer(text):
        continuation = transformed.group("continuation")
        continuation_start = transformed.start("continuation")
        if not _is_nonaffirmative_sensitive_action(
            continuation,
            transformed.start("action") - continuation_start,
            transformed.end("action") - continuation_start,
        ):
            return transformed.group(0)
    for coreference in _SENSITIVE_VALUE_COREFERENCE_RE.finditer(text):
        if not _is_nonaffirmative_sensitive_action(
            text, coreference.start("action"), coreference.end()
        ):
            return coreference.group(0)
    for pattern in (
        _SENSITIVE_PRONOUN_TRANSFER_RE,
        _SENSITIVE_PRONOUN_USE_RE,
        _SENSITIVE_PRONOUN_AUTH_RE,
        _SENSITIVE_PRONOUN_ENTRY_RE,
    ):
        for pronoun_transfer in pattern.finditer(text):
            antecedent = pronoun_transfer.group("material") + pronoun_transfer.group("antecedent")
            if _is_metadata_only_sensitive_antecedent(antecedent):
                continue
            if not _is_nonaffirmative_sensitive_action(
                text, pronoun_transfer.start("action"), pronoun_transfer.end()
            ):
                return pronoun_transfer.group(0)
    for entry in _SENSITIVE_ENTRY_TRANSFER_RE.finditer(text):
        if not _is_metadata_only_sensitive_action(
            text, entry.start(), entry.end()
        ) and not _is_nonaffirmative_sensitive_action(text, entry.start("action"), entry.end()):
            return entry.group(0)
    for pattern in (_SENSITIVE_DEFINITE_USE_RE, _SENSITIVE_DEFINITE_AUTH_RE):
        for match in pattern.finditer(text):
            if not _is_nonaffirmative_sensitive_action(text, match.start(), match.end()):
                return match.group(0)
    for exception in _SENSITIVE_TRANSFER_EXCEPTION_RE.finditer(text):
        if not _is_metadata_only_sensitive_action(text, exception.start(), exception.end()):
            return exception.group(0)
    for pattern in (
        _SENSITIVE_TRANSFER_RE,
        _SENSITIVE_DIRECT_VALUE_OUTPUT_RE,
        _SENSITIVE_RELOCATION_RE,
        _SENSITIVE_ACCESS_RE,
        _SENSITIVE_PASSIVE_TRANSFER_RE,
    ):
        for match in pattern.finditer(text):
            if not _is_metadata_only_sensitive_action(
                text, match.start(), match.end()
            ) and not _is_nonaffirmative_sensitive_action(text, match.start(), match.end()):
                return match.group(0)
    return None


__all__ = ["find_sensitive_exfiltration_instruction"]
