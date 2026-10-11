"""Local-only draft transport, source support, publication, and rendering."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
from docx import Document
from hypothesis import given, settings
from hypothesis import strategies as st

from primr import cli_entry
from primr.ai.local_inference import resolve_local_draft_runtime
from primr.ai.openai_compatible_client import ChatCompletionResult
from primr.core import local_draft, local_stage_eval
from primr.core.evidence_bundle_input import load_prepared_evidence

SOURCE_TEXT = (
    "ExampleCo supplies scheduling software for independent repair businesses. "
    "Its customers use monthly subscriptions to manage workshop bookings. "
    "The website reports that customers can export their scheduling records."
)
SOURCE_QUOTES = (
    "ExampleCo supplies scheduling software for independent repair businesses.",
    "Its customers use monthly subscriptions to manage workshop bookings.",
)


@pytest.fixture
def prep_bundle(tmp_path: Path) -> Path:
    root = tmp_path / "ExampleCo_Primr_Prep_20261011"
    root.mkdir()
    (root / "source_index.json").write_text(
        json.dumps(
            {
                "schema": "primr.evidence-source-index",
                "version": "1.0",
                "sources": [
                    {
                        "source_id": "S001",
                        "url": "https://example.co",
                        "characters": len(SOURCE_TEXT),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "scraped_content.txt").write_text(
        f"# ExampleCo - Scraped Content\n\n{'=' * 60}\nURL: https://example.co\n{'=' * 60}\n{SOURCE_TEXT}\n",
        encoding="utf-8",
        newline="",  # Match the producer's platform-independent atomic byte writer.
    )
    artifacts = []
    for name in ("source_index.json", "scraped_content.txt"):
        content = (root / name).read_bytes()
        artifacts.append(
            {
                "path": name,
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    (root / "prep_manifest.json").write_text(
        json.dumps(
            {
                "schema": "primr.host-evidence-bundle",
                "version": "1.0",
                "status": "partial",
                "company_name": "ExampleCo",
                "artifacts": artifacts,
                "quality": {"limitations": ["Independent market evidence was not collected."]},
            }
        ),
        encoding="utf-8",
    )
    return root


@pytest.fixture
def local_server(monkeypatch):
    state = {
        "requests": [],
        "authorizations": [],
        "remote_metadata": {},
        "chat_status": 200,
        "redirect": None,
        "chat_redirect": None,
        "unexpected_egress": [],
        "reply": None,
        "model": "qwen3:synthetic",
        "models_payload": None,
        "tags_payload": None,
        "tags_status": 200,
        "reducer_reply": None,
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def reply(self, status, payload):
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            state["requests"].append(("GET", self.path, self.headers.get("Authorization")))
            state["authorizations"].append(self.headers.get("Authorization"))
            if state["redirect"]:
                self.send_response(302)
                self.send_header("Location", state["redirect"])
                self.send_header("Content-Length", "0")
                self.end_headers()
            elif self.path == "/v1/models":
                self.reply(
                    200,
                    state["models_payload"]
                    if state["models_payload"] is not None
                    else {"data": [{"id": state["model"], "owned_by": "library"}]},
                )
            elif self.path == "/api/tags":
                self.reply(
                    state["tags_status"],
                    state["tags_payload"]
                    if state["tags_payload"] is not None
                    else {
                        "models": [
                            {
                                "name": state["model"],
                                "details": {"quantization_level": "Q4_K_M"},
                                **state["remote_metadata"],
                            }
                        ]
                    },
                )
            else:
                self.reply(404, {})

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["requests"].append(("POST", self.path, payload))
            state["authorizations"].append(self.headers.get("Authorization"))
            if state["chat_redirect"]:
                self.send_response(307)
                self.send_header("Location", state["chat_redirect"])
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if state["chat_status"] != 200:
                self.reply(state["chat_status"], {"error": {"message": "synthetic busy"}})
                return
            prompt = payload["messages"][-1]["content"]
            assert (
                len("".join(row["content"] for row in payload["messages"]).encode())
                <= local_draft.MAX_PROMPT_BYTES
            )
            if "Extract up to four" in prompt:
                source_id = re.search(r"Source ID: (S\d+)", prompt)[1]
                response = {
                    "claims": [
                        {
                            "section": "company",
                            "claim": "The company reports that it supplies scheduling software to independent repair businesses.",
                            "source_id": source_id,
                            "quote": SOURCE_QUOTES[0],
                        },
                        {
                            "section": "customers",
                            "claim": "The company describes monthly subscriptions that help repair businesses manage their workshop bookings.",
                            "source_id": source_id,
                            "quote": SOURCE_QUOTES[1],
                        },
                    ]
                }
            else:
                response = {"claim_ids": re.findall(r'"claim_id": "(C\d+)"', prompt)}
                if state["reducer_reply"] is not None:
                    response = state["reducer_reply"]
            text = state["reply"] if state["reply"] is not None else json.dumps(response)
            self.reply(
                200,
                {
                    "id": "synthetic-response",
                    "object": "chat.completion",
                    "created": 0,
                    "model": state["model"],
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": text},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
                },
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}/v1"
    state["base_url"] = base_url
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", base_url)
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-unused-key")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-unused-key")
    monkeypatch.delenv("LOCAL_LLM_API_KEY", raising=False)
    original_connect = socket.socket.connect

    def connect_only_to_runtime(stream, address):
        if address[:2] != ("127.0.0.1", server.server_port):
            state["unexpected_egress"].append(address)
        assert address[:2] == ("127.0.0.1", server.server_port), f"Unexpected egress: {address}"
        return original_connect(stream, address)

    monkeypatch.setattr(socket.socket, "connect", connect_only_to_runtime)
    # Either transport trusting ambient proxies would hit an unapproved port.
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        monkeypatch.setenv(name, "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("no_proxy", "")
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert state["unexpected_egress"] == []


def test_draft_dry_run_is_light_and_only_inspects_configured_runtime(
    prep_bundle, local_server, monkeypatch, capsys
):
    monkeypatch.setitem(sys.modules, "primr.core.cli", None)
    assert cli_entry.main(["draft", "--local", "--dry-run", str(prep_bundle)]) == 0
    assert [row[:2] for row in local_server["requests"]] == [
        ("GET", "/v1/models"),
        ("GET", "/api/tags"),
    ]
    assert not list(prep_bundle.glob("Local_Draft*"))
    output = capsys.readouterr().out
    assert "Conservative planning time" in output
    assert "Inference calls: 0" in output
    assert "$0.00" in output


def test_real_local_transport_publishes_cited_markdown_docx_and_zero_spend(
    prep_bundle, local_server
):
    assert cli_entry.main(["draft", "--local", str(prep_bundle)]) == 0
    output = next(prep_bundle.glob("Local_Draft_*"))
    markdown = next(output.glob("*.md")).read_text()
    document = Document(next(output.glob("*.docx")))
    rendered = "\n".join(paragraph.text for paragraph in document.paragraphs)
    for text in (markdown, rendered):
        text = text.replace("\\_", "_")
        assert "Local draft, not the validated Primr report" in text
        assert "Q4_K_M" in text
        assert "qwen3:synthetic" in text
        assert SOURCE_QUOTES[0] in text
        assert SOURCE_QUOTES[1] in text
        assert "[S001]" in text
        assert "\u2014" not in text
        assert "\u2013" not in text
    assert "Q4_K_M" in rendered
    for line in markdown.splitlines():
        if line.startswith("- Reported:"):
            assert set(re.findall(r"\[(S\d+)\]", line)) == {"S001"}
    manifest = json.loads((output / "draft_manifest.json").read_text())
    assert manifest["incremental_api_cost_usd"] == 0.0
    assert manifest["cloud_fallback_allowed"] is False
    assert manifest["baseline_kind"] == "local_draft"
    assert manifest["model_calls_made"] == 3
    assert manifest["coverage"]["prep_status"] == "partial"
    assert (output / "scraped_content.txt").read_bytes() == (
        prep_bundle / "scraped_content.txt"
    ).read_bytes()
    requests = local_server["requests"]
    assert {row[1] for row in requests} == {"/v1/models", "/api/tags", "/v1/chat/completions"}
    assert all(row[2]["model"] == "qwen3:synthetic" for row in requests if row[0] == "POST")
    assert all(row[2]["reasoning_effort"] == "none" for row in requests if row[0] == "POST")
    assert not list(prep_bundle.glob(".primr-local-draft-*"))
    assert cli_entry.main(["draft", "--local", str(prep_bundle)]) == 0
    assert len(list(prep_bundle.glob("Local_Draft_*"))) == 2


@pytest.mark.parametrize(
    "metadata",
    [
        {"remote_host": "https://ollama.com"},
        {"remote_model": "model:cloud"},
        {"details": {"parent_model": "model:cloud"}},
    ],
)
def test_cloud_alias_metadata_never_generates(prep_bundle, local_server, metadata):
    local_server["remote_metadata"] = metadata
    assert cli_entry.main(["draft", "--local", str(prep_bundle)]) == 1
    assert all(row[0] == "GET" for row in local_server["requests"])
    assert not list(prep_bundle.glob("Local_Draft_*"))


@pytest.mark.parametrize("model", ["gpt-oss:120b-cloud", "qwen3:cloud"])
def test_cloud_model_name_is_rejected(local_server, model):
    local_server["model"] = model
    with pytest.raises(ValueError, match="locally served"):
        resolve_local_draft_runtime()
    assert all(row[0] == "GET" for row in local_server["requests"])


def test_redirect_does_not_escape_configured_endpoint(prep_bundle, local_server):
    local_server["redirect"] = "http://127.0.0.1:1/escape"
    assert cli_entry.main(["draft", "--local", str(prep_bundle)]) == 1
    assert len(local_server["requests"]) == 1


def test_chat_redirect_does_not_escape_configured_endpoint(prep_bundle, local_server):
    local_server["chat_redirect"] = "http://127.0.0.1:1/escape"
    assert cli_entry.main(["draft", "--local", str(prep_bundle)]) == 1
    assert sum(row[0] == "POST" for row in local_server["requests"]) == 1
    assert not list(prep_bundle.glob("Local_Draft_*"))


def test_busy_runtime_stops_without_retry_and_retains_non_report_checkpoint(
    prep_bundle, local_server, capsys
):
    local_server["chat_status"] = 503
    assert cli_entry.main(["draft", "--local", str(prep_bundle)]) == 75
    assert "capacity is busy" in capsys.readouterr().err
    assert sum(row[0] == "POST" for row in local_server["requests"]) == 1
    checkpoint = next(prep_bundle.glob("Local_Draft_Checkpoint_*"))
    payload = json.loads((checkpoint / "draft_manifest.json").read_text())
    assert payload["status"] == "busy"
    assert payload["incremental_api_cost_usd"] == 0
    assert payload["coverage"]["processed_chunks"] == 0
    assert not list(checkpoint.glob("*.md"))
    assert not list(checkpoint.glob("*.docx"))


@pytest.mark.parametrize(
    "reply", ["not JSON", '{"claims":[]}', '{"claims":[{"source_id":"S999"}]}']
)
def test_malformed_model_output_cannot_publish_empty_report(prep_bundle, local_server, reply):
    local_server["reply"] = reply
    assert cli_entry.main(["draft", "--local", str(prep_bundle)]) == 1
    assert not list(prep_bundle.glob("Local_Draft_*"))
    assert not list(prep_bundle.glob(".primr-local-draft-*"))


def test_changed_or_linked_bundle_is_rejected_before_runtime_probe(prep_bundle, monkeypatch):
    monkeypatch.setattr(
        "primr.ai.local_inference._http_get_json",
        lambda *args: pytest.fail("Unexpected runtime probe"),
    )
    path = prep_bundle / "scraped_content.txt"
    original = path.read_bytes()
    path.write_bytes(original + b"tampering")
    with pytest.raises(ValueError, match="hash or size"):
        local_draft.plan_local_draft(prep_bundle)
    path.write_bytes(original)
    destination = prep_bundle.parent / "outside.txt"
    destination.write_bytes(original)
    path.unlink()
    path.symlink_to(destination)
    with pytest.raises(RuntimeError, match="links"):
        load_prepared_evidence(prep_bundle)


@given(
    source_id=st.sampled_from(["S001", "S999", "", None]),
    quote=st.sampled_from([SOURCE_QUOTES[0], "Invented supporting quotation that is absent."]),
)
@settings(max_examples=20)
def test_claim_acceptance_requires_exact_source_identity_and_excerpt(source_id, quote):
    payload = {
        "claims": [
            {
                "section": "company",
                "claim": "ExampleCo reports supplying scheduling software to independent repair businesses.",
                "source_id": source_id,
                "quote": quote,
            }
        ]
    }
    claims = local_draft.parse_draft_claims(
        json.dumps(payload), local_draft.EvidenceChunk("S001", SOURCE_TEXT)
    )
    assert bool(claims) is (source_id == "S001" and quote == SOURCE_QUOTES[0])


def test_reducer_context_and_batch_count_are_bounded():
    claims = [
        local_draft.DraftClaim(f"C{i:03d}", "company", "有" * 450, "S001", "有" * 320)
        for i in range(100)
    ]
    batches, omissions = local_draft._reduce_batches("company", claims)
    assert len(batches) <= local_draft.MAX_REDUCE_BATCHES
    assert sum(map(len, batches)) + omissions == len(claims)
    for batch in batches:
        assert (
            len((local_draft._reduce_prompt("company", batch) + local_draft.SYSTEM_PROMPT).encode())
            <= local_draft.MAX_PROMPT_BYTES
        )


def test_flat_prep_draft_discovery_is_review_only_and_excludes_quality_evidence(
    prep_bundle, local_server, monkeypatch, tmp_path
):
    assert cli_entry.main(["draft", "--local", str(prep_bundle)]) == 0
    inputs = local_stage_eval.find_latest_website_summary_eval_inputs(
        prep_bundle.parent, companies=["ExampleCo"]
    )
    assert len(inputs) == 1
    assert inputs[0].baseline_kind == "local_draft"
    assert inputs[0].baseline_model == "qwen3:synthetic"
    assert local_stage_eval.find_latest_website_summary_eval_inputs(prep_bundle) == inputs
    monkeypatch.setattr(
        local_stage_eval,
        "summarize_scraped_content_local",
        lambda *args, **kwargs: "Synthetic candidate summary",
    )
    rows = local_stage_eval.run_local_website_summary_stage_eval(
        inputs=inputs, model="qwen3:synthetic", output_root=tmp_path / "eval"
    )
    assert rows[0].promotion_eligible is False
    assert rows[0].baseline_model == rows[0].model
    assert rows[0].baseline_source_citations > 0
    assert (
        local_stage_eval.build_website_summary_stage_quality_evidence(
            eval_id="synthetic", results=[("local", rows)]
        )
        == []
    )
    report = tmp_path / "eval-summary.json"
    local_stage_eval.write_website_summary_stage_eval_summary(
        report, eval_id="synthetic", results=[("local", rows)]
    )
    assert json.loads(report.read_text())["recommended_models"] == []


def test_installed_entry_draft_help_avoids_operational_cloud_stack(
    tmp_path, prep_bundle, local_server
):
    package_root = tmp_path / "site-packages"
    shutil.copytree(Path(__file__).resolve().parents[2] / "src" / "primr", package_root / "primr")
    script = """
