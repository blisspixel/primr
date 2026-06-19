"""Deterministic validator for skill packs.

No LLM calls. Runs the M365 Cowork ASKILL-* checks (per the v1.28 spec) plus
primr's own security hardening ported from the legacy `output/skills_generator`.

Produces a `ValidationReport` of `SkillIssue`s. The pipeline uses the report
both as a ship gate (HARD-fail blocks shipping) and as structured input to
the refinement LLM call.

Spec references:
    - ASKILL-P006: folder name == frontmatter `name`
    - ASKILL-P007: name is kebab-case (1-64 chars, no leading/trailing or
      consecutive hyphens)
    - DESC-LEN: description in [1, 1024] chars
    - DESC-TRIG: description contains a trigger phrase
    - BODY-SEC: body has all three required H2 sections
    - BODY-LEN: body word count in [300, 3000] (HARD-fail below 300 words
      or above ~5000 tokens)
    - BODY-QUALITY: body includes intake, scope, checkpoint, and worked
      input/output markers instead of shipping as a thin role template
    - SEC-INJECT: no prompt-injection / agent-instruction patterns
    - SEC-PATH: no hardcoded local file paths
    - PACK-OVERLAP: no two skills with >0.85 name+trigger similarity
"""

from __future__ import annotations

import ast
import re
from difflib import SequenceMatcher

from primr.skill_pack.body_quality import missing_quality_markers, quality_marker_guidance
from primr.skill_pack.schema import (
    IssueSeverity,
    Role,
    Skill,
    SkillIssue,
    SkillPack,
    ValidationReport,
)

# --- Naming rules (ASKILL-P007) -------------------------------------------

# Kebab-case: lowercase alphanumeric + single internal hyphens, 1-64 chars.
# Disallows leading/trailing hyphens and consecutive hyphens.
_KEBAB_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_MAX_NAME_LEN = 64

# --- Description rules ----------------------------------------------------

_MIN_DESC_LEN = 1
_MAX_DESC_LEN = 1024

# Trigger phrase regex. The MS Cowork docs require descriptions that signal
# *when* the agent should activate the skill. We accept the canonical
# "Use when..." plus a few common variants the model tends to produce.
_TRIGGER_PATTERN = re.compile(
    r"\b(use when|invoke when|trigger(?:s)? when|when (?:the )?user|when someone)\b",
    re.IGNORECASE,
)

# First-person pronouns that violate Anthropic's third-person discipline.
# A description that starts with "I help..." or "You can use..." causes
# discovery problems because the agent system prompt is written in second
# person, and pronouns clash. SOFT warning — refinement should fix.
_FIRST_PERSON_PATTERN = re.compile(
    r"\b(?:I |I'll|I can|I help|I'm |I will|we |we'll|we can|we help|"
    r"you can|you'll|you should|you may|your )",
    re.IGNORECASE,
)

# A "pushy" description (Anthropic: combats undertriggering) lists multiple
# concrete things the user might ask for. The RELIABLE structural signal is
# the enumeration after the trigger phrase — "Use when the user asks to X, Y,
# or Z" advertises three intents. We count those comma/and/or-separated
# clauses (see _count_trigger_intents). The keyword pattern below is only the
# FALLBACK signal for descriptions with no explicit trigger phrase, and for
# that it stays broad — IT/ML/business/consulting verbs all signal a concrete
# user intent. (The old heuristic counted only lexicon hits across the whole
# description, which under-counted well-formed enumerations that happened to
# use verbs outside the list, e.g. "perform/prepare/conduct" — a false-positive
# source on services packs. Counting enumerated intents fixes that.)
_PUSHY_KEYWORD_PATTERN = re.compile(
    r"\b(ask(?:s|ed|ing)?|request|need|want|trying to|look(?:ing)? for|"
    r"how to|help with|review|analyze|analy[sz]e|generate|extract|draft|"
    r"fix|debug|create|build|configure|investigate|triage|summari[sz]e|"
    r"integrate|schedule|extend|deploy|orchestrate|monitor|migrate|"
    r"refactor|optimi[sz]e|automate|validate|verify|audit|implement|"
    r"design|model|maintain|update|tune|test|ingest|transform|load|"
    r"export|import|merge|split|trace|profile|benchmark|forecast|"
    r"clean|enrich|normali[sz]e|"
    # Consulting / services / ops verbs — common in role-based packs.
    r"perform|prepare|assess|conduct|plan|calculat(?:e|ing)|reconcil(?:e|ing)|"
    r"facilitat(?:e|ing)|coordinat(?:e|ing)|produc(?:e|ing)|oversee|enabl(?:e|ing)|"
    r"deliver|support|map|track|identif(?:y|ies)|evaluat(?:e|ing)|recommend|"
    r"calculate|provision|onboard|reconcile)\b",
    re.IGNORECASE,
)
# A description should advertise at least this many distinct user intents.
_MIN_TRIGGER_INTENTS = 3

