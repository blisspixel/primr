// =============================================================================
// Container App Module
// Container App for MCP Server + Control Plane API
// Requirements: 7.1, 7.5, 2.1, 2.4, 2.5, 2.6, 9.1
//
// TODO (production): Add VNet integration for network isolation.
// The Container Apps Environment should be deployed into a VNet subnet
// with NSG rules restricting egress to required Azure services only.
// See: https://learn.microsoft.com/en-us/azure/container-apps/vnet-custom
// =============================================================================

@description('Azure region for resource deployment')
param location string

@description('Resource name prefix')
param resourcePrefix string

@description('Minimum number of replicas (0 for scale-to-zero)')
param minReplicas int = 0

@description('Maximum number of replicas (default 5 for team tier, 10 for organization — higher values increase cost)')
param maxReplicas int = 5

@description('ACR login server (e.g., myacr.azurecr.io)')
param acrLoginServer string

@description('Container image name')
param imageName string

@description('Container image tag')
param imageTag string = 'latest'

@description('Resource ID of the user-assigned managed identity')
param identityId string

@description('Client ID of the user-assigned managed identity')
param identityClientId string

@description('Cosmos DB endpoint URL')
param cosmosEndpoint string

@description('Storage account name')
param storageAccountName string

@description('Key Vault name')
param keyVaultName string

// SECURITY: corsOrigins must be explicitly set during deployment — do not use '*' in production
@description('CORS allowed origins (must be explicitly configured, empty by default)')
param corsOrigins string = ''

var envName = '${resourcePrefix}-env'
var appName = '${resourcePrefix}-api'

resource containerAppEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: envName
  location: location
  properties: {}
}

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
        corsPolicy: {
          allowedOrigins: [corsOrigins]
          allowedMethods: ['GET', 'POST', 'OPTIONS']
          allowedHeaders: ['Authorization', 'Content-Type']
          maxAge: 3600
        }
      }
      registries: [
        {
          server: acrLoginServer
          identity: identityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: '${acrLoginServer}/${imageName}:${imageTag}'
          // Run the existing MCP server — same as local `primr-mcp --http`
          command: ['primr-mcp', '--http', '--port', '8000', '--host', '0.0.0.0', '--no-auth', '--allow-plaintext']
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            { name: 'COSMOS_ENDPOINT', value: cosmosEndpoint }
            { name: 'STORAGE_ACCOUNT_NAME', value: storageAccountName }
            { name: 'KEY_VAULT_NAME', value: keyVaultName }
            { name: 'AZURE_CLIENT_ID', value: identityClientId }
            { name: 'PRIMR_CORS_ORIGINS', value: corsOrigins }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/healthz'
                port: 8000
              }
              initialDelaySeconds: 10
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/healthz'
                port: 8000
              }
              initialDelaySeconds: 5
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '100'
              }
            }
          }
        ]
      }
    }
  }
}

@description('Container App FQDN')
output fqdn string = containerApp.properties.configuration.ingress.fqdn

@description('Container App resource ID')
output containerAppId string = containerApp.id

@description('Container Apps Environment resource ID')
output environmentId string = containerAppEnv.id
