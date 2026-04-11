// =============================================================================
// Monitoring Module (Organization Tier)
// Application Insights + alert rules
// Requirements: 7.1, 9.9, 10.6
// =============================================================================

@description('Azure region for resource deployment')
param location string

@description('Resource name prefix')
param resourcePrefix string

@description('Daily data cap in GB')
param dailyCapGb int = 5

@description('Container App resource ID for alert scoping')
param containerAppId string

@description('Cosmos DB account resource ID for alert scoping')
param cosmosAccountId string

@description('Service Bus namespace resource ID for alert scoping')
param serviceBusNamespaceId string

var insightsName = '${resourcePrefix}-insights'
var workspaceName = '${resourcePrefix}-logs'

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: workspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: insightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalyticsWorkspace.id
  }
}

// Daily data cap
resource dailyCap 'Microsoft.Insights/components/CurrentBillingFeatures@2015-05-01' = {
  parent: appInsights
  name: 'current'
  properties: {
    CurrentBillingFeatures: ['Basic']
    DataVolumeCap: {
      Cap: dailyCapGb
      ResetTime: 0
      WarningThreshold: 80
    }
  }
}

// Alert: Container App error rate > 5% over 5 minutes
resource containerAppErrorAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: '${resourcePrefix}-container-error-rate'
  location: 'global'
  properties: {
    severity: 2
    enabled: true
    scopes: [containerAppId]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'HighErrorRate'
          metricName: 'Requests'
          metricNamespace: 'Microsoft.App/containerApps'
          operator: 'GreaterThan'
          threshold: 5
          timeAggregation: 'Average'
          dimensions: [
            {
              name: 'statusCodeCategory'
              operator: 'Include'
              values: ['5xx']
            }
          ]
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
  }
}

// Alert: Cosmos DB throttled requests > 0
resource cosmosThrottleAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: '${resourcePrefix}-cosmos-throttle'
  location: 'global'
  properties: {
    severity: 3
    enabled: true
    scopes: [cosmosAccountId]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'ThrottledRequests'
          metricName: 'TotalRequests'
          metricNamespace: 'Microsoft.DocumentDB/databaseAccounts'
          operator: 'GreaterThan'
          threshold: 0
          timeAggregation: 'Total'
          dimensions: [
            {
              name: 'StatusCode'
              operator: 'Include'
              values: ['429']
            }
          ]
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
  }
}

// Alert: Dead-letter queue count > 0
resource deadLetterAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: '${resourcePrefix}-deadletter-count'
  location: 'global'
  properties: {
    severity: 2
    enabled: true
    scopes: [serviceBusNamespaceId]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'DeadLetteredMessages'
          metricName: 'DeadletteredMessages'
          metricNamespace: 'Microsoft.ServiceBus/namespaces'
          operator: 'GreaterThan'
          threshold: 0
          timeAggregation: 'Total'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
  }
}

@description('Application Insights connection string')
output connectionString string = appInsights.properties.ConnectionString

@description('Application Insights instrumentation key')
output instrumentationKey string = appInsights.properties.InstrumentationKey

@description('Application Insights resource ID')
output insightsId string = appInsights.id

@description('Log Analytics workspace ID')
output workspaceId string = logAnalyticsWorkspace.id