# Anthropic prefers gerund-form names (`processing-pdfs`, `analyzing-data`)
# because they describe the *capability* clearly. We accept gerund as
# the FIRST OR SECOND hyphen-separated token (so `fine-tuning-models`
# also counts — `tuning` is a gerund even though `fine` isn't). Noun
# phrases like `pipeline-orchestration` are explicitly acceptable per
# Anthropic so this stays SOFT regardless.
_GERUND_HINT_PATTERN = re.compile(r"^(?:[a-z]+-)?[a-z]+ing(?:-|$)")

# A skill name should describe a TASK, not be a bare product/feature name
# ("azure-front-door", "aks", "salesforce-sales-cloud"). When a name is
# composed *only* of vendor/product brand tokens with no action verb, it has
# been scoped as a product, not a capability. This is a SOFT hint — refinement
# re-scopes the title. The lexicon is intentionally NON-EXHAUSTIVE: it covers
# the high-frequency cloud/SaaS brands that dominate hiring evidence and most
# often leak into titles. A false negative (a product we don't list) is far
# cheaper than blocking a legitimate task name, so the check only fires when
# EVERY non-product token is also absent (i.e. the name carries no verb/task
# word at all).
_PRODUCT_BRAND_TOKENS = frozenset(
    {
        # Cloud platforms + their flagship services / features
        "azure",
        "aws",
        "gcp",
        "ec2",
        "s3",
        "lambda",
        "eks",
        "ecs",
        "rds",
        "aks",
        "acr",
        "synapse",
        "fabric",
        "sentinel",
        "cosmos",
        "cosmosdb",
        "entra",
        "defender",
        "purview",
        "bicep",
        "cloudfront",
        "dynamodb",
        "redshift",
        "bigquery",
        "pubsub",
        "gke",
        "firestore",
        "appservice",
        "kubernetes",
        "k8s",
        "openshift",
        # Data / analytics SaaS
        "snowflake",
        "databricks",
        "tableau",
        "powerbi",
        "looker",
        "dbt",
        "fivetran",
        "airflow",
        "kafka",
        "spark",
        # CRM / business SaaS
        "salesforce",
        "sfdc",
        "hubspot",
        "servicenow",
        "workday",
        "netsuite",
        "sap",
        "dynamics",
        "marketo",
        "pardot",
        "zendesk",
        "jira",
        "confluence",
        "sharepoint",
        "m365",
        "office365",
        "okta",
        # Observability / infra
        "datadog",
        "splunk",
        "grafana",
        "prometheus",
        "terraform",
        "ansible",
    }
)
# Verb/task tokens whose presence proves the name describes a capability, not
# just a product. Reuses the shape of the pushy-keyword set plus gerunds.
_TASK_TOKEN_PATTERN = re.compile(r"(?:ing|ation|ment|sis|tion)$|^(?:manage|operate|run|build)$")

# --- Body rules -----------------------------------------------------------

_REQUIRED_BODY_SECTIONS = [
    "What This Skill Does",
    "Workflow",
    "Output Format",
]
# Target range for skill bodies. A skill under 300 words is almost always
# missing one of the things that makes the artifact useful in practice:
# intake prompts, scope boundaries, a human checkpoint, or a worked example.
# Keep the upper bound generous so rich, grounded skills are allowed, but
# fail closed on thin bodies instead of merely reporting them.
_BODY_MIN_WORDS = 300
_BODY_TARGET_MAX_WORDS = 3000
_BODY_HARD_MAX_WORDS = 5000

# --- Security patterns ---------------------------------------------------

