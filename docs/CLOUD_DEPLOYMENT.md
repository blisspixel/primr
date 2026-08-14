# Primr Cloud Deployment Guide

This guide covers deploying Primr to cloud providers for serverless job execution.

## Architecture Overview

Primr cloud deployment uses a job-based ephemeral execution model:

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Control Plane  │────▶│   Job Queue     │────▶│   Job Runner    │
│   (API + Auth)  │     │  (SQS/SB/PS)    │     │   (Fargate/CA)  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                                               │
        │                                               ▼
        │                                       ┌─────────────────┐
        └──────────────────────────────────────▶│ Artifact Store  │
                                                │  (S3/Blob/GCS)  │
                                                └─────────────────┘
```

### Components

- **Control Plane**: Stateless API for job submission, status, and results
  - Requires NO LLM keys - only JWT, job store, queue, presign credentials
  - Scales to zero when idle
  
- **Job Queue**: Event-driven boundary between control plane and runners
  - FIFO with content-based deduplication
  - Visibility timeout for long-running jobs
  
- **Job Runner**: Ephemeral container executing Primr research
  - Receives job spec via environment variable
  - Writes artifacts to object storage
  - Writes manifest LAST (commit pattern)
  - Handles SIGTERM for graceful cancellation
  
- **Artifact Store**: Object storage for job outputs
  - Presigned URLs for secure retrieval
  - Manifest-as-commit pattern for consistency

## Quick Start

### AWS (Primary)

```bash
cd deploy/aws

# Deploy infrastructure
./deploy.sh -d prod deploy

# Set the key exposed by the current AWS reference task definition
echo "sk-..." | ./deploy.sh secrets set OPENAI_API_KEY -

# Validate deployment
./deploy.sh validate
```

### Azure (Reference)

```bash
cd deploy/azure

# Deploy infrastructure
./deploy.sh -d prod deploy

# Set the measured full-mode provider pair
echo "xai-..." | ./deploy.sh secrets set XAI-API-KEY -
echo "gemini-..." | ./deploy.sh secrets set GEMINI-API-KEY -

# Validate deployment
./deploy.sh validate
```

### GCP (Reference)

```bash
cd deploy/gcp

# Deploy infrastructure
./deploy.sh -d prod -p my-project deploy

# Set the key exposed by the current GCP reference job manifest
echo "sk-..." | ./deploy.sh secrets set OPENAI_API_KEY -

# Validate deployment
./deploy.sh validate
```

## Configuration

### Rebuilding Container Dependency Locks

The production Dockerfiles install dependency exports generated from `uv.lock`
with uv 0.11.33. Regenerate both files whenever the lock changes, then run the
supply-chain tests before committing them:

```bash
uv export --locked --only-group release --prune cyclonedx-bom --prune twine --no-emit-project --no-header --no-annotate --output-file deploy/build-requirements.lock
uv export --locked --no-dev --extra api --no-emit-project --no-header --no-annotate --output-file deploy/runtime-requirements.lock
uv run --no-sync pytest tests/test_supply_chain_pins.py
```

CI builds and smoke-tests both `deploy/Dockerfile` and
`openclaw/Dockerfile.primr`. The exported files intentionally omit generated
headers so the byte-for-byte lock check is stable under the pinned uv release.

### Provider Secret Wiring

The Azure Bicep deployment maps xAI, Gemini, and OpenAI secrets into job
runners. The current AWS task definition and GCP job manifest map only
`OPENAI_API_KEY`. OpenAI-only full-mode estimates are planning-only in the
current runtime and report `execution_ready: false`; a provider-backed full run
still requires xAI or Gemini. Treat AWS and GCP as reference scaffolding for
full mode until their runner manifests map `XAI_API_KEY` and `GEMINI_API_KEY`.
Do not assume that creating a secret makes it available inside a container.

Regardless of deployment target, run the exact job shape through dry-run and
approval before submission. Direct OpenAI and xAI text calls use Responses
with provider storage disabled. Gemini Premium uses stored background
Interactions and may create File Search stores; those resources follow the
cleanup and retention behavior documented in [Internals](INTERNALS.md#file-search-store).

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PRIMR_DEPLOYMENT` | Deployment name (dev/staging/prod) | `dev` |
| `PRIMR_REGION` | Cloud region | Provider default |
| `PRIMR_PREFIX` | Resource name prefix | `primr` |

