"""
Property-based tests for Idempotent Job Submission.

This module contains property tests that verify the idempotency guarantees
of the control plane job submission system.

**Feature: serverless-cloud-deployment**
**Property 2: Idempotent Submission**
**Validates: Requirements 3.5, 3.6, 3.7**
"""

from __future__ import annotations

import string
from typing import Any

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from deploy.control_plane.cost_governor import estimate_cost
from deploy.control_plane.job_store import (
    ConditionalCheckFailedError,
    InMemoryJobStore,
    JobRecord,
    JobStatus,
    JobTiming,
    canonicalize_inputs,
    format_timestamp,
    get_expected_artifacts,
    hash_api_key,
    hash_inputs,
    hash_job_id,
    utc_now,
)

# =============================================================================
# STRATEGIES FOR GENERATING TEST DATA
# =============================================================================

# Strategy for company names (non-empty strings)
company_name_strategy = st.text(
    alphabet=string.ascii_letters + string.digits + " -_.",
    min_size=1,
    max_size=100,
).filter(lambda x: x.strip())

# Strategy for URLs
url_strategy = st.from_regex(
    r"https?://[a-z][a-z0-9-]{0,20}\.(com|org|net|io|example)",
    fullmatch=True,
)

# Strategy for idempotency keys
idempotency_key_strategy = st.text(
    alphabet=string.ascii_letters + string.digits + "-_",
    min_size=1,
    max_size=64,
)

# Strategy for API keys
api_key_strategy = st.text(
    alphabet=string.ascii_letters + string.digits,
    min_size=8,
    max_size=64,
)

# Strategy for deployment names
deployment_strategy = st.sampled_from(["dev", "staging", "prod", "test", "local"])

# Strategy for modes
mode_strategy = st.sampled_from(["scrape", "deep", "full"])

