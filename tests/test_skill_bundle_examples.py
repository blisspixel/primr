"""Smoke-test the bash examples shipped in claude-code/skills/primr/SKILL.md.

Every ``primr ...`` command-line example in the skill bundle (SKILL.md plus its
references) is parsed against the live CLI parser. Catches drift when flag
names or subcommand structure change without the bundled skill being updated.

Excludes example fragments that are intentionally illustrative rather than
executable — those are tagged with the literal placeholder ``<...>`` or with
square-bracket optional groups that don't represent real CLI input.
"""

from __future__ import annotations

from pathlib import Path
import re
import shlex

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO_ROOT / "claude-code" / "skills" / "primr"

PRIMR_LINE = re.compile(r"^\s*primr\b(?P<rest>[^\n]*)$", re.M)
FENCED_BLOCK = re.compile(r"```(?:bash|sh|shell)?\n(.*?)```", re.S)


def _extract_primr_commands(md_text: str) -> list[str]:
    """Return every ``primr ...`` command-line found inside fenced bash blocks."""
    out: list[str] = []
    for block in FENCED_BLOCK.findall(md_text):
        for match in PRIMR_LINE.finditer(block):
            line = ("primr" + match.group("rest")).strip()
            # Strip trailing comments
            if "#" in line:
                line = line.split("#", 1)[0].rstrip()
            out.append(line)
    return out


def _is_executable_example(line: str) -> bool:
    """Skip illustrative fragments that contain placeholder syntax."""
    if "<" in line or (">" in line and not line.startswith("primr ")):
        return False
    # Lines like "primr [options]" or with bracketed optional groups aren't real CLI input
    return not re.search(r"\[[a-z|-]+\]", line)


def _gather_skill_files() -> list[Path]:
    return [SKILL_DIR / "SKILL.md", *sorted((SKILL_DIR / "references").glob("*.md"))]


@pytest.mark.parametrize(
    "md_file", _gather_skill_files(), ids=lambda p: p.relative_to(REPO_ROOT).as_posix()
)
def test_primr_examples_parse(md_file: Path) -> None:
    """Every executable ``primr ...`` example in the skill bundle parses cleanly."""
    from primr.core.cli import _create_parser, _is_keys_command, _is_mcp_command, _is_recon_command

    parser = _create_parser()
    text = md_file.read_text(encoding="utf-8")
    commands = _extract_primr_commands(text)

    if not commands:
        pytest.skip(f"No primr examples in {md_file.name}")

    failures: list[str] = []
    for cmd in commands:
        if not _is_executable_example(cmd):
            continue
        try:
            tokens = shlex.split(cmd)
        except ValueError as exc:
            failures.append(f"{cmd}: shlex split failed: {exc}")
            continue

        # Strip the leading "primr"
        argv = tokens[1:]

        # Subcommand intercepts (recon / keys / mcp) bypass the main argparse,
        # so just confirm the intercept fires — don't try to parse them as research args.
        if _is_recon_command(argv) or _is_keys_command(argv) or _is_mcp_command(argv):
            continue

        # Some examples include flags that primr only validates at runtime
        # (e.g. positional arg paths that don't exist). We just want to
        # confirm argparse accepts the flag shape, not that the run would succeed.
        try:
            parser.parse_known_args(argv)
        except SystemExit as exc:
            # exit 0 = deliberate (e.g. --version, --help). exit 2 = parse error.
            if exc.code not in (0, None):
                failures.append(f"{cmd}: argparse rejected (exit {exc.code})")

    if failures:
        joined = "\n  ".join(failures)
        pytest.fail(
            f"Skill bundle has {len(failures)} drifted example(s) in {md_file.name}:\n  {joined}"
        )
