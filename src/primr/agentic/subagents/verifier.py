"""
Verifier Subagent for claim fact-checking.

This subagent handles the verification phase of the research pipeline,
extracting key claims from reports and searching for corroborating evidence.

Responsibilities:
    - Extract verifiable claims from research reports
    - Search DDG for corroborating/contradicting evidence
    - Classify claims as verified/unverified/contradicted
    - Compute an auditable trust score

Integration:
    Runs after QA as an optional post-processing step.
    Non-blocking: verification failure does not affect report output.

Example:
    context = SubagentContext(
        company_name="Acme Corp",
        company_url="https://acme.com",
        working_dir=Path("./output/acme"),
        parent_results={"report_path": Path("./output/acme/report.txt")},
    )
    verifier = VerifierSubagent(context)
    result = await verifier.execute()

    if result.is_success:
        print(f"Trust Score: {result.data.trust_percentage}%")
"""

from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from primr.agentic.errors import SubagentError
from primr.agentic.subagents.base import (
    Subagent,
    SubagentContext,
    SubagentResult,
    SubagentStatus,
)

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class VerifiableClaim:
    """A claim extracted from a research report."""

    claim_text: str
    section: str
    importance: int  # 1-5

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "claim_text": self.claim_text,
            "section": self.section,
            "importance": self.importance,
        }


@dataclass
class ClaimVerification:
    """Result of verifying a single claim."""

    claim: VerifiableClaim
    status: str  # "verified", "unverified", "contradicted"
    supporting_sources: list[str] = field(default_factory=list)
    explanation: str = ""
    search_query: str = ""
    # Evidence the classifier actually saw: url -> {"provenance", "fetched"}.
    # provenance is "first_party" (company's own domain/subdomains) or
    # "third_party"; fetched marks whether page content was retrieved (vs
    # title-only fallback when the fetch failed).
    evidence_sources: list[dict[str, Any]] = field(default_factory=list)
    # True when a "verified" verdict was downgraded because every supporting
    # source was the company's own domain — self-corroboration is not
    # independent verification.
    first_party_downgrade: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "claim_text": self.claim.claim_text,
            "section": self.claim.section,
            "importance": self.claim.importance,
            "status": self.status,
            "supporting_sources": self.supporting_sources,
            "explanation": self.explanation,
            "search_query": self.search_query,
            "evidence_sources": self.evidence_sources,
            "first_party_downgrade": self.first_party_downgrade,
        }


@dataclass
class VerificationResult:
    """Aggregate result from verification pipeline."""

    trust_score: float  # 0.0 - 1.0
    verified_count: int = 0
    unverified_count: int = 0
    contradicted_count: int = 0
    claim_results: list[ClaimVerification] = field(default_factory=list)
    duration_seconds: float = 0.0

    @property
    def total_claims(self) -> int:
        """Total number of claims checked."""
        return self.verified_count + self.unverified_count + self.contradicted_count

    @property
    def trust_percentage(self) -> int:
        """Trust score as integer percentage."""
        return int(self.trust_score * 100)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "trust_score": round(self.trust_score, 3),
            "trust_percentage": self.trust_percentage,
            "verified_count": self.verified_count,
            "unverified_count": self.unverified_count,
            "contradicted_count": self.contradicted_count,
            "total_claims": self.total_claims,
            "duration_seconds": round(self.duration_seconds, 1),
            "claim_results": [cr.to_dict() for cr in self.claim_results],
        }


# =============================================================================
# VERIFIER SUBAGENT
# =============================================================================