### Deployment Names

Deployment names create isolated environments:
- `dev` - Development testing
- `staging` - Pre-production validation
- `prod` - Production workloads

Each deployment gets separate:
- Job queue
- Job state table
- Artifact bucket prefix
- Secrets namespace

## API Reference

### Submit Job

```bash
curl -X POST https://api.example.com/submit \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "company_name": "Acme Corp",
    "company_url": "https://acme.example",
    "mode": "full",
    "idempotency_key": "unique-request-id",
    "approve": true
  }'
```

Response:
```json
{
  "job_id": "abc123def456",
  "status": "QUEUED",
  "estimate": {"cost_usd": 2.50, "duration_minutes": 15},
  "is_existing": false
}
```

### Check Status

```bash
curl https://api.example.com/status/abc123def456 \
  -H "Authorization: Bearer $API_KEY"
```

### Get Results

```bash
curl https://api.example.com/results/abc123def456 \
  -H "Authorization: Bearer $API_KEY"
```

Returns manifest and presigned URLs for artifacts.

### Cancel Job

```bash
curl -X POST https://api.example.com/cancel/abc123def456 \
  -H "Authorization: Bearer $API_KEY"
```

## Cost Estimation

### AWS (Typical Usage)

| Component | Cost/Month (100 jobs) |
|-----------|----------------------|
| Fargate (2 vCPU, 4GB, 15min avg) | ~$15 |
| S3 (10GB artifacts) | ~$0.25 |
| DynamoDB (on-demand) | ~$1 |
| SQS | ~$0.01 |
| **Total** | **~$16** |

### Cost Optimization Tips

1. Use Fargate Spot for non-urgent jobs (up to 70% savings)
2. Set S3 lifecycle policies for artifact cleanup
3. Use DynamoDB TTL for automatic job record expiry
4. Right-size container resources based on job mode

## Security

### Secrets Management

LLM API keys are stored in cloud secret managers:
- AWS: Secrets Manager
- Azure: Key Vault
- GCP: Secret Manager

**Important**: Only the job runner needs LLM keys. The control plane requires NO LLM keys.

### Network Security

Recommended VPC configuration:
- Control plane in public subnet with WAF
- Job runners in private subnet
- NAT gateway for outbound internet access
- VPC endpoints for AWS services

### SSRF Protection

The runner includes comprehensive SSRF protection:
- Blocks private IP ranges (RFC1918, link-local, loopback)
- Blocks cloud metadata endpoints (169.254.169.254)
- Validates all DNS resolutions
- Re-validates on HTTP redirects

## Troubleshooting

### Common Issues

**Job stuck in QUEUED**
- Check queue visibility timeout
- Verify Step Functions/orchestrator is running
- Check CloudWatch/logs for errors

**Job fails immediately**
- Check secrets are set correctly
- Verify container image exists in registry
- Check task role permissions

**No manifest after job completes**
- Check S3/storage permissions
- Look for runner logs in CloudWatch
- Verify artifact store URL is correct

### Log Access

**AWS**
```bash
# Tail runner logs
aws logs tail /ecs/primr-runner --follow

# Search for specific job
aws logs filter-log-events \
  --log-group-name /ecs/primr-runner \
  --filter-pattern '{ $.job_id = "abc123" }'

# View control plane logs
aws logs tail /aws/lambda/primr-control-plane --follow
```

**Azure**
```bash
# View runner logs
az containerapp logs show -n primr-runner -g primr-rg

# Query Log Analytics
az monitor log-analytics query \
  --workspace primr-workspace \
  --analytics-query "ContainerAppConsoleLogs | where ContainerName == 'runner'"
```

**GCP**
```bash
# View runner logs
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=primr-runner"

# Filter by job ID
gcloud logging read 'jsonPayload.job_id="abc123"'

# View control plane logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=primr-control-plane"
```

### Metrics Access

The control plane exposes metrics at `/metrics` (JSON) and `/metrics/prometheus` (Prometheus format).

