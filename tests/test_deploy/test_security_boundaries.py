"""
Tests for security boundaries in cloud deployment.

Tests:
- SSRF protection (validates existing primr validators)
- Rate limiting
- Resource limits validation

Requirements: 9.1, 9.2, 9.5
"""

from __future__ import annotations

import time
import pytest

from deploy.control_plane.rate_limiter import (
    RateLimiter,
    RateLimitConfig,
    TokenBucket,
    RateLimitResult,
)


class TestRateLimiter:
    """Tests for rate limiting functionality."""
    
    def test_token_bucket_allows_burst(self) -> None:
        """Token bucket allows burst up to burst_size."""
        config = RateLimitConfig(requests_per_second=1.0, burst_size=5)
        bucket = TokenBucket(config)
        
        # Should allow burst_size requests immediately
        for i in range(5):
            result = bucket.try_acquire()
            assert result.allowed, f"Request {i+1} should be allowed"
        
        # Next request should be denied
        result = bucket.try_acquire()
        assert not result.allowed, "Request after burst should be denied"
        assert result.retry_after is not None
        assert result.retry_after > 0
    
    def test_token_bucket_refills(self) -> None:
        """Token bucket refills over time."""
        config = RateLimitConfig(requests_per_second=10.0, burst_size=5)
        bucket = TokenBucket(config)
        
        # Exhaust all tokens
        for _ in range(5):
            bucket.try_acquire()
        
        # Wait for refill (0.1 seconds = 1 token at 10/sec)
        time.sleep(0.15)
        
        # Should have at least 1 token now
        result = bucket.try_acquire()
        assert result.allowed, "Should have refilled at least 1 token"
    
    def test_rate_limiter_per_api_key(self) -> None:
        """Rate limiter maintains separate buckets per API key."""
        limiter = RateLimiter(RateLimitConfig(requests_per_second=1.0, burst_size=2))
        
        # Exhaust key1's tokens
        limiter.check("key1")
        limiter.check("key1")
        result1 = limiter.check("key1")
        assert not result1.allowed, "key1 should be rate limited"
        
        # key2 should still have tokens
        result2 = limiter.check("key2")
        assert result2.allowed, "key2 should not be affected by key1"
    
    def test_rate_limiter_custom_config(self) -> None:
        """Rate limiter supports custom config per API key."""
        limiter = RateLimiter(RateLimitConfig(requests_per_second=1.0, burst_size=2))
        
        # Set higher limit for premium key
        limiter.set_config("premium", RateLimitConfig(requests_per_second=10.0, burst_size=100))
        
        # Premium key should have more capacity
        for _ in range(50):
            result = limiter.check("premium")
            assert result.allowed, "Premium key should have high burst"
    
    def test_rate_limiter_cleanup(self) -> None:
        """Rate limiter can clean up inactive buckets."""
        limiter = RateLimiter()
        
        # Create some buckets
        limiter.check("key1")
        limiter.check("key2")
        
        # Buckets were just created, so cleanup with reasonable age should keep them
        removed = limiter.cleanup_inactive(max_age_seconds=3600)
        assert removed == 0, "Should not remove recently used buckets"
        
        # Verify buckets still exist by checking remaining tokens
        assert limiter.get_remaining("key1") > 0
        assert limiter.get_remaining("key2") > 0
    
    def test_rate_limit_result_retry_after(self) -> None:
        """Rate limit result includes retry_after when denied."""
        config = RateLimitConfig(requests_per_second=1.0, burst_size=1)
        bucket = TokenBucket(config)
        
        # Use the one token
        bucket.try_acquire()
        
        # Next request should have retry_after
        result = bucket.try_acquire()
        assert not result.allowed
        assert result.retry_after is not None
        assert result.retry_after > 0
        assert result.retry_after <= 1.0  # Should be at most 1 second at 1 req/sec
    
    def test_rate_limit_result_to_dict(self) -> None:
        """Rate limit result can be serialized to dict."""
        result = RateLimitResult(
            allowed=False,
            remaining=0,
            reset_after=5.0,
            retry_after=1.0,
        )
        
        d = result.to_dict()
        assert d["allowed"] is False
        assert d["remaining"] == 0
        assert d["reset_after"] == 5.0
        assert d["retry_after"] == 1.0