class VerifierSubagent(Subagent[VerificationResult]):
    """
    Subagent for report claim verification.

    Extracts key claims from the report, searches DDG for corroborating
    evidence, and produces a trust score.

    Pipeline:
        1. Read report text
        2. Extract claims via LLM (Flash model)
        3. Build search queries (no LLM)
        4. Search DDG in parallel
        5. Classify results via LLM (Flash model)
        6. Compute trust score

    Cost: ~$0.01 (2 Flash LLM calls + free DDG searches)
    Time: 3-5 minutes
    """

    DEFAULT_MAX_CLAIMS = 20
    SEARCH_WORKERS = 3
    CLASSIFICATION_BATCH_SIZE = 5
    # Evidence fetching: pages fetched per claim, and snippet size handed to
    # the classifier. Plain HTTP GET (SSRF-guarded), zero token cost.
    MAX_EVIDENCE_PER_CLAIM = 3
    EVIDENCE_SNIPPET_CHARS = 1_500

    def __init__(
        self,
        context: SubagentContext,
        max_claims: int = DEFAULT_MAX_CLAIMS,
    ):
        super().__init__(context, name="VerifierSubagent")
        self._max_claims = max_claims

    @property
    def max_claims(self) -> int:
        """Get maximum number of claims to verify."""
        return self._max_claims

    async def execute(self) -> SubagentResult[VerificationResult]:
        """Execute claim verification pipeline."""
        self._status = SubagentStatus.RUNNING
        start_time = time.perf_counter()

        logger.info(f"VerifierSubagent starting for {self.company_name}")

        try:
            # Step 1: Get report text
            report_path = self._context.get_parent_result("report_path")
            if report_path is None:
                raise SubagentError(
                    message="No report_path in parent results",
                    subagent="verifier",
                )

            if isinstance(report_path, str):
                report_path = Path(report_path)

            if not report_path.exists():
                raise SubagentError(
                    message=f"Report file not found: {report_path}",
                    subagent="verifier",
                )

            report_text = report_path.read_text(encoding="utf-8")
            if not report_text.strip():
                # Empty report → no claims to verify
                duration = time.perf_counter() - start_time
                self._status = SubagentStatus.COMPLETED
                return SubagentResult(
                    status=self._status,
                    data=VerificationResult(
                        trust_score=0.0,
                        duration_seconds=duration,
                    ),
                    metrics={"duration_seconds": duration, "claims_extracted": 0},
                )

            # Step 2: Extract claims
            claims = await self._extract_claims(report_text)
            if not claims:
                duration = time.perf_counter() - start_time
                self._status = SubagentStatus.COMPLETED
                return SubagentResult(
                    status=self._status,
                    data=VerificationResult(
                        trust_score=0.0,
                        duration_seconds=duration,
                    ),
                    metrics={"duration_seconds": duration, "claims_extracted": 0},
                )

            # Step 3: Build search queries
            claim_queries = self._build_search_queries(claims)

            # Step 4: Search DDG in parallel
            search_results = self._search_claims(claim_queries)

            # Step 5: Classify results
            claim_verifications = await self._classify_results(claims, search_results)

            # Step 6: Compute trust score
            verified = sum(1 for cv in claim_verifications if cv.status == "verified")
            unverified = sum(1 for cv in claim_verifications if cv.status == "unverified")
            contradicted = sum(1 for cv in claim_verifications if cv.status == "contradicted")
            total = len(claim_verifications)

            trust_score = verified / total if total > 0 else 0.0

            duration = time.perf_counter() - start_time
            self._status = SubagentStatus.COMPLETED

            verification_result = VerificationResult(
                trust_score=trust_score,
                verified_count=verified,
                unverified_count=unverified,
                contradicted_count=contradicted,
                claim_results=claim_verifications,
                duration_seconds=duration,
            )

            # Save verification.json alongside report
            self._save_result(report_path, verification_result)

            logger.info(
                f"VerifierSubagent completed for {self.company_name}: "
                f"trust={verification_result.trust_percentage}%, "
                f"verified={verified}/{total}"
            )

            return SubagentResult(
                status=self._status,
                data=verification_result,
                metrics={
                    "duration_seconds": duration,
                    "trust_score": trust_score,
                    "claims_extracted": total,
                    "verified": verified,
                    "contradicted": contradicted,
                },
            )

        except SubagentError:
            raise
        except Exception as e:
            duration = time.perf_counter() - start_time
            self._status = SubagentStatus.FAILED

            logger.error(f"VerifierSubagent failed for {self.company_name}: {e}")

            return SubagentResult(
                status=self._status,
                error=str(e),
                metrics={"duration_seconds": duration},
            )

    async def _extract_claims(self, report_text: str) -> list[VerifiableClaim]:
        """Extract verifiable claims from report text using LLM."""
        from primr.ai.llm import llm

        # Load prompt template
        prompt_template = self._load_prompt("claim_extraction")
        # Truncate report to ~30k chars to stay within Flash context
        truncated = report_text[:30_000]
        prompt = prompt_template.format(
            report_text=truncated,
            max_claims=self._max_claims,
        )

        try:
            response = llm(prompt, model_type="fast", temperature=0.2)
            claims_data = self._parse_json_response(response)

            if not isinstance(claims_data, list):
                logger.warning("Claim extraction returned non-list response")
                return []

            claims = []
            for item in claims_data[: self._max_claims]:
                if not isinstance(item, dict):
                    continue
                claims.append(
                    VerifiableClaim(
                        claim_text=str(item.get("claim_text", "")),
                        section=str(item.get("section", "unknown")),
                        importance=min(5, max(1, int(item.get("importance", 3)))),
                    )
                )

            # Sort by importance (highest first)
            claims.sort(key=lambda c: c.importance, reverse=True)
            return claims[: self._max_claims]

        except Exception as e:
            logger.warning(f"Claim extraction failed: {e}")
            return []

    def _build_search_queries(
        self, claims: list[VerifiableClaim]
    ) -> list[tuple[VerifiableClaim, str]]:
        """Build DDG search queries from claims. No LLM needed."""
        company = self._context.company_name
        queries = []
        for claim in claims:
            # Extract key terms: first ~60 chars of claim + company name
            key_terms = claim.claim_text[:60].rstrip(".,;:")
            query = f"{company} {key_terms}"
            queries.append((claim, query))
        return queries

    def _search_claims(
        self, claim_queries: list[tuple[VerifiableClaim, str]]
    ) -> dict[str, list[dict[str, str]]]:
        """Search DDG for each claim in parallel. Individual failures return empty results."""
        from primr.data.search_utils import search_web

        results: dict[str, list[dict[str, str]]] = {}

        def _do_search(claim_text: str, query: str) -> tuple[str, list[dict[str, str]]]:
            try:
                hits = search_web(
                    query,
                    company_name=self._context.company_name,
                    website=self._context.company_url,
                    num_results=3,
                )
                return claim_text, hits if isinstance(hits, list) else []
            except Exception as e:
                logger.warning(f"Search failed for '{query[:50]}...': {e}")
                return claim_text, []

        with ThreadPoolExecutor(max_workers=self.SEARCH_WORKERS) as executor:
            futures = {
                executor.submit(_do_search, claim.claim_text, query): claim.claim_text
                for claim, query in claim_queries
            }
            for future in as_completed(futures):
                try:
                    claim_text, hits = future.result(timeout=30)
                    results[claim_text] = hits
                except Exception as e:
                    claim_text = futures[future]
                    logger.debug(f"Search future failed for claim: {e}")
                    results[claim_text] = []

        return results

    def _source_provenance(self, url: str) -> str:
        """Tag a source URL as first_party (company's own site) or third_party."""
        from primr.data.scraping.net import is_in_scope

        company_url = self._context.company_url or ""
        if not company_url or not url:
            return "third_party"
        try:
            return "first_party" if is_in_scope(url, company_url) else "third_party"
        except Exception:
            return "third_party"

    def _fetch_evidence(
        self, search_results: dict[str, list[dict[str, str]]]
    ) -> dict[str, list[dict[str, Any]]]:
        """Fetch page content for each claim's top hits (evidence, not titles).

        For every hit (capped at MAX_EVIDENCE_PER_CLAIM per claim) this does a
        plain SSRF-guarded HTTP GET and reader-mode extraction, producing a
        snippet the classifier can actually judge against. Fetch failures fall
        back to title-only for that hit — never fail the verification pass.
        URLs are fetched once even when shared across claims.
        """
        from primr.data.fallback_sources import _http_get
        from primr.data.scraping.content import extract_main_content

        # Collect unique URLs across claims (dedupe fetches)
        urls: list[str] = []
        seen: set[str] = set()
        for hits in search_results.values():
            for hit in hits[: self.MAX_EVIDENCE_PER_CLAIM]:
                url = hit.get("url", "")
                if url and url not in seen:
                    seen.add(url)
                    urls.append(url)

        snippets: dict[str, str] = {}

        def _fetch_one(url: str) -> tuple[str, str]:
            try:
                status, body, _final = _http_get(url, timeout=12.0)
                if status and 200 <= status < 300 and body:
                    text = extract_main_content(body)
                    return url, (text or "")[: self.EVIDENCE_SNIPPET_CHARS]
            except Exception as e:
                logger.debug("Evidence fetch failed for %s: %s", url, e)
            return url, ""

        with ThreadPoolExecutor(max_workers=self.SEARCH_WORKERS) as executor:
            futures = [executor.submit(_fetch_one, url) for url in urls]
            for future in as_completed(futures):
                try:
                    url, snippet = future.result(timeout=30)
                    snippets[url] = snippet
                except Exception:
                    pass

        # Re-shape per claim with provenance + snippet
        evidence: dict[str, list[dict[str, Any]]] = {}
        for claim_text, hits in search_results.items():
            enriched: list[dict[str, Any]] = []
            for hit in hits[: self.MAX_EVIDENCE_PER_CLAIM]:
                url = hit.get("url", "")
                snippet = snippets.get(url, "")
                enriched.append(
                    {
                        "title": hit.get("title", ""),
                        "url": url,
                        "provenance": self._source_provenance(url),
                        "fetched": bool(snippet),
                        "snippet": snippet,
                    }
                )
            evidence[claim_text] = enriched
        return evidence

    async def _classify_results(
        self,
        claims: list[VerifiableClaim],
        search_results: dict[str, list[dict[str, str]]],
    ) -> list[ClaimVerification]:
        """Classify claims against fetched page evidence using LLM.

        Evidence-based: the classifier sees fetched page snippets with
        first-party/third-party provenance, not just search-result titles.
        A deterministic post-guard downgrades "verified" verdicts whose only
        support is the company's own domain — self-corroboration is not
        independent verification.
        """
        from primr.ai.llm import llm

        prompt_template = self._load_prompt("classification")
        all_verifications: list[ClaimVerification] = []
        evidence_by_claim = self._fetch_evidence(search_results)

        # Process in batches
        for i in range(0, len(claims), self.CLASSIFICATION_BATCH_SIZE):
            batch = claims[i : i + self.CLASSIFICATION_BATCH_SIZE]
            batch_data = []
            for claim in batch:
                hit_summaries = [
                    {
                        "title": e["title"],
                        "url": e["url"],
                        "provenance": e["provenance"],
                        "evidence": e["snippet"] or "(content not retrievable — title only)",
                    }
                    for e in evidence_by_claim.get(claim.claim_text, [])
                ]
                batch_data.append(
                    {
                        "claim_text": claim.claim_text,
                        "search_results": hit_summaries,
                    }
                )

            prompt = prompt_template.format(
                claims_with_results=json.dumps(batch_data, indent=2),
            )

            try:
                response = llm(prompt, model_type="fast", temperature=0.2)
                classifications = self._parse_json_response(response)

                if not isinstance(classifications, list):
                    classifications = []

                for j, claim in enumerate(batch):
                    if j < len(classifications) and isinstance(classifications[j], dict):
                        cls = classifications[j]
                        status = cls.get("status", "unverified")
                        if status not in ("verified", "unverified", "contradicted"):
                            status = "unverified"
                        supporting = cls.get("supporting_sources", [])
                        if not isinstance(supporting, list):
                            supporting = []
                        explanation = cls.get("explanation", "")

                        # Deterministic guard: a "verified" verdict whose
                        # every supporting source is the company's own domain
                        # is self-corroboration, not verification. Downgrade
                        # regardless of what the LLM decided.
                        first_party_downgrade = False
                        if status == "verified" and supporting:
                            if all(
                                self._source_provenance(str(u)) == "first_party" for u in supporting
                            ):
                                status = "unverified"
                                first_party_downgrade = True
                                explanation = (
                                    "Only first-party (company-domain) sources support "
                                    "this claim — downgraded: self-corroboration is not "
                                    "independent verification. " + explanation
                                ).strip()

                        claim_evidence = [
                            {k: e[k] for k in ("url", "provenance", "fetched")}
                            for e in evidence_by_claim.get(claim.claim_text, [])
                        ]
                        all_verifications.append(
                            ClaimVerification(
                                claim=claim,
                                status=status,
                                supporting_sources=supporting,
                                explanation=explanation,
                                search_query=next(
                                    (q for _c, q in self._build_search_queries([claim])),
                                    "",
                                ),
                                evidence_sources=claim_evidence,
                                first_party_downgrade=first_party_downgrade,
                            )
                        )
                    else:
                        all_verifications.append(
                            ClaimVerification(
                                claim=claim,
                                status="unverified",
                                explanation="Classification failed for this claim",
                            )
                        )

            except Exception as e:
                logger.warning(f"Classification batch failed: {e}")
                for claim in batch:
                    all_verifications.append(
                        ClaimVerification(
                            claim=claim,
                            status="unverified",
                            explanation=f"Classification error: {e}",
                        )
                    )

        return all_verifications

    def _load_prompt(self, template_name: str) -> str:
        """Load a prompt template from verification.yaml."""
        import yaml  # type: ignore[import-untyped]

        prompt_path = Path(__file__).parent.parent.parent / "prompts" / "verification.yaml"
        try:
            with open(prompt_path, encoding="utf-8") as f:
                templates = yaml.safe_load(f)
            return templates.get(template_name, "")
        except Exception as e:
            logger.warning(f"Failed to load prompt template '{template_name}': {e}")
            return ""

    def _parse_json_response(self, response: str) -> Any:
        """Parse JSON from LLM response, handling markdown fencing."""
        text = response.strip()
        # Strip markdown code fences
        match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
        return json.loads(text)

    def _save_result(self, report_path: Path, result: VerificationResult) -> None:
        """Save verification result as JSON next to the report."""
        try:
            output_path = report_path.parent / "verification.json"
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(result.to_dict(), f, indent=2)
            logger.info(f"Verification result saved to {output_path}")
        except Exception as e:
            logger.warning(f"Failed to save verification result: {e}")

    def get_required_tools(self) -> list[str]:
        """Return list of MCP tools this subagent needs."""
        return []
