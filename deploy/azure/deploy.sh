#!/usr/bin/env bash
# =============================================================================
# Primr Azure Deployment Script (REFERENCE TEMPLATE)
# =============================================================================
# Deploy Primr to Azure using:
# - ACR for container registry
# - Container Apps for control plane API
# - Service Bus for job queue
# - Container Apps Jobs for job execution
# - Blob Storage for artifacts
# - Cosmos DB for job state
# - Key Vault for LLM keys (runner only)
#
# NOTE: This is a reference template. AWS deployment is the primary target.
#
# Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 6.11
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# =============================================================================
# CONFIGURATION
# =============================================================================

load_config "$SCRIPT_DIR/deploy.conf"

AZURE_LOCATION="${PRIMR_REGION:-eastus}"
RESOURCE_GROUP="$(resource_name "rg")"
ACR_NAME="$(short_resource_name "acr" 50 | tr -d '-')"
CONTAINER_APP_ENV="$(resource_name "env")"
CONTAINER_APP_NAME="$(resource_name "api")"
JOB_NAME="$(resource_name "runner")"
SERVICE_BUS_NS="$(resource_name "sb")"
QUEUE_NAME="jobs"
STORAGE_ACCOUNT="$(short_resource_name "storage" 24 | tr -d '-')"
COSMOS_ACCOUNT="$(resource_name "cosmos")"
KEY_VAULT_NAME="$(short_resource_name "kv" 24)"

# =============================================================================
# PREREQUISITE CHECKS
# =============================================================================

check_prerequisites() {
    log_step "Checking prerequisites"
    check_docker || exit 1
    check_azure_cli || exit 1
    check_jq || exit 1
    log_success "All prerequisites met"
}

# =============================================================================
# RESOURCE GROUP
# =============================================================================

create_resource_group() {
    log_step "Creating resource group: $RESOURCE_GROUP"
    if az group show --name "$RESOURCE_GROUP" &>/dev/null; then
        log_info "Resource group already exists"
    else
        az group create --name "$RESOURCE_GROUP" --location "$AZURE_LOCATION" \
            --tags Deployment="$PRIMR_DEPLOYMENT"
        log_success "Resource group created"
    fi
}

# =============================================================================
# ACR OPERATIONS
# =============================================================================

create_acr() {
    log_step "Creating ACR: $ACR_NAME"
    if az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
        log_info "ACR already exists"
    else
        az acr create --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" \
            --sku Basic --admin-enabled true
        log_success "ACR created"
    fi
}

push_to_acr() {
    log_step "Building and pushing Docker image to ACR"
    az acr login --name "$ACR_NAME"
    local image="$ACR_NAME.azurecr.io/primr-runner:$PRIMR_DEPLOYMENT"
    build_image "$SCRIPT_DIR/../Dockerfile" "$image" "$SCRIPT_DIR/../.."
    push_image "$image"
}

# =============================================================================
# STORAGE
# =============================================================================

create_storage() {
    log_step "Creating Storage Account: $STORAGE_ACCOUNT"
    if az storage account show --name "$STORAGE_ACCOUNT" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
        log_info "Storage account already exists"
    else
        az storage account create --name "$STORAGE_ACCOUNT" --resource-group "$RESOURCE_GROUP" \
            --location "$AZURE_LOCATION" --sku Standard_LRS --kind StorageV2 \
            --min-tls-version TLS1_2 --allow-blob-public-access false
        az storage container create --name artifacts --account-name "$STORAGE_ACCOUNT"
        log_success "Storage account created"
    fi
}

# =============================================================================
# COSMOS DB
# =============================================================================

create_cosmos() {
    log_step "Creating Cosmos DB: $COSMOS_ACCOUNT"
    if az cosmosdb show --name "$COSMOS_ACCOUNT" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
        log_info "Cosmos DB already exists"
    else
        az cosmosdb create --name "$COSMOS_ACCOUNT" --resource-group "$RESOURCE_GROUP" \
            --default-consistency-level Session --enable-automatic-failover false \
            --enable-free-tier false
        az cosmosdb sql database create --account-name "$COSMOS_ACCOUNT" \
            --resource-group "$RESOURCE_GROUP" --name primr
        # Use autoscale instead of fixed throughput for cost efficiency
        az cosmosdb sql container create --account-name "$COSMOS_ACCOUNT" \
            --resource-group "$RESOURCE_GROUP" --database-name primr --name jobs \
            --partition-key-path /job_id \
            --max-throughput 4000
        log_success "Cosmos DB created with autoscale (400-4000 RU/s)"
    fi
}