class TestSSRFProtection:
    """Tests validating SSRF protection is in place."""
    
    def test_ssrf_validator_exists(self) -> None:
        """SSRF validator function exists and is importable."""
        from primr.utils.validators import validate_url_for_request
        assert callable(validate_url_for_request)
    
    def test_ssrf_blocks_localhost(self) -> None:
        """SSRF protection blocks localhost."""
        from primr.utils.validators import validate_url_for_request
        
        localhost_urls = [
            "http://localhost/",
            "http://localhost:8080/",
            "http://127.0.0.1/",
            "http://127.0.0.1:8000/admin",
        ]
        
        for url in localhost_urls:
            is_valid, _, error = validate_url_for_request(url)
            assert not is_valid, f"Should block localhost URL: {url}"
            assert error is not None
    
    def test_ssrf_blocks_private_ipv4(self) -> None:
        """SSRF protection blocks private IPv4 ranges."""
        from primr.utils.validators import validate_url_for_request
        
        private_ips = [
            "http://10.0.0.1/",
            "http://10.255.255.255/",
            "http://172.16.0.1/",
            "http://172.31.255.255/",
            "http://192.168.0.1/",
            "http://192.168.255.255/",
        ]
        
        for url in private_ips:
            is_valid, _, error = validate_url_for_request(url)
            assert not is_valid, f"Should block private IP: {url}"
            assert error is not None
    
    def test_ssrf_blocks_link_local(self) -> None:
        """SSRF protection blocks link-local addresses."""
        from primr.utils.validators import validate_url_for_request
        
        link_local = [
            "http://169.254.0.1/",
            "http://169.254.169.254/",  # AWS metadata
            "http://169.254.169.254/latest/meta-data/",
        ]
        
        for url in link_local:
            is_valid, _, error = validate_url_for_request(url)
            assert not is_valid, f"Should block link-local: {url}"
            assert error is not None
    
    def test_ssrf_allows_public_urls(self) -> None:
        """SSRF protection allows public URLs."""
        from primr.utils.validators import validate_url_for_request
        
        public_urls = [
            "https://example.com/",
            "https://www.google.com/",
            "https://api.github.com/",
        ]
        
        for url in public_urls:
            is_valid, _, error = validate_url_for_request(url)
            assert is_valid, f"Should allow public URL: {url}, error: {error}"


