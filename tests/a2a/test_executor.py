"""Tests for A2A agent executor."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

a2a = pytest.importorskip("a2a")

from primr.a2a.executor import (
    PrimrAgentExecutor,
    _a2a_client_id,
    _caller_owns_job,
    _extract_skill_id,
    _extract_text,
    _parse_eval_id,
    _parse_job_id,
    _parse_research_params,
)
from primr.a2a.task_store import PrimrTaskStore
from primr.a2a.types import A2ATaskMapping


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

    def test_plain_text_job_id(self):
        assert _parse_job_id(" job-2026-06 ") == "job-2026-06"


class TestA2AOwnershipHelpers:
    """Tests for A2A caller ownership helpers."""

    def test_local_owner_without_auth_context(self):
        mcp_server = MagicMock()
        mcp_server._auth_context = None
        assert _a2a_client_id(mcp_server) == "a2a"

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
