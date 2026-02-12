#!/usr/bin/env bash
# =============================================================================
# Primr Cloud Deployment - Shared Functions
# =============================================================================
# Common utilities for AWS, Azure, and GCP deployment scripts.
#
# Usage:
#   source "$(dirname "$0")/../lib/common.sh"
#
# Requirements: 5.8, 6.8, 7.8
# =============================================================================

set -euo pipefail

# =============================================================================
# COLORS AND OUTPUT
# =============================================================================

# Check if terminal supports colors
if [[ -t 1 ]] && command -v tput &>/dev/null && [[ $(tput colors 2>/dev/null || echo 0) -ge 8 ]]; then
    RED=$(tput setaf 1)
    GREEN=$(tput setaf 2)
    YELLOW=$(tput setaf 3)
    BLUE=$(tput setaf 4)
    MAGENTA=$(tput setaf 5)
    CYAN=$(tput setaf 6)
    BOLD=$(tput bold)
    RESET=$(tput sgr0)
else
    RED=""
    GREEN=""
    YELLOW=""
    BLUE=""
    MAGENTA=""
    CYAN=""
    BOLD=""
    RESET=""
fi

# Logging functions
log_info() {
    echo "${BLUE}[INFO]${RESET} $*"
}

log_success() {
    echo "${GREEN}[SUCCESS]${RESET} $*"
}

log_warn() {
    echo "${YELLOW}[WARN]${RESET} $*" >&2
}

log_error() {
    echo "${RED}[ERROR]${RESET} $*" >&2
}

log_step() {
    echo ""
    echo "${BOLD}${CYAN}==> $*${RESET}"
}

log_substep() {
    echo "    ${MAGENTA}->$RESET $*"
}

# =============================================================================
# PREREQUISITE CHECKING
# =============================================================================

# Check if a command exists
check_command() {
    local cmd="$1"
    local install_hint="${2:-}"
    
    if ! command -v "$cmd" &>/dev/null; then
        log_error "Required command not found: $cmd"
        if [[ -n "$install_hint" ]]; then
            log_info "Install hint: $install_hint"
        fi
        return 1
    fi
    return 0
}

# Check Docker is available and running
check_docker() {
    if ! check_command "docker" "Install Docker from https://docs.docker.com/get-docker/"; then
        return 1
    fi
    
    if ! docker info &>/dev/null; then
        log_error "Docker daemon is not running"
        log_info "Start Docker Desktop or run: sudo systemctl start docker"
        return 1
    fi
    
    log_substep "Docker: $(docker --version | head -1)"
    return 0
}

# Check AWS CLI is available and configured
check_aws_cli() {
    if ! check_command "aws" "Install AWS CLI from https://aws.amazon.com/cli/"; then
        return 1
    fi
    
    # Check if credentials are configured
    if ! aws sts get-caller-identity &>/dev/null; then
        log_error "AWS credentials not configured or invalid"
        log_info "Run: aws configure"
        return 1
    fi
    
    local account_id
    account_id=$(aws sts get-caller-identity --query Account --output text)
    log_substep "AWS CLI: $(aws --version | head -1)"
    log_substep "AWS Account: $account_id"
    return 0
}

# Check Azure CLI is available and logged in
check_azure_cli() {
    if ! check_command "az" "Install Azure CLI from https://docs.microsoft.com/cli/azure/install-azure-cli"; then
        return 1
    fi
    
    # Check if logged in
    if ! az account show &>/dev/null; then
        log_error "Not logged in to Azure"
        log_info "Run: az login"
        return 1
    fi
    
    local subscription
    subscription=$(az account show --query name --output tsv)
    log_substep "Azure CLI: $(az --version | head -1)"
    log_substep "Azure Subscription: $subscription"
    return 0
}

# Check GCP CLI is available and configured
check_gcp_cli() {
    if ! check_command "gcloud" "Install gcloud from https://cloud.google.com/sdk/docs/install"; then
        return 1
    fi
    
    # Check if authenticated
    if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | head -1 | grep -q .; then
        log_error "Not authenticated with GCP"
        log_info "Run: gcloud auth login"
        return 1
    fi
    
    local project
    project=$(gcloud config get-value project 2>/dev/null || echo "not set")
    log_substep "gcloud: $(gcloud --version | head -1)"
    log_substep "GCP Project: $project"
    return 0
}

# Check jq is available
check_jq() {
    check_command "jq" "Install jq from https://stedolan.github.io/jq/download/"
}

# =============================================================================
# CONFIGURATION LOADING
# =============================================================================

# Default configuration values
PRIMR_DEPLOYMENT="${PRIMR_DEPLOYMENT:-dev}"
PRIMR_REGION="${PRIMR_REGION:-}"
PRIMR_PREFIX="${PRIMR_PREFIX:-primr}"

# Load configuration from file if exists
load_config() {
    local config_file="${1:-deploy.conf}"
    
    if [[ -f "$config_file" ]]; then
        log_info "Loading configuration from $config_file"
        # shellcheck source=/dev/null
        source "$config_file"
    fi
    
    # Export common variables
    export PRIMR_DEPLOYMENT
    export PRIMR_REGION
    export PRIMR_PREFIX
}

