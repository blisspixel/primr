# Azure Quickstart

Deploy Primr to Azure as a shared MCP server for your team or organization. This guide gets you from zero to a running deployment in under 10 minutes.

> **Primr is CLI-first, local-first.** The cloud deployment is an optional scaling path for teams that need shared access, agent platform integration, or always-on availability. If you're a solo user, `primr` on your laptop is the primary experience - you don't need any of this.

## Prerequisites

- Azure CLI (`az`) installed and authenticated
- Docker installed and running
- `jq` installed
- An Azure subscription with Contributor access

```bash
# Verify prerequisites
az version
docker --version
jq --version
```

## Part A: Team-Tier Deployment (< 10 minutes)

The team tier gives you a shared MCP server on Azure Container Apps with API key auth and one persistent controller replica. The controller does not scale to zero because its governed job, approval, rate-limit, and audit state is process-local. Check the Azure pricing calculator for the selected region before deployment.

### 1. Clone and configure

```bash
git clone https://github.com/blisspixel/primr.git
cd primr

# Set your deployment name and region
export PRIMR_DEPLOYMENT=myteam
export PRIMR_REGION=eastus
```

### 2. Deploy with the script

```bash
# Team tier is the default
./deploy/azure/deploy.sh -d $PRIMR_DEPLOYMENT deploy
```

This provisions: Resource Group, ACR, Container Apps environment, Container App (MCP + control plane), Container App Job (runner), Cosmos DB (serverless), Blob Storage, and Key Vault.

### 3. Or deploy with Bicep (declarative IaC)

```bash
# Create resource group first
az group create --name primr-${PRIMR_DEPLOYMENT}-rg --location $PRIMR_REGION

# Deploy with Bicep templates
az deployment group create \
  --resource-group primr-${PRIMR_DEPLOYMENT}-rg \
  --template-file deploy/azure/bicep/main.bicep \
  --parameters \
    deploymentName=$PRIMR_DEPLOYMENT \
    location=$PRIMR_REGION \
    tier=team \
    acrLoginServer=primr${PRIMR_DEPLOYMENT}acr.azurecr.io \
    imageName=primr-runner \
    contactEmails='["you@example.com"]'
```

### 4. Set your API keys

```bash
# Store LLM keys in Key Vault
./deploy/azure/deploy.sh -d $PRIMR_DEPLOYMENT secrets set XAI-API-KEY
./deploy/azure/deploy.sh -d $PRIMR_DEPLOYMENT secrets set GEMINI-API-KEY
```

### 5. Validate the deployment

```bash
./deploy/azure/deploy.sh -d $PRIMR_DEPLOYMENT validate
```

### 6. Connect from any MCP client

Your MCP server is now live at `https://{primr-fqdn}/mcp`. Connect from Claude Desktop, Cursor, or any MCP-compatible client:

```json
{
  "mcpServers": {
    "primr": {
      "url": "https://{primr-fqdn}/mcp",
      "headers": {
        "Authorization": "Bearer {your-api-key}"
      }
    }
  }
}
```

The server exposes the same tools as the local MCP server: `estimate_run`, `research_company`, `check_jobs`, `wait_for_status_change`, `run_qa`, `doctor`, `show_usage`.

## Part B: Create a Copilot Studio Connector

Once your team-tier deployment is running, you can connect it to Copilot Studio using the included OpenAPI spec.

1. Open the OpenAPI spec at `deploy/azure/openapi.yaml`
2. Replace `{primr-fqdn}` with your Container App's FQDN
3. Follow the step-by-step guide: [Copilot Studio Guide](COPILOT_STUDIO_GUIDE.md)

The OpenAPI spec includes the `x-ms-agentic-protocol: mcp-streamable-1.0` extension, which enables automatic MCP tool discovery in Copilot Studio.

For Foundry Agent Service integration, see [Foundry Agent Guide](FOUNDRY_AGENT_GUIDE.md).

## Part C: Upgrade to Organization Tier

When your team grows or you need Entra ID auth, per-user budget tracking, and full observability - upgrade to the organization tier.

### What changes

