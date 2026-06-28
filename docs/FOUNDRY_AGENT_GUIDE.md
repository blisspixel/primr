# Foundry Agent Service - Primr MCP Integration

Connect Primr's MCP server as a tool source in Microsoft Foundry Agent Service. This enables any Foundry prompt agent, workflow agent, or hosted agent to discover and invoke Primr's research tools via standard MCP tool discovery.

> **Primr is CLI-first, local-first.** This guide is for teams that have deployed Primr to Azure Container Apps and want to connect it to Foundry agents. If you haven't deployed yet, start with the [Azure Quickstart](AZURE_QUICKSTART.md).

## Prerequisites

- Primr deployed to Azure Container Apps ([Azure Quickstart](AZURE_QUICKSTART.md))
- Access to [Azure AI Foundry](https://ai.azure.com)
- A Foundry project with agent capabilities enabled

## How It Works

Foundry Agent Service natively supports remote MCP server connections. Primr's MCP server on Container Apps exposes the `/mcp` endpoint using MCP Streamable HTTP transport. Foundry connects to it as a tool source, discovers available tools via `tools/list`, and invokes them via `tools/call`.

```
Foundry Agent → MCP tool connection → https://{primr-fqdn}/mcp → Primr tools
```

## Step 1: Create a Foundry Project Connection

The project connection stores the MCP endpoint URL and authentication credentials.

### Option A: API Key Authentication (Team Tier)

1. Open your Foundry project in [Azure AI Foundry](https://ai.azure.com)
2. Go to **Project settings** → **Connected resources** → **+ New connection**
3. Select **Custom keys** connection type
4. Configure:
   - **Name**: `primr-mcp`
   - **Endpoint**: `https://{primr-fqdn}/mcp`
   - **Authentication type**: API Key
   - **API Key**: Your Primr API key (stored in Key Vault during deployment)

### Option B: Entra ID Authentication (Organization Tier)

For organization-tier deployments with Entra ID enabled:

1. Go to **Project settings** → **Connected resources** → **+ New connection**
2. Select **Custom keys** connection type
3. Configure:
   - **Name**: `primr-mcp`
   - **Endpoint**: `https://{primr-fqdn}/mcp`
   - **Authentication type**: Entra agent identity (or Entra project managed identity)
   - **Audience**: `api://{app-id}` (your Container App's Entra ID application ID)

Foundry supports three Entra auth methods for MCP connections:
- **Key-based**: API key via the project connection (simplest)
- **Entra agent identity**: The agent authenticates as itself
- **Entra project managed identity**: The project's managed identity authenticates on behalf of the agent

## Step 2: Add MCP Tool to a Foundry Prompt Agent

1. In your Foundry project, go to **Agents** → **+ New agent**
2. Select **Prompt agent** as the agent type
3. In the agent configuration, go to **Tools** → **+ Add tool**
4. Select **MCP tool** and choose the `primr-mcp` connection you created
5. Foundry will call `tools/list` on the MCP endpoint and display the discovered tools:
   - `estimate_run` - Get cost estimate before running research
   - `research_company` - Submit a company research job
   - `check_jobs` - Check job status and progress
   - `wait_for_status_change` - Poll until job status changes
   - `run_qa` - Run quality checks on completed research
   - `doctor` - System diagnostics
   - `show_usage` - Check spending and remaining budget
6. Enable the tools you want the agent to use (recommend enabling all)

### Configure Agent Instructions

Add instructions that help the agent understand Primr's async job lifecycle:

```
You have access to Primr company research tools. When a user asks you to research a company:

1. First call estimate_run to show the cost and duration estimate
2. After user confirms, call research_company to submit the job
3. Use check_jobs to monitor progress (jobs take 35-50 minutes)
4. When the job completes, read `resources/list` and `resources/read` for
   `primr://output/artifacts/by_job/{job_id}` if your Foundry MCP surface
   exposes resource reads. If QA artifacts are attached, read
   `primr://output/qa_summary/by_job/{job_id}` for compact QA metadata. Read
   `primr://output/usage_summary/by_job/{job_id}` when the user needs cost,
   timing, approval, or artifact-count metadata. Read
   `primr://output/source_summary/by_job/{job_id}` when the user needs
   citation/source appendix metadata. Read
   `primr://output/trace_summary/by_job/{job_id}` when the user needs scrape
   trace health metadata. Request report content only if the user
   needs a summary or downstream action
5. Share the results with the user

Always estimate before submitting. Research jobs cost real money (~$0.75 for standard mode).
Use show_usage to check remaining budget if the user asks about costs.
```

## Step 3: Test Tool Discovery and Invocation

### Test tool discovery

In the agent's test panel, ask:

```
What research tools do you have available?
```

The agent should list the Primr tools discovered via MCP `tools/list`.

### Test a research workflow

```
Can you estimate the cost of researching ExampleCo at https://example.co?
```

The agent should call `estimate_run` and return the cost estimate.

### Test the full lifecycle

```
Research ExampleCo at https://example.co for me.
```

The agent should:
1. Call `estimate_run` → show estimate
2. Call `research_company` → get job_id
3. Call `check_jobs` periodically → report progress
4. Read `primr://output/artifacts/by_job/{job_id}` when resource reads are
   available
5. Read `primr://output/qa_summary/by_job/{job_id}` when QA artifacts are
   attached and resource reads are available
6. Read `primr://output/usage_summary/by_job/{job_id}` when run cost, timing,
   approval, or artifact-count metadata is needed
7. Read `primr://output/source_summary/by_job/{job_id}` when citation/source
   appendix metadata is needed
8. Read `primr://output/trace_summary/by_job/{job_id}` when scrape trace health
   metadata is needed
9. Return results when the job completes

## Private Endpoints (VNet Integration)

For organization-tier deployments that require private networking:

### 1. Configure Container App with VNet

The Bicep templates support VNet integration. Deploy with a custom VNet:

```bash
az deployment group create \
  --resource-group primr-${PRIMR_DEPLOYMENT}-rg \
  --template-file deploy/azure/bicep/main.bicep \
  --parameters \
    deploymentName=$PRIMR_DEPLOYMENT \
    tier=organization \
    # ... other params
```

### 2. Create a Private Endpoint for the MCP Server

When the Container App is deployed inside a VNet, the `/mcp` endpoint is only accessible from within the VNet or via private endpoints.

### 3. Configure Foundry Project Connection for Private Endpoint

1. Ensure your Foundry project is in the same VNet (or a peered VNet)
2. Create the project connection using the private endpoint URL:
   - **Endpoint**: `https://{primr-private-fqdn}/mcp`
3. Foundry agents will route MCP traffic through the private network

### 4. DNS Resolution

If using private DNS zones, ensure the Foundry project can resolve the Container App's private FQDN. This typically requires:
- A Private DNS Zone linked to the VNet
- An A record pointing to the Container App's private IP

## Troubleshooting

| Issue | Solution |
|---|---|
| Tool discovery returns empty list | Verify the MCP endpoint is reachable: `curl https://{primr-fqdn}/mcp -X POST -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'` |
| 401 Unauthorized | Check API key or Entra ID configuration in the project connection |
| Connection timeout | For private endpoints, verify VNet peering and DNS resolution |
| Tools discovered but invocation fails | Check Container App logs in Application Insights for errors |

## Reference

- OpenAPI spec: [`deploy/azure/openapi.yaml`](https://github.com/blisspixel/primr/blob/main/deploy/azure/openapi.yaml)
- Bicep templates: [`deploy/azure/bicep/`](https://github.com/blisspixel/primr/tree/main/deploy/azure/bicep)
- Deploy script: [`deploy/azure/deploy.sh`](https://github.com/blisspixel/primr/blob/main/deploy/azure/deploy.sh)
- [Azure Quickstart](AZURE_QUICKSTART.md) - Deploy Primr to Azure
- [Copilot Studio Guide](COPILOT_STUDIO_GUIDE.md) - Alternative: connect via Power Platform
