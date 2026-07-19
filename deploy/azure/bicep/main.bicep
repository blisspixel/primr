// =============================================================================
// Primr Azure Deployment - Main Orchestrator
// Declarative IaC that produces the same topology as deploy.sh
// Requirements: 7.1, 7.2, 7.7, 7.8
// =============================================================================

@description('Deployment name for resource tagging')
param deploymentName string

@description('Azure region for all resources')
param location string = 'eastus'

@description('Resource name prefix')
param resourcePrefix string = 'primr'

@description('Deployment tier: team (minimal) or organization (full)')
@allowed(['team', 'organization'])
param tier string = 'team'

@description('MCP controller replicas. Primr currently supports exactly one persistent controller because governed job, approval, rate-limit, and audit state are process-local.')
@minValue(1)
@maxValue(1)
param minReplicas int = 1

@description('MCP controller replicas. Must remain one until the control plane uses shared transactional state.')
@minValue(1)
@maxValue(1)
param maxReplicas int = 1

@description('Monthly Azure budget amount in USD (default: 50 for team, 200 for org)')
param budgetAmount int = tier == 'organization' ? 200 : 50

@description('ACR login server (e.g., myacr.azurecr.io)')
param acrLoginServer string

@description('Container image name for the API/MCP server')
param imageName string

@description('Container image tag')
param imageTag string = 'latest'

@description('CORS allowed origins')
param corsOrigins string = '*'

@description('Contact emails for budget alerts')
param contactEmails array

@description('LLM routing mode: direct (Key Vault API keys) or azure (Azure OpenAI endpoints)')
@allowed(['direct', 'azure'])
param llmRoutingMode string = 'direct'

@description('Azure OpenAI endpoint URL (required when llmRoutingMode is azure)')
param azureOpenaiEndpoint string = ''

@description('Azure OpenAI deployment name (required when llmRoutingMode is azure)')
param azureOpenaiDeployment string = ''

@description('Principal ID of the deploying user (for Key Vault access). Get via: az ad signed-in-user show --query id -o tsv')
param deployerPrincipalId string = ''

@description('MCP server JWT signing secret (HS256). Leave unset to auto-generate a cryptographically random secret on every deployment; pass an explicit 32+ character random value to pin a stable secret you rotate out-of-band. Marked @secure() so it never appears in deployment history/logs. Do NOT pass a guessable or placeholder string - the MCP server fails closed on known placeholders in cloud mode.')
@secure()
@minLength(32)
param mcpJwtSecret string = '${newGuid()}-${newGuid()}'

var isOrgTier = tier == 'organization'

// =============================================================================
// Core Infrastructure (both tiers)
// =============================================================================

// Managed Identity
module identity 'modules/identity.bicep' = {
  name: '${deploymentName}-identity'
  params: {
    location: location
    resourcePrefix: resourcePrefix
    acrName: split(acrLoginServer, '.')[0]
  }
}

// Key Vault
module keyVault 'modules/keyvault.bicep' = {
  name: '${deploymentName}-keyvault'
  params: {
    location: location
    resourcePrefix: resourcePrefix
    identityPrincipalId: identity.outputs.principalId
    deployerPrincipalId: deployerPrincipalId
    mcpJwtSecret: mcpJwtSecret
  }
}

// Cosmos DB
module cosmosDb 'modules/cosmos-db.bicep' = {
  name: '${deploymentName}-cosmos'
  params: {
    location: location
    resourcePrefix: resourcePrefix
    tier: tier
    identityPrincipalId: identity.outputs.principalId
  }
}

// Storage
module storage 'modules/storage.bicep' = {
  name: '${deploymentName}-storage'
  params: {
    location: location
    resourcePrefix: resourcePrefix
    identityPrincipalId: identity.outputs.principalId
  }
}

// ACR Pull role for managed identity - assigned in container-app module via acrName param
// Container App (MCP + Control Plane)
module containerApp 'modules/container-app.bicep' = {
  name: '${deploymentName}-container-app'
  params: {
    location: location
    resourcePrefix: resourcePrefix
    minReplicas: minReplicas
    maxReplicas: maxReplicas
    acrLoginServer: acrLoginServer
    imageName: imageName
    imageTag: imageTag
    identityId: identity.outputs.identityId
    identityClientId: identity.outputs.clientId
    cosmosEndpoint: cosmosDb.outputs.endpoint
    storageAccountName: storage.outputs.storageAccountName
    keyVaultName: keyVault.outputs.keyVaultName
    keyVaultUri: keyVault.outputs.keyVaultUri
    corsOrigins: corsOrigins
  }
}

// Container App Job (Runner)
module containerAppJob 'modules/container-app-job.bicep' = {
  name: '${deploymentName}-container-app-job'
  params: {
    location: location
    resourcePrefix: resourcePrefix
    acrLoginServer: acrLoginServer
    imageName: imageName
    imageTag: imageTag
    identityId: identity.outputs.identityId
    storageAccountName: storage.outputs.storageAccountName
    keyVaultUri: keyVault.outputs.keyVaultUri
    environmentId: containerApp.outputs.environmentId
    llmRoutingMode: llmRoutingMode
    azureOpenaiEndpoint: azureOpenaiEndpoint
    azureOpenaiDeployment: azureOpenaiDeployment
  }
}

// Budget alerts (both tiers)
module budget 'modules/budget.bicep' = {
  name: '${deploymentName}-budget'
  params: {
    budgetAmount: budgetAmount
    contactEmails: contactEmails
  }
}

// =============================================================================
// Organization Tier Only
// =============================================================================

// Service Bus (org tier)
module serviceBus 'modules/service-bus.bicep' = if (isOrgTier) {
  name: '${deploymentName}-service-bus'
  params: {
    location: location
    resourcePrefix: resourcePrefix
  }
}

// Monitoring - Application Insights + alerts (org tier)
module monitoring 'modules/monitoring.bicep' = if (isOrgTier) {
  name: '${deploymentName}-monitoring'
  params: {
    location: location
    resourcePrefix: resourcePrefix
    dailyCapGb: 5
    containerAppId: containerApp.outputs.containerAppId
    cosmosAccountId: cosmosDb.outputs.accountId
    serviceBusNamespaceId: serviceBus.outputs.namespaceId
  }
}

// Reconciler Azure Function (org tier)
module reconcilerFunction 'modules/function.bicep' = if (isOrgTier) {
  name: '${deploymentName}-function'
  params: {
    location: location
    resourcePrefix: resourcePrefix
    identityId: identity.outputs.identityId
    identityPrincipalId: identity.outputs.principalId
    cosmosEndpoint: cosmosDb.outputs.endpoint
    storageAccountName: storage.outputs.storageAccountName
  }
}

// =============================================================================
// Outputs
// =============================================================================

@description('MCP Server FQDN')
output mcpServerFqdn string = containerApp.outputs.fqdn

@description('Cosmos DB endpoint')
output cosmosEndpoint string = cosmosDb.outputs.endpoint

@description('Storage account name')
output storageAccountName string = storage.outputs.storageAccountName

@description('Key Vault URI')
output keyVaultUri string = keyVault.outputs.keyVaultUri

@description('Managed identity client ID')
output identityClientId string = identity.outputs.clientId

@description('Application Insights connection string (org tier only)')
output appInsightsConnectionString string = isOrgTier ? monitoring.outputs.connectionString : 'not-deployed'
