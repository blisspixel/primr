# Copilot Cowork — Publish Primr to M365 Agent Store

Publish your Copilot Studio research agent to the Microsoft 365 Agent Store so that Copilot Cowork (and other M365 Copilot users) can discover and invoke it. Once published, users can say things like "Research ExampleCo for me" in Copilot and it routes to your Primr agent.

> **Primr is CLI-first, local-first.** Copilot Cowork publishing is the furthest end of the scaling spectrum — it makes Primr available to your entire organization through M365 Copilot. Most users don't need this. Start with the [Azure Quickstart](AZURE_QUICKSTART.md) if you haven't deployed yet.

## Prerequisites

- Primr deployed to Azure Container Apps at **organization tier** ([Azure Quickstart](AZURE_QUICKSTART.md))
- A Copilot Studio agent configured with the Primr MCP connector ([Copilot Studio Guide](COPILOT_STUDIO_GUIDE.md))
- Entra ID authentication enabled (required for M365 Agent Store)
- M365 admin permissions to approve agent publishing

## How It Works

The chain is: **Copilot Cowork → Copilot Studio Agent → MCP Server (Primr)**

Copilot Cowork is Microsoft 365 Copilot's agentic execution layer. It discovers agents from the M365 Agent Store and invokes them to carry out multi-step tasks. By publishing your Copilot Studio agent to the store, any M365 Copilot user in your organization can trigger Primr research through natural language.

## Step 1: Prepare the Agent for Publishing

1. Open your Primr agent in [Copilot Studio](https://copilotstudio.microsoft.com)
2. Go to **Settings** → **Details**
3. Fill in the required metadata:
   - **Display name**: `Company Research (Primr)`
   - **Short description**: `Research any company using AI-powered analysis. Produces strategic overviews, competitive analysis, and consultant-grade insights.`
   - **Long description**: `Submit a company name and website URL to get deep strategic analysis including competitive positioning, technology stack, strategic initiatives, financial profile, and discovery questions. Research takes 35-50 minutes and costs ~$0.75 in API fees. Results include 23 structured sections with inline confidence levels.`
   - **Icon**: Upload a recognizable icon for the agent
4. Go to **Settings** → **Security**
   - Ensure **Authentication** is set to **Microsoft Entra ID**
   - This is required for M365 Agent Store publishing

## Step 2: Configure Agent Capabilities for Cowork

Copilot Cowork needs to understand what your agent can do. In the agent's **Instructions**, ensure the capabilities are clearly stated:

```
This agent researches companies using Primr. It can:
- Estimate research costs before running
- Submit company research jobs (scrape, deep, or full analysis)
- Monitor job progress and report status
- Retrieve completed research results
- Check remaining budget

Trigger phrases: "research [company]", "analyze [company]", "look up [company]",
"what do you know about [company]", "company research for [company]"
```

## Step 3: Test in Copilot Studio

Before publishing, thoroughly test the agent:

1. In the Copilot Studio test panel, verify:
   - Tool discovery works (agent lists available research tools)
   - Cost estimation works (`estimate_run`)
   - Job submission works (`research_company`)
   - Status checking works (`check_jobs`)
   - Budget checking works (`show_usage`)
2. Test with multiple company URLs to ensure reliability
3. Verify error handling (invalid URLs, budget exceeded, service unavailable)

## Step 4: Publish to M365 Agent Store

1. In Copilot Studio, go to **Publish** → **Publish to Microsoft 365**
2. Select **Microsoft 365 Agent Store** as the target
3. Review the submission details:
   - Agent metadata (name, description, icon)
   - Authentication configuration (Entra ID)
   - Permissions required
4. Click **Submit for approval**

### Admin Approval

An M365 admin must approve the agent before it appears in the store:

1. Go to [Microsoft 365 Admin Center](https://admin.microsoft.com)
2. Navigate to **Settings** → **Integrated apps** → **Agent Store**
3. Find the pending `Company Research (Primr)` submission
4. Review the agent's permissions and capabilities
5. **Approve** or **Reject** the submission
6. Optionally restrict availability to specific user groups

## Step 5: Verify Cowork Reachability

Once approved, verify the agent is discoverable:

1. Open Microsoft 365 Copilot (in Teams, Edge, or microsoft365.com)
2. In the Copilot chat, try:
   ```
   Research ExampleCo at https://example.co for me
   ```
3. Copilot should route the request to your Primr agent
4. The agent should estimate costs, confirm, and submit the research job

### Alternative trigger patterns

Users can invoke the agent in various ways:

```
@Company Research analyze Northwind Corp at https://northwind.com
Research ExampleCo for me
Can you look up what ExampleCo does? Their website is https://example.co
I need a strategic analysis of ExampleCo
```

## Managing the Published Agent

### Update the agent

1. Make changes in Copilot Studio (instructions, tools, metadata)
2. Re-publish: **Publish** → **Publish to Microsoft 365**
3. Updates may require re-approval depending on the changes

### Monitor usage

- Check agent invocation metrics in Copilot Studio analytics
- Check Primr-level usage via the `show_usage` tool or `/usage/{api-key-hash}` endpoint
- Monitor Application Insights for error rates and latency

### Revoke access

1. In M365 Admin Center, go to **Integrated apps** → **Agent Store**
2. Find the Primr agent and select **Remove** or **Disable**

## Troubleshooting

| Issue | Solution |
|---|---|
| Agent not visible in Copilot | Check admin approval status in M365 Admin Center |
| "Agent not available" error | Verify the Container App is running and healthy (`/healthz` endpoint) |
| Authentication failures | Ensure Entra ID is configured on both the Copilot Studio agent and the Container App |
| Copilot doesn't route to agent | Refine the agent's trigger phrases and instructions |
| Publishing rejected | Review the rejection reason in M365 Admin Center; common issues: missing metadata, insufficient description, or security concerns |

## Reference

- [Azure Quickstart](AZURE_QUICKSTART.md) — Deploy Primr to Azure
- [Copilot Studio Guide](COPILOT_STUDIO_GUIDE.md) — Create the Copilot Studio agent (prerequisite)
- [Foundry Agent Guide](FOUNDRY_AGENT_GUIDE.md) — Alternative: connect via Foundry Agent Service
- OpenAPI spec: [`deploy/azure/openapi.yaml`](../deploy/azure/openapi.yaml)
- Bicep templates: [`deploy/azure/bicep/`](../deploy/azure/bicep/)