# Get resource name with prefix and deployment
resource_name() {
    local name="$1"
    echo "${PRIMR_PREFIX}-${name}-${PRIMR_DEPLOYMENT}"
}

# Get short resource name (for resources with length limits)
short_resource_name() {
    local name="$1"
    local max_len="${2:-24}"
    local full_name="${PRIMR_PREFIX}-${name}-${PRIMR_DEPLOYMENT}"
    echo "${full_name:0:$max_len}"
}

# =============================================================================
# SECRETS MANAGEMENT
# =============================================================================

# Validate secret name format
validate_secret_name() {
    local name="$1"
    
    # Only allow alphanumeric, hyphens, underscores
    if [[ ! "$name" =~ ^[a-zA-Z0-9_-]+$ ]]; then
        log_error "Invalid secret name: $name"
        log_info "Secret names must contain only alphanumeric characters, hyphens, and underscores"
        return 1
    fi
    return 0
}

# Read secret value from stdin or file
read_secret_value() {
    local source="${1:--}"
    
    if [[ "$source" == "-" ]]; then
        # Read from stdin
        cat
    elif [[ -f "$source" ]]; then
        # Read from file
        cat "$source"
    else
        log_error "Secret source not found: $source"
        return 1
    fi
}

# =============================================================================
# DOCKER UTILITIES
# =============================================================================

# Build Docker image
build_image() {
    local dockerfile="$1"
    local tag="$2"
    local context="${3:-.}"
    
    log_step "Building Docker image: $tag"
    
    docker build \
        --file "$dockerfile" \
        --tag "$tag" \
        --build-arg "BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        --build-arg "VERSION=${PRIMR_VERSION:-dev}" \
        "$context"
    
    log_success "Image built: $tag"
}

# Push Docker image to registry
push_image() {
    local tag="$1"
    
    log_step "Pushing Docker image: $tag"
    docker push "$tag"
    log_success "Image pushed: $tag"
}

# =============================================================================
# VALIDATION UTILITIES
# =============================================================================

# Validate deployment name
validate_deployment() {
    local deployment="$1"
    
    # Only allow alphanumeric and hyphens, 3-20 chars
    if [[ ! "$deployment" =~ ^[a-z0-9-]{3,20}$ ]]; then
        log_error "Invalid deployment name: $deployment"
        log_info "Deployment names must be 3-20 lowercase alphanumeric characters or hyphens"
        return 1
    fi
    return 0
}

# Validate URL format
validate_url() {
    local url="$1"
    
    if [[ ! "$url" =~ ^https?:// ]]; then
        log_error "Invalid URL: $url"
        log_info "URLs must start with http:// or https://"
        return 1
    fi
    return 0
}

# =============================================================================
# WAIT UTILITIES
# =============================================================================

# Wait for a condition with timeout
wait_for() {
    local description="$1"
    local check_cmd="$2"
    local timeout="${3:-300}"
    local interval="${4:-5}"
    
    log_info "Waiting for $description (timeout: ${timeout}s)..."
    
    local elapsed=0
    while [[ $elapsed -lt $timeout ]]; do
        if eval "$check_cmd" &>/dev/null; then
            log_success "$description ready"
            return 0
        fi
        sleep "$interval"
        elapsed=$((elapsed + interval))
        echo -n "."
    done
    
    echo ""
    log_error "Timeout waiting for $description"
    return 1
}

# =============================================================================
# CLEANUP UTILITIES
# =============================================================================

# Trap handler for cleanup
cleanup_on_exit() {
    local exit_code=$?
    
    if [[ $exit_code -ne 0 ]]; then
        log_error "Script failed with exit code $exit_code"
    fi
    
    # Call custom cleanup function if defined
    if declare -f cleanup &>/dev/null; then
        cleanup
    fi
    
    exit $exit_code
}

# Register cleanup handler
register_cleanup() {
    trap cleanup_on_exit EXIT INT TERM
}

# =============================================================================
# HELP UTILITIES
# =============================================================================

# Print usage header
print_usage_header() {
    local script_name="$1"
    local description="$2"
    
    echo ""
    echo "${BOLD}$script_name${RESET} - $description"
    echo ""
}

# Print usage command
print_usage_command() {
    local command="$1"
    local description="$2"
    
    printf "  ${GREEN}%-15s${RESET} %s\n" "$command" "$description"
}

# Print usage option
print_usage_option() {
    local option="$1"
    local description="$2"
    
    printf "  ${YELLOW}%-20s${RESET} %s\n" "$option" "$description"
}

# =============================================================================
# VERSION INFO
# =============================================================================

COMMON_SH_VERSION="1.0.0"

print_version() {
    echo "Primr Cloud Deployment Scripts v${COMMON_SH_VERSION}"
    echo "Deployment: ${PRIMR_DEPLOYMENT}"
    echo "Prefix: ${PRIMR_PREFIX}"
}