# =============================================================================
# SERVICE BUS
# =============================================================================

create_service_bus() {
    log_step "Creating Service Bus: $SERVICE_BUS_NS"
    if az servicebus namespace show --name "$SERVICE_BUS_NS" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
        log_info "Service Bus already exists"
    else
        az servicebus namespace create --name "$SERVICE_BUS_NS" --resource-group "$RESOURCE_GROUP" \
            --location "$AZURE_LOCATION" --sku Standard
        az servicebus queue create --name "$QUEUE_NAME" --namespace-name "$SERVICE_BUS_NS" \
            --resource-group "$RESOURCE_GROUP" --enable-duplicate-detection true \
            --duplicate-detection-history-time-window P1D --max-delivery-count 3
        log_success "Service Bus created"
    fi
}

# =============================================================================
# KEY VAULT
# =============================================================================

create_key_vault() {
    log_step "Creating Key Vault: $KEY_VAULT_NAME"
    if az keyvault show --name "$KEY_VAULT_NAME" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
        log_info "Key Vault already exists"
    else
        az keyvault create --name "$KEY_VAULT_NAME" --resource-group "$RESOURCE_GROUP" \
            --location "$AZURE_LOCATION" --enable-rbac-authorization true
        log_success "Key Vault created"
    fi
}

# =============================================================================
# APPLICATION INSIGHTS
# =============================================================================

APP_INSIGHTS_NAME="$(resource_name "insights")"

create_app_insights() {
    log_step "Creating Application Insights: $APP_INSIGHTS_NAME"
    if az monitor app-insights component show --app "$APP_INSIGHTS_NAME" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
        log_info "Application Insights already exists"
    else
        az monitor app-insights component create \
            --app "$APP_INSIGHTS_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --location "$AZURE_LOCATION" \
            --kind web \
            --application-type web \
            --tags Deployment="$PRIMR_DEPLOYMENT"
        log_success "Application Insights created"
    fi
}

get_app_insights_connection_string() {
    az monitor app-insights component show \
        --app "$APP_INSIGHTS_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query connectionString -o tsv
}

# =============================================================================
# MANAGED IDENTITY
# =============================================================================

MANAGED_IDENTITY_NAME="$(resource_name "identity")"

create_managed_identity() {
    log_step "Creating managed identity: $MANAGED_IDENTITY_NAME"
    if az identity show --name "$MANAGED_IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
        log_info "Managed identity already exists"
    else
        az identity create --name "$MANAGED_IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" \
            --location "$AZURE_LOCATION" --tags Deployment="$PRIMR_DEPLOYMENT"
        log_success "Managed identity created"
    fi
    
    # Get identity details
    local identity_id
    identity_id=$(az identity show --name "$MANAGED_IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" \
        --query id -o tsv)
    local principal_id
    principal_id=$(az identity show --name "$MANAGED_IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" \
        --query principalId -o tsv)
    
    # Assign roles for Cosmos DB access
    log_substep "Assigning Cosmos DB Contributor role"
    local cosmos_id
    cosmos_id=$(az cosmosdb show --name "$COSMOS_ACCOUNT" --resource-group "$RESOURCE_GROUP" --query id -o tsv)
    az role assignment create --assignee "$principal_id" --role "Cosmos DB Account Reader Role" \
        --scope "$cosmos_id" 2>/dev/null || true
    az role assignment create --assignee "$principal_id" --role "DocumentDB Account Contributor" \
        --scope "$cosmos_id" 2>/dev/null || true
    
    # Assign roles for Storage access
    log_substep "Assigning Storage Blob Data Contributor role"
    local storage_id
    storage_id=$(az storage account show --name "$STORAGE_ACCOUNT" --resource-group "$RESOURCE_GROUP" --query id -o tsv)
    az role assignment create --assignee "$principal_id" --role "Storage Blob Data Contributor" \
        --scope "$storage_id" 2>/dev/null || true
    
    # Assign roles for Key Vault access
    log_substep "Assigning Key Vault Secrets User role"
    local kv_id
    kv_id=$(az keyvault show --name "$KEY_VAULT_NAME" --resource-group "$RESOURCE_GROUP" --query id -o tsv)
    az role assignment create --assignee "$principal_id" --role "Key Vault Secrets User" \
        --scope "$kv_id" 2>/dev/null || true
    
    log_success "Managed identity configured with RBAC roles"
}

