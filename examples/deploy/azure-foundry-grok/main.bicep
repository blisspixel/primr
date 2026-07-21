// Deploy an xAI Grok model on Azure AI Foundry (AI Services account + deployment),
// exposing the OpenAI-compatible /openai/v1/ endpoint that primr's AzureFoundryProvider
// targets. Verified live against the catalog: format 'xAI', version '1', SKU GlobalStandard.
//
// Deploy / verify / clean up: see README.md in this directory.

@description('Azure AI Services (Foundry) account name; must be globally unique.')
param accountName string = 'primr-grok-${uniqueString(resourceGroup().id)}'

@description('Region with xAI Grok serverless availability (e.g. eastus2).')
param location string = resourceGroup().location

@description('Grok model to deploy. Query live options with: az cognitiveservices model list --location <region> --query "[?model.format==\'xAI\'].model.name". As of 2026-07 grok-4.3 is current; grok-3-mini is deprecated.')
param modelName string = 'grok-4.3'

@description('Model version from the catalog.')
param modelVersion string = '1'

@description('Per-minute token quota increment (each unit ~ provisioned throughput).')
param capacity int = 1

// Unified AI Services account — hosts the OpenAI-compatible inference router.
resource aiAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: accountName
  location: location
  sku: {
    name: 'S0'
  }
  kind: 'AIServices'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: accountName
    publicNetworkAccess: 'Enabled'
  }
}

// Grok model deployment (Foundry "sold by Azure" direct model).
resource grokDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: aiAccount
  name: modelName
  sku: {
    name: 'GlobalStandard'
    capacity: capacity
  }
  properties: {
    model: {
      format: 'xAI'
      name: modelName
      version: modelVersion
    }
  }
}

@description('OpenAI-compatible base URL for primr AZURE_OPENAI_BASE_URL.')
output openaiBaseUrl string = '${aiAccount.properties.endpoint}openai/v1/'

@description('Deployment name to pass as the OpenAI `model` field.')
output deploymentName string = grokDeployment.name

@description('Account name (needed to purge the soft-deleted account on cleanup).')
output accountName string = aiAccount.name
