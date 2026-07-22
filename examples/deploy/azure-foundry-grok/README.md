# Deploy Grok on Azure AI Foundry (for primr's Foundry provider)

This Bicep deploys an Azure AI Foundry (AI Services) account and an **xAI Grok**
model, exposing the OpenAI-compatible `/openai/v1/` endpoint that primr's
`AzureFoundryProvider` consumes. Verified end-to-end on 2026-07-21.

## Prerequisites

- Azure CLI (`az`) logged in to a subscription: `az login`
- Bicep (bundled with recent `az`): `az bicep version`
- A region with xAI Grok serverless availability (e.g. `eastus2`).

## 1. Pick a current model (verify against the live catalog)

Model ids drift and some go deprecated — **query the catalog, don't guess**:

```bash
az cognitiveservices model list --location eastus2 \
  --query "[?model.format=='xAI'].model.name" --output tsv | sort -u
```

As of 2026-07, `grok-4.3` is current; `grok-3-mini` is deprecated for new
deployments (a deploy with it fails `ServiceModelDeprecated`).

## 2. Deploy

```bash
az group create --name primr-grok-rg --location eastus2

az deployment group create \
  --resource-group primr-grok-rg \
  --name grok-iac \
  --template-file main.bicep \
  --parameters modelName=grok-4.3 \
  --query "properties.outputs"
```

The outputs give `openaiBaseUrl`, `deploymentName`, and `accountName`.

## 3. Point primr at it

```bash
ACCT=<accountName-from-output>
export AZURE_OPENAI_API_KEY=$(az cognitiveservices account keys list \
  --resource-group primr-grok-rg --name "$ACCT" --query key1 -o tsv)
export AZURE_OPENAI_BASE_URL="https://$ACCT.cognitiveservices.azure.com/openai/v1/"

primr keys test foundry     # free, auth-only: should report "authenticated"
```

This unified AIServices account uses the `*.cognitiveservices.azure.com` host; a
dedicated Azure OpenAI resource would use `*.openai.azure.com` instead.

`primr keys test foundry` validates the deployment credentials. To route a
pipeline stage through this Foundry deployment, declare the deployment name and
its pricing (a Foundry model id is your deployment name, so primr prices it from
what you declare rather than guessing):

```bash
AZURE_OPENAI_DEPLOYMENT=<your-deployment-name>   # e.g. the Grok deployment
AZURE_FOUNDRY_PRICE_AS=grok-4.3                  # price/spec as this registered model
# ...or set explicit rates instead of PRICE_AS:
# AZURE_FOUNDRY_INPUT_PRICE=1.25
# AZURE_FOUNDRY_OUTPUT_PRICE=2.50

AI_REASONING_MODEL=<your-deployment-name>        # select it for the reasoning stage
```

primr then routes that stage to the Foundry endpoint (using the deployment name)
and prices it from your declaration, so the mandatory cost estimate is accurate.
Note that a bare `AI_REASONING_MODEL=grok-4.3` still routes to first-party xAI
(`api.x.ai`) — use your **deployment name**, not the underlying model id, to hit
Foundry. **Main-process only:** Foundry routing is refused inside a supervised
MCP worker, which does not carry Azure credentials.

## 4. Clean up (avoid ongoing cost)

`S0` AI Services accounts have no standing charge (pay-per-token), but delete
when done and **purge the soft-deleted account** so the name/quota release:

```bash
az group delete --name primr-grok-rg --yes
az cognitiveservices account purge \
  --name "$ACCT" --location eastus2 --resource-group primr-grok-rg
# verify: az cognitiveservices account list-deleted --query "[?name=='$ACCT']"
```

## Note: Azure lags the first-party API

The Foundry catalog trails xAI's own API (e.g. `grok-4.5` shipped first-party
2026-07-16 but the catalog still tops out at `grok-4.3`). Use deployment
surfaces for cost/consolidation/your-existing-cloud; use the first-party xAI API
for the newest models.
