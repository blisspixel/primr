// =============================================================================
// Container App Job Module
// Runner job: 2 vCPU, 4GB memory, 120-minute timeout, 0 retries, manual trigger
// Requirements: 7.1, 7.5, 9.12
// =============================================================================

@description('Azure region for resource deployment')
param location string

@description('Resource name prefix')
param resourcePrefix string

@description('ACR login server (e.g., myacr.azurecr.io)')
param acrLoginServer string

@description('Container image name')
param imageName string

@description('Container image tag')
param imageTag string = 'latest'

@description('Resource ID of the user-assigned managed identity')
param identityId string

@description('Storage account name for artifact storage')
param storageAccountName string

@description('Key Vault URI for secret references')
param keyVaultUri string

@description('Container Apps Environment resource ID')
param environmentId string

@description('LLM routing mode: direct (Key Vault API keys) or azure (Azure OpenAI endpoints)')
@allowed(['direct', 'azure'])
param llmRoutingMode string = 'direct'

@description('Azure OpenAI endpoint URL (used when llmRoutingMode is azure)')
param azureOpenaiEndpoint string = ''

@description('Azure OpenAI deployment name (used when llmRoutingMode is azure)')
param azureOpenaiDeployment string = ''

var jobName = '${resourcePrefix}-runner'

// Secrets: only include Key Vault references in direct mode
var directModeSecrets = [
  {
    name: 'openai-api-key'
    keyVaultUrl: '${keyVaultUri}secrets/OPENAI-API-KEY'
    identity: identityId
  }
  {
    name: 'anthropic-api-key'
    keyVaultUrl: '${keyVaultUri}secrets/ANTHROPIC-API-KEY'
    identity: identityId
  }
  {
    name: 'xai-api-key'
    keyVaultUrl: '${keyVaultUri}secrets/XAI-API-KEY'
    identity: identityId
  }
  {
    name: 'gemini-api-key'
    keyVaultUrl: '${keyVaultUri}secrets/GEMINI-API-KEY'
    identity: identityId
  }
]

// Env vars for direct mode (Key Vault secret references)
var directModeEnv = [
  {
    name: 'ARTIFACT_STORE_URL'
    value: 'https://${storageAccountName}.blob.${environment().suffixes.storage}/artifacts'
  }
  {
    name: 'LLM_ROUTING_MODE'
    value: 'direct'
  }
  {
    name: 'OPENAI_API_KEY'
    secretRef: 'openai-api-key'
  }
  {
    name: 'ANTHROPIC_API_KEY'
    secretRef: 'anthropic-api-key'
  }
  {
    name: 'XAI_API_KEY'
    secretRef: 'xai-api-key'
  }
  {
    name: 'GEMINI_API_KEY'
    secretRef: 'gemini-api-key'
  }
]

// Env vars for azure mode (Azure OpenAI endpoints, no Key Vault secrets needed for LLM)
var azureModeEnv = [
  {
    name: 'ARTIFACT_STORE_URL'
    value: 'https://${storageAccountName}.blob.${environment().suffixes.storage}/artifacts'
  }
  {
    name: 'LLM_ROUTING_MODE'
    value: 'azure'
  }
  {
    name: 'AZURE_OPENAI_ENDPOINT'
    value: azureOpenaiEndpoint
  }
  {
    name: 'AZURE_OPENAI_DEPLOYMENT'
    value: azureOpenaiDeployment
  }
]

resource containerAppJob 'Microsoft.App/jobs@2024-03-01' = {
  name: jobName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    environmentId: environmentId
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 7200 // 120 minutes
      replicaRetryLimit: 0
      registries: [
        {
          server: acrLoginServer
          identity: identityId
        }
      ]
      secrets: llmRoutingMode == 'direct' ? directModeSecrets : []
    }
    template: {
      containers: [
        {
          name: 'runner'
          image: '${acrLoginServer}/${imageName}:${imageTag}'
          resources: {
            cpu: json('2')
            memory: '4Gi'
          }
          env: llmRoutingMode == 'direct' ? directModeEnv : azureModeEnv
        }
      ]
    }
  }
}

@description('Container App Job resource ID')
output jobId string = containerAppJob.id

@description('Container App Job name')
output jobName string = containerAppJob.name