| Capability | Team | Organization |
|---|---|---|
| Authentication | API keys only | API keys + Entra ID |
| Budget tracking | - | Per-user/team limits |
| Observability | - | Application Insights + alerts |
| Job queue | Direct trigger | Service Bus + dead-letter |
| Reconciler | - | Azure Function (timer) |
| Copilot Cowork | - | M365 Agent Store publishing |
| Pricing | Check selected region and configuration | Check selected region and configuration |

### Deploy organization tier

```bash
# Script-based
./deploy/azure/deploy.sh --tier organization -d $PRIMR_DEPLOYMENT deploy

# Or Bicep-based
az deployment group create \
  --resource-group primr-${PRIMR_DEPLOYMENT}-rg \
  --template-file deploy/azure/bicep/main.bicep \
  --parameters \
    deploymentName=$PRIMR_DEPLOYMENT \
    tier=organization \
    acrLoginServer=primr${PRIMR_DEPLOYMENT}acr.azurecr.io \
    imageName=primr-runner \
    contactEmails='["platform-team@example.com"]'
```

This adds: Service Bus (Standard, with dead-letter), Application Insights (5 GB/day cap), reconciler Azure Function, Budget Tracker Cosmos DB container, Entra ID app registration, and Azure Budget alerts at $200/month.

### Configure Entra ID authentication

After organization-tier deployment, configure your Container App for Entra ID:

```bash
# The deploy script registers an Entra ID app automatically
# Clients authenticate with JWT tokens:
curl -X POST https://{primr-fqdn}/mcp \
  -H "Authorization: Bearer {entra-jwt-token}" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

For publishing to the M365 Agent Store (Copilot Cowork), see [Copilot Cowork Guide](COPILOT_COWORK_GUIDE.md).

## Part D: Configure Budget Limits

Budget controls work at two levels: Azure-level spending alerts and Primr-level per-user limits.

### Azure Budget alerts (both tiers)

The Bicep templates create Azure Budget resources with alerts at 50%, 80%, and 100% of your monthly threshold.

```bash
# Set a custom budget during deployment
az deployment group create \
  --resource-group primr-${PRIMR_DEPLOYMENT}-rg \
  --template-file deploy/azure/bicep/main.bicep \
  --parameters budgetAmount=75 \
  # ... other params
```

Defaults: $50/month (team), $200/month (organization).

### Per-user spending limits (organization tier)

Configure per-API-key limits via environment variables or Key Vault secrets:

```bash
# Per-job maximum (default: $1)
./deploy/azure/deploy.sh -d $PRIMR_DEPLOYMENT secrets set PRIMR-MAX-JOB-COST-USD 2.00

# Daily maximum per user (default: $10)
./deploy/azure/deploy.sh -d $PRIMR_DEPLOYMENT secrets set PRIMR-MAX-DAILY-COST-USD 25.00

# Monthly maximum per user (default: $100)
./deploy/azure/deploy.sh -d $PRIMR_DEPLOYMENT secrets set PRIMR-MAX-MONTHLY-COST-USD 500.00
```

Users can check their remaining budget via the `show_usage` MCP tool or the REST API:

```bash
curl https://{primr-fqdn}/usage/{api-key-hash} \
  -H "Authorization: Bearer {api-key}"
```

## Tear Down

```bash
# Destroy all resources (prompts for confirmation)
./deploy/azure/deploy.sh -d $PRIMR_DEPLOYMENT destroy

# Skip confirmation
./deploy/azure/deploy.sh -d $PRIMR_DEPLOYMENT destroy --force
```

## Related Guides

- [Foundry Agent Service Guide](FOUNDRY_AGENT_GUIDE.md) - Connect Primr as a tool in Foundry prompt agents
- [Copilot Studio Guide](COPILOT_STUDIO_GUIDE.md) - Create a Power Platform connector for Copilot Studio
- [Copilot Cowork Guide](COPILOT_COWORK_GUIDE.md) - Publish to M365 Agent Store for Copilot Cowork
- [Cloud Deployment Guide](CLOUD_DEPLOYMENT.md) - General cloud deployment reference (AWS, Azure, GCP)
- [API Reference](API.md) - MCP server and control plane API documentation