# Ported verbatim from output/skills_generator.py:_AGENT_INSTRUCTION_PATTERNS.
# These are the load-bearing prompt-injection filters: anything matching is
# a HARD failure that drops the role rather than risking a downstream agent
# host obeying scraped third-party content as an instruction.
_AGENT_INSTRUCTION_PATTERNS = [
    # "ignore previous instructions"-style injection. Requires an
    # instruction-like OBJECT after previous/prior/above so benign domain
    # prose ("ignore previously assigned licenses", "disregard prior true-up
    # estimates") does not false-positive and drop a good skill.
    re.compile(
        r"\b(?:ignore|disregard|forget)\b[^\n]{0,60}"
        r"(?:previous|prior|earlier|preceding|above|foregoing)\b[^\n]{0,40}"
        r"(?:instruction|directive|prompt|message|context|rule|guidance|persona|system)",
        re.IGNORECASE,
    ),
    re.compile(r"\bsystem\s+prompt\b", re.IGNORECASE),
    # "run a shell command"-style injection. Requires a real shell indicator
    # (bash/powershell/terminal/...) rather than the bare words "script" or
    # "command", so legitimate skill prose like "run the scripts/foo.py
    # helper" or "run the assessment" does not false-positive. Actual shell
    # blocks are still caught by the fenced-code and curl/wget patterns below.
    re.compile(
        r"\b(?:run|execute|invoke)\b[^\n]{0,40}"
        r"(?:bash|powershell|pwsh|zsh|\bsh\b|terminal|sudo|/bin/|"
        r"(?:shell|bash|system|terminal)\s+command)",
        re.IGNORECASE,
    ),
    # Bare "command"/"script" injection, gated on the DEMONSTRATIVE that
    # signals an inline payload ("run THIS command", "execute THE FOLLOWING
    # script", "paste THESE commands"). This closes the bypass where the
    # shell-indicator pattern above misses "run this command: rm -rf ..." or
    # "execute the script that ..." while preserving the false-positive guard
    # the narrowing was added for: benign prose says "run the scripts/foo.py
    # helper" / "run the assessment", never "run THIS command" with a payload.
    # Bare "the"/"a" are intentionally NOT in the alternation so the legit
    # forms stay clean.
    re.compile(
        r"\b(?:run|execute|invoke|paste|enter|type)\b[^\n]{0,30}"
        r"\b(?:this|that|these|below|the\s+following|the\s+next)\b"
        r"[^\n]{0,25}\b(?:commands?|scripts?|code|payloads?|snippets?|one[-\s]?liners?)\b",
        re.IGNORECASE,
    ),
    # Literal destructive shell commands — caught regardless of the English
    # framing around them, so a reworded injection still trips on its actual
    # payload. These tokens never legitimately appear in a SKILL.md body.
    re.compile(
        r"\brm\s+-[rf]{1,2}\b|\bdel\s+/[a-z]|\bformat\s+[a-z]:|\bmkfs\b|"
        r"\bdd\s+if=|\bchmod\s+[0-7]{3,4}\b|:\(\)\s*\{\s*:\s*\|\s*:|"
        r"\bshutdown\b\s+-|\bsudo\s+rm\b|>\s*/dev/sd",
        re.IGNORECASE,
    ),
    # Destructive action explicitly targeting the USER'S OWN environment
    # ("deletes local files", "wipe your disk", "encrypt all files on the
    # host"). The local/system/your/all qualifier on a filesystem noun is the
    # tell that separates an attack instruction from benign data work
    # ("removes duplicate rows from the staging files").
    re.compile(
        r"\b(?:delet|remov|wip|eras|destroy|overwrit|encrypt|exfiltrat|corrupt)\w*\b"
        r"[^\n]{0,30}\b(?:local|system|your|all)\b[^\n]{0,15}"
        r"\b(?:file|files|data|disk|drive|machine|directory|folder|host|home)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:read|cat|exfiltrate|exfil|dump|leak)\b[^\n]{0,80}"
        r"(?:~/\.ssh|id_rsa|\.env|credentials|secrets?)",
        re.IGNORECASE,
    ),
    re.compile(r"\bcurl\b[^\n]{0,200}\bhttps?://", re.IGNORECASE),
    re.compile(r"\bwget\b[^\n]{0,200}\bhttps?://", re.IGNORECASE),
    re.compile(r"```(?:bash|sh|shell|zsh|powershell|pwsh|cmd)\b", re.IGNORECASE),
    re.compile(r"<\s*tool[^>]*>|<\s*function[^>]*>", re.IGNORECASE),
    re.compile(r"\ballowed[-_ ]?tools\s*:", re.IGNORECASE),
    re.compile(r"```\s*ya?ml\s*\n\s*---", re.IGNORECASE),
    # Additions for the structured-output era (plan §Q1):
    re.compile(r"<\s*allowed-tools", re.IGNORECASE),
    re.compile(r"\bfile://", re.IGNORECASE),
    re.compile(r"\$\{[^}]+\}"),  # env-var exfil templating
]

# Hardcoded local paths — even if benign, they make the skill non-portable
# and violate Cowork's "don't hardcode file paths" best-practice.
_HARDCODED_PATH_PATTERNS = [
    re.compile(r"(?:^|[\s'\"`])/Users/[A-Za-z0-9._-]+", re.IGNORECASE),
    re.compile(r"(?:^|[\s'\"`])[A-Z]:\\Users\\[A-Za-z0-9._-]+", re.IGNORECASE),
    re.compile(r"(?:^|[\s'\"`])~/[A-Za-z0-9._/-]+"),
    re.compile(r"(?:^|[\s'\"`])/home/[A-Za-z0-9._-]+", re.IGNORECASE),
]


