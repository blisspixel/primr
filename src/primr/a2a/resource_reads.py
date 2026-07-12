"""A2A adapters for compact MCP resources and explicit report reads."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from a2a.utils import new_agent_text_message

from primr.a2a.input_parsing import (
    parse_eval_id,
    parse_job_id,
    report_read_uri_from_text,
)
from primr.a2a.skill_ids import (
    A2A_COMPACT_RESOURCE_READ_SKILLS,
    A2A_REPORT_RESOURCE_READ_SKILLS,
    A2A_RESOURCE_READ_SKILLS,
)
from primr.mcp_server.artifact_resources import (
    ARTIFACT_METADATA_BY_JOB_URI,
    QA_SUMMARY_BY_JOB_URI,
    USAGE_SUMMARY_BY_JOB_URI,
    read_artifact_metadata_by_job_resource,
    read_qa_summary_by_job_resource,
    read_usage_summary_by_job_resource,
)
from primr.mcp_server.calibration_summary import (
    CALIBRATION_SUMMARY_BY_JOB_URI,
    read_calibration_summary_by_job_resource,
)
from primr.mcp_server.report_resources import read_report_by_job_resource
from primr.mcp_server.resource_auth import caller_can_read_report
from primr.mcp_server.server_context import MCPServerContext
from primr.mcp_server.source_summary import (
    SOURCE_SUMMARY_BY_JOB_URI,
    read_source_summary_by_job_resource,
)
from primr.mcp_server.stage_scorecard_summary import (
    STAGE_SCORECARD_SUMMARY_URI,
    read_stage_scorecard_summary_resource,
)
from primr.mcp_server.trace_summary import (
    TRACE_SUMMARY_BY_JOB_URI,
    read_trace_summary_by_job_resource,
)
from primr.mcp_server.verification_summary import (
    VERIFICATION_SUMMARY_BY_JOB_URI,
    read_verification_summary_by_job_resource,
)

if TYPE_CHECKING:
    from a2a.server.events import EventQueue


class JobResourceReader(Protocol):
    """Callable shape shared by compact job-scoped MCP resource readers."""

    def __call__(
        self,
        mcp_server: MCPServerContext,
        uri: str,
        *,
        client_id: str,
    ) -> list[Any]: ...


@dataclass(frozen=True)
class JobResourceReadSpec:
    """A compact job-resource reader exposed as an A2A skill."""

    resource_uri: str
    reader: JobResourceReader
    missing_message: str
    success_status: str


JOB_RESOURCE_READ_SPECS: dict[str, JobResourceReadSpec] = {
    "read_artifacts_by_job": JobResourceReadSpec(
        resource_uri=ARTIFACT_METADATA_BY_JOB_URI,
        reader=read_artifact_metadata_by_job_resource,
        missing_message="Please provide a job_id for the artifact metadata summary.",
        success_status="artifact_metadata_read",
    ),
    "read_calibration_summary_by_job": JobResourceReadSpec(
        resource_uri=CALIBRATION_SUMMARY_BY_JOB_URI,
        reader=read_calibration_summary_by_job_resource,
        missing_message="Please provide a job_id for the calibration summary.",
        success_status="calibration_summary_read",
    ),
    "read_qa_summary_by_job": JobResourceReadSpec(
        resource_uri=QA_SUMMARY_BY_JOB_URI,
        reader=read_qa_summary_by_job_resource,
        missing_message="Please provide a job_id for the QA summary.",
        success_status="qa_summary_read",
    ),
    "read_usage_summary_by_job": JobResourceReadSpec(
        resource_uri=USAGE_SUMMARY_BY_JOB_URI,
        reader=read_usage_summary_by_job_resource,
        missing_message="Please provide a job_id for the usage summary.",
        success_status="usage_summary_read",
    ),
    "read_source_summary_by_job": JobResourceReadSpec(
        resource_uri=SOURCE_SUMMARY_BY_JOB_URI,
        reader=read_source_summary_by_job_resource,
        missing_message="Please provide a job_id for the source summary.",
        success_status="source_summary_read",
    ),
    "read_trace_summary_by_job": JobResourceReadSpec(
        resource_uri=TRACE_SUMMARY_BY_JOB_URI,
        reader=read_trace_summary_by_job_resource,
        missing_message="Please provide a job_id for the trace summary.",
        success_status="trace_summary_read",
    ),
    "read_verification_summary_by_job": JobResourceReadSpec(
        resource_uri=VERIFICATION_SUMMARY_BY_JOB_URI,
        reader=read_verification_summary_by_job_resource,
        missing_message="Please provide a job_id for the verification summary.",
        success_status="verification_summary_read",
    ),
}

assert set(JOB_RESOURCE_READ_SPECS) == A2A_COMPACT_RESOURCE_READ_SKILLS - {"read_stage_scorecard"}


async def handle_a2a_resource_read(
    skill_id: str | None,
    text: str,
    event_queue: EventQueue,
    *,
    mcp_server: MCPServerContext,
    client_id: str,
) -> dict[str, Any]:
    """Dispatch a known A2A resource-read skill to the shared MCP reader."""
    if skill_id in JOB_RESOURCE_READ_SPECS:
        return await _handle_job_resource_summary(
            text,
            event_queue,
            mcp_server=mcp_server,
            client_id=client_id,
            spec=JOB_RESOURCE_READ_SPECS[skill_id],
        )
    if skill_id == "read_stage_scorecard":
        return await _handle_stage_scorecard_summary(text, event_queue)
    if skill_id in A2A_REPORT_RESOURCE_READ_SKILLS:
        return await _handle_report_read(
            text,
            event_queue,
            mcp_server=mcp_server,
            client_id=client_id,
        )

    payload = {
        "error": True,
        "error_type": "unknown_resource_read_skill",
        "skill_id": skill_id,
    }
    await event_queue.enqueue_event(new_agent_text_message(json.dumps(payload)))
    return payload


def resource_read_skill_list() -> str:
    """Return a stable comma-separated skill list for unknown-skill messages."""
    return ", ".join(sorted(A2A_RESOURCE_READ_SKILLS))


async def _handle_job_resource_summary(
    text: str,
    event_queue: EventQueue,
    *,
    mcp_server: MCPServerContext,
    client_id: str,
    spec: JobResourceReadSpec,
) -> dict[str, Any]:
    job_id = parse_job_id(text, uri_prefix=spec.resource_uri)
    if not job_id:
        payload = {
            "error": True,
            "error_type": "missing_job_id",
            "message": spec.missing_message,
        }
        await event_queue.enqueue_event(new_agent_text_message(json.dumps(payload)))
        return payload

    contents = spec.reader(
        mcp_server,
        f"{spec.resource_uri}/{job_id}",
        client_id=client_id,
    )
    payload = _resource_payload(contents)
    await event_queue.enqueue_event(new_agent_text_message(json.dumps(payload, indent=2)))
    return payload if isinstance(payload, dict) else {"status": spec.success_status}


async def _handle_stage_scorecard_summary(
    text: str,
    event_queue: EventQueue,
) -> dict[str, Any]:
    eval_id = parse_eval_id(text)
    if not eval_id:
        payload = {
            "error": True,
            "error_type": "missing_eval_id",
            "message": "Please provide an eval_id for the stage scorecard summary.",
        }
        await event_queue.enqueue_event(new_agent_text_message(json.dumps(payload)))
        return payload

    contents = read_stage_scorecard_summary_resource(f"{STAGE_SCORECARD_SUMMARY_URI}/{eval_id}")
    payload = _resource_payload(contents)
    await event_queue.enqueue_event(new_agent_text_message(json.dumps(payload, indent=2)))
    return payload if isinstance(payload, dict) else {"status": "scorecard_read"}


async def _handle_report_read(
    text: str,
    event_queue: EventQueue,
    *,
    mcp_server: MCPServerContext,
    client_id: str,
) -> dict[str, Any]:
    uri = report_read_uri_from_text(text)
    if not uri:
        payload = {
            "error": True,
            "error_type": "missing_job_id",
            "message": "Please provide a job_id for the report read.",
        }
        await event_queue.enqueue_event(new_agent_text_message(json.dumps(payload)))
        return payload

    contents = read_report_by_job_resource(
        mcp_server,
        uri,
        client_id=client_id,
        can_read_report=caller_can_read_report(mcp_server),
    )
    payload = _resource_payload(contents)
    await event_queue.enqueue_event(new_agent_text_message(json.dumps(payload, indent=2)))
    return payload if isinstance(payload, dict) else {"status": "report_read"}


def _resource_payload(contents: list[Any]) -> Any:
    """Decode a compact MCP resource payload returned by a shared reader."""
    content = contents[0].content if contents else "{}"
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"error": True, "error_type": "invalid_resource_payload"}
