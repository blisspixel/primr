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

# Configurable parameters (set via CLI flags)
DEPLOY_TIER="${DEPLOY_TIER:-team}"
USE_BICEP=false
BUDGET_AMOUNT=""
MIN_REPLICAS=1
MAX_REPLICAS=1
SKIP_SMOKE_TEST=false
LLM_ROUTING="${LLM_ROUTING:-direct}"
AZURE_OPENAI_ENDPOINT=""
AZURE_OPENAI_DEPLOYMENT=""

# =============================================================================
# TIER HELPERS
# =============================================================================

is_org_tier() {
    [[ "$DEPLOY_TIER" == "organization" ]]
}

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
            --sku Basic
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
        --runtime-version 3.12 \
        --functions-version 4 \
        --os-type Linux \
        --assign-identity "$identity_id" \
        --tags Deployment="$PRIMR_DEPLOYMENT"
    
    # Get Cosmos DB endpoint (use managed identity instead of connection string)
    local cosmos_endpoint
    cosmos_endpoint=$(az cosmosdb show --name "$COSMOS_ACCOUNT" --resource-group "$RESOURCE_GROUP" \
        --query documentEndpoint -o tsv)
    
    # Get Storage account name (use managed identity instead of connection string)
    
    # Configure app settings with Application Insights and managed identity
    az functionapp config appsettings set \
        --name "$FUNCTION_APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --settings \
            "COSMOS_ENDPOINT=$cosmos_endpoint" \
            "COSMOS_DATABASE=primr" \
            "COSMOS_CONTAINER=jobs" \
            "STORAGE_ACCOUNT_NAME=$STORAGE_ACCOUNT" \
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

    # Q3: Copy extracted function files instead of using heredocs
    local functions_src="$SCRIPT_DIR/functions"
    cp "$functions_src/host.json" "$temp_dir/host.json"
    cp "$functions_src/requirements.txt" "$temp_dir/requirements.txt"
    mkdir -p "$temp_dir/reconciler"
    cp "$functions_src/reconciler/function.json" "$temp_dir/reconciler/function.json"
    cp "$functions_src/reconciler/__init__.py" "$temp_dir/reconciler/__init__.py"
    
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
# BICEP DEPLOYMENT
# =============================================================================

cmd_deploy_bicep() {
    log_step "Deploying Primr to Azure via Bicep templates"
    log_info "Deployment: $PRIMR_DEPLOYMENT"
    log_info "Location: $AZURE_LOCATION"
    log_info "Tier: $DEPLOY_TIER"

    check_prerequisites
    create_resource_group

    # Build and push image first (Bicep needs the image in ACR)
    create_acr
    push_to_acr

    local bicep_file="$SCRIPT_DIR/bicep/main.bicep"
    if [[ ! -f "$bicep_file" ]]; then
        log_error "Bicep template not found: $bicep_file"
        exit 1
    fi

    local budget="${BUDGET_AMOUNT:-}"
    if [[ -z "$budget" ]]; then
        if is_org_tier; then budget=200; else budget=50; fi
    fi

    local params=(
        "deploymentName=$PRIMR_DEPLOYMENT"
        "location=$AZURE_LOCATION"
        "resourcePrefix=$PRIMR_PREFIX"
        "tier=$DEPLOY_TIER"
        "minReplicas=$MIN_REPLICAS"
        "maxReplicas=$MAX_REPLICAS"
        "budgetAmount=$budget"
        "acrLoginServer=$ACR_NAME.azurecr.io"
        "imageName=primr-runner"
        "imageTag=$PRIMR_DEPLOYMENT"
        "contactEmails=[\"$PRIMR_DEPLOYMENT@primr.dev\"]"
        "llmRoutingMode=$LLM_ROUTING"
    )

    if [[ "$LLM_ROUTING" == "azure" ]]; then
        if [[ -n "$AZURE_OPENAI_ENDPOINT" ]]; then
            params+=("azureOpenaiEndpoint=$AZURE_OPENAI_ENDPOINT")
        fi
        if [[ -n "$AZURE_OPENAI_DEPLOYMENT" ]]; then
            params+=("azureOpenaiDeployment=$AZURE_OPENAI_DEPLOYMENT")
        fi
    fi

    log_step "Running az deployment group create"
    local param_args=()
    for p in "${params[@]}"; do
        param_args+=("$p")
    done

    az deployment group create \
        --resource-group "$RESOURCE_GROUP" \
        --template-file "$bicep_file" \
        --parameters "${param_args[@]}" \
        --name "$PRIMR_DEPLOYMENT-$(date +%Y%m%d%H%M%S)"

    log_success "Bicep deployment complete!"
    print_post_deploy_summary
}

