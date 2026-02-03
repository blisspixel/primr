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
            --default-consistency-level Session --enable-automatic-failover false
        az cosmosdb sql database create --account-name "$COSMOS_ACCOUNT" \
            --resource-group "$RESOURCE_GROUP" --name primr
        az cosmosdb sql container create --account-name "$COSMOS_ACCOUNT" \
            --resource-group "$RESOURCE_GROUP" --database-name primr --name jobs \
            --partition-key-path /job_id --throughput 400
        log_success "Cosmos DB created"
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
    create_container_app_env
    create_container_app_job
    
    log_success "Deployment complete!"
    log_info "Next steps:"
    log_info "  1. Set LLM API keys: $0 secrets set OPENAI-API-KEY"
    log_info "  2. Validate deployment: $0 validate"
}

cmd_destroy() {
    log_step "Destroying Primr Azure deployment"
    log_warn "This will delete resource group: $RESOURCE_GROUP"
    read -p "Are you sure? (yes/no): " confirm
    [[ "$confirm" != "yes" ]] && { log_info "Aborted"; return 1; }
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
    print_usage_command "destroy" "Tear down all Azure resources"
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
        deploy) cmd_deploy ;; destroy) cmd_destroy ;; validate) cmd_validate ;;
        secrets) cmd_secrets "$@" ;; "") usage; exit 1 ;;
        *) log_error "Unknown command: $cmd"; usage; exit 1 ;;
    esac
}

main "$@"