set_secret() {
    local name="$1"
    local value="${2:--}"
    validate_secret_name "$name" || return 1
    local secret_value
    secret_value=$(read_secret_value "$value")
    log_step "Setting secret: $name"
    az keyvault secret set --vault-name "$KEY_VAULT_NAME" --name "$name" --value "$secret_value"
    log_success "Secret set"
}

list_secrets() {
    log_step "Listing secrets in Key Vault: $KEY_VAULT_NAME"
    az keyvault secret list --vault-name "$KEY_VAULT_NAME" --query "[].name" -o table
}

# =============================================================================
# RECONCILER (AZURE FUNCTION WITH TIMER TRIGGER)
# =============================================================================

FUNCTION_APP_NAME="$(resource_name "reconciler")"
FUNCTION_STORAGE="$(short_resource_name "funcstor" 24 | tr -d '-')"

create_function_storage() {
    log_step "Creating Function App storage: $FUNCTION_STORAGE"
    if az storage account show --name "$FUNCTION_STORAGE" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
        log_info "Function storage already exists"
    else
        az storage account create --name "$FUNCTION_STORAGE" --resource-group "$RESOURCE_GROUP" \
            --location "$AZURE_LOCATION" --sku Standard_LRS --kind StorageV2
        log_success "Function storage created"
    fi
}

create_reconciler_function() {
    log_step "Creating reconciler Azure Function: $FUNCTION_APP_NAME"
    
    if az functionapp show --name "$FUNCTION_APP_NAME" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
        log_info "Function App already exists, updating..."
        update_reconciler_function
        return
    fi
    
    # Get managed identity ID
    local identity_id
    identity_id=$(az identity show --name "$MANAGED_IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" \
        --query id -o tsv)
    
    # Get Application Insights connection string
    local app_insights_conn
    app_insights_conn=$(get_app_insights_connection_string)
    
    # Create Function App with managed identity
    az functionapp create \
        --name "$FUNCTION_APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --storage-account "$FUNCTION_STORAGE" \
        --consumption-plan-location "$AZURE_LOCATION" \
        --runtime python \
        --runtime-version 3.10 \
        --functions-version 4 \
        --os-type Linux \
        --assign-identity "$identity_id" \
        --tags Deployment="$PRIMR_DEPLOYMENT"
    
    # Get Cosmos DB endpoint (use managed identity instead of connection string)
    local cosmos_endpoint
    cosmos_endpoint=$(az cosmosdb show --name "$COSMOS_ACCOUNT" --resource-group "$RESOURCE_GROUP" \
        --query documentEndpoint -o tsv)
    
    # Get Storage account name (use managed identity instead of connection string)
    local storage_conn
    storage_conn=$(az storage account show-connection-string --name "$STORAGE_ACCOUNT" \
        --resource-group "$RESOURCE_GROUP" --query connectionString -o tsv)
    
    # Configure app settings with Application Insights and managed identity
    az functionapp config appsettings set \
        --name "$FUNCTION_APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --settings \
            "COSMOS_ENDPOINT=$cosmos_endpoint" \
            "COSMOS_DATABASE=primr" \
            "COSMOS_CONTAINER=jobs" \
            "STORAGE_ACCOUNT_NAME=$STORAGE_ACCOUNT" \
            "STORAGE_CONNECTION_STRING=$storage_conn" \
            "STORAGE_CONTAINER=artifacts" \
            "DEPLOYMENT=$PRIMR_DEPLOYMENT" \
            "APPLICATIONINSIGHTS_CONNECTION_STRING=$app_insights_conn" \
            "AZURE_CLIENT_ID=$(az identity show --name "$MANAGED_IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" --query clientId -o tsv)"
    
    # Deploy function code
    deploy_reconciler_function_code
    
    log_success "Reconciler Function App created with managed identity and Application Insights"
}

update_reconciler_function() {
    log_substep "Updating reconciler function code"
    deploy_reconciler_function_code
    log_success "Reconciler function updated"
}

