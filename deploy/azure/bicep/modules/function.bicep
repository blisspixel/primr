// =============================================================================
// Reconciler Azure Function Module (Organization Tier)
// Timer-triggered function on Consumption plan (every 5 min)
// Requirements: 7.1, 9.3
// =============================================================================

@description('Azure region for resource deployment')
param location string

@description('Resource name prefix')
param resourcePrefix string

@description('Resource ID of the user-assigned managed identity')
param identityId string

@description('Principal ID of the user-assigned managed identity for RBAC')
param identityPrincipalId string

@description('Cosmos DB endpoint URL')
param cosmosEndpoint string

@description('Storage account name for artifact access')
param storageAccountName string

var functionAppName = '${resourcePrefix}-reconciler'
var functionStorageName = toLower(replace('${resourcePrefix}funcstor', '-', ''))
var hostingPlanName = '${resourcePrefix}-func-plan'

// Storage account for Azure Functions runtime
resource functionStorage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: functionStorageName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

// Consumption plan (pay-per-execution, zero idle cost)
resource hostingPlan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: hostingPlanName
  location: location
  sku: {
    name: 'Y1'
    tier: 'Dynamic'
  }
  kind: 'functionapp,linux'
  properties: {
    reserved: true // Linux
  }
}

resource functionApp 'Microsoft.Web/sites@2023-01-01' = {
  name: functionAppName
  location: location
  kind: 'functionapp,linux'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    serverFarmId: hostingPlan.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.12'
      appSettings: [
        { name: 'AzureWebJobsStorage__accountName', value: functionStorage.name }
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'python' }
        { name: 'COSMOS_ENDPOINT', value: cosmosEndpoint }
        { name: 'COSMOS_DATABASE', value: 'primr' }
        { name: 'COSMOS_CONTAINER', value: 'jobs' }
        { name: 'STORAGE_ACCOUNT_NAME', value: storageAccountName }
        { name: 'STORAGE_CONTAINER', value: 'artifacts' }
      ]
    }
    httpsOnly: true
  }
}

// Storage Blob Data Owner role for managed identity on function storage
var storageBlobDataOwnerRoleId = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'

resource functionStorageRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(functionStorage.id, identityPrincipalId, storageBlobDataOwnerRoleId)
  scope: functionStorage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataOwnerRoleId)
    principalId: identityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

@description('Function App name')
output functionAppName string = functionApp.name

@description('Function App resource ID')
output functionAppId string = functionApp.id

@description('Function App default hostname')
output defaultHostname string = functionApp.properties.defaultHostName
