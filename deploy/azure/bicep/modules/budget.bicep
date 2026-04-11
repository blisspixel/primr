// =============================================================================
// Azure Budget Module
// Budget alerts at 50%, 80%, 100% of configurable monthly spend
// Requirements: 9.11
// =============================================================================

@description('Monthly budget amount in USD')
param budgetAmount int

@description('Contact emails for budget alerts')
param contactEmails array

@description('Budget start date in yyyy-MM-dd format (defaults to first of current month)')
param startDate string = utcNow('yyyy-MM-01')

var budgetName = 'primr-monthly-budget'

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: budgetName
  properties: {
    category: 'Cost'
    amount: budgetAmount
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: startDate
    }
    notifications: {
      fiftyPercent: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 50
        contactEmails: contactEmails
        thresholdType: 'Actual'
      }
      eightyPercent: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 80
        contactEmails: contactEmails
        thresholdType: 'Actual'
      }
      hundredPercent: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        contactEmails: contactEmails
        thresholdType: 'Actual'
      }
    }
  }
}

@description('Budget resource ID')
output budgetId string = budget.id

@description('Budget name')
output budgetName string = budget.name
