"""Validated input and option boundary for one research CLI request."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from primr.core.cli_batch import _ensure_valid_url
from primr.core.cli_command_output import report_command_error
from primr.core.cli_inference import (
    configure_inference_runtime,
    prepare_inference_runtime,
    validate_inference_options,
)
from primr.utils import validators
from primr.utils.console import console

_FULL_RESEARCH_MODES = ("complete", "structured", "hybrid")


class _ResearchConfig(Protocol):
    @property
    def company_name(self) -> str | None:
        raise NotImplementedError

    @property
    def website(self) -> str | None:
        raise NotImplementedError

    @property
    def premium_mode(self) -> bool:
        raise NotImplementedError

    @property
    def fast_mode(self) -> bool:
        raise NotImplementedError

    @property
    def mode(self) -> str:
        raise NotImplementedError

    @property
    def json_output(self) -> bool:
        raise NotImplementedError

    @property
    def skip_confirm(self) -> bool:
        raise NotImplementedError

    @property
    def inference_profile(self) -> str:
        raise NotImplementedError

    @property
    def acknowledge_host_agent_may_bill(self) -> bool:
        raise NotImplementedError

    @property
    def context_files(self) -> tuple[str, ...]:
        raise NotImplementedError

    @property
    def context_folder(self) -> str | None:
        raise NotImplementedError


@dataclass(frozen=True)
class ValidatedResearchRequest:
    """Normalized user inputs that are safe to pass to research setup."""

    company_name: str
    website: str


def validate_research_request(config: _ResearchConfig) -> ValidatedResearchRequest | None:
    """Validate inputs, mode combinations, and inference policy once."""
    if not config.company_name or not config.website:
        report_command_error(
            json_output=config.json_output,
            operation="research",
            error_type="missing_research_input",
            message="Both company name and website are required",
            hints=(
                'Usage: primr "Company Name" https://company.com',
                "Run 'primr doctor' to check system configuration",
            ),
        )
        return None

    try:
        company_name = validators.validate_company_name(config.company_name)
    except validators.InputValidationError as exc:
        report_command_error(
            json_output=config.json_output,
            operation="research",
            error_type="invalid_company_name",
            message=f"Invalid company name: {exc.reason}",
        )
        return None

    try:
        website = validators.validate_url(_ensure_valid_url(config.website))
    except validators.InputValidationError as exc:
        report_command_error(
            json_output=config.json_output,
            operation="research",
            error_type="invalid_website_url",
            message=f"Invalid website URL: {exc.reason}",
        )
        return None

    if config.premium_mode and config.fast_mode:
        report_command_error(
            json_output=config.json_output,
            operation="research",
            error_type="incompatible_mode_options",
            message="Cannot use both --fast and --premium. Choose one.",
        )
        return None
    if config.premium_mode and config.mode not in _FULL_RESEARCH_MODES:
        report_command_error(
            json_output=config.json_output,
            operation="research",
            error_type="incompatible_mode_options",
            message=f"--premium only works with full mode, not --mode {config.mode}",
        )
        return None
    if config.fast_mode and config.mode not in _FULL_RESEARCH_MODES:
        report_command_error(
            json_output=config.json_output,
            operation="research",
            error_type="incompatible_mode_options",
            message=f"--fast only works with full mode, not --mode {config.mode}",
            hints=('Usage: primr "Company" https://url --fast [--platform aws azure]',),
        )
        return None

    if config.json_output:
        inference_error = validate_inference_options(
            config.inference_profile,
            config.acknowledge_host_agent_may_bill,
        )
        if inference_error:
            report_command_error(
                json_output=True,
                operation="research",
                error_type="invalid_inference_options",
                message=inference_error,
            )
            return None
        configure_inference_runtime(
            config.inference_profile,
            config.acknowledge_host_agent_may_bill,
        )
    elif not prepare_inference_runtime(config, console):
        return None

    return ValidatedResearchRequest(company_name=company_name, website=website)


def ensure_research_approval_transport(config: _ResearchConfig) -> bool:
    """Refuse paid execution when no prompt or explicit approval is available."""
    stdin = sys.stdin
    try:
        stdin_is_interactive = bool(stdin is not None and stdin.isatty())
    except (OSError, ValueError):
        stdin_is_interactive = False
    if config.skip_confirm or stdin_is_interactive:
        return True
    json_modifier = " --json" if config.json_output else ""
    report_command_error(
        json_output=config.json_output,
        operation="research",
        error_type="approval_required",
        message="Research requires explicit approval before provider work can start.",
        hints=(
            f"Run the exact command with --dry-run{json_modifier}, then repeat it "
            "with --skip-confirm after approval.",
        ),
    )
    return False


def report_research_workspace_error(error: Exception, *, json_output: bool) -> int:
    """Render one active-run or unsafe-workspace failure consistently."""
    from primr.core.workspace import ActiveRunLeaseError

    if isinstance(error, ActiveRunLeaseError):
        error_type = "active_run"
        hint = "Wait for the active run to finish, then retry."
    else:
        error_type = "workspace_lease"
        hint = "Inspect the run log and lease file before retrying."
    return report_command_error(
        json_output=json_output,
        operation="research",
        error_type=error_type,
        message=str(error),
        hints=(hint,),
    )


def resolve_research_context_files(config: _ResearchConfig) -> list[str] | None:
    """Consolidate and validate optional context inputs for one run."""
    from primr.core.workspace import consolidate_working_folder, validate_context_files

    context_files: list[str | Path] = list(config.context_files)
    if config.context_folder:
        try:
            consolidated_file = consolidate_working_folder(config.context_folder)
        except Exception as error:
            report_command_error(
                json_output=config.json_output,
                operation="research",
                error_type="invalid_context_folder",
                message=f"Failed to consolidate context folder: {error}",
            )
            return None
        context_files.insert(0, consolidated_file)

    if not context_files:
        return []
    validation = validate_context_files(context_files)
    if not config.json_output:
        for warning in validation.warnings:
            console.warn(warning)
    if validation.invalid_files:
        invalid_messages = tuple(
            f"Invalid context file: {file_path} - {reason}"
            for file_path, reason in validation.invalid_files
        )
        report_command_error(
            json_output=config.json_output,
            operation="research",
            error_type="invalid_context_file",
            message="One or more context files are invalid",
            hints=(*validation.warnings, *invalid_messages),
        )
        return None
    return [str(path) for path in validation.valid_files]


__all__ = [
    "ValidatedResearchRequest",
    "ensure_research_approval_transport",
    "report_research_workspace_error",
    "resolve_research_context_files",
    "validate_research_request",
]