# Bundled progressive-disclosure files: markdown under references/, python
# under scripts/, JSON eval sets under evals/. Path must be safe (no
# traversal, no absolute, forward slashes, single subdir). Anything else is
# dropped at package time.
_BUNDLED_PATH_PATTERN = re.compile(
    r"^(references|scripts|evals)/[a-z0-9][a-z0-9._-]*\.(md|py|json)$"
)
_BUNDLED_SUBDIR_EXT = {"references": "md", "scripts": "py", "evals": "json"}


def validate_bundled_path(relpath: str) -> str | None:
    """Return None if the bundled-file relpath is safe, else a reason string."""
    if not relpath:
        return "empty path"
    if "\\" in relpath or ".." in relpath or relpath.startswith("/"):
        return "path traversal or absolute path not allowed"
    m = _BUNDLED_PATH_PATTERN.match(relpath)
    if not m:
        return (
            "must be references/<name>.md, scripts/<name>.py, or "
            "evals/<name>.json (lowercase, single subdir)"
        )
    subdir, ext = m.group(1), m.group(2)
    if _BUNDLED_SUBDIR_EXT[subdir] != ext:
        return f"{subdir}/ files must be .{_BUNDLED_SUBDIR_EXT[subdir]}"
    return None


# --- Bundled-script content safety ---------------------------------------
#
# Bundled `scripts/*.py` files are LLM-authored from adversarial web/hiring
# evidence and ship verbatim into agent hosts (Claude/Cursor/Cowork) that may
# execute them. A path-only check is a supply-chain RCE hole, so we AST-scan
# every Python script for the constructs a "deterministic helper (parsing,
# validation, a calculation)" never needs and an exfiltration payload always
# does: process execution, network egress, dynamic eval/exec, credential/env
# reads, destructive filesystem calls, and file-writes. Any hit is fail-closed.
#
# AST (not regex) so the scan can't be bypassed by string-concatenation,
# whitespace, or comment tricks. A script that doesn't parse is itself
# rejected — a real helper is "complete and runnable" per the authoring prompt.

# Importing any of these modules from a deterministic helper is disqualifying:
# process control, raw network, remote shells, and (de)serialization RCE sinks.
_DANGEROUS_IMPORT_MODULES = frozenset(
    {
        "subprocess",
        "socket",
        "requests",
        "httpx",
        "urllib",
        "http",
        "ftplib",
        "telnetlib",
        "smtplib",
        "poplib",
        "imaplib",
        "paramiko",
        "pickle",
        "marshal",
        "ctypes",
        "pty",
        "shutil",
        "multiprocessing",
    }
)

# Fully-qualified calls that are disqualifying regardless of imports.
_DANGEROUS_CALL_NAMES = frozenset(
    {
        "eval",
        "exec",
        "compile",
        "__import__",
        "breakpoint",
        "os.system",
        "os.popen",
        "os.remove",
        "os.unlink",
        "os.rmdir",
        "os.removedirs",
        "os.rename",
        "os.replace",
        "os.chmod",
        "os.chown",
        "os.kill",
        "os.fork",
        "os.putenv",
        "os.setuid",
    }
)

# Attribute prefixes for the os.exec*/os.spawn* process-replacement family.
_DANGEROUS_CALL_PREFIXES = ("os.exec", "os.spawn")

# Attribute reads that pull credentials / secrets out of the environment —
# the classic first half of an exfiltration chain.
_SECRET_ATTRS = frozenset({"os.environ"})


