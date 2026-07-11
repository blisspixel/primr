from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from primr.ai.capability_routing import BackendKind, BillingMode
from primr.ai.host_agent_cli import (
    CodexCliHostAgentRunner,
    HostAgentExecutionError,
    codex_cli_backend,
)
from primr.ai.host_agent_runner import (
    HostAgentBillingMode,
    HostAgentKind,
    HostAgentPolicy,
    HostAgentStagePacket,
    HostAgentUnavailableError,
)


def test_codex_cli_runner_reports_unavailable() -> None:
    runner = CodexCliHostAgentRunner(which=lambda _: None)

    assert runner.is_available() is False
    with pytest.raises(HostAgentUnavailableError, match="codex CLI"):
        runner.run(HostAgentStagePacket(stage_id="s", role="utility", instructions="Run."))


def test_codex_cli_runner_invokes_bounded_exec_command(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_run(
        args: Sequence[str],
        *,
        input: str,
        text: bool,
        capture_output: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        captured["args"] = list(args)
        captured["input"] = input
        captured["text"] = text
        captured["capture_output"] = capture_output
        captured["timeout"] = timeout
        output_path = Path(args[args.index("--output-last-message") + 1])
        output_path.write_text("[1, 2, 3]", encoding="utf-8")
        schema_path = Path(args[args.index("--output-schema") + 1])
        captured["schema"] = json.loads(schema_path.read_text(encoding="utf-8"))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    runner = CodexCliHostAgentRunner(
        workdir=tmp_path,
        model="gpt-5-codex",
        profile="primr-host",
        which=lambda _: "C:/tools/codex.cmd",
        run_command=fake_run,
    )

    result = runner.run(
        HostAgentStagePacket(
            stage_id="fast.source_relevance",
            role="utility",
            instructions="Return source ids.",
            output_schema={"type": "array", "items": {"type": "integer"}},
            policy=HostAgentPolicy(billing_mode=HostAgentBillingMode.HOST_PLAN_USAGE),
        )
    )

    args = captured["args"]
    assert isinstance(args, list)
    assert args[:2] == ["C:/tools/codex.cmd", "exec"]
    assert args[args.index("--cd") + 1] == str(tmp_path)
    assert args[args.index("--ask-for-approval") + 1] == "never"
    assert args[args.index("--sandbox") + 1] == "read-only"
    assert "--ephemeral" in args
    assert "--skip-git-repo-check" in args
    assert 'web_search="disabled"' in args
    assert "features.shell_tool=false" in args
    assert 'history.persistence="none"' in args
    assert args[args.index("--model") + 1] == "gpt-5-codex"
    assert args[args.index("--profile") + 1] == "primr-host"
    assert args[-1] == "-"
    assert captured["timeout"] == 600
    assert "Do not fetch URLs, run shell commands, or write files." in str(captured["input"])
    assert captured["schema"] == {"items": {"type": "integer"}, "type": "array"}
    assert result.runner is HostAgentKind.CODEX
    assert result.billing_mode is HostAgentBillingMode.HOST_PLAN_USAGE
    assert result.text == "[1, 2, 3]"
    assert result.metadata["transport"] == "codex_cli_exec"
    assert result.metadata["web_search"] == "disabled"
    assert result.metadata["shell_tool"] is False


def test_codex_cli_runner_does_not_invoke_exec_with_unknown_billing(tmp_path: Path) -> None:
    invoked = False

    def fake_run(
        args: Sequence[str],
        *,
        input: str,
        text: bool,
        capture_output: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        nonlocal invoked
        invoked = True
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    runner = CodexCliHostAgentRunner(
        workdir=tmp_path,
        which=lambda _: "codex",
        run_command=fake_run,
    )

    with pytest.raises(HostAgentUnavailableError, match="billing mode is unverified"):
        runner.run(HostAgentStagePacket(stage_id="s", role="utility", instructions="Run."))

    assert invoked is False


def test_codex_cli_runner_raises_on_failed_exec(tmp_path: Path) -> None:
    def fake_run(
        args: Sequence[str],
        *,
        input: str,
        text: bool,
        capture_output: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 2, stdout="", stderr="blocked")

    runner = CodexCliHostAgentRunner(
        workdir=tmp_path,
        which=lambda _: "codex",
        run_command=fake_run,
    )

    with pytest.raises(HostAgentExecutionError, match="exit code 2"):
        runner.run(
            HostAgentStagePacket(
                stage_id="s",
                role="utility",
                instructions="Run.",
                policy=HostAgentPolicy(billing_mode=HostAgentBillingMode.HOST_PLAN_USAGE),
            )
        )


def test_codex_cli_backend_is_official_host_runner() -> None:
    backend = codex_cli_backend(
        available=True,
        billing_mode=BillingMode.UNKNOWN,
    )

    assert backend.backend_id == "codex-cli"
    assert backend.kind is BackendKind.HOST_AGENT
    assert backend.billing_mode is BillingMode.UNKNOWN
    assert backend.official_host_runner is True
    assert backend.available is True
    assert backend.metadata["runner"] == "codex"


def test_codex_cli_backend_preserves_explicit_plan_billing() -> None:
    backend = codex_cli_backend(
        available=True,
        billing_mode=BillingMode.HOST_PLAN_USAGE,
    )

    assert backend.billing_mode is BillingMode.HOST_PLAN_USAGE