# Strategy for options (simple key-value pairs)
options_strategy = st.dictionaries(
    keys=st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=10),
    values=st.one_of(st.booleans(), st.integers(-100, 100), st.text(max_size=20)),
    max_size=5,
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def create_job_record(
    job_store: InMemoryJobStore,
    deployment: str,
    idempotency_key: str,
    api_key: str,
    company_name: str,
    company_url: str,
    mode: str,
    options: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """
    Create a job record and return (job_id, canonical_hash).

    Simulates the submit_job logic from the API.
    """
    # Canonicalize inputs
    canonical = canonicalize_inputs(
        company_name=company_name,
        company_url=company_url,
        mode=mode,
        options=options,
    )
    canonical_hash = hash_inputs(canonical)

    # Derive job_id
    job_id = hash_job_id(deployment, idempotency_key, api_key)
    api_key_hash = hash_api_key(api_key)

    # Create job record
    job = JobRecord(
        job_id=job_id,
        deployment=deployment,
        idempotency_key=idempotency_key,
        api_key_hash=api_key_hash,
        canonical_hash=canonical_hash,
        status=JobStatus.QUEUED,
        inputs=canonical,
        expected_artifacts=get_expected_artifacts(mode),
        estimate=estimate_cost(mode),
        timing=JobTiming(submitted_at=format_timestamp(utc_now())),
    )

    job_store.put_if_not_exists(job)
    return job_id, canonical_hash


def submit_job_idempotent(
    job_store: InMemoryJobStore,
    deployment: str,
    idempotency_key: str,
    api_key: str,
    company_name: str,
    company_url: str,
    mode: str,
    options: dict[str, Any] | None = None,
) -> tuple[str, bool, bool]:
    """
    Submit a job with idempotency handling.

    Returns (job_id, is_existing, is_conflict).

    - is_existing: True if job already existed with same inputs
    - is_conflict: True if idempotency key was reused with different inputs
    """
    # Canonicalize inputs
    canonical = canonicalize_inputs(
        company_name=company_name,
        company_url=company_url,
        mode=mode,
        options=options,
    )
    canonical_hash = hash_inputs(canonical)

    # Derive job_id
    job_id = hash_job_id(deployment, idempotency_key, api_key)
    api_key_hash = hash_api_key(api_key)

    # Check for existing job
    existing = job_store.get(job_id)
    if existing:
        # Check for input mismatch
        if existing.canonical_hash != canonical_hash:
            return job_id, False, True  # Conflict!
        return job_id, True, False  # Existing job, same inputs

    # Create new job
    job = JobRecord(
        job_id=job_id,
        deployment=deployment,
        idempotency_key=idempotency_key,
        api_key_hash=api_key_hash,
        canonical_hash=canonical_hash,
        status=JobStatus.QUEUED,
        inputs=canonical,
        expected_artifacts=get_expected_artifacts(mode),
        estimate=estimate_cost(mode),
        timing=JobTiming(submitted_at=format_timestamp(utc_now())),
    )

    try:
        job_store.put_if_not_exists(job)
        return job_id, False, False  # New job created
    except ConditionalCheckFailedError:
        # Race condition - another request created the job
        existing = job_store.get(job_id)
        if existing and existing.canonical_hash != canonical_hash:
            return job_id, False, True  # Conflict!
        return job_id, True, False  # Existing job


# =============================================================================
# PROPERTY 2.1: SAME INPUTS RETURNS SAME JOB_ID
# =============================================================================


class TestSameInputsReturnsSameJobId:
    """
    **Property 2.1: Same Inputs Returns Same Job ID**

    For any valid job submission with the same (deployment, idempotency_key, api_key)
    and same inputs, the system SHALL return the same job_id.

    **Validates: Requirements 3.5**
    """

    @given(
        deployment=deployment_strategy,
        idempotency_key=idempotency_key_strategy,
        api_key=api_key_strategy,
        company_name=company_name_strategy,
        company_url=url_strategy,
        mode=mode_strategy,
        options=options_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_duplicate_submission_returns_same_job_id(
        self,
        deployment: str,
        idempotency_key: str,
        api_key: str,
        company_name: str,
        company_url: str,
        mode: str,
        options: dict[str, Any],
    ) -> None:
        """
        Same (deployment, idempotency_key, api_key) + same inputs returns same job_id.

        Feature: serverless-cloud-deployment, Property 2: Idempotent Submission
        **Validates: Requirements 3.5**
        """
        job_store = InMemoryJobStore()

        # First submission
        job_id_1, is_existing_1, is_conflict_1 = submit_job_idempotent(
            job_store=job_store,
            deployment=deployment,
            idempotency_key=idempotency_key,
            api_key=api_key,
            company_name=company_name,
            company_url=company_url,
            mode=mode,
            options=options,
        )

        # Second submission with identical inputs
        job_id_2, is_existing_2, is_conflict_2 = submit_job_idempotent(
            job_store=job_store,
            deployment=deployment,
            idempotency_key=idempotency_key,
            api_key=api_key,
            company_name=company_name,
            company_url=company_url,
            mode=mode,
            options=options,
        )

        # Assertions
        assert job_id_1 == job_id_2, "Same inputs should return same job_id"
        assert not is_conflict_1, "First submission should not be a conflict"
        assert not is_conflict_2, "Second submission should not be a conflict"
        assert is_existing_2, "Second submission should return existing job"

    @given(
        deployment=deployment_strategy,
        idempotency_key=idempotency_key_strategy,
        api_key=api_key_strategy,
        company_name=company_name_strategy,
        company_url=url_strategy,
        mode=mode_strategy,
        num_submissions=st.integers(min_value=2, max_value=10),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_multiple_submissions_all_return_same_job_id(
        self,
        deployment: str,
        idempotency_key: str,
        api_key: str,
        company_name: str,
        company_url: str,
        mode: str,
        num_submissions: int,
    ) -> None:
        """
        Multiple submissions with same inputs all return same job_id.

        Feature: serverless-cloud-deployment, Property 2: Idempotent Submission
        **Validates: Requirements 3.5**
        """
        job_store = InMemoryJobStore()
        job_ids = []

        for _ in range(num_submissions):
            job_id, _, is_conflict = submit_job_idempotent(
                job_store=job_store,
                deployment=deployment,
                idempotency_key=idempotency_key,
                api_key=api_key,
                company_name=company_name,
                company_url=company_url,
                mode=mode,
            )
            assert not is_conflict
            job_ids.append(job_id)

        # All job_ids should be identical
        assert len(set(job_ids)) == 1, "All submissions should return same job_id"


# =============================================================================
# PROPERTY 2.2: DIFFERENT INPUTS RETURNS 409
# =============================================================================


class TestDifferentInputsReturns409:
    """
    **Property 2.2: Different Inputs Returns 409**

    For any job submission where the idempotency_key matches an existing job
    but the inputs differ, the system SHALL return a 409 Conflict.

    **Validates: Requirements 3.6**
    """

    @given(
        deployment=deployment_strategy,
        idempotency_key=idempotency_key_strategy,
        api_key=api_key_strategy,
        company_name_1=company_name_strategy,
        company_name_2=company_name_strategy,
        company_url=url_strategy,
        mode=mode_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_different_company_name_returns_conflict(
        self,
        deployment: str,
        idempotency_key: str,
        api_key: str,
        company_name_1: str,
        company_name_2: str,
        company_url: str,
        mode: str,
    ) -> None:
        """
        Same idempotency_key + different company_name returns 409.

        Feature: serverless-cloud-deployment, Property 2: Idempotent Submission
        **Validates: Requirements 3.6**
        """
        # Ensure company names are actually different after canonicalization
        assume(company_name_1.strip() != company_name_2.strip())

        job_store = InMemoryJobStore()

        # First submission
        job_id_1, _, is_conflict_1 = submit_job_idempotent(
            job_store=job_store,
            deployment=deployment,
            idempotency_key=idempotency_key,
            api_key=api_key,
            company_name=company_name_1,
            company_url=company_url,
            mode=mode,
        )
        assert not is_conflict_1

        # Second submission with different company_name
        job_id_2, _, is_conflict_2 = submit_job_idempotent(
            job_store=job_store,
            deployment=deployment,
            idempotency_key=idempotency_key,
            api_key=api_key,
            company_name=company_name_2,  # Different!
            company_url=company_url,
            mode=mode,
        )

        assert is_conflict_2, "Different inputs should return conflict"

    @given(
        deployment=deployment_strategy,
        idempotency_key=idempotency_key_strategy,
        api_key=api_key_strategy,
        company_name=company_name_strategy,
        company_url_1=url_strategy,
        company_url_2=url_strategy,
        mode=mode_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_different_url_returns_conflict(
        self,
        deployment: str,
        idempotency_key: str,
        api_key: str,
        company_name: str,
        company_url_1: str,
        company_url_2: str,
        mode: str,
    ) -> None:
        """
        Same idempotency_key + different URL returns 409.

        Feature: serverless-cloud-deployment, Property 2: Idempotent Submission
        **Validates: Requirements 3.6**
        """
        # Ensure URLs are actually different after canonicalization
        canonical_1 = canonicalize_inputs(company_name, company_url_1, mode)
        canonical_2 = canonicalize_inputs(company_name, company_url_2, mode)
        assume(canonical_1.company_url != canonical_2.company_url)

        job_store = InMemoryJobStore()

        # First submission
        _, _, is_conflict_1 = submit_job_idempotent(
            job_store=job_store,
            deployment=deployment,
            idempotency_key=idempotency_key,
            api_key=api_key,
            company_name=company_name,
            company_url=company_url_1,
            mode=mode,
        )
        assert not is_conflict_1

        # Second submission with different URL
        _, _, is_conflict_2 = submit_job_idempotent(
            job_store=job_store,
            deployment=deployment,
            idempotency_key=idempotency_key,
            api_key=api_key,
            company_name=company_name,
            company_url=company_url_2,  # Different!
            mode=mode,
        )

        assert is_conflict_2, "Different URL should return conflict"

    @given(
        deployment=deployment_strategy,
        idempotency_key=idempotency_key_strategy,
        api_key=api_key_strategy,
        company_name=company_name_strategy,
        company_url=url_strategy,
        mode_1=mode_strategy,
        mode_2=mode_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_different_mode_returns_conflict(
        self,
        deployment: str,
        idempotency_key: str,
        api_key: str,
        company_name: str,
        company_url: str,
        mode_1: str,
        mode_2: str,
    ) -> None:
        """
        Same idempotency_key + different mode returns 409.

        Feature: serverless-cloud-deployment, Property 2: Idempotent Submission
        **Validates: Requirements 3.6**
        """
        assume(mode_1 != mode_2)

        job_store = InMemoryJobStore()

        # First submission
        _, _, is_conflict_1 = submit_job_idempotent(
            job_store=job_store,
            deployment=deployment,
            idempotency_key=idempotency_key,
            api_key=api_key,
            company_name=company_name,
            company_url=company_url,
            mode=mode_1,
        )
        assert not is_conflict_1

        # Second submission with different mode
        _, _, is_conflict_2 = submit_job_idempotent(
            job_store=job_store,
            deployment=deployment,
            idempotency_key=idempotency_key,
            api_key=api_key,
            company_name=company_name,
            company_url=company_url,
            mode=mode_2,  # Different!
        )

        assert is_conflict_2, "Different mode should return conflict"


# =============================================================================
# PROPERTY 2.3: DIFFERENT DEPLOYMENT RETURNS DIFFERENT JOB_ID
# =============================================================================


class TestDifferentDeploymentReturnsDifferentJobId:
    """
    **Property 2.3: Different Deployment Returns Different Job ID**

    For any job submission where the deployment differs but idempotency_key
    and api_key are the same, the system SHALL return different job_ids.

    This prevents cross-environment collisions.

    **Validates: Requirements 3.7**
    """

    @given(
        deployment_1=deployment_strategy,
        deployment_2=deployment_strategy,
        idempotency_key=idempotency_key_strategy,
        api_key=api_key_strategy,
        company_name=company_name_strategy,
        company_url=url_strategy,
        mode=mode_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_different_deployment_returns_different_job_id(
        self,
        deployment_1: str,
        deployment_2: str,
        idempotency_key: str,
        api_key: str,
        company_name: str,
        company_url: str,
        mode: str,
    ) -> None:
        """
        Different deployment + same idempotency_key returns different job_id.

        Feature: serverless-cloud-deployment, Property 2: Idempotent Submission
        **Validates: Requirements 3.7**
        """
        assume(deployment_1 != deployment_2)

        job_id_1 = hash_job_id(deployment_1, idempotency_key, api_key)
        job_id_2 = hash_job_id(deployment_2, idempotency_key, api_key)

        assert job_id_1 != job_id_2, "Different deployments should produce different job_ids"

    @given(
        deployment_1=deployment_strategy,
        deployment_2=deployment_strategy,
        idempotency_key=idempotency_key_strategy,
        api_key=api_key_strategy,
        company_name=company_name_strategy,
        company_url=url_strategy,
        mode=mode_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_different_deployment_no_conflict(
        self,
        deployment_1: str,
        deployment_2: str,
        idempotency_key: str,
        api_key: str,
        company_name: str,
        company_url: str,
        mode: str,
    ) -> None:
        """
        Same idempotency_key in different deployments should not conflict.

        Feature: serverless-cloud-deployment, Property 2: Idempotent Submission
        **Validates: Requirements 3.7**
        """
        assume(deployment_1 != deployment_2)

        job_store = InMemoryJobStore()

        # Submit to first deployment
        job_id_1, _, is_conflict_1 = submit_job_idempotent(
            job_store=job_store,
            deployment=deployment_1,
            idempotency_key=idempotency_key,
            api_key=api_key,
            company_name=company_name,
            company_url=company_url,
            mode=mode,
        )
        assert not is_conflict_1

        # Submit to second deployment with same idempotency_key
        job_id_2, is_existing_2, is_conflict_2 = submit_job_idempotent(
            job_store=job_store,
            deployment=deployment_2,
            idempotency_key=idempotency_key,
            api_key=api_key,
            company_name=company_name,
            company_url=company_url,
            mode=mode,
        )

        # Should create a new job, not conflict
        assert not is_conflict_2, "Different deployment should not conflict"
        assert not is_existing_2, "Different deployment should create new job"
        assert job_id_1 != job_id_2, "Different deployments should have different job_ids"


# =============================================================================
# PROPERTY 2.4: DIFFERENT API KEY RETURNS DIFFERENT JOB_ID
# =============================================================================


class TestDifferentApiKeyReturnsDifferentJobId:
    """
    **Property 2.4: Different API Key Returns Different Job ID**

    For any job submission where the api_key differs but deployment and
    idempotency_key are the same, the system SHALL return different job_ids.

    This prevents cross-tenant collisions.

    **Validates: Requirements 3.7**
    """

    @given(
        deployment=deployment_strategy,
        idempotency_key=idempotency_key_strategy,
        api_key_1=api_key_strategy,
        api_key_2=api_key_strategy,
        company_name=company_name_strategy,
        company_url=url_strategy,
        mode=mode_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_different_api_key_returns_different_job_id(
        self,
        deployment: str,
        idempotency_key: str,
        api_key_1: str,
        api_key_2: str,
        company_name: str,
        company_url: str,
        mode: str,
    ) -> None:
        """
        Different api_key + same idempotency_key returns different job_id.

        Feature: serverless-cloud-deployment, Property 2: Idempotent Submission
        **Validates: Requirements 3.7**
        """
        assume(api_key_1 != api_key_2)

        job_id_1 = hash_job_id(deployment, idempotency_key, api_key_1)
        job_id_2 = hash_job_id(deployment, idempotency_key, api_key_2)

        assert job_id_1 != job_id_2, "Different API keys should produce different job_ids"

    @given(
        deployment=deployment_strategy,
        idempotency_key=idempotency_key_strategy,
        api_key_1=api_key_strategy,
        api_key_2=api_key_strategy,
        company_name=company_name_strategy,
        company_url=url_strategy,
        mode=mode_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_different_api_key_no_conflict(
        self,
        deployment: str,
        idempotency_key: str,
        api_key_1: str,
        api_key_2: str,
        company_name: str,
        company_url: str,
        mode: str,
    ) -> None:
        """
        Same idempotency_key with different API keys should not conflict.

        Feature: serverless-cloud-deployment, Property 2: Idempotent Submission
        **Validates: Requirements 3.7**
        """
        assume(api_key_1 != api_key_2)

        job_store = InMemoryJobStore()

        # Submit with first API key
        job_id_1, _, is_conflict_1 = submit_job_idempotent(
            job_store=job_store,
            deployment=deployment,
            idempotency_key=idempotency_key,
            api_key=api_key_1,
            company_name=company_name,
            company_url=company_url,
            mode=mode,
        )
        assert not is_conflict_1

        # Submit with second API key (same idempotency_key)
        job_id_2, is_existing_2, is_conflict_2 = submit_job_idempotent(
            job_store=job_store,
            deployment=deployment,
            idempotency_key=idempotency_key,
            api_key=api_key_2,
            company_name=company_name,
            company_url=company_url,
            mode=mode,
        )

        # Should create a new job, not conflict
        assert not is_conflict_2, "Different API key should not conflict"
        assert not is_existing_2, "Different API key should create new job"
        assert job_id_1 != job_id_2, "Different API keys should have different job_ids"


# =============================================================================
# PROPERTY 2.5: CANONICAL HASH CONSISTENCY
# =============================================================================


class TestCanonicalHashConsistency:
    """
    **Property 2.5: Canonical Hash Consistency**

    For any inputs, the canonical hash SHALL be deterministic and consistent
    across multiple computations.

    **Validates: Requirements 3.5, 3.6**
    """

    @given(
        company_name=company_name_strategy,
        company_url=url_strategy,
        mode=mode_strategy,
        options=options_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_canonical_hash_is_deterministic(
        self,
        company_name: str,
        company_url: str,
        mode: str,
        options: dict[str, Any],
    ) -> None:
        """
        Canonical hash should be deterministic for same inputs.

        Feature: serverless-cloud-deployment, Property 2: Idempotent Submission
        **Validates: Requirements 3.5**
        """
        canonical_1 = canonicalize_inputs(company_name, company_url, mode, options)
        canonical_2 = canonicalize_inputs(company_name, company_url, mode, options)

        hash_1 = hash_inputs(canonical_1)
        hash_2 = hash_inputs(canonical_2)

        assert hash_1 == hash_2, "Same inputs should produce same hash"

    @given(
        company_name=company_name_strategy,
        company_url=url_strategy,
        mode=mode_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_url_normalization_produces_same_hash(
        self,
        company_name: str,
        company_url: str,
        mode: str,
    ) -> None:
        """
        URL normalization should produce consistent hashes.

        Feature: serverless-cloud-deployment, Property 2: Idempotent Submission
        **Validates: Requirements 3.5**
        """
        # Add trailing slash to URL
        url_with_slash = company_url.rstrip("/") + "/"
        url_without_slash = company_url.rstrip("/")

        canonical_1 = canonicalize_inputs(company_name, url_with_slash, mode)
        canonical_2 = canonicalize_inputs(company_name, url_without_slash, mode)

        # After normalization, URLs should be the same
        assert canonical_1.company_url == canonical_2.company_url
        assert hash_inputs(canonical_1) == hash_inputs(canonical_2)

    @given(
        company_name=company_name_strategy,
        company_url=url_strategy,
        mode=mode_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_whitespace_normalization_produces_same_hash(
        self,
        company_name: str,
        company_url: str,
        mode: str,
    ) -> None:
        """
        Whitespace normalization should produce consistent hashes.

        Feature: serverless-cloud-deployment, Property 2: Idempotent Submission
        **Validates: Requirements 3.5**
        """
        name_with_spaces = f"  {company_name}  "
        name_without_spaces = company_name.strip()

        canonical_1 = canonicalize_inputs(name_with_spaces, company_url, mode)
        canonical_2 = canonicalize_inputs(name_without_spaces, company_url, mode)

        # After normalization, names should be the same
        assert canonical_1.company_name == canonical_2.company_name
        assert hash_inputs(canonical_1) == hash_inputs(canonical_2)


# =============================================================================
# PROPERTY 2.6: JOB ID UNIQUENESS
# =============================================================================


class TestJobIdUniqueness:
    """
    **Property 2.6: Job ID Uniqueness**

    For any two distinct (deployment, idempotency_key, api_key) tuples,
    the derived job_ids SHALL be different.

    **Validates: Requirements 3.7**
    """

    @given(
        deployment_1=deployment_strategy,
        deployment_2=deployment_strategy,
        idempotency_key_1=idempotency_key_strategy,
        idempotency_key_2=idempotency_key_strategy,
        api_key_1=api_key_strategy,
        api_key_2=api_key_strategy,
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_different_tuples_produce_different_job_ids(
        self,
        deployment_1: str,
        deployment_2: str,
        idempotency_key_1: str,
        idempotency_key_2: str,
        api_key_1: str,
        api_key_2: str,
    ) -> None:
        """
        Different (deployment, idempotency_key, api_key) tuples produce different job_ids.

        Feature: serverless-cloud-deployment, Property 2: Idempotent Submission
        **Validates: Requirements 3.7**
        """
        # At least one component must differ
        tuple_1 = (deployment_1, idempotency_key_1, api_key_1)
        tuple_2 = (deployment_2, idempotency_key_2, api_key_2)
        assume(tuple_1 != tuple_2)

        job_id_1 = hash_job_id(deployment_1, idempotency_key_1, api_key_1)
        job_id_2 = hash_job_id(deployment_2, idempotency_key_2, api_key_2)

        assert job_id_1 != job_id_2, "Different tuples should produce different job_ids"