def _dotted_name(node: ast.AST) -> str:
    """Reconstruct a dotted attribute/name chain (``os.path.join``) from an
    AST node. Returns "" when the base isn't a plain Name (e.g. a call or
    subscript), which the caller treats as unresolvable rather than safe."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _is_write_open(call: ast.Call) -> bool:
    """True when a call is ``open(..., 'w'|'a'|'x'|'+')`` — a filesystem write."""
    if _dotted_name(call.func) not in ("open", "io.open"):
        return False
    mode = None
    if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant):
        mode = call.args[1].value
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            mode = kw.value.value
    return isinstance(mode, str) and any(c in mode for c in ("w", "a", "x", "+"))


def _scan_python_script(content: str) -> str | None:
    """Return a reason string if a bundled Python script is unsafe, else None."""
    try:
        tree = ast.parse(content)
    except SyntaxError as exc:
        return f"script is not valid, runnable Python (does not parse): {exc.msg}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _DANGEROUS_IMPORT_MODULES:
                    return f"imports disallowed module {alias.name!r}"
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in _DANGEROUS_IMPORT_MODULES:
                return f"imports from disallowed module {node.module!r}"
        elif isinstance(node, ast.Call):
            name = _dotted_name(node.func)
            if name:
                if name in _DANGEROUS_CALL_NAMES or name.startswith(_DANGEROUS_CALL_PREFIXES):
                    return f"calls disallowed function {name}()"
                if name.split(".")[0] in _DANGEROUS_IMPORT_MODULES:
                    return f"calls into disallowed module via {name}()"
            if _is_write_open(node):
                return "opens a file for writing (helpers must be read-only)"
        elif isinstance(node, ast.Attribute):
            if _dotted_name(node) in _SECRET_ATTRS:
                return "reads credentials/secrets from os.environ"
    return None


def scan_bundled_content(relpath: str, content: str) -> str | None:
    """Return a reason string if a bundled file's CONTENT is unsafe, else None.

    Runs the agent-instruction (injection) and hardcoded-path filters over all
    authored bundled content, plus a strict AST danger-scan over ``scripts/*.py``.
    ``evals/*.json`` is intentionally skipped: it is primr-generated (not the
    adversarial authoring vector) and may legitimately embed adversarial test
    strings that the injection filter would false-positive on.

    Used by both the validator (HARD SEC-BUNDLE finding) and the packager
    (defense-in-depth file drop) so unreviewed executable/injected content
    can never reach the Claude tree or the Cowork zip.
    """
    if relpath.endswith(".json"):
        return None
    hit = _find_injection_match(content)
    if hit:
        return f"agent-instruction pattern in bundled content: {hit[:80]}"
    path_hit = _find_hardcoded_path(content)
    if path_hit:
        return f"hardcoded local path in bundled content: {path_hit}"
    if relpath.endswith(".py"):
        danger = _scan_python_script(content)
        if danger:
            return f"unsafe Python helper: {danger}"
    return None


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def _approx_token_count(text: str) -> int:
    """Approximate token count using the standard 4-chars-per-token heuristic.

    Avoids pulling tiktoken as a hard dep. The HARD-fail threshold has a
    generous margin so the approximation is safe.
    """
    return len(text) // 4


def _find_injection_match(text: str) -> str | None:
    """Return the first agent-instruction pattern hit, or None."""
    if not text:
        return None
    for pattern in _AGENT_INSTRUCTION_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(0)
    return None


def _find_hardcoded_path(text: str) -> str | None:
    if not text:
        return None
    for pattern in _HARDCODED_PATH_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(0).strip()
    return None


# Split the trigger tail into enumerated intents on list separators only.
# Deliberately NOT splitting on "and": "review and report on X" is one intent,
# and splitting on "and" inflated the count enough to pass thin descriptions.
_INTENT_SPLIT_RE = re.compile(r",|;|\bor\b|/", re.IGNORECASE)


def _count_trigger_intents(desc: str) -> int:
    """Count the distinct user-intent phrases a description advertises.

    Primary signal: the enumeration after the trigger phrase ("Use when the
    user asks to X, Y, or Z" → 3). We split the trigger tail on commas /
    semicolons / and / or / slashes and count clauses with real content
    (>=2 words). Falls back to a verb-keyword count across the whole
    description when there is no explicit trigger phrase, so a description
    that signals intent without the canonical "Use when..." form still
    scores. This is deliberately generous: under-counting a well-formed
    description (the old failure mode) is worse than over-counting.
    """
    if not desc:
        return 0
    match = _TRIGGER_PATTERN.search(desc)
    if match is None:
        return len(_PUSHY_KEYWORD_PATTERN.findall(desc))
    tail = desc[match.end() :]
    clauses = [c for c in _INTENT_SPLIT_RE.split(tail) if len(c.split()) >= 2]
    # The trigger phrase itself implies one intent even if nothing parses out.
    intents = max(len(clauses), 1)
    # Never score below the whole-description verb count — a long prose
    # description with many verbs but few commas still advertises intent.
    return max(intents, len(_PUSHY_KEYWORD_PATTERN.findall(desc)))


def _looks_like_product_name(name: str, display_name: str) -> bool:
    """True when a skill title reads as a bare product/feature rather than a
    task. Fires only when the name contains a known brand token AND carries
    no task/verb token — so `azure-front-door` flags but
    `configuring-azure-front-door` does not.
    """
    tokens = [t for t in re.split(r"[-\s]+", name.lower()) if t]
    if not tokens:
        return False
    has_brand = any(t in _PRODUCT_BRAND_TOKENS for t in tokens)
    if not has_brand:
        return False
    # Any verb/gerund/nominalized-action token anywhere in the kebab name OR
    # the display name rescues it (the title names an action on the product).
    display_tokens = [t for t in re.split(r"[-\s]+", display_name.lower()) if t]
    has_task = any(_TASK_TOKEN_PATTERN.search(t) for t in tokens + display_tokens)
    return not has_task


def _has_required_sections(body: str) -> list[str]:
    """Return the list of REQUIRED sections that are MISSING from body."""
    missing: list[str] = []
    for section in _REQUIRED_BODY_SECTIONS:
        pattern = re.compile(rf"^##\s+{re.escape(section)}\s*$", re.IGNORECASE | re.MULTILINE)
        if not pattern.search(body):
            missing.append(section)
    return missing


def validate_kebab_case(name: str) -> bool:
    """Public helper for use outside the pipeline (e.g. CLI input parsing)."""
    if not name or len(name) > _MAX_NAME_LEN:
        return False
    return bool(_KEBAB_PATTERN.match(name))


def is_body_too_short(body: str) -> bool:
    """True when a skill body is under the soft word floor. Public so the
    refiner can treat a too-short body (but not a too-long one) as an
    actionable finding worth one expansion turn."""
    return _word_count(body) < _BODY_MIN_WORDS


def validate_skill(skill: Skill, role_name: str) -> list[SkillIssue]:
    """Validate one Skill and return any findings."""
    issues: list[SkillIssue] = []

    # ASKILL-P006/P007: name shape + folder match
    if not validate_kebab_case(skill.name):
        issues.append(
            SkillIssue(
                code="ASKILL-P007",
                severity=IssueSeverity.HARD,
                message=(
                    f"name {skill.name!r} is not kebab-case "
                    "(lowercase alphanumeric + single internal hyphens, 1-64 chars)"
                ),
                role_name=role_name,
                field="name",
                excerpt=skill.name[:80],
            )
        )

    # DESC-LEN
    desc = skill.description or ""
    if not (_MIN_DESC_LEN <= len(desc) <= _MAX_DESC_LEN):
        issues.append(
            SkillIssue(
                code="DESC-LEN",
                severity=IssueSeverity.HARD,
                message=(
                    f"description length {len(desc)} outside [{_MIN_DESC_LEN}, {_MAX_DESC_LEN}]"
                ),
                role_name=role_name,
                field="description",
                excerpt=desc[:120],
            )
        )

    # DESC-TRIG
    if not _TRIGGER_PATTERN.search(desc):
        issues.append(
            SkillIssue(
                code="DESC-TRIG",
                severity=IssueSeverity.HARD,
                message=(
                    "description lacks an explicit trigger phrase (e.g. 'Use when user asks to...')"
                ),
                role_name=role_name,
                field="description",
                excerpt=desc[:120],
            )
        )

    # DESC-VOICE — Anthropic: third-person only. First/second-person
    # pronouns in the description clash with the system-prompt POV and
    # degrade discovery. SOFT so existing packs don't break instantly.
    if desc and _FIRST_PERSON_PATTERN.search(desc):
        issues.append(
            SkillIssue(
                code="DESC-VOICE",
                severity=IssueSeverity.SOFT,
                message=(
                    "description uses first/second-person voice; Anthropic "
                    "recommends third person (e.g. 'Processes contracts' "
                    "not 'I help review contracts')"
                ),
                role_name=role_name,
                field="description",
                excerpt=desc[:120],
            )
        )

    # DESC-PUSHY — Anthropic explicitly recommends descriptions be a "little
    # bit pushy", advertising multiple concrete user intents to combat
    # undertriggering. We count distinct intents (enumerated clauses after the
    # trigger phrase), not raw keyword hits, so a well-formed enumeration that
    # uses verbs outside the keyword set is not falsely flagged.
    if desc:
        intents = _count_trigger_intents(desc)
        if intents < _MIN_TRIGGER_INTENTS:
            issues.append(
                SkillIssue(
                    code="DESC-PUSHY",
                    severity=IssueSeverity.SOFT,
                    message=(
                        f"description advertises only {intents} distinct user "
                        f"intent(s); Anthropic recommends listing multiple "
                        f"concrete triggers (e.g. 'Use when the user asks to X, "
                        f"Y, or Z') to combat undertriggering"
                    ),
                    role_name=role_name,
                    field="description",
                    excerpt=desc[:120],
                )
            )

    # NAME-GERUND — soft hint, not a fail. Gerund form ("processing-pdfs")
    # is preferred per Anthropic. Noun phrases are explicitly acceptable
    # too, so this stays SOFT and informational.
    if skill.name and not _GERUND_HINT_PATTERN.match(skill.name):
        issues.append(
            SkillIssue(
                code="NAME-GERUND",
                severity=IssueSeverity.SOFT,
                message=(
                    "name does not use gerund form (verb + -ing); "
                    "Anthropic recommends gerund for clearer capability "
                    "description (e.g. 'drafting-models' over 'draft-models')"
                ),
                role_name=role_name,
                field="name",
                excerpt=skill.name,
            )
        )

    # NAME-PRODUCT — a skill title should name a task, not a bare product /
    # feature ("azure-front-door", "aks"). SOFT: refinement re-scopes the
    # title to the job the person uses that product to do.
    if skill.name and _looks_like_product_name(skill.name, skill.display_name or ""):
        issues.append(
            SkillIssue(
                code="NAME-PRODUCT",
                severity=IssueSeverity.SOFT,
                message=(
                    "name reads as a bare product/feature, not a task; "
                    "re-scope to the capability the product is used for "
                    "(e.g. 'configuring-edge-routing' not 'azure-front-door')"
                ),
                role_name=role_name,
                field="name",
                excerpt=skill.name,
            )
        )

    # BODY-SEC
    missing_sections = _has_required_sections(skill.body)
    if missing_sections:
        issues.append(
            SkillIssue(
                code="BODY-SEC",
                severity=IssueSeverity.HARD,
                message=f"body is missing required H2 section(s): {', '.join(missing_sections)}",
                role_name=role_name,
                field="body",
            )
        )

    # BODY-LEN
    words = _word_count(skill.body)
    tokens = _approx_token_count(skill.body)
    if tokens > _BODY_HARD_MAX_WORDS:
        issues.append(
            SkillIssue(
                code="BODY-LEN",
                severity=IssueSeverity.HARD,
                message=(
                    f"body exceeds hard token cap (~{tokens} tokens > {_BODY_HARD_MAX_WORDS})"
                ),
                role_name=role_name,
                field="body",
            )
        )
    elif words < _BODY_MIN_WORDS:
        issues.append(
            SkillIssue(
                code="BODY-LEN",
                severity=IssueSeverity.HARD,
                message=(
                    f"body word count {words} is below the minimum "
                    f"{_BODY_MIN_WORDS}; thin skills are not shipped"
                ),
                role_name=role_name,
                field="body",
            )
        )
    elif words > _BODY_TARGET_MAX_WORDS:
        issues.append(
            SkillIssue(
                code="BODY-LEN",
                severity=IssueSeverity.SOFT,
                message=(
                    f"body word count {words} outside target "
                    f"[{_BODY_MIN_WORDS}, {_BODY_TARGET_MAX_WORDS}]"
                ),
                role_name=role_name,
                field="body",
            )
        )

    # BODY-QUALITY
    missing_markers = missing_quality_markers(skill.body)
    if missing_markers:
        issues.append(
            SkillIssue(
                code="BODY-QUALITY",
                severity=IssueSeverity.HARD,
                message=(
                    "body is missing required quality marker(s): "
                    + ", ".join(missing_markers)
                    + ". "
                    + quality_marker_guidance(missing_markers)
                ),
                role_name=role_name,
                field="body",
            )
        )

    # SEC-INJECT — run across every string field
    for field_name, content in [
        ("name", skill.name),
        ("display_name", skill.display_name),
        ("description", skill.description),
        ("body", skill.body),
    ]:
        hit = _find_injection_match(content)
        if hit:
            issues.append(
                SkillIssue(
                    code="SEC-INJECT",
                    severity=IssueSeverity.HARD,
                    message=f"agent-instruction pattern detected in {field_name}",
                    role_name=role_name,
                    field=field_name,
                    excerpt=hit[:120],
                )
            )

    # BUNDLE-PATH — progressive-disclosure files must use safe references/ or
    # scripts/ paths. SOFT: the packager drops an unsafe file rather than
    # failing the whole skill.
    for bf in skill.bundled_files:
        reason = validate_bundled_path(bf.relpath)
        if reason:
            issues.append(
                SkillIssue(
                    code="BUNDLE-PATH",
                    severity=IssueSeverity.SOFT,
                    message=f"bundled file {bf.relpath!r} rejected: {reason}",
                    role_name=role_name,
                    field="bundled_files",
                    excerpt=bf.relpath[:120],
                )
            )

    # SEC-BUNDLE — scan bundled-file CONTENT, not just the path. Bundled
    # scripts/*.py and references/*.md are LLM-authored from adversarial
    # evidence and ship verbatim to downstream agent hosts that may execute
    # them, so a path-only gate is a supply-chain hole. HARD: a content hit
    # drops the role (fail closed — no unreviewed executable/injected content
    # ships). The packager re-checks this as defense-in-depth.
    for bf in skill.bundled_files:
        unsafe = scan_bundled_content(bf.relpath, bf.content)
        if unsafe:
            issues.append(
                SkillIssue(
                    code="SEC-BUNDLE",
                    severity=IssueSeverity.HARD,
                    message=f"bundled file {bf.relpath!r}: {unsafe}",
                    role_name=role_name,
                    field="bundled_files",
                    excerpt=bf.relpath[:120],
                )
            )

    # SEC-PATH
    path_hit = _find_hardcoded_path(skill.body)
    if path_hit:
        issues.append(
            SkillIssue(
                code="SEC-PATH",
                severity=IssueSeverity.HARD,
                message=f"hardcoded local path in body: {path_hit}",
                role_name=role_name,
                field="body",
                excerpt=path_hit[:120],
            )
        )

    return issues


def validate_role(role: Role) -> list[SkillIssue]:
    """Validate one Role (its skills, plus role-level checks)."""
    issues: list[SkillIssue] = []

    if not validate_kebab_case(role.name):
        issues.append(
            SkillIssue(
                code="ASKILL-P007",
                severity=IssueSeverity.HARD,
                message=f"role name {role.name!r} is not kebab-case",
                role_name=role.name,
                field="name",
                excerpt=role.name[:80],
            )
        )

    if not role.skills:
        issues.append(
            SkillIssue(
                code="ROLE-EMPTY",
                severity=IssueSeverity.HARD,
                message="role has no skills attached",
                role_name=role.name,
            )
        )

    # SEC-INJECT on role metadata. display_name / confidence / summary can come
    # from job postings, research evidence, LLM planning, saved plans, or
    # operator labels, and the packager can emit display_name + confidence into
    # SKILL.md frontmatter (primr-role / primr-confidence) when metadata is
    # enabled. Without
    # this scan an attacker who influences role discovery could land a
    # prompt-injection string in agent-consumed metadata even though every
    # Skill field passed SEC-INJECT. HARD: a hit drops the role (fail closed).
    for field_name, content in [
        ("display_name", role.display_name),
        ("confidence", role.confidence),
        ("summary", role.summary or ""),
    ]:
        hit = _find_injection_match(content)
        if hit:
            issues.append(
                SkillIssue(
                    code="SEC-INJECT",
                    severity=IssueSeverity.HARD,
                    message=f"agent-instruction pattern detected in role {field_name}",
                    role_name=role.name,
                    field=field_name,
                    excerpt=hit[:120],
                )
            )

    for skill in role.skills:
        issues.extend(validate_skill(skill, role.name))

    return issues


def _similarity(a: str, b: str) -> float:
    """Cheap similarity for the pack-level overlap check.

    Uses difflib (stdlib, no extra deps). Cosine on TF-IDF would be more
    accurate but the threshold is intentionally generous (0.85) so the
    sequence-ratio comparison is sufficient as a soft warning.
    """
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


_OVERLAP_THRESHOLD = 0.85


def validate_pack(pack: SkillPack) -> ValidationReport:
    """Run all skill-level + role-level + pack-level validation.

    Mutates nothing; the caller decides whether to drop, refine, or ship.
    """
    issues: list[SkillIssue] = []

    for role in pack.roles:
        issues.extend(validate_role(role))

    # Pack-level overlap: compare every pair of skills' name+description.
    # Only emit one SOFT issue per pair (refinement may collapse duplicates).
    seen_pairs: set[tuple[str, str]] = set()
    all_skills: list[tuple[str, Skill]] = [(r.name, s) for r in pack.roles for s in r.skills]
    for i, (r1, s1) in enumerate(all_skills):
        for r2, s2 in all_skills[i + 1 :]:
            if r1 == r2 and s1.name == s2.name:
                continue
            pair_key = tuple(sorted([f"{r1}/{s1.name}", f"{r2}/{s2.name}"]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)  # type: ignore[arg-type]
            sig1 = f"{s1.display_name} :: {s1.description[:200]}"
            sig2 = f"{s2.display_name} :: {s2.description[:200]}"
            sim = _similarity(sig1, sig2)
            if sim >= _OVERLAP_THRESHOLD:
                issues.append(
                    SkillIssue(
                        code="PACK-OVERLAP",
                        severity=IssueSeverity.SOFT,
                        message=(
                            f"skills {r1}/{s1.name} and {r2}/{s2.name} have "
                            f"{sim:.2f} similarity (>= {_OVERLAP_THRESHOLD})"
                        ),
                    )
                )

    return ValidationReport(issues=issues)


__all__ = [
    "scan_bundled_content",
    "validate_bundled_path",
    "validate_kebab_case",
    "validate_pack",
    "validate_role",
    "validate_skill",
]
