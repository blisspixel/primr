// =============================================================================
// Cosmos DB Module
// Cosmos DB account with conditional throughput (serverless vs autoscale)
// Requirements: 7.1, 7.5, 9.6
// =============================================================================

@description('Azure region for resource deployment')
param location string

@description('Resource name prefix')
param resourcePrefix string

@description('Deployment tier: team (serverless) or organization (autoscale)')
@allowed(['team', 'organization'])
param tier string

@description('Principal ID of the managed identity for RBAC assignment')
param identityPrincipalId string

var cosmosAccountName = '${resourcePrefix}-cosmos'
var databaseName = 'primr'
var jobsContainerName = 'jobs'
var budgetContainerName = 'budget'
var isOrgTier = tier == 'organization'

// Cosmos DB Built-in Data Contributor role
var cosmosDbDataContributorRoleId = '00000000-0000-0000-0000-000000000002'

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: cosmosAccountName
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    capabilities: isOrgTier ? [] : [
      {
        name: 'EnableServerless'
      }
    ]
    enableAutomaticFailover: false
    // Free tier: only one per subscription. Set to false if you already have a free-tier Cosmos DB.
    enableFreeTier: false
  }
}

resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmosAccount
  name: databaseName
  properties: {
    resource: {
      id: databaseName
    }
  }
}

// Jobs container — serverless (no throughput settings) or autoscale
resource jobsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: jobsContainerName
  properties: {
    resource: {
      id: jobsContainerName
      partitionKey: {
        paths: ['/job_id']
        kind: 'Hash'
      }
      defaultTtl: 2592000 // 30 days in seconds
    }
    options: isOrgTier ? {
      autoscaleSettings: {
        maxThroughput: 4000
      }
    } : {}
  }
}

// Budget container — organization tier only
resource budgetContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = if (isOrgTier) {
  parent: database
  name: budgetContainerName
  properties: {
    resource: {
      id: budgetContainerName
      partitionKey: {
        paths: ['/api_key_hash']
        kind: 'Hash'
      }
      defaultTtl: 2592000 // 30 days
    }
    options: {
      autoscaleSettings: {
        maxThroughput: 4000
      }
    }
  }
}

// RBAC: Cosmos DB Data Contributor for managed identity
resource cosmosRoleAssignment 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  parent: cosmosAccount
  name: guid(cosmosAccount.id, identityPrincipalId, cosmosDbDataContributorRoleId)
  properties: {
    roleDefinitionId: '${cosmosAccount.id}/sqlRoleDefinitions/${cosmosDbDataContributorRoleId}'
    principalId: identityPrincipalId
    scope: cosmosAccount.id
  }
}

@description('Cosmos DB account endpoint')
output endpoint string = cosmosAccount.properties.documentEndpoint

@description('Cosmos DB account resource ID')
output accountId string = cosmosAccount.id

@description('Cosmos DB account name')
output accountName string = cosmosAccount.name
