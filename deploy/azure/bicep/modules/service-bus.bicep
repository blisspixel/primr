// =============================================================================
// Service Bus Module (Organization Tier)
// Service Bus namespace with jobs queue, duplicate detection, dead-letter
// Requirements: 7.1, 9.8
// =============================================================================

@description('Azure region for resource deployment')
param location string

@description('Resource name prefix')
param resourcePrefix string

var namespaceName = '${resourcePrefix}-sb'
var queueName = 'jobs'

resource serviceBusNamespace 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: namespaceName
  location: location
  sku: {
    name: 'Standard'
    tier: 'Standard'
  }
}

resource jobsQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBusNamespace
  name: queueName
  properties: {
    requiresDuplicateDetection: true
    duplicateDetectionHistoryTimeWindow: 'P1D' // 1 day
    maxDeliveryCount: 3
    deadLetteringOnMessageExpiration: true
    lockDuration: 'PT5M' // 5 minutes
    defaultMessageTimeToLive: 'P7D' // 7 days
  }
}

@description('Service Bus namespace resource ID')
output namespaceId string = serviceBusNamespace.id

@description('Service Bus namespace name')
output namespaceName string = serviceBusNamespace.name
