// =============================================================================
// Key Vault Module
// Key Vault with RBAC authorization, deployer access, and placeholder secrets
// Requirements: 7.1
// =============================================================================

@description('Azure region for resource deployment')
param location string

@description('Resource name prefix')
param resourcePrefix string

@description('Principal ID of the managed identity for RBAC assignment')
param identityPrincipalId string

@description('Principal ID of the deploying user (for secret management). Empty = skip.')
param deployerPrincipalId string = ''

var keyVaultName = '${resourcePrefix}-kv'

// Key Vault Secrets User role (read secrets)
var keyVaultSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'
// Key Vault Secrets Officer role (read + write secrets)
var keyVaultSecretsOfficerRoleId = 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 30
    enablePurgeProtection: true
  }
}

// RBAC: Key Vault Secrets User for managed identity (read secrets at runtime)
resource identitySecretsRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, identityPrincipalId, keyVaultSecretsUserRoleId)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUserRoleId)
    principalId: identityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// RBAC: Key Vault Secrets Officer for deploying user (manage secrets via CLI)
resource deployerSecretsRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(deployerPrincipalId)) {
  name: guid(keyVault.id, deployerPrincipalId, keyVaultSecretsOfficerRoleId)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsOfficerRoleId)
    principalId: deployerPrincipalId
    principalType: 'User'
  }
}

// Placeholder secrets so Container App Job can reference them at deploy time.
// Replace with real keys after deployment: az keyvault secret set --vault-name <name> --name XAI-API-KEY --value <key>
resource xaiSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'XAI-API-KEY'
  properties: {
    value: 'placeholder-replace-after-deploy'
  }
}

resource geminiSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'GEMINI-API-KEY'
  properties: {
    value: 'placeholder-replace-after-deploy'
  }
}

resource openaiSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'OPENAI-API-KEY'
  properties: {
    value: 'placeholder-replace-after-deploy'
  }
}

resource anthropicSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'ANTHROPIC-API-KEY'
  properties: {
    value: 'placeholder-replace-after-deploy'
  }
}

// MCP server bearer-token verifier secret. The MCP Starlette app installs
// its auth middleware only when require_auth=true; the middleware uses
// MCP_JWT_SECRET to verify HS256 tokens. We seed a placeholder so the
// Container App can start; replace the value before exposing the public
// FQDN to real traffic:
//   az keyvault secret set --vault-name <name> --name MCP-JWT-SECRET \
//     --value "$(openssl rand -base64 48)"
resource mcpJwtSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'MCP-JWT-SECRET'
  properties: {
    value: 'placeholder-replace-before-exposing-public-fqdn'
  }
}

@description('Key Vault name')
output keyVaultName string = keyVault.name

@description('Key Vault resource ID')
output keyVaultId string = keyVault.id

@description('Key Vault URI')
output keyVaultUri string = keyVault.properties.vaultUri