import sys
import socket
sys.modules['primr.core.cli'] = None
original_connect = socket.socket.connect
allowed_port = int(sys.argv[2])
def endpoint_only(stream, address):
    assert address[:2] == ('127.0.0.1', allowed_port), f'Unexpected egress: {address}'
    return original_connect(stream, address)
socket.socket.connect = endpoint_only
from primr.cli_entry import main
try:
    main(['draft', '--help'])
except SystemExit as exc:
    assert exc.code == 0
assert main(['draft', '--local', '--dry-run', sys.argv[1]]) == 0
assert 'google.genai' not in sys.modules
assert 'primr.core.research_agent' not in sys.modules
"""
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            script,
            str(prep_bundle),
            local_server["base_url"].split(":")[-1].split("/")[0],
        ],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(package_root)},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert "primr draft" in result.stdout
    assert "Inference calls: 0" in result.stdout


def test_generic_private_runtime_uses_installed_family_and_explicit_selection(monkeypatch):
    calls = []

    def metadata(url, timeout):
        calls.append(url)
        if url.endswith("/models"):
            return {
                "data": [{"id": "llama3:small"}, {"id": "qwen3:small"}, {"id": "nomic-embed-text"}]
            }
        import httpx

        response = httpx.Response(404, request=httpx.Request("GET", url))
        raise httpx.HTTPStatusError("unsupported tags", request=response.request, response=response)

    monkeypatch.setattr("primr.ai.local_inference._http_get_json", metadata)
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://garage-box:8080")
    runtime = resolve_local_draft_runtime()
    assert runtime.base_url == "http://garage-box:8080/v1"
    assert runtime.model == "qwen3:small"
    assert runtime.quantization == "unknown (runtime did not report it)"
    assert runtime.runtime == "OpenAI-compatible (operator configured)"
    assert resolve_local_draft_runtime("llama3:small").model == "llama3:small"
    with pytest.raises(ValueError, match="installed"):
        resolve_local_draft_runtime("absent-model")
    with pytest.raises(ValueError, match="text draft"):
        resolve_local_draft_runtime("nomic-embed-text")
    assert set(calls) == {"http://garage-box:8080/v1/models", "http://garage-box:8080/api/tags"}


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://ollama.com",
        "https://api.openai.com.",
        "https://api.anthropic.com",
        "file:///tmp/runtime",
        "http://user:secret@garage-box:8080",
    ],
)
def test_invalid_or_known_cloud_endpoint_is_rejected_before_network(monkeypatch, endpoint):
    monkeypatch.setattr(
        "primr.ai.local_inference._http_get_json", lambda *args: pytest.fail("Unexpected probe")
    )
    with pytest.raises(ValueError):
        resolve_local_draft_runtime(base_url=endpoint)


@pytest.mark.parametrize("payload", [{}, {"models": None}, {"models": [None]}])
def test_malformed_runtime_metadata_cannot_generate(prep_bundle, local_server, payload):
    local_server["tags_payload"] = payload
    # A list containing no usable installed tag is malformed for Ollama draft use.
    assert cli_entry.main(["draft", "--local", str(prep_bundle)]) == 1
    assert all(row[0] == "GET" for row in local_server["requests"])


def test_unknown_reducer_claim_ids_cannot_become_report(prep_bundle, local_server):
    local_server["reducer_reply"] = {"claim_ids": ["C999", {"claim_id": "C001"}]}
    assert cli_entry.main(["draft", "--local", str(prep_bundle)]) == 1
    assert not list(prep_bundle.glob("Local_Draft_*"))


def test_foreign_citation_is_dropped_despite_matching_quote():
    row = {
        "section": "company",
        "claim": "ExampleCo supplies scheduling software to independent repair businesses [S999].",
        "source_id": "S001",
        "quote": SOURCE_QUOTES[0],
    }
    assert (
        local_draft.parse_draft_claims(
            json.dumps({"claims": [row]}), local_draft.EvidenceChunk("S001", SOURCE_TEXT)
        )
        == []
    )
    assert (
        local_draft.parse_draft_claims(
            "[" * 2_000 + "]" * 2_000, local_draft.EvidenceChunk("S001", SOURCE_TEXT)
        )
        == []
    )


def test_unicode_chunking_preserves_source_bytes_within_cap():
    from primr.core.evidence_bundle_input import EvidenceSource

    text = "a有𠮷" * 2_000
    chunks = local_draft._source_chunks(EvidenceSource("S001", "https://example.co", text))
    assert "".join(chunk.text for chunk in chunks) == text
    assert all(len(chunk.text.encode()) <= local_draft.CHUNK_BYTES for chunk in chunks)


def test_render_failure_and_interrupt_remove_incomplete_publication(
    prep_bundle, local_server, monkeypatch
):
    monkeypatch.setattr(
        "primr.output.markdown_converter.markdown_to_docx",
        lambda *args: (_ for _ in ()).throw(OSError("synthetic render failure")),
    )
    assert cli_entry.main(["draft", "--local", str(prep_bundle)]) == 1
    assert not list(prep_bundle.glob("Local_Draft_*"))
    assert not list(prep_bundle.glob(".primr-local-draft-*"))
    monkeypatch.setattr(
        local_draft,
        "chat_completion",
        lambda *args, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    assert cli_entry.main(["draft", "--local", str(prep_bundle)]) == 130
    assert not list(prep_bundle.glob("Local_Draft_*"))
    assert not list(prep_bundle.glob(".primr-local-draft-*"))


def test_local_semantic_rows_and_mixed_summary_cannot_promote_local_comparisons(
    prep_bundle, local_server, monkeypatch, tmp_path
):
    assert cli_entry.main(["draft", "--local", str(prep_bundle)]) == 0
    inputs = local_stage_eval.find_latest_website_summary_eval_inputs(prep_bundle)
    monkeypatch.setattr(
        local_stage_eval,
        "summarize_scraped_content_local",
        lambda *args, **kwargs: "Synthetic candidate summary",
    )
    rows = local_stage_eval.run_local_website_summary_stage_eval(
        inputs=inputs, model="qwen3:synthetic", output_root=tmp_path / "eval"
    )
    Path(rows[0].local_summary_path).write_text("Synthetic candidate summary", encoding="utf-8")
    judge = ChatCompletionResult(
        json.dumps({"semantic_score": 100, "rationale": "Synthetic self comparison"}), 20, 10
    )
    monkeypatch.setattr(
        "primr.ai.openai_compatible_client.chat_completion", lambda *args, **kwargs: judge
    )
    semantic = local_stage_eval.run_local_website_summary_semantic_eval(
        rows=rows, judge_model="qwen3:synthetic"
    )
    assert semantic[0].baseline_kind == "local_draft"
    assert semantic[0].promotion_eligible is False
    inconsistent = replace(rows[0], promotion_eligible=True)
    assert (
        local_stage_eval.build_website_summary_stage_quality_evidence(
            eval_id="synthetic", results=[("local", [inconsistent])]
        )
        == []
    )
    assert (
        local_stage_eval.build_website_summary_semantic_quality_evidence(
            eval_id="synthetic",
            results=[("local", [replace(semantic[0], promotion_eligible=True)])],
        )
        == []
    )
    assert (
        local_stage_eval.build_website_summary_semantic_quality_evidence(
            eval_id="synthetic", results=[("local", semantic)]
        )
        == []
    )
    report = tmp_path / "semantic.json"
    local_stage_eval.write_website_summary_semantic_eval_report(
        report,
        eval_id="synthetic",
        judge_model="qwen3:synthetic",
        results=[("local", semantic)],
        base_url=None,
        credential_env_var="",
    )
    assert json.loads(report.read_text())["decision_policy"] == "local_draft_review_only"
    provider_a = replace(
        rows[0],
        model="provider-a",
        baseline_kind="provider_run",
        baseline_model=None,
        promotion_eligible=True,
        completeness_score=80,
    )
    provider_b = replace(provider_a, model="provider-b", completeness_score=70)
    local_a = replace(rows[0], model="provider-a", completeness_score=0)
    local_b = replace(rows[0], model="provider-b", completeness_score=100)
    summary = tmp_path / "mixed.json"
    local_stage_eval.write_website_summary_stage_eval_summary(
        summary,
        eval_id="synthetic",
        results=[("provider-a", [provider_a, local_a]), ("provider-b", [provider_b, local_b])],
    )
    assert json.loads(summary.read_text())["recommended_models"] == ["provider-a", "provider-b"]


@pytest.mark.parametrize("key", [None, "synthetic-garage-token"])
def test_metadata_uses_only_optional_local_key_for_models_and_tags(monkeypatch, key):
    if key is None:
        monkeypatch.delenv("LOCAL_LLM_API_KEY", raising=False)
    else:
        monkeypatch.setenv("LOCAL_LLM_API_KEY", key)
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-reused")
    monkeypatch.setenv("GEMINI_API_KEY", "must-not-be-reused")
    seen = []

    def handle(request):
        seen.append((str(request.url), request.headers.get("Authorization")))
        assert request.url.host == "garage.invalid"
        payload = (
            {"data": [{"id": "synthetic"}]}
            if request.url.path == "/v1/models"
            else {"models": [{"name": "synthetic", "details": {"quantization_level": "Q4"}}]}
        )
        return httpx.Response(200, json=payload)

    real_client = httpx.Client

    def client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        return real_client(transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr("primr.ai.local_inference.httpx.Client", client)
    runtime = resolve_local_draft_runtime(base_url="https://garage.invalid/v1")
    assert runtime.model == "synthetic"
    expected = f"Bearer {key}" if key else None
    assert seen == [
        ("https://garage.invalid/v1/models", expected),
        ("https://garage.invalid/api/tags", expected),
    ]


@pytest.mark.parametrize("failure_path", ["/v1/models", "/api/tags"])
@pytest.mark.parametrize("status", [401, 302])
def test_metadata_auth_failure_and_redirect_never_forward_credentials(
    monkeypatch, failure_path, status
):
    key = "synthetic-private-key-never-log"
    monkeypatch.setenv("LOCAL_LLM_API_KEY", key)
    seen = []

    def handle(request):
        seen.append((request.url.host, request.url.path))
        assert request.url.host == "garage.invalid"
        assert request.headers["Authorization"] == f"Bearer {key}"
        if request.url.path == failure_path:
            return httpx.Response(
                status,
                headers={"Location": "https://external.invalid/credential-sink"},
                json={"error": {"message": key}},
            )
        return httpx.Response(200, json={"data": [{"id": "synthetic"}]})

    real_client = httpx.Client
    monkeypatch.setattr(
        "primr.ai.local_inference.httpx.Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    with pytest.raises(RuntimeError) as error:
        resolve_local_draft_runtime(base_url="https://garage.invalid/v1")
    assert key not in str(error.value)
    expected = [("garage.invalid", "/v1/models")]
    if failure_path == "/api/tags":
        expected.append(("garage.invalid", "/api/tags"))
    assert seen == expected


def test_real_transport_authenticates_metadata_and_chat_without_recording_key(
    prep_bundle, local_server, monkeypatch
):
    key = "synthetic-private-runtime-token"
    monkeypatch.setenv("LOCAL_LLM_API_KEY", key)
    assert cli_entry.main(["draft", "--local", str(prep_bundle)]) == 0
    assert local_server["authorizations"] == [f"Bearer {key}"] * 5
    output = next(prep_bundle.glob("Local_Draft_*"))
    for artifact in output.iterdir():
        if artifact.suffix in {".json", ".txt", ".md"}:
            assert key not in artifact.read_text()
