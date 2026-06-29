# Security Operations Guide

This guide covers operational security for Primr deployments, including API key management, audit log storage, and security testing recommendations.

## Table of Contents

1. [API Key Management](#api-key-management)
2. [Audit Log Storage](#audit-log-storage)
3. [Security Testing](#security-testing)
4. [Incident Response](#incident-response)

---

## API Key Management

### Key Rotation

Primr supports zero-downtime key rotation with configurable grace periods.

```python
from primr.api.auth import create_api_key, rotate_api_key, get_auth

# Create a key with 90-day expiration
key = create_api_key("production-app", expires_in_days=90)

# Later: rotate the key with 24-hour grace period
new_key = rotate_api_key(key, grace_hours=24)
# Both keys work for 24 hours, then only new_key works
```

### Rotation Best Practices

1. **Schedule regular rotations** - Rotate keys every 90 days
2. **Use grace periods** - Allow 24-48 hours for applications to update
3. **Monitor old key usage** - Alert if old keys are still being used after grace period
4. **Automate rotation** - Use the callback system for notifications

```python
# Set up rotation notifications
auth = get_auth()

def notify_rotation(name, old_prefix, new_prefix):
    # Send to Slack, email, etc.
    print(f"Key rotated: {name}")
    # Update secrets manager, notify team, etc.

auth.on_rotation(notify_rotation)
```

### Expiration Monitoring

```python
# Check for keys expiring in the next 7 days
expiring = get_auth().get_expiring_keys(within_days=7)
for key_info in expiring:
    print(f"Key '{key_info['name']}' expires in {key_info['days_remaining']} days")
```

### Key Cleanup

Run periodically to remove expired keys from memory:

```python
# Clean up expired and rotated-out keys
cleaned = get_auth().cleanup_expired()
print(f"Removed {cleaned} expired keys")
```

---

## Audit Log Storage

Primr generates security audit logs that should be stored persistently for
compliance and incident investigation. MCP tool invocations, MCP resource
reads, and A2A skill calls are appended to `output/.mcp_audit_log.jsonl` by
default, or beside a custom MCP job journal when one is configured.

### Log Format

Security events are logged with structured data:

```json
{
  "schema_version": "1.0",
  "event_type": "tool_call",
  "timestamp": "2026-06-25T12:00:00Z",
  "tool_name": "research_company",
  "status": "success",
  "client_id_hash": "sha256:...",
  "auth_scopes": ["research"],
  "args_hash": "sha256:...",
  "result_hash": "sha256:...",
  "approval_token_id": "tok_...",
  "job_id": "job_abc123",
  "duration_ms": 12
}
```

Resource-read events use `event_type: "resource_read"` and
`tool_name: "resources/read"`. They include `resource_kind`, `resource_uri_hash`,
`result_hash`, `job_id` when present, scopes, duration, and outcome. A2A
skill-call events use `transport: "a2a"` and `tool_name: "a2a/<skill>"` with
hashed message/result payloads, hashed caller ids, granted scopes, duration,
outcome, and job id when present. Raw tool arguments, raw tool results, raw A2A
message text, task ids, raw resource URI query values, raw resource bodies,
raw client ids, report paths, URLs, and full approval tokens are not persisted.

### AWS S3 Storage

Store audit logs in S3 with lifecycle policies for cost optimization.

#### Terraform Configuration

```hcl
# terraform/audit-logs-aws.tf

resource "aws_s3_bucket" "audit_logs" {
  bucket = "primr-audit-logs-${var.environment}"
  
  tags = {
    Environment = var.environment
    Purpose     = "security-audit-logs"
  }
}

resource "aws_s3_bucket_versioning" "audit_logs" {
  bucket = aws_s3_bucket.audit_logs.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit_logs" {
  bucket = aws_s3_bucket.audit_logs.id
  
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.audit_logs.arn
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "audit_logs" {
  bucket = aws_s3_bucket.audit_logs.id
  
  rule {
    id     = "audit-log-lifecycle"
    status = "Enabled"
    
    # Move to Infrequent Access after 30 days
    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
    
    # Move to Glacier after 90 days
    transition {
      days          = 90
      storage_class = "GLACIER"
    }
    
    # Delete after 7 years (compliance requirement)
    expiration {
      days = 2555  # 7 years
    }
  }
}

resource "aws_s3_bucket_public_access_block" "audit_logs" {
  bucket = aws_s3_bucket.audit_logs.id
  
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_kms_key" "audit_logs" {
  description             = "KMS key for audit log encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}
```

#### Python Upload Script

```python
# scripts/upload_audit_logs.py
import boto3
import gzip
from datetime import datetime
from pathlib import Path

def upload_audit_logs(log_dir: str, bucket: str, prefix: str = "audit"):
    """Upload and compress audit logs to S3."""
    s3 = boto3.client('s3')
    
    for log_file in Path(log_dir).glob("*.log"):
        # Compress the log file
        compressed = log_file.with_suffix('.log.gz')
        with open(log_file, 'rb') as f_in:
            with gzip.open(compressed, 'wb') as f_out:
                f_out.writelines(f_in)
        
        # Upload to S3 with date-based prefix
        date_prefix = datetime.now().strftime("%Y/%m/%d")
        s3_key = f"{prefix}/{date_prefix}/{compressed.name}"
        
        s3.upload_file(
            str(compressed),
            bucket,
            s3_key,
            ExtraArgs={
                'ServerSideEncryption': 'aws:kms',
                'ContentType': 'application/gzip',
            }
        )
        
        # Clean up local files
        compressed.unlink()
        log_file.unlink()
        
        print(f"Uploaded {log_file.name} to s3://{bucket}/{s3_key}")
```

### Google Cloud Storage

#### Terraform Configuration

```hcl
# terraform/audit-logs-gcp.tf

resource "google_storage_bucket" "audit_logs" {
  name          = "primr-audit-logs-${var.project_id}"
  location      = var.region
  storage_class = "STANDARD"
  
  uniform_bucket_level_access = true
  
  versioning {
    enabled = true
  }
  
  encryption {
    default_kms_key_name = google_kms_crypto_key.audit_logs.id
  }
  
  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }
  
  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type          = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }
  
  lifecycle_rule {
    condition {
      age = 365
    }
    action {
      type          = "SetStorageClass"
      storage_class = "ARCHIVE"
    }
  }
  
  lifecycle_rule {
    condition {
      age = 2555  # 7 years
    }
    action {
      type = "Delete"
    }
  }
  
  labels = {
    environment = var.environment
    purpose     = "security-audit-logs"
  }
}

resource "google_kms_key_ring" "audit_logs" {
  name     = "primr-audit-logs-keyring"
  location = var.region
}

resource "google_kms_crypto_key" "audit_logs" {
  name            = "primr-audit-logs-key"
  key_ring        = google_kms_key_ring.audit_logs.id
  rotation_period = "7776000s"  # 90 days
}
```

### Azure Blob Storage

#### Terraform Configuration

```hcl
# terraform/audit-logs-azure.tf

resource "azurerm_storage_account" "audit_logs" {
  name                     = "primrauditlogs${var.environment}"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "GRS"
  
  blob_properties {
    versioning_enabled = true
    
    delete_retention_policy {
      days = 30
    }
  }
  
  identity {
    type = "SystemAssigned"
  }
  
  tags = {
    environment = var.environment
    purpose     = "security-audit-logs"
  }
}

resource "azurerm_storage_container" "audit_logs" {
  name                  = "audit-logs"
  storage_account_name  = azurerm_storage_account.audit_logs.name
  container_access_type = "private"
}

resource "azurerm_storage_management_policy" "audit_logs" {
  storage_account_id = azurerm_storage_account.audit_logs.id
  
  rule {
    name    = "audit-log-lifecycle"
    enabled = true
    
    filters {
      blob_types   = ["blockBlob"]
      prefix_match = ["audit-logs/"]
    }
    
    actions {
      base_blob {
        tier_to_cool_after_days_since_modification_greater_than    = 30
        tier_to_archive_after_days_since_modification_greater_than = 90
        delete_after_days_since_modification_greater_than          = 2555
      }
    }
  }
}
```

### Log Shipping with Fluentd

```yaml
# fluentd/fluent.conf
<source>
  @type tail
  path /var/log/primr/security.log
  pos_file /var/log/fluentd/primr-security.pos
  tag primr.security
  <parse>
    @type regexp
    expression /^(?<time>\S+) (?<event>\S+): (?<message>.*)$/
  </parse>
</source>

<match primr.security>
  @type s3
  s3_bucket primr-audit-logs
  s3_region us-east-1
  path audit/%Y/%m/%d/
  <buffer time>
    @type file
    path /var/log/fluentd/s3-buffer
    timekey 3600
    timekey_wait 10m
    chunk_limit_size 256m
  </buffer>
  <format>
    @type json
  </format>
</match>
```

---

## Security Testing

### Recommended Testing Approach

Since Primr is open source, security testing should be part of your deployment process rather than CI/CD.

### 1. Pre-Deployment Security Scan

Run before each deployment:

```bash
# Run the built-in security scan
python scripts/security_scan.py

# Run bandit for Python security issues
pip install bandit
bandit -r src/primr -ll

# Check dependencies for vulnerabilities (matches the CI gate)
pip install pip-audit
pip-audit
```

### 2. Unit Security Tests

Run the security test suite:

```bash
# All security-related tests
pytest tests/mcp_server/test_auth.py \
       tests/mcp_server/test_security.py \
       tests/test_security.py \
       tests/test_utils/test_security.py \
       tests/test_api/test_auth.py \
       -v

# Quick security smoke test
pytest -k "security or auth" --tb=short
```

### 3. Integration Security Tests

Test security in a staging environment:

```python
# tests/integration/test_security_integration.py
import requests

def test_rate_limiting(api_url, api_key):
    """Verify rate limiting is enforced."""
    responses = []
    for _ in range(150):  # Exceed default 100/hour limit
        r = requests.post(
            f"{api_url}/research",
            json={"company_name": "Test"},
            headers={"X-API-Key": api_key}
        )
        responses.append(r.status_code)
    
    # Should see 429 responses after limit exceeded
    assert 429 in responses, "Rate limiting not enforced"

def test_invalid_auth_rejected(api_url):
    """Verify invalid authentication is rejected."""
    r = requests.post(
        f"{api_url}/research",
        json={"company_name": "Test"},
        headers={"X-API-Key": "invalid-key"}
    )
    assert r.status_code == 401

def test_security_headers_present(api_url):
    """Verify security headers are set."""
    r = requests.get(f"{api_url}/health")
    
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert "max-age=" in r.headers.get("Strict-Transport-Security", "")
```

### 4. Penetration Testing Checklist

For production deployments, consider testing:

| Category | Test | Tool/Method |
|----------|------|-------------|
| Authentication | JWT token forgery | Manual + Burp Suite |
| Authentication | Brute force protection | Custom script |
| Authorization | Privilege escalation | Manual testing |
| Input Validation | SQL injection | sqlmap |
| Input Validation | XSS | Manual + OWASP ZAP |
| SSRF | Internal network access | Manual testing |
| Rate Limiting | Bypass attempts | Custom script |
| API Security | Parameter tampering | Burp Suite |

### 5. OWASP ZAP Automated Scan

```bash
# Run OWASP ZAP against staging
docker run -t owasp/zap2docker-stable zap-baseline.py \
    -t https://staging-api.example.com \
    -r zap-report.html
```

### 6. Load Testing with Security Focus

```python
# locustfile.py - Security-focused load test
from locust import HttpUser, task, between

class SecurityLoadTest(HttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        # Get valid API key
        self.api_key = "your-test-api-key"
    
    @task(10)
    def valid_request(self):
        """Normal authenticated request."""
        self.client.post(
            "/research",
            json={"company_name": "Test Corp"},
            headers={"X-API-Key": self.api_key}
        )
    
    @task(1)
    def invalid_auth(self):
        """Test invalid auth handling under load."""
        self.client.post(
            "/research",
            json={"company_name": "Test"},
            headers={"X-API-Key": "invalid"}
        )
    
    @task(1)
    def malformed_request(self):
        """Test malformed request handling."""
        self.client.post(
            "/research",
            data="not-json",
            headers={"X-API-Key": self.api_key}
        )
```

Run with:
```bash
locust -f locustfile.py --host=https://staging-api.example.com
```

---

## Incident Response

### Security Event Monitoring

Set up alerts for these security events:

| Event | Threshold | Action |
|-------|-----------|--------|
| AUTH_FAILURE | >10/minute from same IP | Block IP, investigate |
| RATE_LIMIT | >5 clients/hour | Review rate limits |
| SECURITY_VIOLATION | Any | Immediate investigation |
| Expired key usage | Any | Contact key owner |

### Response Procedures

#### 1. Suspected Key Compromise

```python
from primr.api.auth import revoke_api_key, get_auth

# Immediately revoke the compromised key
revoke_api_key(compromised_key)

# Check for suspicious activity
auth = get_auth()
key_info = auth.get_key_info(compromised_key)
print(f"Last used: {key_info.last_used}")
print(f"Request count: {key_info.request_count}")

# Issue new key to legitimate user
new_key = create_api_key("replacement-key")
```

#### 2. Rate Limit Abuse

```python
# Identify abusive clients from logs
# grep "RATE_LIMIT" /var/log/primr/security.log | sort | uniq -c | sort -rn

# Temporarily reduce rate limit for abusive client
auth = get_auth()
# Or revoke entirely if malicious
```

#### 3. SSRF Attempt Detected

1. Review logs for `SECURITY_VIOLATION: type=ssrf`
2. Identify source IP and API key
3. Revoke API key if compromised
4. Block IP at firewall level
5. Review URL validation rules

### Log Analysis Queries

```bash
# Find all auth failures in last hour
grep "AUTH_FAILURE" /var/log/primr/security.log | \
    awk -v d="$(date -d '1 hour ago' +%Y-%m-%dT%H)" '$1 > d'

# Find rate-limited clients
grep "RATE_LIMIT" /var/log/primr/security.log | \
    grep -oP 'user=\K[^,]+' | sort | uniq -c | sort -rn

# Find security violations
grep "SECURITY_VIOLATION" /var/log/primr/security.log
```

---

## Quick Reference

### Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `MCP_JWT_SECRET` | JWT signing key | 32+ char random string |
| `MCP_JWT_ISSUER` | JWT issuer validation | `primr-api` |
| `MCP_JWT_AUDIENCE` | JWT audience validation | `primr-clients` |
| `MCP_ADMIN_TOKENS` | Static admin tokens | `token1,token2` |
| `PRIMR_CORS_ORIGINS` | Allowed CORS origins | `https://app.example.com` |

### Security Test Commands

```bash
# Full security test suite
pytest tests/ -k "security or auth" -v

# Quick security check
python scripts/security_scan.py

# Dependency vulnerability scan
pip-audit
```

### Key Rotation Schedule

| Key Type | Rotation Frequency | Grace Period |
|----------|-------------------|--------------|
| Production API keys | 90 days | 48 hours |
| Development keys | 30 days | 24 hours |
| Admin tokens | 30 days | 4 hours |
| JWT secrets | 180 days | 7 days |