deploy_reconciler_function_code() {
    # Create temporary directory for function code
    local temp_dir
    temp_dir=$(mktemp -d)
    
    # Create function.json for timer trigger (every 5 minutes)
    mkdir -p "$temp_dir/reconciler"
    cat > "$temp_dir/reconciler/function.json" << 'EOF'
{
    "scriptFile": "__init__.py",
    "bindings": [
        {
            "name": "timer",
            "type": "timerTrigger",
            "direction": "in",
            "schedule": "0 */5 * * * *"
        }
    ]
}
EOF
    
    # Create the function code
    cat > "$temp_dir/reconciler/__init__.py" << 'EOF'
import logging
import os
import json
import azure.functions as func
from deploy.control_plane.reconciler import Reconciler, ReconciliationConfig
from deploy.control_plane.job_store import CosmosStore
from deploy.storage import BlobStore

def main(timer: func.TimerRequest) -> None:
    """Timer-triggered reconciliation function."""
    logging.info("Reconciler function triggered")
    
    # Get configuration from environment
    cosmos_conn = os.environ.get("COSMOS_CONNECTION_STRING")
    storage_conn = os.environ.get("STORAGE_CONNECTION_STRING")
    deployment = os.environ.get("DEPLOYMENT", "prod")
    database = os.environ.get("COSMOS_DATABASE", "primr")
    container = os.environ.get("COSMOS_CONTAINER", "jobs")
    storage_container = os.environ.get("STORAGE_CONTAINER", "artifacts")
    
    # Create stores
    job_store = CosmosStore(
        connection_string=cosmos_conn,
        database_name=database,
        container_name=container,
    )
    artifact_store = BlobStore(
        container_name=storage_container,
        deployment=deployment,
        connection_string=storage_conn,
    )
    
    # Create reconciler with config
    config = ReconciliationConfig(
        max_duration_seconds=7200,  # 2 hours
        cancellation_grace_seconds=300,  # 5 minutes
        heartbeat_stale_seconds=600,  # 10 minutes
    )
    reconciler = Reconciler(job_store, artifact_store, config)
    
    # Run reconciliation
    result = reconciler.reconcile()
    
    logging.info(f"Reconciliation complete: {result.to_dict()}")
EOF
    
    # Create host.json
    cat > "$temp_dir/host.json" << 'EOF'
{
    "version": "2.0",
    "logging": {
        "applicationInsights": {
            "samplingSettings": {
                "isEnabled": true,
                "excludedTypes": "Request"
            }
        }
    },
    "extensionBundle": {
        "id": "Microsoft.Azure.Functions.ExtensionBundle",
        "version": "[3.*, 4.0.0)"
    }
}
EOF
    
    # Create requirements.txt
    cat > "$temp_dir/requirements.txt" << 'EOF'
azure-functions
azure-cosmos
azure-storage-blob
EOF
    
    # Copy deploy module
    cp -r "$SCRIPT_DIR/../" "$temp_dir/deploy"
    
    # Deploy using zip deployment
    local zip_file="$temp_dir/function.zip"
    (cd "$temp_dir" && zip -r "$zip_file" . -x "*.pyc" -x "__pycache__/*")
    
    az functionapp deployment source config-zip \
        --name "$FUNCTION_APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --src "$zip_file"
    
    # Clean up
    rm -rf "$temp_dir"
}

# =============================================================================
# CONTAINER APPS
# =============================================================================

create_container_app_env() {
    log_step "Creating Container Apps Environment: $CONTAINER_APP_ENV"
    if az containerapp env show --name "$CONTAINER_APP_ENV" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
        log_info "Container Apps Environment already exists"
    else
        az containerapp env create --name "$CONTAINER_APP_ENV" --resource-group "$RESOURCE_GROUP" \
            --location "$AZURE_LOCATION"
        log_success "Container Apps Environment created"
    fi
}

create_container_app_job() {
    log_step "Creating Container Apps Job: $JOB_NAME"
    local image="$ACR_NAME.azurecr.io/primr-runner:$PRIMR_DEPLOYMENT"
    
    # Create job from template
    az containerapp job create --name "$JOB_NAME" --resource-group "$RESOURCE_GROUP" \
        --environment "$CONTAINER_APP_ENV" --trigger-type Manual \
        --replica-timeout 7200 --replica-retry-limit 0 \
        --image "$image" --cpu 2 --memory 4Gi \
        --registry-server "$ACR_NAME.azurecr.io" \
        --yaml "$SCRIPT_DIR/job-template.yaml" 2>/dev/null || \
    az containerapp job create --name "$JOB_NAME" --resource-group "$RESOURCE_GROUP" \
        --environment "$CONTAINER_APP_ENV" --trigger-type Manual \
        --replica-timeout 7200 --replica-retry-limit 0 \
        --image "$image" --cpu 2 --memory 4Gi \
        --registry-server "$ACR_NAME.azurecr.io"
    
    log_success "Container Apps Job created"
}

# =============================================================================
# COMMANDS
# =============================================================================