# =============================================================================
# POST-DEPLOYMENT SUMMARY
# =============================================================================

print_post_deploy_summary() {
    log_step "Post-Deployment Summary"

    # MCP Server FQDN
    local fqdn=""
    fqdn=$(az containerapp show --name "$CONTAINER_APP_NAME" --resource-group "$RESOURCE_GROUP" \
        --query "properties.configuration.ingress.fqdn" -o tsv 2>/dev/null || echo "not-available")
    log_info "MCP Server FQDN:   https://${fqdn}"

    # Auth method
    local auth_method="API Key (Bearer token)"
    if is_org_tier; then
        auth_method="Entra ID + API Key"
    fi
    log_info "Auth Method:       ${auth_method}"

    # OpenAPI spec URL
    log_info "OpenAPI Spec URL:  https://${fqdn}/openapi.json"

    # LLM routing mode
    log_info "LLM Routing:       ${LLM_ROUTING}"

    log_info "MCP Replicas:      1 persistent controller"
    log_info "Pricing:           Verify for the selected region and configuration"

    echo ""
    log_success "Deployment ready!"
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
    log_info "Tier: $DEPLOY_TIER"
    log_info "LLM Routing: $LLM_ROUTING"
    
    check_prerequisites
    create_resource_group
    create_acr
    push_to_acr
    create_storage
    create_cosmos
    create_key_vault

    # Organization-tier resources only
    if is_org_tier; then
        create_service_bus
        create_app_insights
    fi

    create_managed_identity
    create_container_app_env
    create_container_app_job

    # Organization-tier: reconciler function
    if is_org_tier; then
        create_function_storage
        create_reconciler_function
    fi

    # Budget alert (if --budget was specified)
    if [[ -n "${BUDGET_AMOUNT:-}" ]]; then
        log_step "Configuring budget alert: \$${BUDGET_AMOUNT}/month"
        log_info "Budget alerts will be created via Bicep or Azure portal"
    fi
    
    log_success "Deployment complete!"
    print_post_deploy_summary
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
    log_step "Validating Azure deployment (tier: $DEPLOY_TIER)"
    check_prerequisites
    local errors=0

    # Core resources (both tiers)
    az group show --name "$RESOURCE_GROUP" &>/dev/null && log_substep "Resource group: OK" || { log_error "Resource group not found"; ((errors++)); }
    az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" &>/dev/null && log_substep "ACR: OK" || { log_error "ACR not found"; ((errors++)); }
    az storage account show --name "$STORAGE_ACCOUNT" --resource-group "$RESOURCE_GROUP" &>/dev/null && log_substep "Storage: OK" || { log_error "Storage not found"; ((errors++)); }
    az cosmosdb show --name "$COSMOS_ACCOUNT" --resource-group "$RESOURCE_GROUP" &>/dev/null && log_substep "Cosmos DB: OK" || { log_error "Cosmos DB not found"; ((errors++)); }
    az keyvault show --name "$KEY_VAULT_NAME" --resource-group "$RESOURCE_GROUP" &>/dev/null && log_substep "Key Vault: OK" || { log_error "Key Vault not found"; ((errors++)); }
    az identity show --name "$MANAGED_IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" &>/dev/null && log_substep "Managed Identity: OK" || { log_error "Managed Identity not found"; ((errors++)); }

    # Organization-tier resources only
    if is_org_tier; then
        az monitor app-insights component show --app "$APP_INSIGHTS_NAME" --resource-group "$RESOURCE_GROUP" &>/dev/null && log_substep "Application Insights: OK" || { log_error "Application Insights not found"; ((errors++)); }
        az servicebus namespace show --name "$SERVICE_BUS_NS" --resource-group "$RESOURCE_GROUP" &>/dev/null && log_substep "Service Bus: OK" || { log_error "Service Bus not found"; ((errors++)); }
        az functionapp show --name "$FUNCTION_APP_NAME" --resource-group "$RESOURCE_GROUP" &>/dev/null && log_substep "Reconciler Function: OK" || { log_error "Reconciler Function not found"; ((errors++)); }
    fi

    if [[ $errors -eq 0 ]]; then
        log_success "All resources validated"
    else
        log_error "$errors resource(s) missing"
        return 1
    fi

    # Smoke test (unless --skip-smoke-test)
    if [[ "$SKIP_SMOKE_TEST" == "false" ]]; then
        log_step "Running smoke test"
        local fqdn
        fqdn=$(az containerapp show --name "$CONTAINER_APP_NAME" --resource-group "$RESOURCE_GROUP" \
            --query "properties.configuration.ingress.fqdn" -o tsv 2>/dev/null || echo "")

        if [[ -z "$fqdn" ]]; then
            log_error "Cannot determine Container App FQDN"
            return 1
        else
            local smoke_errors=0

            # 1. Health check
            log_substep "Checking /healthz ..."
            local health_status
            health_status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://${fqdn}/healthz" 2>/dev/null || echo "000")
            if [[ "$health_status" == "200" ]]; then
                log_substep "/healthz: PASS (HTTP $health_status)"
            else
                log_error "/healthz: FAIL (HTTP $health_status)"
                ((smoke_errors++))
            fi

            # 2. Controller readiness
            log_substep "Checking /readyz ..."
            local readiness_status
            readiness_status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://${fqdn}/readyz" 2>/dev/null || echo "000")
            if [[ "$readiness_status" == "200" ]]; then
                log_substep "/readyz: PASS (HTTP $readiness_status)"
            else
                log_error "/readyz: FAIL (HTTP $readiness_status)"
                ((smoke_errors++))
            fi

            # 3. MCP tools/list JSON-RPC request
            log_substep "Checking /mcp tools/list ..."
            local mcp_body='{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
            local mcp_status
            mcp_status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
                -X POST "https://${fqdn}/mcp" \
                -H "Content-Type: application/json" \
                -d "$mcp_body" 2>/dev/null || echo "000")
            if [[ "$mcp_status" == "200" || "$mcp_status" == "401" ]]; then
                # 401 is acceptable — it means the endpoint is live but requires auth
                log_substep "/mcp tools/list: PASS (HTTP $mcp_status)"
            else
                log_error "/mcp tools/list: FAIL (HTTP $mcp_status)"
                ((smoke_errors++))
            fi

            if [[ $smoke_errors -eq 0 ]]; then
                log_success "Smoke test passed"
            else
                log_error "Smoke test failed ($smoke_errors check(s))"
                return 1
            fi
        fi
    else
        log_info "Smoke test skipped (--skip-smoke-test)"
    fi
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
    print_usage_header "deploy.sh" "Deploy Primr to Azure"
    echo "Commands:"
    print_usage_command "deploy" "Deploy all Azure resources"
    print_usage_command "destroy [--force]" "Tear down all Azure resources (--force skips confirmation)"
    print_usage_command "validate" "Validate deployed resources and run smoke test"
    print_usage_command "secrets" "Manage secrets (set, list)"
    echo ""
    echo "Options:"
    print_usage_option "-d, --deployment" "Deployment name (default: dev)"
    print_usage_option "-r, --region" "Azure region (default: eastus)"
    print_usage_option "--tier" "Deployment tier: team (default) or organization"
    print_usage_option "--bicep" "Use Bicep templates instead of imperative CLI"
    print_usage_option "--budget N" "Monthly Azure budget alert threshold in USD"
    print_usage_option "--min-replicas N" "MCP controller minimum; only 1 is supported"
    print_usage_option "--max-replicas N" "MCP controller maximum; only 1 is supported"
    print_usage_option "--skip-smoke-test" "Skip smoke test during validate"
    print_usage_option "--llm-routing" "LLM routing mode: direct (default) or azure"
    print_usage_option "--azure-openai-endpoint" "Azure OpenAI endpoint URL (when --llm-routing azure)"
    print_usage_option "--azure-openai-deployment" "Azure OpenAI deployment name (when --llm-routing azure)"
    echo ""
    echo "Examples:"
    echo "  $0 --tier team -d prod deploy"
    echo "  $0 --tier organization --bicep -d prod deploy"
    echo "  $0 --budget 100 -d prod deploy"
    echo "  $0 --llm-routing azure --azure-openai-endpoint https://myoai.openai.azure.com -d prod deploy"
    echo "  $0 -d prod validate --skip-smoke-test"
}

main() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -d|--deployment) PRIMR_DEPLOYMENT="$2"; shift 2 ;;
            -r|--region) AZURE_LOCATION="$2"; PRIMR_REGION="$2"; shift 2 ;;
            --tier)
                if [[ "$2" != "team" && "$2" != "organization" ]]; then
                    log_error "Invalid tier: $2 (must be 'team' or 'organization')"
                    exit 1
                fi
                DEPLOY_TIER="$2"; shift 2 ;;
            --bicep) USE_BICEP=true; shift ;;
            --budget)
                if ! [[ "$2" =~ ^[0-9]+$ ]]; then
                    log_error "Invalid budget: $2 (must be a positive integer)"
                    exit 1
                fi
                BUDGET_AMOUNT="$2"; shift 2 ;;
            --min-replicas)
                if [[ "$2" != "1" ]]; then
                    log_error "Invalid min-replicas: $2 (the MCP controller requires exactly 1)"
                    exit 1
                fi
                MIN_REPLICAS="$2"; shift 2 ;;
            --max-replicas)
                if [[ "$2" != "1" ]]; then
                    log_error "Invalid max-replicas: $2 (the MCP controller requires exactly 1)"
                    exit 1
                fi
                MAX_REPLICAS="$2"; shift 2 ;;
            --skip-smoke-test) SKIP_SMOKE_TEST=true; shift ;;
            --llm-routing)
                if [[ "$2" != "direct" && "$2" != "azure" ]]; then
                    log_error "Invalid llm-routing: $2 (must be 'direct' or 'azure')"
                    exit 1
                fi
                LLM_ROUTING="$2"; shift 2 ;;
            --azure-openai-endpoint) AZURE_OPENAI_ENDPOINT="$2"; shift 2 ;;
            --azure-openai-deployment) AZURE_OPENAI_DEPLOYMENT="$2"; shift 2 ;;
            -h|--help) usage; exit 0 ;;
            -*) log_error "Unknown option: $1"; usage; exit 1 ;;
            *) break ;;
        esac
    done

    # Validate --llm-routing azure requires endpoint
    if [[ "$LLM_ROUTING" == "azure" && -z "$AZURE_OPENAI_ENDPOINT" ]]; then
        log_error "--azure-openai-endpoint is required when --llm-routing azure"
        exit 1
    fi

    validate_deployment "$PRIMR_DEPLOYMENT" || exit 1

    # L6: Enforce Azure naming constraints (lowercase alphanumeric + hyphens, 3-24 chars, starts with letter)
    if [[ ! "$PRIMR_DEPLOYMENT" =~ ^[a-z][a-z0-9-]{2,23}$ ]]; then
        log_error "Deployment name must be 3-24 chars, lowercase alphanumeric + hyphens, starting with a letter"
        exit 1
    fi

    local cmd="${1:-}"; shift || true
    case "$cmd" in
        deploy)
            if [[ "$USE_BICEP" == "true" ]]; then
                cmd_deploy_bicep
            else
                cmd_deploy
            fi
            ;;
        destroy) cmd_destroy "${1:-}" ;;
        validate) cmd_validate ;;
        secrets) cmd_secrets "$@" ;;
        "") usage; exit 1 ;;
        *) log_error "Unknown command: $cmd"; usage; exit 1 ;;
    esac
}

main "$@"