**AWS CloudWatch Metrics**
- Custom metrics are published to the `Primr` namespace
- View in CloudWatch console or query via CLI

**Azure Monitor**
- Metrics available in Azure Monitor
- Create dashboards in Azure Portal

**GCP Cloud Monitoring**
- Metrics available in Cloud Monitoring
- Create dashboards in GCP Console

## Lifecycle Management

### Job Record TTL

Job records automatically expire after 30 days. Adjust in task definition:
```python
ttl=int(time.time()) + 30 * 24 * 3600  # 30 days
```

### Artifact Retention

Configure S3 lifecycle policy for artifact cleanup:
```json
{
  "Rules": [{
    "ID": "cleanup-old-artifacts",
    "Status": "Enabled",
    "Filter": {"Prefix": ""},
    "Expiration": {"Days": 90}
  }]
}
```

### Infrastructure Teardown

```bash
# AWS
./deploy/aws/deploy.sh -d prod destroy

# Azure
./deploy/azure/deploy.sh -d prod destroy

# GCP
./deploy/gcp/deploy.sh -d prod destroy
```

## Provider Comparison

| Feature | AWS | Azure | GCP |
|---------|-----|-------|-----|
| Control Plane | Lambda | Container Apps | Cloud Run |
| Job Queue | SQS FIFO | Service Bus | Pub/Sub |
| Job Runner | Fargate | Container Apps Jobs | Cloud Run Jobs |
| Artifacts | S3 | Blob Storage | GCS |
| Job State | DynamoDB | Cosmos DB | Firestore |
| Secrets | Secrets Manager | Key Vault | Secret Manager |
| Max Timeout | 120 min | 120 min | 120 min |
| Scale to Zero | Yes | Control-plane API only; MCP: No | Yes |

Azure has two explicit container surfaces. `deploy/azure/container-app.yaml`
describes the Cosmos-backed `primr-api` control plane and may scale to zero.
The Bicep quickstart runs `primr-mcp`, whose governed controller state is
process-local and therefore requires exactly one persistent replica.

## Production Hardening

Each provider deployment includes production-grade features beyond the basic architecture.

### AWS Production Features

**Resource Lifecycle:**
- ECR lifecycle policy keeps last 10 images, auto-deletes older ones
- S3 lifecycle rules transition artifacts to Infrequent Access after 30 days
- S3 versioning with non-current version cleanup after 7 days

**Reliability:**
- SQS dead-letter queue captures failed messages after 3 retries
- Step Functions role scoped to specific resources (least-privilege IAM)
- DynamoDB on-demand capacity with auto-scaling

**Observability:**
- X-Ray tracing enabled on reconciler Lambda
- CloudWatch alarms for:
  - Lambda error rate > 5%
  - DynamoDB throttled requests
  - Dead-letter queue message count > 0
  - Queue message age > 15 minutes

### Azure Production Features

**Resource Scaling:**
- Cosmos DB autoscale: 400-4000 RU/s (adjusts to load automatically)
- The MCP Container App runs exactly one persistent controller replica. Do not scale it horizontally or to zero until controller state has a shared transactional backend.
- Research execution remains isolated in separately created Container Apps Jobs.

**Security:**
- Managed identity for all service-to-service authentication
- RBAC roles: Cosmos DB Data Contributor, Storage Blob Data Contributor, Key Vault Secrets User
- No connection strings in environment variables

**Observability:**
- Application Insights for distributed tracing
- Log Analytics workspace for centralized logging
- Custom metrics for job duration and success rates

### GCP Production Features

**Security:**
- Dedicated service account for Cloud Function (not default App Engine SA)
- Least-privilege IAM roles:
  - `roles/datastore.user` for Firestore access
  - `roles/storage.objectViewer` for GCS artifact retrieval
  - `roles/run.invoker` for Cloud Run invocation
- Cloud Scheduler uses dedicated service account with OIDC authentication

**Performance:**
- Firestore composite indexes for efficient reconciler queries:
  - `(status, updated_at)` for timeout detection
  - `(status, deployment)` for environment-scoped queries

**Observability:**
- Cloud Trace integration
- Cloud Logging with structured JSON
- Cloud Monitoring dashboards
