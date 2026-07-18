# Security Operations Guide

This guide covers operational security for Primr deployments, including API key management, audit log storage, and security testing recommendations.

## Table of Contents

1. [API Key Management](#api-key-management)
2. [Audit Log Storage](#audit-log-storage)
3. [Security Testing](#security-testing)
4. [Incident Response](#incident-response)

---

## API Key Management

### Supported Production Boundary

Use the credential system that matches the deployed surface:

1. Store model-provider keys in the deployment secret manager and expose them
   to Primr through the documented environment variables. Rotate and revoke
   them through the provider and deployment platform.
2. Protect networked MCP and A2A deployments with signed JWTs, scoped bearer
   tokens, cost controls, and transport security. Static `MCP_ADMIN_TOKENS`
   are an operator bootstrap surface; rotate them by updating the secret and
   restarting the service.
3. Never pass agent-host OAuth credentials, browser cookies, or subscription
   tokens into Primr.

### Process-Local REST Scaffold

`primr.api.auth` is a process-local development scaffold. Its keys, rotation
state, usage counters, and callbacks exist only in memory and are lost on
restart. The REST research submission endpoint is not wired to the production
pipeline. Do not use this module as a durable production identity store or
claim zero-downtime production rotation from it.

For local tests only, the scaffold supports create, rotate, inspect, revoke,
and cleanup operations:

```python
from primr.api.auth import create_api_key, get_auth, rotate_api_key

key = create_api_key("local-test", expires_in_days=1)
rotated = rotate_api_key(key, grace_hours=1)
assert rotated is not None
assert get_auth().verify(rotated)
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

### Review Recent Events

Read `primr://agent/audit/recent?limit=50` through an MCP resource client for a
bounded recent-event view. Local stdio sessions can read it directly. HTTP
sessions require the `admin` scope; a token with only `read` is denied and the
denial is itself audited. The resource returns structured metadata and hashes,
not raw request bodies, report content, URLs, or caller identifiers.

For longer retention, ship snapshots of `output/.mcp_audit_log.jsonl` or the
audit file beside the configured job journal. Preserve the active local file
until the application owns an explicit, tested rotation policy.

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

#### Safe Snapshot Upload Example

```python
import boto3
import gzip
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

def upload_audit_snapshot(audit_path: str, bucket: str, prefix: str = "audit") -> str:
    """Upload a temporary snapshot without deleting or renaming the active log."""
    source = Path(audit_path)
    if source.name != ".mcp_audit_log.jsonl" or source.is_symlink() or not source.is_file():
        raise ValueError("audit_path must be the regular Primr MCP audit JSONL file")

    date_prefix = datetime.now().strftime("%Y/%m/%d")
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    with tempfile.TemporaryDirectory(prefix="primr-audit-") as temp_dir:
        snapshot = Path(temp_dir) / f"mcp-audit-{timestamp}.jsonl"
        compressed = snapshot.with_suffix(".jsonl.gz")
        shutil.copyfile(source, snapshot)
        with snapshot.open("rb") as source_stream, gzip.open(compressed, "wb") as target_stream:
            shutil.copyfileobj(source_stream, target_stream)

        s3_key = f"{prefix}/{date_prefix}/{compressed.name}"
        boto3.client("s3").upload_file(
            str(compressed),
            bucket,
            s3_key,
            ExtraArgs={"ServerSideEncryption": "aws:kms", "ContentType": "application/gzip"},
        )
    return s3_key
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
  path /srv/primr/output/.mcp_audit_log.jsonl
  pos_file /var/lib/fluentd/primr-mcp-audit.pos
  tag primr.security
  <parse>
    @type json
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

Repository CI hard-gates Bandit, `pip-audit`, the deploy secret scan, and
Trivy container and configuration scanning. Deployment owners must also run
the environment-specific preflight and staging checks below; CI cannot verify
runtime identity, network, secret-store, or ingress configuration.

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

Test the deployed MCP or A2A protocol boundary with its official client. Do
not point deployment tests at the process-local REST scaffold or its
unimplemented `/research` submission route.

Use non-billable operations such as MCP initialization, `doctor`,
`check_jobs`, and `estimate_run` for staging verification. Confirm all of the
following before enabling research traffic:

Run negative approval and budget tests only with provider credentials absent
or stubbed and provider egress blocked at the network boundary. A broken guard
must fail without any route to provider spend. Any positive provider-backed
staging launch remains a separately estimated action that requires explicit
approval.

- missing, expired, incorrectly signed, wrong-issuer, and wrong-audience
  bearer tokens are rejected;
- a `read` token can call read tools but cannot call `research_company`;
- a `research` token cannot read report bodies without `report` scope and
  cannot call admin-only cleanup;
- job ownership prevents one authenticated client from reading or cancelling
  another client's job;
- tool limits produce the documented structured rate-limit error;
- estimate and approval controls reject an unapproved or over-budget launch;
- MCP tool calls, resource reads, denials, and A2A calls create redacted audit
  events; and
- the ingress supplies TLS and the deployment's required security headers.

The repository auth, authorization, ownership, cost-control, SSRF, and audit
tests are the executable baseline. Environment checks must exercise the same
deployed transport and identity configuration that clients will use.

### 4. Penetration Testing Checklist

For production deployments, test the threats Primr actually exposes:

| Category | Test | Tool/Method |
|----------|------|-------------|
| Authentication | JWT forgery, expiry, issuer, and audience | Protocol client plus identity test tokens |
| Authorization | Tool scopes, report scope, admin scope, and job ownership | MCP and A2A protocol tests |
| Cost controls | Missing approval, altered estimate, and budget overrun | Offline or stubbed governed-tool tests with provider egress blocked |
| SSRF | Loopback, private, metadata, redirect, and DNS-rebinding targets | Repository SSRF suite plus isolated staging canaries |
| Rate limiting | Per-client and per-tool bypass attempts | Protocol-aware load harness |
| Audit privacy | Secrets, URLs, report paths, and caller ids absent from events | Audit JSONL and admin-resource inspection |
| Transport | TLS, CORS, proxy headers, body limits, and timeouts | Ingress scanner and deployment checks |

### 5. Transport Scanning

An ingress scanner can assess TLS and generic HTTP behavior, but it cannot
prove MCP or A2A authorization semantics. Scan only a deployment you control,
use a non-production identity, and pair the result with protocol-aware tests.
Do not interpret a generic scan of `/mcp` as proof that tool scopes, job
ownership, approval tokens, or audit redaction work.

### 6. Load Testing with Security Focus

Drive the actual MCP or A2A protocol with isolated staging tokens. Use read
tools for steady-state traffic and a dedicated client identity when testing
rate-limit exhaustion. Do not include `research_company`, strategy generation,
or other billable operations in a load test. Verify bounded latency, correct
per-client isolation, structured throttling, audit volume, log rotation, and
recovery after the load stops.

---

## Incident Response

### Security Event Monitoring

Set up alerts for these security events:

| Event | Threshold | Action |
|-------|-----------|--------|
| `scope_denied` | Repeated for one client hash | Review granted scopes and investigate misuse |
| `rate_limited` | Repeated after the published retry window | Review client behavior and ingress controls |
| `exception` | Any sustained cluster | Triage the operation, deployment logs, and dependencies |
| Failed or expired bearer verification | Any sustained cluster in service logs | Correlate at the identity provider and ingress |

### Response Procedures

#### 1. Suspected Key Compromise

1. Revoke the model-provider key, JWT signing key, or admin token at its owning
   secret or identity system.
2. Replace the deployment secret and restart affected Primr services so the
   old value is no longer resident in any process.
3. Review `primr://agent/audit/recent` and the retained JSONL snapshots for the
   affected client hash, scope, job, and outcome patterns.
4. Review provider billing and access logs, then invalidate any dependent
   approval tokens or integration credentials.

The process-local `primr.api.auth` scaffold is not a source of production
credential history after a restart.

#### 2. Rate Limit Abuse

Use the MCP audit stream to identify repeated `rate_limited` outcomes by
`client_id_hash`. Revoke or narrow the owning JWT or admin token, then apply
network controls at the ingress when the source is malicious. Do not attempt
to modify the unrelated process-local REST scaffold.

#### 3. SSRF Attempt Detected

1. Review the service log and matching MCP audit event for the rejected call.
2. Correlate the client hash with the identity and ingress logs that own the
   raw client and network metadata.
3. Revoke the compromised bearer token or provider credential.
4. Block the source at the ingress when appropriate.
5. Preserve the rejected input through the deployment's restricted incident
   evidence process, then review URL validation and redirect rules.

### Log Analysis Queries

```bash
# Scope denials
jq -c 'select(.status == "scope_denied")' output/.mcp_audit_log.jsonl

# Rate-limited calls
jq -c 'select(.status == "rate_limited")' output/.mcp_audit_log.jsonl

# Exceptions and visible operation failures
jq -c 'select(.status == "exception" or .status == "error")' output/.mcp_audit_log.jsonl
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
| `MCP_ADMIN_TOKEN_MAX_AGE_HOURS` | Reject static admin tokens after first-use age | `720` |
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
| Model-provider keys | Provider and deployment policy | Provider-managed overlap when supported |
| MCP admin tokens | 30 days or stricter local policy | Deployment-controlled restart window |
| JWT signing secrets | Identity and deployment policy | Issuer-controlled overlap |
| Process-local REST scaffold keys | Not applicable to production | Lost on process restart |
