"""Official CLI-backed host-agent runners.

These transports are deliberately narrow: Primr owns the pipeline stage,
packet, timeout, schema, filesystem policy, and web-search policy. The host
agent only produces bounded stage text.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol

from primr.ai.capability_routing import (
    BackendCapabilities,
    BackendKind,
    BillingMode,
    LatencyClass,
    ReasoningDepth,
    TrustSensitivity,
)
from primr.ai.host_agent_runner import (
    HostAgentBillingMode,
    HostAgentKind,
    HostAgentResult,
    HostAgentRunner,
    HostAgentStagePacket,
    HostAgentUnavailableError,
    render_host_agent_prompt,
)
from primr.ai.routing import Role

CODEX_CLI_BACKEND_ID = "codex-cli"


class HostAgentExecutionError(RuntimeError):
    """Raised when an available host-agent runner cannot complete a stage."""


class RunCommand(Protocol):
    """Callable shape used to invoke subprocesses in tests and production."""

    def __call__(
        self,
        args: Sequence[str],
        *,
        input: str,
        text: bool,
        capture_output: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]: ...


class CodexCliHostAgentRunner(HostAgentRunner):
    """Run a bounded stage packet through official `codex exec` automation."""

    def __init__(
        self,
        *,
        executable: str = "codex",
        workdir: str | Path | None = None,
        model: str | None = None,
        profile: str | None = None,
        which: Callable[[str], str | None] = shutil.which,
        run_command: RunCommand = subprocess.run,
    ) -> None:
        self.executable = executable
        self.workdir = Path.cwd() if workdir is None else Path(workdir)
        self.model = model
        self.profile = profile
        self._which = which
        self._run_command = run_command

    @property
    def kind(self) -> HostAgentKind:
        """Return the host-agent family this runner uses."""

        return HostAgentKind.CODEX

    def is_available(self) -> bool:
        """Return True when the Codex CLI executable is available.

        This transport check does not establish how the CLI is authenticated or
        billed. Routing and execution therefore require a separately verified
        billing policy before treating the runner as usable.
        """

        return self._resolved_executable() is not None

    def run(self, packet: HostAgentStagePacket) -> HostAgentResult:
        """Execute the packet through `codex exec` and return final text."""

        executable = self._resolved_executable()
        if executable is None:
            raise HostAgentUnavailableError("codex CLI is not installed or not on PATH")
        if packet.policy.billing_mode is HostAgentBillingMode.UNKNOWN:
            raise HostAgentUnavailableError("codex CLI billing mode is unverified")

        prompt = render_host_agent_prompt(packet)
        with tempfile.TemporaryDirectory(prefix="primr-codex-stage-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            output_path = temp_dir / "final.txt"
            schema_path = self._write_schema(packet.output_schema, temp_dir)
            command = self._build_command(executable, output_path, schema_path)
            completed = self._run_codex(command, prompt, packet.policy.max_wall_seconds)
            if completed.returncode != 0:
                raise HostAgentExecutionError(
                    f"codex exec failed with exit code {completed.returncode}"
                )
            text = self._read_output(output_path)

        if len(text) > packet.policy.max_output_chars:
            raise HostAgentExecutionError("codex exec output exceeded max_output_chars")
        return HostAgentResult(
            runner=HostAgentKind.CODEX,
            text=text,
            billing_mode=packet.policy.billing_mode,
            metadata={
                "transport": "codex_cli_exec",
                "sandbox": "read-only",
                "web_search": "disabled",
                "shell_tool": False,
                "output_schema": packet.output_schema is not None,
                "output_chars": len(text),
            },
        )

    def _resolved_executable(self) -> str | None:
        found = self._which(self.executable)
        return found if found else None

    def _build_command(
        self,
        executable: str,
        output_path: Path,
        schema_path: Path | None,
    ) -> list[str]:
        command = [
            executable,
            "exec",
            "--cd",
            str(self.workdir),
            "--ask-for-approval",
            "never",
            "--sandbox",
            "read-only",
            "--color",
            "never",
            "--ephemeral",
            "--skip-git-repo-check",
            "--output-last-message",
            str(output_path),
            "-c",
            'web_search="disabled"',
            "-c",
            "features.shell_tool=false",
            "-c",
            'history.persistence="none"',
        ]
        if self.model:
            command.extend(("--model", self.model))
        if self.profile:
            command.extend(("--profile", self.profile))
        if schema_path is not None:
            command.extend(("--output-schema", str(schema_path)))
        command.append("-")
        return command

    def _run_codex(
        self,
        command: Sequence[str],
        prompt: str,
        timeout_seconds: int,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return self._run_command(
                command,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise HostAgentExecutionError("codex exec timed out") from exc

    @staticmethod
    def _write_schema(output_schema: Mapping[str, object] | None, temp_dir: Path) -> Path | None:
        if output_schema is None:
            return None
        schema_path = temp_dir / "schema.json"
        schema_path.write_text(
            json.dumps(dict(output_schema), sort_keys=True),
            encoding="utf-8",
        )
        return schema_path

    @staticmethod
    def _read_output(output_path: Path) -> str:
        if not output_path.exists():
            raise HostAgentExecutionError("codex exec did not write final output")
        return output_path.read_text(encoding="utf-8").strip()


def codex_cli_backend(
    *,
    available: bool | None = None,
    billing_mode: BillingMode | str = BillingMode.UNKNOWN,
) -> BackendCapabilities:
    """Return the Codex CLI host-runner capability row."""

    is_available = CodexCliHostAgentRunner().is_available() if available is None else available
    return BackendCapabilities(
        backend_id=CODEX_CLI_BACKEND_ID,
        kind=BackendKind.HOST_AGENT,
        roles=(Role.UTILITY,),
        reasoning_depth=ReasoningDepth.MEDIUM,
        max_trust_sensitivity=TrustSensitivity.MEDIUM,
        max_context_tokens=128_000,
        supports_structured_output=True,
        latency_class=LatencyClass.STANDARD,
        billing_mode=billing_mode,
        available=is_available,
        official_host_runner=True,
        metadata={
            "runner": HostAgentKind.CODEX.value,
            "transport": "codex_cli_exec",
            "sandbox": "read-only",
            "web_search": "disabled",
        },
    )


def supported_host_agent_backends() -> tuple[BackendCapabilities, ...]:
    """Return supported official host-agent backends for runtime routing."""

    return (codex_cli_backend(),)


def run_host_agent_stage(
    packet: HostAgentStagePacket,
    *,
    kind: HostAgentKind | str = HostAgentKind.CODEX,
) -> HostAgentResult:
    """Run one stage packet through the selected official host-agent runner."""

    selected = HostAgentKind(kind)
    if selected is HostAgentKind.CODEX:
        return CodexCliHostAgentRunner().run(packet)
    raise HostAgentUnavailableError(f"Unsupported host-agent runner: {selected.value}")
