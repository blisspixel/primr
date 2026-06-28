# Copilot Studio - Primr MCP Integration

Create a Copilot Studio agent that uses Primr's research tools via a Power Platform custom connector. This enables conversational company research directly in Microsoft 365 Copilot, Teams, and other Power Platform surfaces.

> **Primr is CLI-first, local-first.** This guide is for teams that have deployed Primr to Azure Container Apps and want to connect it to Copilot Studio. If you haven't deployed yet, start with the [Azure Quickstart](AZURE_QUICKSTART.md).

## Prerequisites

- Primr deployed to Azure Container Apps ([Azure Quickstart](AZURE_QUICKSTART.md))
- Access to [Copilot Studio](https://copilotstudio.microsoft.com)
- Power Platform environment with custom connector permissions
- The OpenAPI spec at `deploy/azure/openapi.yaml`

## How It Works

Copilot Studio connects to Primr via a Power Platform custom connector created from the OpenAPI spec. The spec includes the `x-ms-agentic-protocol: mcp-streamable-1.0` extension, which tells Copilot Studio that this endpoint speaks MCP - enabling automatic tool discovery.

```
Copilot Studio Agent → Custom Connector → https://{primr-fqdn}/mcp → Primr tools
```

## Step 1: Prepare the OpenAPI Spec

1. Copy `deploy/azure/openapi.yaml` to your local machine
2. Edit the server URL to match your deployment:

```yaml
servers:
  - url: https://{primr-fqdn}
```

Replace `{primr-fqdn}` with your Container App's FQDN (e.g., `primr-myteam-api.eastus.azurecontainerapps.io`).

3. If using Entra ID auth (organization tier), update the security scheme:

```yaml
securitySchemes:
  entraId:
    type: oauth2
    flows:
      authorizationCode:
        authorizationUrl: https://login.microsoftonline.com/{tenant-id}/oauth2/v2.0/authorize
        tokenUrl: https://login.microsoftonline.com/{tenant-id}/oauth2/v2.0/token
        scopes:
          "api://{app-id}/.default": Access Primr MCP Server
```

Replace `{tenant-id}` with your Azure AD tenant ID and `{app-id}` with your Container App's Entra ID application ID.

## Step 2: Create the Power Platform Custom Connector

1. Go to [Power Platform Admin Center](https://admin.powerplatform.microsoft.com) or [Power Automate](https://make.powerautomate.com)
2. Navigate to **Custom connectors** → **+ New custom connector** → **Import an OpenAPI file**
3. Upload your edited `openapi.yaml`
4. On the **General** tab:
   - **Connector name**: `Primr MCP`
   - **Host**: `{primr-fqdn}`
   - **Base URL**: `/`
5. On the **Security** tab, configure authentication:

### API Key Auth (Team Tier)

- **Authentication type**: API Key
- **Parameter label**: Authorization
- **Parameter name**: Authorization
- **Parameter location**: Header
- **Default value**: `Bearer {your-api-key}`

### OAuth 2.0 (Organization Tier)

- **Authentication type**: OAuth 2.0
- **Identity provider**: Azure Active Directory
- **Client ID**: `{app-id}`
- **Client secret**: (from your Entra ID app registration)
- **Authorization URL**: `https://login.microsoftonline.com/{tenant-id}/oauth2/v2.0/authorize`
- **Token URL**: `https://login.microsoftonline.com/{tenant-id}/oauth2/v2.0/token`
- **Scope**: `api://{app-id}/.default`

6. On the **Definition** tab, verify the `mcpRequest` action is listed
7. Click **Create connector**
8. On the **Test** tab, create a connection and test with:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list",
  "params": {}
}
```

You should see the list of Primr tools in the response.

## Step 3: Create a Copilot Studio Agent

1. Go to [Copilot Studio](https://copilotstudio.microsoft.com)
2. Click **+ Create** → **New agent**
3. Name it (e.g., "Company Research Assistant")
4. In the agent configuration, go to **Actions** → **+ Add an action**
5. Search for your `Primr MCP` custom connector
6. Select the `mcpRequest` action
7. Copilot Studio will detect the `x-ms-agentic-protocol: mcp-streamable-1.0` extension and enable MCP tool discovery automatically

## Step 4: Configure Agent Instructions

In the agent's **Instructions** field, add guidance for research workflows:

```
You are a company research assistant powered by Primr. You help users research companies
by gathering public information, analyzing it, and producing strategic analysis.

When a user asks you to research a company:
1. Ask for the company name and website URL if not provided
2. Call estimate_run to show the expected cost and duration
3. Wait for the user to confirm before proceeding
4. Call research_company to submit the research job
5. Use check_jobs to monitor progress - research takes 35-50 minutes
6. When complete, use MCP `resources/read` for
   `primr://output/artifacts/by_job/{job_id}` if your connector exposes
   resource reads. If QA artifacts are attached, read
   `primr://output/qa_summary/by_job/{job_id}` for compact QA metadata. Request
   report content only when the user needs a summary or downstream action
7. Share the key findings with the user

Important:
- Always estimate costs before submitting a job (~$0.75 for standard research)
- Research jobs are asynchronous and take 35-50 minutes to complete
- Use show_usage to check the user's remaining budget
- Use doctor to diagnose any connectivity issues

Available research modes:
- scrape: Website data extraction only (~5-10 min, ~$0.10)
- deep: External research only (~10-15 min, ~$2.50)
- full: Complete analysis (~35-50 min, ~$0.75)
```

## Step 5: Test with Sample Queries

In the Copilot Studio test panel, try these queries:

### Cost estimation
```
How much would it cost to research ExampleCo at https://example.co?
```

Expected: The agent calls `estimate_run` and returns cost/duration.

### Submit research
```
Research ExampleCo at https://example.co for me.
```

Expected: The agent estimates, confirms, submits, and monitors the job.

### Check status
```
What's the status of my research job?
```

Expected: The agent calls `check_jobs` with the job ID.

### Budget check
```
How much research budget do I have left?
```

Expected: The agent calls `show_usage` and returns the spending summary.

### Diagnostics
```
Is the research service healthy?
```

Expected: The agent calls `doctor` and reports system status.

## Troubleshooting

| Issue | Solution |
|---|---|
| Connector creation fails | Verify the OpenAPI spec is valid: use the [Swagger Editor](https://editor.swagger.io) to validate |
| MCP tools not discovered | Ensure `x-ms-agentic-protocol: mcp-streamable-1.0` is in the spec's operation extension |
| Authentication errors | For API key: verify the key is valid. For OAuth: check tenant ID, app ID, and client secret |
| Agent can't invoke tools | Test the connector directly in Power Automate first to isolate the issue |
| Timeout on tool calls | Research jobs are async (35-50 min). The agent should use `check_jobs` to poll, not wait for a synchronous response |

## Reference

- OpenAPI spec: [`deploy/azure/openapi.yaml`](https://github.com/blisspixel/primr/blob/main/deploy/azure/openapi.yaml)
- Bicep templates: [`deploy/azure/bicep/`](https://github.com/blisspixel/primr/tree/main/deploy/azure/bicep)
- Deploy script: [`deploy/azure/deploy.sh`](https://github.com/blisspixel/primr/blob/main/deploy/azure/deploy.sh)
- [Azure Quickstart](AZURE_QUICKSTART.md) - Deploy Primr to Azure
- [Foundry Agent Guide](FOUNDRY_AGENT_GUIDE.md) - Alternative: connect via Foundry Agent Service
- [Copilot Cowork Guide](COPILOT_COWORK_GUIDE.md) - Publish this agent to M365 Agent Store