class TestResourceLimits:
    """Tests validating resource limits are configured."""
    
    def test_aws_task_definition_has_limits(self) -> None:
        """AWS task definition has CPU and memory limits."""
        import json
        from pathlib import Path
        
        task_def_path = Path("deploy/aws/task-definition.json")
        if not task_def_path.exists():
            pytest.skip("AWS task definition not found")
        
        task_def = json.loads(task_def_path.read_text())
        
        # Check CPU and memory limits
        assert "cpu" in task_def, "Task definition should have CPU limit"
        assert "memory" in task_def, "Task definition should have memory limit"
        
        # Verify reasonable limits
        cpu = int(task_def["cpu"])
        memory = int(task_def["memory"])
        
        assert cpu >= 256, "CPU should be at least 256 units"
        assert cpu <= 4096, "CPU should not exceed 4096 units"
        assert memory >= 512, "Memory should be at least 512 MB"
        assert memory <= 8192, "Memory should not exceed 8192 MB"
    
    def test_azure_job_has_limits(self) -> None:
        """Azure job template has resource limits."""
        import yaml
        from pathlib import Path
        
        job_path = Path("deploy/azure/job-template.yaml")
        if not job_path.exists():
            pytest.skip("Azure job template not found")
        
        job = yaml.safe_load(job_path.read_text())
        
        # Navigate to container resources
        containers = job.get("properties", {}).get("template", {}).get("containers", [])
        assert len(containers) > 0, "Should have at least one container"
        
        resources = containers[0].get("resources", {})
        assert "cpu" in resources, "Container should have CPU limit"
        assert "memory" in resources, "Container should have memory limit"
    
    def test_gcp_job_has_limits(self) -> None:
        """GCP job config has resource limits."""
        import yaml
        from pathlib import Path
        
        job_path = Path("deploy/gcp/job.yaml")
        if not job_path.exists():
            pytest.skip("GCP job config not found")
        
        job = yaml.safe_load(job_path.read_text())
        
        # Navigate to container resources
        containers = (
            job.get("spec", {})
            .get("template", {})
            .get("spec", {})
            .get("template", {})
            .get("spec", {})
            .get("containers", [])
        )
        assert len(containers) > 0, "Should have at least one container"
        
        resources = containers[0].get("resources", {}).get("limits", {})
        assert "cpu" in resources, "Container should have CPU limit"
        assert "memory" in resources, "Container should have memory limit"
    
    def test_timeout_limits_configured(self) -> None:
        """Job timeout limits are configured."""
        import yaml
        from pathlib import Path
        
        # Check Azure timeout
        azure_path = Path("deploy/azure/job-template.yaml")
        if azure_path.exists():
            azure_job = yaml.safe_load(azure_path.read_text())
            timeout = azure_job.get("properties", {}).get("configuration", {}).get("replicaTimeout")
            assert timeout is not None, "Azure should have timeout"
            assert timeout <= 7200, "Timeout should not exceed 2 hours"
        
        # Check GCP timeout
        gcp_path = Path("deploy/gcp/job.yaml")
        if gcp_path.exists():
            gcp_job = yaml.safe_load(gcp_path.read_text())
            timeout = (
                gcp_job.get("spec", {})
                .get("template", {})
                .get("spec", {})
                .get("template", {})
                .get("spec", {})
                .get("timeoutSeconds")
            )
            assert timeout is not None, "GCP should have timeout"
            assert timeout <= 7200, "Timeout should not exceed 2 hours"


class TestConcurrencyLimits:
    """Tests for concurrency limits in cost governor."""
    
    def test_default_concurrent_limit(self) -> None:
        """Default concurrent job limit is reasonable."""
        from deploy.control_plane.cost_governor import QuotaConfig
        
        config = QuotaConfig()
        assert config.max_concurrent_jobs > 0
        assert config.max_concurrent_jobs <= 10  # Reasonable default
    
    def test_quota_enforces_concurrent_limit(self) -> None:
        """Cost governor enforces concurrent job limit."""
        from deploy.control_plane.cost_governor import (
            CostGovernor,
            QuotaConfig,
            QuotaExceededError,
            estimate_cost,
        )
        from deploy.control_plane.job_store import (
            InMemoryJobStore,
            JobRecord,
            JobStatus,
            JobInputs,
            JobTiming,
            CostEstimate,
        )
        
        store = InMemoryJobStore()
        governor = CostGovernor(store, QuotaConfig(max_concurrent_jobs=2))
        
        # Create 2 running jobs
        for i in range(2):
            job = JobRecord(
                job_id=f"job{i}",
                deployment="test",
                idempotency_key=f"key{i}",
                api_key_hash="test_key",
                canonical_hash=f"hash{i}",
                status=JobStatus.RUNNING,
                inputs=JobInputs(company_name="Test", company_url="https://test.com", mode="scrape"),
                expected_artifacts=["test.txt"],
                estimate=CostEstimate(cost_usd=0.1, duration_minutes=5),
                timing=JobTiming(submitted_at="2024-01-01T00:00:00Z"),
            )
            store.put_if_not_exists(job)
        
        # Third job should be rejected
        estimate = estimate_cost("scrape")
        with pytest.raises(QuotaExceededError) as exc_info:
            governor.check_quota("test_key", estimate)
        
        assert "concurrent" in str(exc_info.value).lower()
