"""Tests for A2A agent executor."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

a2a = pytest.importorskip("a2a")

from primr.a2a.call_context import LOCAL_A2A_CLIENT_ID
from primr.a2a.executor import (
    PrimrAgentExecutor,
    _a2a_client_id,
    _caller_owns_job,
    _extract_skill_id,
    _extract_text,
)
from primr.a2a.input_parsing import (
    parse_eval_id as _parse_eval_id,
)
from primr.a2a.input_parsing import (
    parse_job_id as _parse_job_id,
)
from primr.a2a.input_parsing import (
    parse_research_params as _parse_research_params,
)
from primr.a2a.input_parsing import (
    report_read_uri_from_text as _report_read_uri_from_text,
)
from primr.a2a.task_store import PrimrTaskStore
from primr.a2a.types import A2ATaskMapping
from primr.mcp_server.resource_auth import TRUSTED_LOCAL_A2A_AUTH_CONTEXT
from primr.mcp_server.types import ResearchStage


class TestExtractSkillId:
    """Tests for _extract_skill_id helper."""

    def test_from_dict_message(self):
        msg = {"metadata": {"skillId": "research_company"}}
        assert _extract_skill_id(msg) == "research_company"

    def test_from_dict_no_metadata(self):
        msg = {"parts": [{"kind": "text", "text": "hello"}]}
        assert _extract_skill_id(msg) is None

    def test_from_object_with_metadata(self):
        msg = MagicMock()
        msg.metadata = {"skillId": "check_jobs"}
        assert _extract_skill_id(msg) == "check_jobs"

    def test_from_none_metadata(self):
        msg = MagicMock()
        msg.metadata = None
        assert _extract_skill_id(msg) is None


class TestExtractText:
    """Tests for _extract_text helper."""

    def test_from_dict_parts(self):
        msg = {"parts": [{"kind": "text", "text": "hello world"}]}
        assert _extract_text(msg) == "hello world"

    def test_multiple_parts(self):
        msg = {
            "parts": [
                {"kind": "text", "text": "hello"},
                {"kind": "text", "text": "world"},
            ]
        }
        assert _extract_text(msg) == "hello world"

    def test_ignores_non_text_parts(self):
        msg = {
            "parts": [
                {"kind": "file", "uri": "data:..."},
                {"kind": "text", "text": "text only"},
            ]
        }
        assert _extract_text(msg) == "text only"

    def test_empty_message(self):
        assert _extract_text({}) == ""
        assert _extract_text("not a dict") == ""


class TestParseResearchParams:
    """Tests for _parse_research_params helper."""

    def test_json_params(self):
        text = json.dumps({"url": "http://example.com", "mode": "deep"})
        params = _parse_research_params(text)
        assert params["url"] == "http://example.com"
        assert params["mode"] == "deep"

    def test_url_extraction(self):
        text = "Research Acme at https://acme.com please"
        params = _parse_research_params(text)
        assert params["url"] == "https://acme.com"

    def test_mode_extraction(self):
        text = "Run deep research on https://example.com"
        params = _parse_research_params(text)
        assert params["mode"] == "deep"

    def test_no_url(self):
        text = "What is the status?"
        params = _parse_research_params(text)
        assert "url" not in params

    def test_empty_text(self):
        params = _parse_research_params("")
        assert params == {}


class TestParseEvalId:
    """Tests for _parse_eval_id helper."""

    def test_json_eval_id(self):
        assert _parse_eval_id('{"eval_id": "eval-2026-06"}') == "eval-2026-06"

    def test_json_eval_id_alias(self):
        assert _parse_eval_id('{"evalId": "eval-2026-06"}') == "eval-2026-06"

    def test_stage_scorecard_uri(self):
        assert _parse_eval_id("primr://eval/stage_scorecard/eval-2026-06") == "eval-2026-06"

    def test_plain_text_eval_id(self):
        assert _parse_eval_id(" eval-2026-06 ") == "eval-2026-06"


class TestParseJobId:
    """Tests for _parse_job_id helper."""

    def test_json_job_id(self):
        assert _parse_job_id('{"job_id": "job-2026-06"}') == "job-2026-06"

    def test_json_job_id_alias(self):
        assert _parse_job_id('{"jobId": "job-2026-06"}') == "job-2026-06"

    def test_artifact_resource_uri(self):
        assert _parse_job_id("primr://output/artifacts/by_job/job-2026-06") == "job-2026-06"

    def test_calibration_summary_resource_uri(self):
        assert (
            _parse_job_id(
                "primr://output/calibration_summary/by_job/job-2026-06",
                uri_prefix="primr://output/calibration_summary/by_job",
            )
            == "job-2026-06"
        )

    def test_qa_summary_resource_uri(self):
        assert (
            _parse_job_id(
                "primr://output/qa_summary/by_job/job-2026-06",
                uri_prefix="primr://output/qa_summary/by_job",
            )
            == "job-2026-06"
        )

    def test_usage_summary_resource_uri(self):
        assert (
            _parse_job_id(
                "primr://output/usage_summary/by_job/job-2026-06",
                uri_prefix="primr://output/usage_summary/by_job",
            )
            == "job-2026-06"
        )

    def test_source_summary_resource_uri(self):
        assert (
            _parse_job_id(
                "primr://output/source_summary/by_job/job-2026-06",
                uri_prefix="primr://output/source_summary/by_job",
            )
            == "job-2026-06"
        )

    def test_trace_summary_resource_uri(self):
        assert (
            _parse_job_id(
                "primr://output/trace_summary/by_job/job-2026-06",
                uri_prefix="primr://output/trace_summary/by_job",
            )
            == "job-2026-06"
        )

    def test_verification_summary_resource_uri(self):
        assert (
            _parse_job_id(
                "primr://output/verification_summary/by_job/job-2026-06",
                uri_prefix="primr://output/verification_summary/by_job",
            )
            == "job-2026-06"
        )

    def test_plain_text_job_id(self):
        assert _parse_job_id(" job-2026-06 ") == "job-2026-06"


class TestReportReadUri:
    """Tests for report-resource URI construction."""

    def test_json_report_options(self):
        uri = _report_read_uri_from_text(
            json.dumps(
                {
                    "job_id": "job-2026-06",
                    "content_mode": "full",
                    "artifact_type": "all",
                    "max_chars": 42,
                }
            )
        )
        assert uri == (
            "primr://output/report/by_job/job-2026-06?"
            "content_mode=full&artifact_type=all&max_chars=42"
        )

    def test_report_resource_uri_passthrough(self):
        uri = "primr://output/report/by_job/job-2026-06?content_mode=metadata"
        assert _report_read_uri_from_text(uri) == uri


class TestA2AOwnershipHelpers:
    """Tests for A2A caller ownership helpers."""

    def test_local_owner_uses_server_trusted_context(self):
        mcp_server = MagicMock()
        mcp_server._auth_context = TRUSTED_LOCAL_A2A_AUTH_CONTEXT
        assert _a2a_client_id(mcp_server) == LOCAL_A2A_CLIENT_ID

    def test_missing_auth_context_is_anonymous(self):
        mcp_server = MagicMock()
        mcp_server._auth_context = None
        assert _a2a_client_id(mcp_server) == "anonymous"

    def test_authenticated_owner_uses_client_id(self):
        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.client_id = "client-1"
        mcp_server = MagicMock()
        mcp_server._auth_context = auth_context
        assert _a2a_client_id(mcp_server) == "client-1"

    def test_caller_owns_job_by_exact_owner(self):
        job = MagicMock()
        job.owner_client_id = "client-1"
        assert _caller_owns_job(job, "client-1")
        assert not _caller_owns_job(job, "client-2")


class TestPrimrAgentExecutor:
    """Tests for PrimrAgentExecutor."""

    @pytest.fixture
    def executor(self, tmp_path):
        """Create executor with mocked MCP server."""
        from primr.mcp_server.server import create_mcp_server

        journal_path = str(tmp_path / "journal.json")
        mcp_server = create_mcp_server(
            journal_path=journal_path,
            skip_background_tasks=True,
        )

        task_store = PrimrTaskStore(mcp_server.job_store)
        executor = PrimrAgentExecutor(mcp_server, task_store)
        mcp_server._auth_context = TRUSTED_LOCAL_A2A_AUTH_CONTEXT
        return executor

    @pytest.fixture
    def event_queue(self):
        """Create a mock EventQueue."""
        queue = MagicMock()
        queue.enqueue_event = AsyncMock()
        return queue

    @pytest.fixture
    def context(self):
        """Create a mock RequestContext."""
        ctx = MagicMock()
        ctx.message = {
            "parts": [{"kind": "text", "text": "test"}],
            "messageId": "msg-1",
        }
        ctx.task_id = None
        return ctx

    @pytest.mark.asyncio
    async def test_handle_unknown_skill(self, executor, event_queue, context):
        """Unknown skill returns available skills list."""
        context.message["metadata"] = {"skillId": "unknown_skill"}
        await executor.execute(context, event_queue)
        event_queue.enqueue_event.assert_called()

    @pytest.mark.asyncio
    async def test_handle_check_jobs_no_active(self, executor, event_queue, context):
        """check_jobs with no active job returns idle."""
        context.message["metadata"] = {"skillId": "check_jobs"}
        await executor.execute(context, event_queue)
        event_queue.enqueue_event.assert_called()

    @pytest.mark.asyncio
    async def test_check_jobs_writes_hashed_a2a_audit_event(self, executor, event_queue, context):
        """A2A skill calls are audited without raw message text or caller ids."""
        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["read"]
        auth_context.client_id = "sensitive-client"
        executor._mcp._auth_context = auth_context
        context.message = {
            "parts": [
                {
                    "kind": "text",
                    "text": "status for https://example.com/private?token=secret",
                }
            ],
            "metadata": {"skillId": "check_jobs"},
        }

        try:
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        audit_text = executor._mcp.audit_log.path.read_text(encoding="utf-8")
        assert "sensitive-client" not in audit_text
        assert "example.com" not in audit_text
        assert "private" not in audit_text
        assert "secret" not in audit_text

        event = _audit_events(executor)[0]
        assert event["transport"] == "a2a"
        assert event["event_type"] == "tool_call"
        assert event["tool_name"] == "a2a/check_jobs"
        assert event["status"] == "success"
        assert event["actor"] is None
        assert event["client_id_hash"].startswith("sha256:")
        assert event["auth_scopes"] == ["read"]
        assert event["args_hash"].startswith("sha256:")
        assert event["result_hash"].startswith("sha256:")
        assert event["request_id"] == event["event_id"]
        assert event["otel_span"]["name"] == "primr.a2a.tool_call.a2a.check_jobs"
        attrs = event["otel_span"]["attributes"]
        assert attrs["primr.request_id"] == event["request_id"]
        assert attrs["primr.transport"] == "a2a"
        assert attrs["primr.tool_name"] == "a2a/check_jobs"
        assert attrs["primr.status"] == "success"

    @pytest.mark.asyncio
    async def test_handle_doctor(self, executor, event_queue, context):
        """system_health dispatches to doctor."""
        context.message["metadata"] = {"skillId": "system_health"}
        with patch("primr.a2a.executor.get_doctor_status", return_value={"healthy": True}):
            await executor.execute(context, event_queue)
        event_queue.enqueue_event.assert_called()

    @pytest.mark.asyncio
    async def test_handle_estimate_no_url(self, executor, event_queue, context):
        """estimate_research without URL asks for one."""
        context.message = {
            "parts": [{"kind": "text", "text": "estimate something"}],
            "metadata": {"skillId": "estimate_research"},
        }
        await executor.execute(context, event_queue)
        event_queue.enqueue_event.assert_called()

    @pytest.mark.asyncio
    async def test_cancel_no_task(self, executor, event_queue, context):
        """Cancel with no task_id returns message."""
        context.task_id = None
        await executor.cancel(context, event_queue)
        event_queue.enqueue_event.assert_called()

    @pytest.mark.asyncio
    async def test_cancel_unknown_task(self, executor, event_queue, context):
        """Cancel with unknown task returns message."""
        context.task_id = "nonexistent-task"
        await executor.cancel(context, event_queue)
        event_queue.enqueue_event.assert_called()

    @pytest.mark.asyncio
    async def test_cancel_request_cancellation_releases_stream_suppression(
        self,
        executor,
        event_queue,
        context,
        monkeypatch,
    ):
        """A dropped cancel request cannot suppress the research terminal event."""
        job = executor._mcp.job_store.create("Acme", "full", owner_client_id="a2a")
        executor._task_store.register_mapping(
            A2ATaskMapping(task_id="task-1", job_id=job.job_id, skill_id="research_company")
        )
        executor._mcp._skip_background_tasks = False
        context.task_id = "task-1"
        context.context_id = "ctx-1"
        entered = asyncio.Event()

        async def blocking_cancel(_job_id):
            entered.set()
            await asyncio.Future()

        monkeypatch.setattr(executor._mcp.job_supervisor, "cancel", blocking_cancel)
        cancel_task = asyncio.create_task(executor.cancel(context, event_queue))
        await asyncio.wait_for(entered.wait(), timeout=1.0)
        assert executor._lifecycle_events.cancel_is_pending(job.job_id)
        cancel_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancel_task
        assert not executor._lifecycle_events.cancel_is_pending(job.job_id)

    @pytest.mark.asyncio
    async def test_cancel_completion_race_reports_observed_terminal_truth(
        self,
        executor,
        event_queue,
        context,
        monkeypatch,
    ):
        """Completion winning cancellation is not called an unconfirmed exit."""
        from primr.mcp_server.job_process import CancellationOutcome

        job = executor._mcp.job_store.create("Acme", "full", owner_client_id="a2a")
        executor._task_store.register_mapping(
            A2ATaskMapping(task_id="task-1", job_id=job.job_id, skill_id="research_company")
        )
        executor._mcp._skip_background_tasks = False
        context.task_id = "task-1"
        context.context_id = "ctx-1"
        monkeypatch.setattr(
            executor._mcp.job_supervisor,
            "cancel",
            AsyncMock(
                return_value=CancellationOutcome(
                    status="completed",
                    worker_exit_confirmed=True,
                )
            ),
        )

        await executor.cancel(context, event_queue)
        text = _get_event_text(event_queue.enqueue_event.call_args[0][0])
        assert "completed before cancellation" in text
        assert "could not be confirmed" not in text

    @pytest.mark.asyncio
    async def test_cancel_writes_a2a_audit_event_with_job_id(self, executor, event_queue, context):
        """A2A cancellation audit records job provenance without raw task ids."""
        job = executor._mcp.job_store.create(
            company_name="Acme",
            mode="full",
            owner_client_id="client-1",
        )
        executor._task_store.register_mapping(
            A2ATaskMapping(
                task_id="task-secret-1",
                job_id=job.job_id,
                skill_id="research_company",
            )
        )
        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["research"]
        auth_context.client_id = "client-1"
        executor._mcp._auth_context = auth_context
        context.task_id = "task-secret-1"
        context.context_id = "ctx-1"

        try:
            await executor.cancel(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        audit_text = executor._mcp.audit_log.path.read_text(encoding="utf-8")
        assert "task-secret-1" not in audit_text
        event = _audit_events(executor)[0]
        assert event["transport"] == "a2a"
        assert event["tool_name"] == "a2a/cancel_task"
        assert event["status"] == "success"
        assert event["job_id"] == job.job_id
        assert event["client_id_hash"].startswith("sha256:")

    @pytest.mark.asyncio
    async def test_check_jobs_returns_json(self, executor, event_queue, context):
        """check_jobs response is valid JSON with status field."""
        context.message["metadata"] = {"skillId": "check_jobs"}
        await executor.execute(context, event_queue)

        call_args = event_queue.enqueue_event.call_args
        # Extract text from the agent message event
        event = call_args[0][0]
        text = _get_event_text(event)
        data = json.loads(text)
        assert "status" in data
        assert data["status"] == "idle"
        assert data["job_status"]["schema"] == "primr.job-status"

    @pytest.mark.asyncio
    async def test_check_jobs_completed_job_returns_resource_pointers_not_paths(
        self, executor, event_queue, context, tmp_path
    ):
        """A2A check_jobs advertises compact read surfaces without raw paths."""
        report = tmp_path / "Acme_Strategic_Overview.md"
        report.write_text("# SECRET REPORT BODY", encoding="utf-8")
        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["read"]
        auth_context.client_id = "client-a"
        executor._mcp._auth_context = auth_context
        job = executor._mcp.job_store.create(
            "Acme Corp",
            "full",
            owner_client_id="client-a",
        )
        job.output_paths = [str(report)]
        job.advance_stage(ResearchStage.COMPLETED)
        executor._mcp.job_store.update(job)
        context.message["metadata"] = {"skillId": "check_jobs"}

        try:
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        event = event_queue.enqueue_event.call_args[0][0]
        data = json.loads(_get_event_text(event))
        text = json.dumps(data)
        assert data["job_id"] == job.job_id
        assert data["artifact_metadata_uri"] == f"primr://output/artifacts/by_job/{job.job_id}"
        assert data["report_read_uri"] == f"primr://output/report/by_job/{job.job_id}"
        assert data["output_paths_available"] is True
        assert data["job_status"]["lifecycle_state"] == "completed"
        assert isinstance(data["job_status"]["progress"], dict)
        assert "output_paths" not in data
        assert str(report) not in text
        assert "SECRET REPORT BODY" not in text

    @pytest.mark.asyncio
    async def test_doctor_returns_json(self, executor, event_queue, context):
        """system_health returns valid JSON."""
        context.message["metadata"] = {"skillId": "system_health"}
        with patch("primr.a2a.executor.get_doctor_status", return_value={"status": "healthy"}):
            await executor.execute(context, event_queue)

        event = event_queue.enqueue_event.call_args[0][0]
        text = _get_event_text(event)
        data = json.loads(text)
        assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_estimate_invalid_url(self, executor, event_queue, context):
        """estimate_research with invalid URL returns error message."""
        context.message = {
            "parts": [{"kind": "text", "text": '{"url": "http://169.254.169.254/meta"}'}],
            "metadata": {"skillId": "estimate_research"},
        }
        await executor.execute(context, event_queue)
        event = event_queue.enqueue_event.call_args[0][0]
        text = _get_event_text(event)
        assert "Invalid URL" in text or "url" in text.lower()

    @pytest.mark.asyncio
    async def test_estimate_research_returns_approval_token(self, executor, event_queue, context):
        """A2A estimates use the same approval-token contract as MCP estimates."""
        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["read"]
        auth_context.client_id = "client-1"
        executor._mcp._auth_context = auth_context
        context.message = {
            "parts": [
                {
                    "kind": "text",
                    "text": (
                        '{"url": "https://example.com/private?token=secret", '
                        '"mode": "full", "platform": "azure"}'
                    ),
                }
            ],
            "metadata": {"skillId": "estimate_research"},
        }

        try:
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        event = event_queue.enqueue_event.call_args[0][0]
        data = json.loads(_get_event_text(event))
        assert data["approval_token"]
        assert data["approval_token_id"]
        assert data["approval_expires_at"].endswith("Z")
        assert data["platforms"] == ["azure"]

        audit_text = executor._mcp.audit_log.path.read_text(encoding="utf-8")
        assert "example.com" not in audit_text
        assert "private" not in audit_text
        assert "secret" not in audit_text
        assert data["approval_token"] not in audit_text

        audit_event = _audit_events(executor)[0]
        assert audit_event["tool_name"] == "a2a/estimate_research"
        assert audit_event["status"] == "success"
        assert audit_event["approval_token_id"] == data["approval_token_id"]
        assert audit_event["estimated_cost_usd"] == data["estimated_cost_usd"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "shape,error_type",
        [
            ({"platforms": ["azure", "aws"]}, "unsupported_platform_fanout"),
            ({"platforms": ["ms"]}, "unsupported_platform_fanout"),
            ({"platform": "ms"}, "unsupported_platform_fanout"),
            (
                {"platform": "azure", "platforms": ["azure"]},
                "conflicting_platform_parameters",
            ),
            ({"strategy_type": "customer_experience"}, "unsupported_strategy_type"),
        ],
    )
    async def test_estimate_rejects_unexecutable_integrated_shape(
        self,
        executor,
        event_queue,
        context,
        shape,
        error_type,
    ):
        context.message = {
            "parts": [
                {
                    "kind": "text",
                    "text": json.dumps({"url": "https://example.com", **shape}),
                }
            ],
            "metadata": {"skillId": "estimate_research"},
        }

        await executor.execute(context, event_queue)

        data = json.loads(_get_event_text(event_queue.enqueue_event.call_args[0][0]))
        assert data["error"] is True
        assert data["error_type"] == error_type
        assert "approval_token" not in data

    @pytest.mark.asyncio
    async def test_research_no_url(self, executor, event_queue, context):
        """research_company without URL asks for one."""
        context.message = {
            "parts": [{"kind": "text", "text": "research something"}],
            "metadata": {"skillId": "research_company"},
        }
        await executor.execute(context, event_queue)
        event = event_queue.enqueue_event.call_args[0][0]
        text = _get_event_text(event)
        assert "URL" in text

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "shape,error_type",
        [
            ({"platforms": ["azure"]}, "unsupported_platforms_parameter"),
            ({"platform": "ms"}, "unsupported_platform_fanout"),
            ({"strategy_type": "customer_experience"}, "unsupported_strategy_type"),
        ],
    )
    async def test_research_rejects_unexecutable_shape_before_job_creation(
        self,
        executor,
        event_queue,
        context,
        shape,
        error_type,
    ):
        context.message = {
            "parts": [
                {
                    "kind": "text",
                    "text": json.dumps(
                        {
                            "url": "https://example.com",
                            "name": "Example",
                            **shape,
                        }
                    ),
                }
            ],
            "metadata": {"skillId": "research_company"},
        }

        await executor.execute(context, event_queue)

        data = json.loads(_get_event_text(event_queue.enqueue_event.call_args[0][0]))
        assert data["error"] is True
        assert data["error_type"] == error_type
        assert executor._mcp.job_store.get_active() is None

    @pytest.mark.asyncio
    async def test_research_denied_for_read_only_token(self, executor, event_queue, context):
        """research_company is blocked before handler execution without research scope."""
        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["read"]
        auth_context.client_id = "sensitive-client"
        executor._mcp._auth_context = auth_context
        context.message = {
            "parts": [
                {
                    "kind": "text",
                    "text": '{"url":"https://example.com/private?token=secret"}',
                }
            ],
            "metadata": {"skillId": "research_company"},
        }

        try:
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        event = event_queue.enqueue_event.call_args[0][0]
        data = json.loads(_get_event_text(event))
        assert data["error_type"] == "insufficient_scope"
        assert data["missing_scopes"] == ["research"]
        audit_text = executor._mcp.audit_log.path.read_text(encoding="utf-8")
        assert "sensitive-client" not in audit_text
        assert "example.com" not in audit_text
        assert "private" not in audit_text
        assert "secret" not in audit_text
        audit_event = _audit_events(executor)[0]
        assert audit_event["transport"] == "a2a"
        assert audit_event["tool_name"] == "a2a/research_company"
        assert audit_event["status"] == "scope_denied"
        assert audit_event["error_type"] == "insufficient_scope"
        assert audit_event["client_id_hash"].startswith("sha256:")
        assert audit_event["auth_scopes"] == ["read"]

    @pytest.mark.asyncio
    async def test_research_requires_cost_cap_when_enforced(
        self, executor, event_queue, context, monkeypatch
    ):
        """A2A research refuses paid execution without an approved cap."""
        monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", "1")
        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["research"]
        auth_context.client_id = "client-1"
        executor._mcp._auth_context = auth_context
        context.message = {
            "parts": [
                {
                    "kind": "text",
                    "text": '{"url": "https://example.com", "name": "Example"}',
                }
            ],
            "metadata": {"skillId": "research_company"},
        }

        try:
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        event = event_queue.enqueue_event.call_args[0][0]
        data = json.loads(_get_event_text(event))
        assert data["error_type"] == "cost_cap_required"
        assert executor._mcp.job_store.get_active() is None

        audit_event = _audit_events(executor)[0]
        assert audit_event["tool_name"] == "a2a/research_company"
        assert audit_event["status"] == "error"
        assert audit_event["error_type"] == "cost_cap_required"
        assert audit_event["estimated_cost_usd"] == data["estimated_cost_usd"]

    @pytest.mark.asyncio
    async def test_research_requires_approval_token_when_enforced(
        self, executor, event_queue, context, monkeypatch
    ):
        """A2A research requires a matching approval token when caps are enforced."""
        monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", "1")
        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["research"]
        auth_context.client_id = "client-1"
        executor._mcp._auth_context = auth_context
        context.message = {
            "parts": [
                {
                    "kind": "text",
                    "text": (
                        '{"url": "https://example.com", "name": "Example", '
                        '"max_estimated_cost_usd": 100.0}'
                    ),
                }
            ],
            "metadata": {"skillId": "research_company"},
        }

        try:
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        event = event_queue.enqueue_event.call_args[0][0]
        data = json.loads(_get_event_text(event))
        assert data["error_type"] == "approval_token_required"
        assert data["max_estimated_cost_usd"] == 100.0
        assert executor._mcp.job_store.get_active() is None

        audit_event = _audit_events(executor)[0]
        assert audit_event["status"] == "error"
        assert audit_event["error_type"] == "approval_token_required"
        assert audit_event["max_estimated_cost_usd"] == 100.0

    @pytest.mark.asyncio
    async def test_research_rejects_approval_args_swap(
        self, executor, event_queue, context, monkeypatch
    ):
        """A2A approval tokens are bound to the estimated research shape."""
        monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", "1")
        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["read", "research"]
        auth_context.client_id = "client-1"
        executor._mcp._auth_context = auth_context

        context.message = {
            "parts": [
                {
                    "kind": "text",
                    "text": '{"url": "https://example.com", "mode": "full"}',
                }
            ],
            "metadata": {"skillId": "estimate_research"},
        }
        try:
            await executor.execute(context, event_queue)
            estimate = json.loads(_get_event_text(event_queue.enqueue_event.call_args[0][0]))
            event_queue.enqueue_event.reset_mock()
            context.message = {
                "parts": [
                    {
                        "kind": "text",
                        "text": json.dumps(
                            {
                                "url": "https://example.org",
                                "name": "Example",
                                "mode": "full",
                                "max_estimated_cost_usd": estimate["estimated_cost_usd"],
                                "approval_token": estimate["approval_token"],
                            }
                        ),
                    }
                ],
                "metadata": {"skillId": "research_company"},
            }
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        event = event_queue.enqueue_event.call_args[0][0]
        data = json.loads(_get_event_text(event))
        assert data["error_type"] == "invalid_approval_token"
        assert "arguments do not match" in data["message"]
        assert executor._mcp.job_store.get_active() is None

    @pytest.mark.asyncio
    async def test_research_accepts_matching_approval_and_passes_budget_to_supervisor(
        self, executor, event_queue, context, monkeypatch
    ):
        """A2A research propagates the approved cap as the runtime budget."""
        monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", "1")
        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["read", "research"]
        auth_context.client_id = "client-1"
        executor._mcp._auth_context = auth_context

        context.message = {
            "parts": [
                {
                    "kind": "text",
                    "text": ('{"url": "https://example.com", "mode": "full", "platform": "azure"}'),
                }
            ],
            "metadata": {"skillId": "estimate_research"},
        }

        done = asyncio.Event()
        seen = {}

        async def fake_start(**kwargs):
            seen.update(kwargs)
            done.set()
            return asyncio.create_task(asyncio.sleep(0))

        try:
            await executor.execute(context, event_queue)
            estimate = json.loads(_get_event_text(event_queue.enqueue_event.call_args[0][0]))
            event_queue.enqueue_event.reset_mock()
            executor._mcp._skip_background_tasks = False
            monkeypatch.setattr(executor._mcp.job_supervisor, "start", fake_start)
            context.task_id = "task-1"
            context.context_id = "ctx-1"
            context.message = {
                "parts": [
                    {
                        "kind": "text",
                        "text": json.dumps(
                            {
                                "url": "https://example.com",
                                "name": "Example",
                                "mode": "full",
                                "platform": "azure",
                                "max_estimated_cost_usd": estimate["estimated_cost_usd"],
                                "approval_token": estimate["approval_token"],
                            }
                        ),
                    }
                ],
                "metadata": {"skillId": "research_company"},
            }
            await executor.execute(context, event_queue)
            await asyncio.wait_for(done.wait(), timeout=1)
        finally:
            executor._mcp._auth_context = None

        assert seen["company_url"] == "https://example.com"
        assert seen["mode"] == "full"
        assert seen["platform"] == "azure"
        assert seen["budget_usd"] == estimate["estimated_cost_usd"]

        audit_event = _audit_events(executor)[-1]
        assert audit_event["tool_name"] == "a2a/research_company"
        assert audit_event["status"] == "success"
        assert audit_event["estimated_cost_usd"] == estimate["estimated_cost_usd"]
        assert audit_event["max_estimated_cost_usd"] == estimate["estimated_cost_usd"]

    @pytest.mark.asyncio
    async def test_stage_scorecard_summary_requires_read_scope(
        self, executor, event_queue, context
    ):
        """read_stage_scorecard is blocked before handler execution without read scope."""
        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["research"]
        auth_context.client_id = "sensitive-client"
        executor._mcp._auth_context = auth_context
        context.message = {
            "parts": [
                {
                    "kind": "text",
                    "text": '{"eval_id":"eval-private-secret"}',
                }
            ],
            "metadata": {"skillId": "read_stage_scorecard"},
        }

        try:
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        event = event_queue.enqueue_event.call_args[0][0]
        data = json.loads(_get_event_text(event))
        assert data["error_type"] == "insufficient_scope"
        assert data["missing_scopes"] == ["read"]
        audit_text = executor._mcp.audit_log.path.read_text(encoding="utf-8")
        assert "sensitive-client" not in audit_text
        assert "eval-private-secret" not in audit_text

    @pytest.mark.asyncio
    async def test_report_read_requires_report_scope(self, executor, event_queue, context):
        """read_report_by_job is blocked before handler execution without report scope."""
        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["read"]
        auth_context.client_id = "sensitive-client"
        executor._mcp._auth_context = auth_context
        context.message = {
            "parts": [
                {
                    "kind": "text",
                    "text": "primr://output/report/by_job/job-private-secret?content_mode=full",
                }
            ],
            "metadata": {"skillId": "read_report_by_job"},
        }

        try:
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        event = event_queue.enqueue_event.call_args[0][0]
        data = json.loads(_get_event_text(event))
        assert data["error_type"] == "insufficient_scope"
        assert data["missing_scopes"] == ["report"]
        audit_text = executor._mcp.audit_log.path.read_text(encoding="utf-8")
        assert "sensitive-client" not in audit_text
        assert "job-private-secret" not in audit_text

    @pytest.mark.asyncio
    async def test_report_read_returns_owned_bounded_content(
        self, executor, event_queue, context, tmp_path
    ):
        """read_report_by_job returns negotiated content only with report scope."""
        report_path = tmp_path / "report.md"
        report_path.write_text("# Report\n\nSECRET REPORT BODY", encoding="utf-8")
        job = executor._mcp.job_store.create(
            company_name="Acme",
            mode="full",
            owner_client_id="client-1",
        )
        job.output_paths = [str(report_path)]

        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["report"]
        auth_context.client_id = "client-1"
        executor._mcp._auth_context = auth_context
        context.message = {
            "parts": [
                {
                    "kind": "text",
                    "text": json.dumps(
                        {
                            "job_id": job.job_id,
                            "content_mode": "full",
                            "artifact_type": "report",
                            "max_chars": 200,
                        }
                    ),
                }
            ],
            "metadata": {"skillId": "read_report_by_job"},
        }

        try:
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        event = event_queue.enqueue_event.call_args[0][0]
        data = json.loads(_get_event_text(event))
        assert data["job_id"] == job.job_id
        assert data["content_mode"] == "full"
        assert data["content_included"] is True
        assert data["full_content_included"] is True
        assert data["artifacts"][0]["filename"] == "report.md"
        assert data["artifacts"][0]["content"] == "# Report\n\nSECRET REPORT BODY"

        audit_text = executor._mcp.audit_log.path.read_text(encoding="utf-8")
        assert "SECRET REPORT BODY" not in audit_text
        audit_event = _audit_events(executor)[0]
        assert audit_event["tool_name"] == "a2a/read_report_by_job"
        assert audit_event["status"] == "success"
        assert audit_event["auth_scopes"] == ["report"]
        assert audit_event["job_id"] == job.job_id

    @pytest.mark.asyncio
    async def test_trusted_local_reads_own_report_and_artifact_metadata(
        self,
        executor,
        event_queue,
        context,
        tmp_path,
    ):
        """Loopback no-auth A2A can read its own bounded job resources."""
        report_path = tmp_path / "local-report.md"
        report_path.write_text("# Local report", encoding="utf-8")
        job = executor._mcp.job_store.create(
            company_name="Local Acme",
            mode="full",
            owner_client_id="a2a",
        )
        job.output_paths = [str(report_path)]

        context.message = {
            "parts": [
                {
                    "kind": "text",
                    "text": json.dumps(
                        {
                            "job_id": job.job_id,
                            "content_mode": "full",
                            "max_chars": 200,
                        }
                    ),
                }
            ],
            "metadata": {"skillId": "read_report_by_job"},
        }
        await executor.execute(context, event_queue)
        report = json.loads(_get_event_text(event_queue.enqueue_event.call_args[0][0]))

        event_queue.enqueue_event.reset_mock()
        context.message = {
            "parts": [{"kind": "text", "text": json.dumps({"job_id": job.job_id})}],
            "metadata": {"skillId": "read_artifacts_by_job"},
        }
        await executor.execute(context, event_queue)
        artifacts = json.loads(_get_event_text(event_queue.enqueue_event.call_args[0][0]))

        assert report["job_id"] == job.job_id
        assert report["artifacts"][0]["content"] == "# Local report"
        assert artifacts["job_id"] == job.job_id
        assert artifacts["company_name"] == "Local Acme"

    @pytest.mark.asyncio
    async def test_anonymous_report_read_fails_before_job_lookup(
        self,
        executor,
        event_queue,
        context,
    ):
        """An unmarked unauthenticated A2A request fails closed."""
        job = executor._mcp.job_store.create(
            company_name="Private",
            mode="full",
            owner_client_id="a2a",
        )
        executor._mcp._auth_context = None
        context.message = {
            "parts": [{"kind": "text", "text": json.dumps({"job_id": job.job_id})}],
            "metadata": {"skillId": "read_report_by_job"},
        }

        await executor.execute(context, event_queue)

        payload = json.loads(_get_event_text(event_queue.enqueue_event.call_args[0][0]))
        assert payload["error_type"] == "authentication_required"
        assert payload["missing_scopes"] == ["report"]

    @pytest.mark.asyncio
    async def test_authenticated_reserved_subject_cannot_read_local_a2a_job(
        self,
        executor,
        event_queue,
        context,
    ):
        """A caller-controlled reserved JWT subject cannot select local trust."""
        job = executor._mcp.job_store.create(
            company_name="Private",
            mode="full",
            owner_client_id="a2a",
        )
        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["report"]
        auth_context.client_id = "a2a"
        executor._mcp._auth_context = auth_context
        context.message = {
            "parts": [{"kind": "text", "text": json.dumps({"job_id": job.job_id})}],
            "metadata": {"skillId": "read_report_by_job"},
        }

        await executor.execute(context, event_queue)

        payload = json.loads(_get_event_text(event_queue.enqueue_event.call_args[0][0]))
        assert payload["error"] == "job_not_found"
        assert payload["job_id"] == job.job_id

    @pytest.mark.asyncio
    async def test_report_read_hides_other_client_job(
        self, executor, event_queue, context, tmp_path
    ):
        """read_report_by_job reuses the MCP ownership gate for A2A callers."""
        report_path = tmp_path / "Other_Report.md"
        report_path.write_text("# Report\n\nOTHER CLIENT REPORT BODY", encoding="utf-8")
        job = executor._mcp.job_store.create(
            company_name="Other Corp",
            mode="full",
            owner_client_id="client-2",
        )
        job.output_paths = [str(report_path)]

        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["report"]
        auth_context.client_id = "client-1"
        executor._mcp._auth_context = auth_context
        context.message = {
            "parts": [{"kind": "text", "text": json.dumps({"job_id": job.job_id})}],
            "metadata": {"skillId": "read_report_by_job"},
        }

        try:
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        event = event_queue.enqueue_event.call_args[0][0]
        data = json.loads(_get_event_text(event))
        text = json.dumps(data)
        assert data["error"] == "job_not_found"
        assert data["job_id"] == job.job_id
        assert "Other Corp" not in text
        assert "Other_Report.md" not in text
        assert "OTHER CLIENT REPORT BODY" not in text

    @pytest.mark.asyncio
    async def test_artifact_metadata_returns_owned_compact_a2a_payload(
        self, executor, event_queue, context, tmp_path
    ):
        """read_artifacts_by_job returns metadata for an owned job without report bodies."""
        report_path = tmp_path / "report.md"
        report_path.write_text("SECRET REPORT BODY", encoding="utf-8")
        missing_path = tmp_path / "missing.docx"
        job = executor._mcp.job_store.create(
            company_name="Acme",
            mode="full",
            owner_client_id="client-1",
        )
        job.output_paths = [str(report_path), str(missing_path)]

        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["read"]
        auth_context.client_id = "client-1"
        executor._mcp._auth_context = auth_context
        context.message = {
            "parts": [{"kind": "text", "text": json.dumps({"job_id": job.job_id})}],
            "metadata": {"skillId": "read_artifacts_by_job"},
        }

        try:
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        event = event_queue.enqueue_event.call_args[0][0]
        data = json.loads(_get_event_text(event))
        text = json.dumps(data)
        assert data["job_id"] == job.job_id
        assert data["company_name"] == "Acme"
        assert data["artifact_count"] == 2
        assert data["full_content_included"] is False
        assert data["artifacts"][0]["file_name"] == "report.md"
        assert data["artifacts"][0]["content_hash"].startswith("sha256:")
        assert data["artifacts"][1]["exists"] is False
        assert "SECRET REPORT BODY" not in text

        audit_event = _audit_events(executor)[0]
        assert audit_event["tool_name"] == "a2a/read_artifacts_by_job"
        assert audit_event["status"] == "success"
        assert audit_event["auth_scopes"] == ["read"]
        assert audit_event["job_id"] == job.job_id

    @pytest.mark.asyncio
    async def test_artifact_metadata_hides_other_client_job(
        self, executor, event_queue, context, tmp_path
    ):
        """read_artifacts_by_job uses the MCP ownership gate for A2A callers."""
        report_path = tmp_path / "other-report.md"
        report_path.write_text("OTHER CLIENT REPORT BODY", encoding="utf-8")
        job = executor._mcp.job_store.create(
            company_name="Other Corp",
            mode="full",
            owner_client_id="client-2",
        )
        job.output_paths = [str(report_path)]

        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["read"]
        auth_context.client_id = "client-1"
        executor._mcp._auth_context = auth_context
        context.message = {
            "parts": [{"kind": "text", "text": json.dumps({"job_id": job.job_id})}],
            "metadata": {"skillId": "read_artifacts_by_job"},
        }

        try:
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        event = event_queue.enqueue_event.call_args[0][0]
        data = json.loads(_get_event_text(event))
        text = json.dumps(data)
        assert data["error"] == "job_not_found"
        assert data["job_id"] == job.job_id
        assert "Other Corp" not in text
        assert "other-report.md" not in text
        assert "OTHER CLIENT REPORT BODY" not in text

    @pytest.mark.asyncio
    async def test_qa_summary_returns_owned_compact_a2a_payload(
        self, executor, event_queue, context, tmp_path
    ):
        """read_qa_summary_by_job returns compact QA metadata without detailed bodies."""
        qa_summary = tmp_path / "Acme_QA_Report.json"
        qa_summary.write_text(
            json.dumps(
                {
                    "overall_score": 94,
                    "status": "passed",
                    "ready_for_use": True,
                    "issues": [{"description": "SECRET QA ISSUE BODY"}],
                    "warnings": ["SECRET QA WARNING BODY"],
                    "recommendations": ["SECRET QA RECOMMENDATION BODY"],
                    "secret_details": "SECRET QA NARRATIVE BODY",
                }
            ),
            encoding="utf-8",
        )
        report_path = tmp_path / "report.md"
        report_path.write_text("SECRET REPORT BODY", encoding="utf-8")
        job = executor._mcp.job_store.create(
            company_name="Acme",
            mode="full",
            owner_client_id="client-1",
        )
        job.output_paths = [str(report_path), str(qa_summary)]

        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["read"]
        auth_context.client_id = "client-1"
        executor._mcp._auth_context = auth_context
        context.message = {
            "parts": [{"kind": "text", "text": json.dumps({"job_id": job.job_id})}],
            "metadata": {"skillId": "read_qa_summary_by_job"},
        }

        try:
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        event = event_queue.enqueue_event.call_args[0][0]
        data = json.loads(_get_event_text(event))
        text = json.dumps(data)
        assert data["job_id"] == job.job_id
        assert data["company_name"] == "Acme"
        assert data["summary_count"] == 1
        assert data["full_content_included"] is False
        summary = data["summaries"][0]
        assert summary["artifact_type"] == "qa_summary"
        assert summary["parsed"] is True
        assert summary["score_fields"] == {"overall_score": 94}
        assert summary["status_fields"] == {
            "ready_for_use": True,
            "status": "passed",
        }
        assert summary["count_fields"] == {
            "issues_count": 1,
            "recommendations_count": 1,
            "warnings_count": 1,
        }
        assert "SECRET QA ISSUE BODY" not in text
        assert "SECRET QA WARNING BODY" not in text
        assert "SECRET QA RECOMMENDATION BODY" not in text
        assert "SECRET QA NARRATIVE BODY" not in text
        assert "SECRET REPORT BODY" not in text

        audit_event = _audit_events(executor)[0]
        assert audit_event["tool_name"] == "a2a/read_qa_summary_by_job"
        assert audit_event["status"] == "success"
        assert audit_event["auth_scopes"] == ["read"]
        assert audit_event["job_id"] == job.job_id

    @pytest.mark.asyncio
    async def test_qa_summary_hides_other_client_job(
        self, executor, event_queue, context, tmp_path
    ):
        """read_qa_summary_by_job reuses the MCP ownership gate for A2A callers."""
        qa_summary = tmp_path / "Other_QA_Report.json"
        qa_summary.write_text(
            '{"overall_score": 88, "secret": "OTHER CLIENT QA BODY"}',
            encoding="utf-8",
        )
        job = executor._mcp.job_store.create(
            company_name="Other Corp",
            mode="full",
            owner_client_id="client-2",
        )
        job.output_paths = [str(qa_summary)]

        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["read"]
        auth_context.client_id = "client-1"
        executor._mcp._auth_context = auth_context
        context.message = {
            "parts": [{"kind": "text", "text": json.dumps({"job_id": job.job_id})}],
            "metadata": {"skillId": "read_qa_summary_by_job"},
        }

        try:
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        event = event_queue.enqueue_event.call_args[0][0]
        data = json.loads(_get_event_text(event))
        text = json.dumps(data)
        assert data["error"] == "job_not_found"
        assert data["job_id"] == job.job_id
        assert "Other Corp" not in text
        assert "Other_QA_Report.json" not in text
        assert "OTHER CLIENT QA BODY" not in text

    @pytest.mark.asyncio
    async def test_usage_summary_returns_owned_compact_a2a_payload(
        self, executor, event_queue, context, tmp_path
    ):
        """read_usage_summary_by_job returns compact manifest metadata without raw details."""
        report_path = tmp_path / "report.md"
        report_path.write_text("SECRET REPORT BODY", encoding="utf-8")
        job = executor._mcp.job_store.create(
            company_name="Acme",
            mode="full",
            owner_client_id="client-1",
        )
        manifest = tmp_path / "run_manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "job_id": job.job_id,
                    "company_name": "Acme",
                    "company_url": "https://secret.example",
                    "mode": "full",
                    "estimate": {
                        "cost_usd": 0.76,
                        "time_minutes": 42,
                        "estimated_at": "2026-06-28T19:00:00Z",
                    },
                    "approval": {
                        "token": "SECRET APPROVAL TOKEN",
                        "approved_at": "2026-06-28T19:01:00Z",
                        "approved_by": "client-secret",
                        "bound_to_estimate": True,
                    },
                    "budget": {
                        "approved_ceiling_usd": 0.8,
                        "runtime_budget_active": True,
                        "enforcement": {
                            "preflight": "refuses to start when estimate exceeds cap",
                            "runtime_checkpoints": True,
                            "runtime": "required Deep Research task cannot be stopped",
                            "checkpointed_stages": ["optional strategy generation"],
                            "non_interruptible_required_tasks": ["required Deep Research task"],
                        },
                    },
                    "execution": {
                        "started_at": "2026-06-28T19:02:00Z",
                        "completed_at": "2026-06-28T19:44:00Z",
                        "status": "completed",
                        "actual_cost_usd": 0.72,
                        "actual_time_minutes": 42,
                    },
                    "artifacts": [str(report_path), "secret artifact path"],
                }
            ),
            encoding="utf-8",
        )
        job.output_paths = [str(report_path)]

        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["read"]
        auth_context.client_id = "client-1"
        executor._mcp._auth_context = auth_context
        context.message = {
            "parts": [{"kind": "text", "text": json.dumps({"job_id": job.job_id})}],
            "metadata": {"skillId": "read_usage_summary_by_job"},
        }

        try:
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        event = event_queue.enqueue_event.call_args[0][0]
        data = json.loads(_get_event_text(event))
        text = json.dumps(data)
        assert data["job_id"] == job.job_id
        assert data["company_name"] == "Acme"
        assert data["summary_count"] == 1
        assert data["full_content_included"] is False
        summary = data["summaries"][0]
        assert summary["artifact_type"] == "run_manifest"
        assert summary["parsed"] is True
        assert summary["mode"] == "full"
        assert summary["estimate"] == {
            "cost_usd": 0.76,
            "estimated_at": "2026-06-28T19:00:00Z",
            "time_minutes": 42,
        }
        assert summary["approval"] == {
            "approved": True,
            "approved_at": "2026-06-28T19:01:00Z",
            "approved_by_present": True,
            "bound_to_estimate": True,
            "token_present": True,
        }
        assert summary["budget"] == {
            "approved_ceiling_usd": 0.8,
            "checkpointed_stages": ["optional strategy generation"],
            "non_interruptible_required_tasks": ["required Deep Research task"],
            "preflight": "refuses to start when estimate exceeds cap",
            "runtime": "required Deep Research task cannot be stopped",
            "runtime_budget_active": True,
            "runtime_checkpoints": True,
        }
        assert summary["execution"] == {
            "actual_cost_usd": 0.72,
            "actual_time_minutes": 42,
            "completed_at": "2026-06-28T19:44:00Z",
            "started_at": "2026-06-28T19:02:00Z",
            "status": "completed",
        }
        assert summary["artifact_count"] == 2
        assert "SECRET APPROVAL TOKEN" not in text
        assert "client-secret" not in text
        assert "https://secret.example" not in text
        assert "secret artifact path" not in text
        assert "SECRET REPORT BODY" not in text

        audit_event = _audit_events(executor)[0]
        assert audit_event["tool_name"] == "a2a/read_usage_summary_by_job"
        assert audit_event["status"] == "success"
        assert audit_event["auth_scopes"] == ["read"]
        assert audit_event["job_id"] == job.job_id

    @pytest.mark.asyncio
    async def test_usage_summary_hides_other_client_job(
        self, executor, event_queue, context, tmp_path
    ):
        """read_usage_summary_by_job reuses the MCP ownership gate for A2A callers."""
        report_path = tmp_path / "other-report.md"
        report_path.write_text("OTHER CLIENT REPORT BODY", encoding="utf-8")
        manifest = tmp_path / "run_manifest.json"
        manifest.write_text(
            '{"schema_version": "1.0", "company_url": "https://other-secret.example"}',
            encoding="utf-8",
        )
        job = executor._mcp.job_store.create(
            company_name="Other Corp",
            mode="full",
            owner_client_id="client-2",
        )
        job.output_paths = [str(report_path)]

        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["read"]
        auth_context.client_id = "client-1"
        executor._mcp._auth_context = auth_context
        context.message = {
            "parts": [{"kind": "text", "text": json.dumps({"job_id": job.job_id})}],
            "metadata": {"skillId": "read_usage_summary_by_job"},
        }

        try:
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        event = event_queue.enqueue_event.call_args[0][0]
        data = json.loads(_get_event_text(event))
        text = json.dumps(data)
        assert data["error"] == "job_not_found"
        assert data["job_id"] == job.job_id
        assert "Other Corp" not in text
        assert "other-report.md" not in text
        assert "https://other-secret.example" not in text
        assert "OTHER CLIENT REPORT BODY" not in text

    @pytest.mark.asyncio
    async def test_source_summary_returns_owned_compact_a2a_payload(
        self, executor, event_queue, context, tmp_path
    ):
        """read_source_summary_by_job returns compact source metadata without report prose."""
        report_path = tmp_path / "Acme_Strategic_Overview.md"
        report_path.write_text(
            "\n".join(
                [
                    "# Strategic Overview",
                    "SECRET BODY CLAIM uses sources [cite: 1] and [cite: 2].",
                    "Another body-only reference appears as [3].",
                    "",
                    "## Sources",
                    "[cite: 1] Acme newsroom - https://www.acme.example/news?q=launch",
                    "[cite: 2] https://investors.acme.example/q4",
                    "[3] SEC filing",
                    "    https://sec.gov/Archives/example",
                    "[cite: 4] https://www.acme.example/news?q=launch",
                    "[cite: 5] not-a-url",
                ]
            ),
            encoding="utf-8",
        )
        job = executor._mcp.job_store.create(
            company_name="Acme",
            mode="full",
            owner_client_id="client-1",
        )
        job.output_paths = [str(report_path)]

        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["read"]
        auth_context.client_id = "client-1"
        executor._mcp._auth_context = auth_context
        context.message = {
            "parts": [{"kind": "text", "text": json.dumps({"job_id": job.job_id})}],
            "metadata": {"skillId": "read_source_summary_by_job"},
        }

        try:
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        event = event_queue.enqueue_event.call_args[0][0]
        data = json.loads(_get_event_text(event))
        text = json.dumps(data)
        assert data["job_id"] == job.job_id
        assert data["company_name"] == "Acme"
        assert data["summary_count"] == 1
        assert data["full_content_included"] is False
        summary = data["summaries"][0]
        assert summary["artifact_type"] == "report_markdown"
        assert summary["parsed"] is True
        assert summary["source_section_present"] is True
        assert summary["inline_reference_count"] == 3
        assert summary["referenced_numbers"] == [1, 2, 3]
        assert summary["definition_count"] == 4
        assert summary["invalid_source_count"] == 1
        assert summary["duplicate_url_count"] == 1
        assert summary["unused_definition_numbers"] == [4]
        assert summary["domains"][0] == {"count": 2, "domain": "acme.example"}
        assert summary["sources"][0] == {
            "domain": "acme.example",
            "reference": 1,
            "title": "Acme newsroom",
            "url": "https://www.acme.example/news?q=launch",
        }
        assert "SECRET BODY CLAIM" not in text
        assert "Another body-only reference" not in text

        audit_event = _audit_events(executor)[0]
        assert audit_event["tool_name"] == "a2a/read_source_summary_by_job"
        assert audit_event["status"] == "success"
        assert audit_event["auth_scopes"] == ["read"]
        assert audit_event["job_id"] == job.job_id

    @pytest.mark.asyncio
    async def test_source_summary_hides_other_client_job(
        self, executor, event_queue, context, tmp_path
    ):
        """read_source_summary_by_job reuses the MCP ownership gate for A2A callers."""
        report_path = tmp_path / "Other_Report.md"
        report_path.write_text(
            "OTHER CLIENT REPORT BODY [cite: 1]\n\n## Sources\n[cite: 1] https://other.example",
            encoding="utf-8",
        )
        job = executor._mcp.job_store.create(
            company_name="Other Corp",
            mode="full",
            owner_client_id="client-2",
        )
        job.output_paths = [str(report_path)]

        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["read"]
        auth_context.client_id = "client-1"
        executor._mcp._auth_context = auth_context
        context.message = {
            "parts": [{"kind": "text", "text": json.dumps({"job_id": job.job_id})}],
            "metadata": {"skillId": "read_source_summary_by_job"},
        }

        try:
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        event = event_queue.enqueue_event.call_args[0][0]
        data = json.loads(_get_event_text(event))
        text = json.dumps(data)
        assert data["error"] == "job_not_found"
        assert data["job_id"] == job.job_id
        assert "Other Corp" not in text
        assert "Other_Report.md" not in text
        assert "https://other.example" not in text
        assert "OTHER CLIENT REPORT BODY" not in text

    def _write_trace(self, path) -> None:
        header = {
            "schema_version": "1.1",
            "run_id": "trace-run-1",
            "company": "Acme_Corp",
            "started_at": "2026-06-28T21:00:00",
        }
        base_entry = {
            "run_id": "trace-run-1",
            "url": "https://secret.example/page",
            "timestamp": "2026-06-28T21:00:01",
            "tier_attempts": [],
            "success_tier": None,
            "blocked": False,
            "block_type": None,
            "blocked_reason": None,
            "http_status": None,
            "content_type": None,
            "final_url": "https://secret.example/final",
            "elapsed_total_ms": 0.0,
            "extracted_text_length": None,
            "validation_result": None,
            "access_assessment": None,
        }
        entries = [
            {
                **base_entry,
                "tier_attempts": [
                    {"tier": "requests", "success": False, "elapsed_ms": 100.0},
                    {"tier": "playwright", "success": True, "elapsed_ms": 500.0},
                ],
                "success_tier": "playwright",
                "http_status": 200,
                "extracted_text_length": 1200,
                "validation_result": {"valid": True},
            },
            {
                **base_entry,
                "tier_attempts": [
                    {"tier": "requests", "success": False, "elapsed_ms": 250.0},
                ],
                "blocked": True,
                "block_type": "hard_block",
                "http_status": 403,
                "extracted_text_length": 100,
                "validation_result": {"valid": False},
            },
        ]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(json.dumps(row) for row in [header, *entries]) + "\n",
            encoding="utf-8",
        )

    @pytest.mark.asyncio
    async def test_trace_summary_returns_owned_compact_a2a_payload(
        self, executor, event_queue, context, tmp_path
    ):
        """read_trace_summary_by_job returns compact scrape telemetry only."""
        trace_path = tmp_path / "logs" / "scrape_traces" / "Acme_Corp_20260628.jsonl"
        self._write_trace(trace_path)
        job = executor._mcp.job_store.create(
            company_name="Acme",
            mode="full",
            owner_client_id="client-1",
        )
        job.output_paths = [str(trace_path)]

        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["read"]
        auth_context.client_id = "client-1"
        executor._mcp._auth_context = auth_context
        context.message = {
            "parts": [{"kind": "text", "text": json.dumps({"job_id": job.job_id})}],
            "metadata": {"skillId": "read_trace_summary_by_job"},
        }

        try:
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        event = event_queue.enqueue_event.call_args[0][0]
        data = json.loads(_get_event_text(event))
        text = json.dumps(data)
        assert data["job_id"] == job.job_id
        assert data["company_name"] == "Acme"
        assert data["summary_count"] == 1
        assert data["full_content_included"] is False
        summary = data["summaries"][0]
        assert summary["artifact_type"] == "scrape_trace"
        assert summary["parsed"] is True
        assert summary["trace_schema_version"] == "1.1"
        assert summary["raw_entries_included"] is False
        assert summary["urls_included"] is False
        assert summary["entry_count"] == 2
        assert summary["success_count"] == 1
        assert summary["failure_count"] == 1
        assert summary["success_rate"] == 0.5
        assert summary["blocked_count"] == 1
        assert summary["block_type_counts"] == [{"count": 1, "value": "hard_block"}]
        assert summary["http_status_counts"] == [
            {"count": 1, "value": "200"},
            {"count": 1, "value": "403"},
        ]
        assert summary["validated_page_count"] == 2
        assert summary["valid_page_count"] == 1
        assert summary["content_valid_rate"] == 0.5
        by_tier = {tier["tier"]: tier for tier in summary["tier_summaries"]}
        assert by_tier["requests"]["attempts"] == 2
        assert by_tier["requests"]["successes"] == 0
        assert by_tier["playwright"]["success_rate"] == 1.0
        assert by_tier["playwright"]["p95_latency_ms"] == 500.0
        assert "https://secret.example" not in text
        assert "secret.example" not in text

        audit_event = _audit_events(executor)[0]
        assert audit_event["tool_name"] == "a2a/read_trace_summary_by_job"
        assert audit_event["status"] == "success"
        assert audit_event["auth_scopes"] == ["read"]
        assert audit_event["job_id"] == job.job_id

    @pytest.mark.asyncio
    async def test_trace_summary_hides_other_client_job(
        self, executor, event_queue, context, tmp_path
    ):
        """read_trace_summary_by_job reuses the MCP ownership gate for A2A callers."""
        trace_path = tmp_path / "logs" / "scrape_traces" / "Other_Corp_20260628.jsonl"
        self._write_trace(trace_path)
        job = executor._mcp.job_store.create(
            company_name="Other Corp",
            mode="full",
            owner_client_id="client-2",
        )
        job.output_paths = [str(trace_path)]

        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["read"]
        auth_context.client_id = "client-1"
        executor._mcp._auth_context = auth_context
        context.message = {
            "parts": [{"kind": "text", "text": json.dumps({"job_id": job.job_id})}],
            "metadata": {"skillId": "read_trace_summary_by_job"},
        }

        try:
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        event = event_queue.enqueue_event.call_args[0][0]
        data = json.loads(_get_event_text(event))
        text = json.dumps(data)
        assert data["error"] == "job_not_found"
        assert data["job_id"] == job.job_id
        assert "Other Corp" not in text
        assert "Other_Corp_20260628.jsonl" not in text
        assert "secret.example" not in text

    def _write_verification(self, path) -> None:
        path.write_text(
            json.dumps(
                {
                    "trust_score": 0.5,
                    "trust_percentage": 50,
                    "verified_count": 1,
                    "unverified_count": 0,
                    "contradicted_count": 1,
                    "total_claims": 2,
                    "duration_seconds": 12.4,
                    "claim_results": [
                        {
                            "claim": "Secret claim text",
                            "status": "verified",
                            "supporting_sources": ["https://secret.example/source"],
                            "evidence_sources": ["https://evidence.example/source"],
                            "search_query": "secret acquisition query",
                            "explanation": "Sensitive explanation",
                            "first_party_downgrade": True,
                        },
                        {
                            "claim": "Another secret claim",
                            "status": "contradicted",
                            "supporting_sources": ["https://secret.example/conflict"],
                            "search_query": "secret contradiction query",
                            "explanation": "Sensitive contradiction",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

    @pytest.mark.asyncio
    async def test_verification_summary_returns_owned_compact_a2a_payload(
        self, executor, event_queue, context, tmp_path
    ):
        """read_verification_summary_by_job returns compact claim metadata only."""
        verification = tmp_path / "verification.json"
        self._write_verification(verification)
        job = executor._mcp.job_store.create(
            company_name="Acme",
            mode="full",
            owner_client_id="client-1",
        )
        job.output_paths = [str(verification)]

        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["read"]
        auth_context.client_id = "client-1"
        executor._mcp._auth_context = auth_context
        context.message = {
            "parts": [{"kind": "text", "text": json.dumps({"job_id": job.job_id})}],
            "metadata": {"skillId": "read_verification_summary_by_job"},
        }

        try:
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        event = event_queue.enqueue_event.call_args[0][0]
        data = json.loads(_get_event_text(event))
        text = json.dumps(data)
        assert data["job_id"] == job.job_id
        assert data["company_name"] == "Acme"
        assert data["summary_count"] == 1
        assert data["full_content_included"] is False
        summary = data["summaries"][0]
        assert summary["artifact_type"] == "verification_summary"
        assert summary["parsed"] is True
        assert summary["raw_claim_results_included"] is False
        assert summary["source_urls_included"] is False
        assert summary["search_queries_included"] is False
        assert summary["trust_score"] == 0.5
        assert summary["trust_percentage"] == 50
        assert summary["verification_gate"] == "WARN"
        assert summary["total_claims"] == 2
        assert summary["verified_count"] == 1
        assert summary["contradicted_count"] == 1
        assert summary["claim_result_count"] == 2
        assert summary["first_party_downgrade_count"] == 1
        assert summary["source_reference_count"] == 3
        assert summary["claim_status_counts"] == [
            {"count": 1, "value": "contradicted"},
            {"count": 1, "value": "verified"},
        ]
        assert "Secret claim text" not in text
        assert "secret.example" not in text
        assert "secret acquisition query" not in text
        assert "Sensitive explanation" not in text

        audit_event = _audit_events(executor)[0]
        assert audit_event["tool_name"] == "a2a/read_verification_summary_by_job"
        assert audit_event["status"] == "success"
        assert audit_event["auth_scopes"] == ["read"]
        assert audit_event["job_id"] == job.job_id

    @pytest.mark.asyncio
    async def test_verification_summary_hides_other_client_job(
        self, executor, event_queue, context, tmp_path
    ):
        """read_verification_summary_by_job reuses the MCP ownership gate."""
        verification = tmp_path / "verification.json"
        self._write_verification(verification)
        job = executor._mcp.job_store.create(
            company_name="Other Corp",
            mode="full",
            owner_client_id="client-2",
        )
        job.output_paths = [str(verification)]

        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["read"]
        auth_context.client_id = "client-1"
        executor._mcp._auth_context = auth_context
        context.message = {
            "parts": [{"kind": "text", "text": json.dumps({"job_id": job.job_id})}],
            "metadata": {"skillId": "read_verification_summary_by_job"},
        }

        try:
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        event = event_queue.enqueue_event.call_args[0][0]
        data = json.loads(_get_event_text(event))
        text = json.dumps(data)
        assert data["error"] == "job_not_found"
        assert data["job_id"] == job.job_id
        assert "Other Corp" not in text
        assert "verification.json" not in text
        assert "Secret claim text" not in text
        assert "secret.example" not in text

    def _write_calibration_sidecar(self, report_path) -> None:
        sidecar = report_path.with_name(report_path.name + ".calibration.json")
        sidecar.write_text(
            json.dumps(
                {
                    "report_file": report_path.name,
                    "max_per_label": 10,
                    "judge": {
                        "kind": "local",
                        "model": "qwen2.5:14b",
                        "cloud_fallbacks": 1,
                    },
                    "judge_agreement": {
                        "scope": "report",
                        "local_model": "qwen2.5:14b",
                        "compared": 4,
                        "agreed": 3,
                        "agreement": 0.75,
                    },
                    "per_label": {
                        "Confirmed": {
                            "sampled": 3,
                            "traceable": 1,
                            "untraceable": 1,
                            "no_source": 1,
                            "unfetchable": 0,
                            "exempt": 0,
                            "source_copied": 0,
                            "precision": 0.333,
                        },
                        "Hypothesis": {
                            "sampled": 2,
                            "traceable": 0,
                            "untraceable": 0,
                            "no_source": 0,
                            "unfetchable": 0,
                            "exempt": 1,
                            "source_copied": 1,
                            "precision": None,
                        },
                    },
                    "validation_rubric": {
                        "claims_with_reviews": 2,
                        "source_reviews": 3,
                        "support": {"supported": 2, "unsupported": 1},
                        "contradiction": {
                            "direct": 1,
                            "none": 2,
                            "partial": 0,
                            "unknown": 0,
                        },
                        "source_independence": {
                            "independent": 1,
                            "first_party": 2,
                            "unknown": 0,
                        },
                        "source_authority": {
                            "high": 1,
                            "medium": 1,
                            "low": 1,
                            "unknown": 0,
                        },
                        "reasoning_strength": {
                            "strong": 2,
                            "partial": 1,
                            "weak": 0,
                            "unknown": 0,
                        },
                        "uncertainty_honesty": {
                            "honest": 2,
                            "overstated": 1,
                            "understated": 0,
                            "unknown": 0,
                        },
                        "business_relevance": {
                            "high": 2,
                            "medium": 1,
                            "low": 0,
                            "unknown": 0,
                        },
                    },
                    "claims": [
                        {
                            "label": "Confirmed",
                            "section": "Secret Section",
                            "sentence": "Secret calibrated claim text",
                            "source_urls": ["https://secret.example/source"],
                            "verdict": "traceable",
                            "evidence_reviews": [
                                {
                                    "supported": True,
                                    "rationale": "Sensitive evidence rationale",
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    @pytest.mark.asyncio
    async def test_calibration_summary_returns_owned_compact_a2a_payload(
        self, executor, event_queue, context, tmp_path
    ):
        """read_calibration_summary_by_job returns compact label metadata only."""
        report = tmp_path / "Acme_Report.md"
        report.write_text("# Report\n\nSECRET REPORT BODY", encoding="utf-8")
        self._write_calibration_sidecar(report)
        job = executor._mcp.job_store.create(
            company_name="Acme",
            mode="full",
            owner_client_id="client-1",
        )
        job.output_paths = [str(report)]

        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["read"]
        auth_context.client_id = "client-1"
        executor._mcp._auth_context = auth_context
        context.message = {
            "parts": [{"kind": "text", "text": json.dumps({"job_id": job.job_id})}],
            "metadata": {"skillId": "read_calibration_summary_by_job"},
        }

        try:
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        event = event_queue.enqueue_event.call_args[0][0]
        data = json.loads(_get_event_text(event))
        text = json.dumps(data)
        assert data["job_id"] == job.job_id
        assert data["company_name"] == "Acme"
        assert data["summary_count"] == 1
        assert data["full_content_included"] is False
        summary = data["summaries"][0]
        assert summary["artifact_type"] == "calibration_sidecar"
        assert summary["parsed"] is True
        assert summary["raw_claims_included"] is False
        assert summary["claim_text_included"] is False
        assert summary["source_urls_included"] is False
        assert summary["evidence_reviews_included"] is False
        assert summary["rationales_included"] is False
        assert summary["report_file"] == "Acme_Report.md"
        assert summary["judge"] == {
            "kind": "local",
            "model": "qwen2.5:14b",
            "cloud_fallbacks": 1,
        }
        assert summary["judge_agreement"] == {
            "scope": "report",
            "local_model": "qwen2.5:14b",
            "compared": 4,
            "agreed": 3,
            "agreement": 0.75,
        }
        assert summary["claim_result_count"] == 1
        assert summary["claims_sampled"] == 5
        assert summary["decidable_claims"] == 3
        assert summary["traceable_count"] == 1
        assert summary["untraceable_count"] == 1
        assert summary["no_source_count"] == 1
        assert summary["exempt_count"] == 1
        assert summary["source_copied_count"] == 1
        by_label = {item["label"]: item for item in summary["per_label"]}
        assert by_label["Confirmed"]["precision"] == 0.333
        assert by_label["Hypothesis"]["exempt"] == 1
        assert by_label["Hypothesis"]["source_copied"] == 1
        rubric = summary["validation_rubric"]
        assert rubric["claims_with_reviews"] == 2
        assert rubric["source_reviews"] == 3
        assert rubric["support_counts"] == [
            {"count": 2, "value": "supported"},
            {"count": 1, "value": "unsupported"},
        ]
        assert "SECRET REPORT BODY" not in text
        assert "Secret calibrated claim text" not in text
        assert "secret.example" not in text
        assert "Sensitive evidence rationale" not in text

        audit_event = _audit_events(executor)[0]
        assert audit_event["tool_name"] == "a2a/read_calibration_summary_by_job"
        assert audit_event["status"] == "success"
        assert audit_event["auth_scopes"] == ["read"]
        assert audit_event["job_id"] == job.job_id

    @pytest.mark.asyncio
    async def test_calibration_summary_hides_other_client_job(
        self, executor, event_queue, context, tmp_path
    ):
        """read_calibration_summary_by_job reuses the MCP ownership gate."""
        report = tmp_path / "Other_Report.md"
        report.write_text("# Report\n\nOTHER CLIENT REPORT BODY", encoding="utf-8")
        self._write_calibration_sidecar(report)
        job = executor._mcp.job_store.create(
            company_name="Other Corp",
            mode="full",
            owner_client_id="client-2",
        )
        job.output_paths = [str(report)]

        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["read"]
        auth_context.client_id = "client-1"
        executor._mcp._auth_context = auth_context
        context.message = {
            "parts": [{"kind": "text", "text": json.dumps({"job_id": job.job_id})}],
            "metadata": {"skillId": "read_calibration_summary_by_job"},
        }

        try:
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        event = event_queue.enqueue_event.call_args[0][0]
        data = json.loads(_get_event_text(event))
        text = json.dumps(data)
        assert data["error"] == "job_not_found"
        assert data["job_id"] == job.job_id
        assert "Other Corp" not in text
        assert "Other_Report.md" not in text
        assert "OTHER CLIENT REPORT BODY" not in text
        assert "Secret calibrated claim text" not in text
        assert "secret.example" not in text

    @pytest.mark.asyncio
    async def test_stage_scorecard_summary_returns_compact_a2a_payload(
        self, executor, event_queue, context, tmp_path, monkeypatch
    ):
        """read_stage_scorecard reuses the compact MCP summary without raw bodies."""
        monkeypatch.chdir(tmp_path)
        scorecard_dir = tmp_path / "output" / "evals" / "eval-a2a-1"
        scorecard_dir.mkdir(parents=True)
        (scorecard_dir / "stage_eval_scorecard.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "decision_policy": "candidate_for_human_review_only",
                    "min_quality_score": 85.0,
                    "max_failure_rate": 0.0,
                    "prompt": "SECRET PROMPT",
                    "report_body": "SECRET REPORT BODY",
                    "rows": [
                        {
                            "stage_id": "fast.source_relevance",
                            "backend_id": "codex-host",
                            "inference_profile": "agent",
                            "attempts": 2,
                            "selected_attempts": 2,
                            "fallback_attempts": 0,
                            "failed_attempts": 0,
                            "failure_rate": 0.0,
                            "actual_cost_usd": 0.0,
                            "avg_duration_seconds": 1.5,
                            "quality_score": 95.0,
                            "quality_sample_size": 4,
                            "quality_sources": ["SECRET QUALITY SOURCE BODY"],
                            "review_status": "candidate_for_human_review",
                            "blockers": [],
                            "raw_run_state": "SECRET RAW RUN STATE",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["read"]
        auth_context.client_id = "client-1"
        executor._mcp._auth_context = auth_context
        context.message = {
            "parts": [{"kind": "text", "text": '{"eval_id":"eval-a2a-1"}'}],
            "metadata": {"skillId": "read_stage_scorecard"},
        }

        try:
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        event = event_queue.enqueue_event.call_args[0][0]
        data = json.loads(_get_event_text(event))
        text = json.dumps(data)
        assert data["eval_id"] == "eval-a2a-1"
        assert data["summary"]["row_count"] == 1
        assert data["summary"]["candidate_count"] == 1
        assert data["summary"]["rows"][0]["backend_id"] == "codex-host"
        assert "SECRET PROMPT" not in text
        assert "SECRET REPORT BODY" not in text
        assert "SECRET QUALITY SOURCE BODY" not in text
        assert "SECRET RAW RUN STATE" not in text

        audit_event = _audit_events(executor)[0]
        assert audit_event["tool_name"] == "a2a/read_stage_scorecard"
        assert audit_event["status"] == "success"
        assert audit_event["auth_scopes"] == ["read"]

    @pytest.mark.asyncio
    async def test_research_create_uses_authenticated_client_owner(
        self, executor, event_queue, context
    ):
        """research_company passes the caller client id into job creation."""
        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["research"]
        auth_context.client_id = "client-1"
        executor._mcp._auth_context = auth_context
        context.context_id = "ctx-1"
        captured_kwargs = {}

        def capture_create(**kwargs):
            captured_kwargs.update(kwargs)
            raise RuntimeError("stop before background stream")

        context.message = {
            "parts": [
                {
                    "kind": "text",
                    "text": '{"url": "https://example.com", "name": "Example"}',
                }
            ],
            "metadata": {"skillId": "research_company"},
        }

        try:
            with patch.object(executor._mcp.job_store, "create", side_effect=capture_create):
                await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        assert captured_kwargs["owner_client_id"] == "client-1"

    @pytest.mark.asyncio
    async def test_check_jobs_hides_other_client_job(self, executor, event_queue, context):
        """A2A check_jobs does not expose another authenticated client's job."""
        executor._mcp.job_store.create(
            company_name="Other",
            mode="full",
            owner_client_id="client-2",
        )
        auth_context = MagicMock()
        auth_context.is_authenticated = True
        auth_context.scopes = ["read"]
        auth_context.client_id = "client-1"
        executor._mcp._auth_context = auth_context
        context.message["metadata"] = {"skillId": "check_jobs"}

        try:
            await executor.execute(context, event_queue)
        finally:
            executor._mcp._auth_context = None

        event = event_queue.enqueue_event.call_args[0][0]
        data = json.loads(_get_event_text(event))
        assert data["status"] == "idle"

    @pytest.mark.asyncio
    async def test_qa_no_report(self, executor, event_queue, context):
        """run_qa without path and no recent job asks for path."""
        context.message = {
            "parts": [{"kind": "text", "text": "run qa"}],
            "metadata": {"skillId": "run_qa"},
        }
        await executor.execute(context, event_queue)
        event = event_queue.enqueue_event.call_args[0][0]
        text = _get_event_text(event)
        assert "path" in text.lower() or "report" in text.lower()

    @pytest.mark.asyncio
    async def test_executor_handles_exception(self, executor, event_queue, context):
        """Executor catches exceptions and enqueues error event."""
        context.message["metadata"] = {"skillId": "system_health"}
        with patch("primr.a2a.executor.get_doctor_status", side_effect=RuntimeError("boom")):
            await executor.execute(context, event_queue)

        # Should enqueue at least one event with error content
        assert event_queue.enqueue_event.called
        event = event_queue.enqueue_event.call_args[0][0]
        text = _get_event_text(event)
        assert "failed" in text.lower() or "error" in text.lower() or "Internal" in text


def _audit_events(executor) -> list[dict]:
    return [
        json.loads(line)
        for line in executor._mcp.audit_log.path.read_text(encoding="utf-8").splitlines()
    ]


def _get_event_text(event) -> str:
    """Extract text from an A2A event (handles Message, TaskStatusUpdateEvent, etc.)."""
    # Direct Message with parts
    if hasattr(event, "parts") and event.parts:
        for part in event.parts:
            # Part(root=TextPart(...)) wrapper
            root = getattr(part, "root", part)
            if hasattr(root, "text"):
                return root.text
            if isinstance(root, dict) and root.get("kind") == "text":
                return root["text"]

    # TaskStatusUpdateEvent — message in status.message
    status = getattr(event, "status", None)
    if status:
        msg = getattr(status, "message", None)
        if isinstance(msg, dict):
            parts = msg.get("parts", [])
            for part in parts:
                if isinstance(part, dict) and part.get("kind") == "text":
                    return part.get("text", "")
        elif hasattr(msg, "parts"):
            for part in msg.parts:
                root = getattr(part, "root", part)
                if hasattr(root, "text"):
                    return root.text

    return ""
