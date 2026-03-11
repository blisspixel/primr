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
        start_time = time.time()

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
                duration = time.time() - start_time
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
                duration = time.time() - start_time
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

            duration = time.time() - start_time
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
            duration = time.time() - start_time
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

    async def _classify_results(
        self,
        claims: list[VerifiableClaim],
        search_results: dict[str, list[dict[str, str]]],
    ) -> list[ClaimVerification]:
        """Classify claims based on search results using LLM."""
        from primr.ai.llm import llm

        prompt_template = self._load_prompt("classification")
        all_verifications: list[ClaimVerification] = []

        # Process in batches
        for i in range(0, len(claims), self.CLASSIFICATION_BATCH_SIZE):
            batch = claims[i : i + self.CLASSIFICATION_BATCH_SIZE]
            batch_data = []
            for claim in batch:
                hits = search_results.get(claim.claim_text, [])
                hit_summaries = [
                    {"title": h.get("title", ""), "url": h.get("url", "")} for h in hits[:5]
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
                        all_verifications.append(
                            ClaimVerification(
                                claim=claim,
                                status=status,
                                supporting_sources=cls.get("supporting_sources", []),
                                explanation=cls.get("explanation", ""),
                                search_query=next(
                                    (q for c, q in self._build_search_queries([claim])),
                                    "",
                                ),
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