cmd_deploy() {
    log_step "Deploying Primr to Azure"
    log_info "Deployment: $PRIMR_DEPLOYMENT"
    log_info "Location: $AZURE_LOCATION"
    
    check_prerequisites
    create_resource_group
    create_acr
    push_to_acr
    create_storage
    create_cosmos
    create_service_bus
    create_key_vault
    
    # Create observability and identity
    create_app_insights
    create_managed_identity
    
    create_container_app_env
    create_container_app_job
    
    # Create reconciler (Azure Function with Timer trigger)
    create_function_storage
    create_reconciler_function
    
    log_success "Deployment complete!"
    log_info "Next steps:"
    log_info "  1. Set LLM API keys: $0 secrets set OPENAI-API-KEY"
    log_info "  2. Validate deployment: $0 validate"
}

cmd_destroy() {
    local force="${1:-}"
    
    log_step "Destroying Primr Azure deployment"
    log_warn "This will delete resource group: $RESOURCE_GROUP"
    
    if [[ "$force" != "--force" ]]; then
        read -p "Are you sure? (yes/no): " confirm
        [[ "$confirm" != "yes" ]] && { log_info "Aborted"; return 1; }
    fi
    
    check_prerequisites
    az group delete --name "$RESOURCE_GROUP" --yes --no-wait
    log_success "Destroy initiated (running in background)"
}

cmd_validate() {
    log_step "Validating Azure deployment"
    check_prerequisites
    local errors=0
    az group show --name "$RESOURCE_GROUP" &>/dev/null && log_substep "Resource group: OK" || { log_error "Resource group not found"; ((errors++)); }
    az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" &>/dev/null && log_substep "ACR: OK" || { log_error "ACR not found"; ((errors++)); }
    az storage account show --name "$STORAGE_ACCOUNT" --resource-group "$RESOURCE_GROUP" &>/dev/null && log_substep "Storage: OK" || { log_error "Storage not found"; ((errors++)); }
    az cosmosdb show --name "$COSMOS_ACCOUNT" --resource-group "$RESOURCE_GROUP" &>/dev/null && log_substep "Cosmos DB: OK" || { log_error "Cosmos DB not found"; ((errors++)); }
    az monitor app-insights component show --app "$APP_INSIGHTS_NAME" --resource-group "$RESOURCE_GROUP" &>/dev/null && log_substep "Application Insights: OK" || { log_error "Application Insights not found"; ((errors++)); }
    az identity show --name "$MANAGED_IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" &>/dev/null && log_substep "Managed Identity: OK" || { log_error "Managed Identity not found"; ((errors++)); }
    az functionapp show --name "$FUNCTION_APP_NAME" --resource-group "$RESOURCE_GROUP" &>/dev/null && log_substep "Reconciler Function: OK" || { log_error "Reconciler Function not found"; ((errors++)); }
    [[ $errors -eq 0 ]] && log_success "All resources validated" || { log_error "$errors resource(s) missing"; return 1; }
}

cmd_secrets() {
    local action="${1:-list}"; shift || true
    case "$action" in
        set) [[ $# -lt 1 ]] && { log_error "Usage: $0 secrets set <name> [value|-]"; return 1; }; set_secret "$1" "${2:--}" ;;
        list) list_secrets ;;
        *) log_error "Unknown action: $action"; return 1 ;;
    esac
}

usage() {
    print_usage_header "deploy.sh" "Deploy Primr to Azure (REFERENCE)"
    echo "Commands:"; print_usage_command "deploy" "Deploy all Azure resources"
    print_usage_command "destroy [--force]" "Tear down all Azure resources (--force skips confirmation)"
    print_usage_command "validate" "Validate deployed resources"
    print_usage_command "secrets" "Manage secrets (set, list)"
}

main() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -d|--deployment) PRIMR_DEPLOYMENT="$2"; shift 2 ;;
            -r|--region) AZURE_LOCATION="$2"; PRIMR_REGION="$2"; shift 2 ;;
            -h|--help) usage; exit 0 ;;
            -*) log_error "Unknown option: $1"; usage; exit 1 ;;
            *) break ;;
        esac
    done
    validate_deployment "$PRIMR_DEPLOYMENT" || exit 1
    local cmd="${1:-}"; shift || true
    case "$cmd" in
        deploy) cmd_deploy ;; destroy) cmd_destroy "${1:-}" ;; validate) cmd_validate ;;
        secrets) cmd_secrets "$@" ;; "") usage; exit 1 ;;
        *) log_error "Unknown command: $cmd"; usage; exit 1 ;;
    esac
}

main "$@"
