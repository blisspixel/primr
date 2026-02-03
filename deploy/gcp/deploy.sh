#!/usr/bin/env bash
# =============================================================================
# Primr GCP Deployment Script (REFERENCE TEMPLATE)
# =============================================================================
# Deploy Primr to GCP using:
# - Artifact Registry for container registry
# - Cloud Run for control plane API
# - Pub/Sub for job queue
# - Cloud Run Jobs for job execution
# - GCS for artifact storage
# - Firestore for job state
# - Secret Manager for LLM keys (runner only)
#
# NOTE: This is a reference template. AWS deployment is the primary target.
#
# Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# =============================================================================
# CONFIGURATION
# =============================================================================

load_config "$SCRIPT_DIR/deploy.conf"

GCP_REGION="${PRIMR_REGION:-us-central1}"
GCP_PROJECT="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
AR_REPO="$(resource_name "repo")"
SERVICE_NAME="$(resource_name "api")"
JOB_NAME="$(resource_name "runner")"
PUBSUB_TOPIC="$(resource_name "jobs")"
PUBSUB_SUB="$(resource_name "jobs-sub")"
GCS_BUCKET="$(short_resource_name "artifacts" 63)"
SECRET_PREFIX="$(resource_name "")"

# =============================================================================
# PREREQUISITE CHECKS
# =============================================================================

check_prerequisites() {
    log_step "Checking prerequisites"
    check_docker || exit 1
    check_gcp_cli || exit 1
    check_jq || exit 1
    [[ -z "$GCP_PROJECT" ]] && { log_error "GCP project not set"; exit 1; }
    log_success "All prerequisites met"
}

# =============================================================================
# ARTIFACT REGISTRY
# =============================================================================

create_artifact_registry() {
    log_step "Creating Artifact Registry: $AR_REPO"
    if gcloud artifacts repositories describe "$AR_REPO" --location="$GCP_REGION" &>/dev/null; then
        log_info "Artifact Registry already exists"
    else
        gcloud artifacts repositories create "$AR_REPO" \
            --repository-format=docker --location="$GCP_REGION" \
            --description="Primr container images"
        log_success "Artifact Registry created"
    fi
}

push_to_ar() {
    log_step "Building and pushing Docker image to Artifact Registry"
    gcloud auth configure-docker "$GCP_REGION-docker.pkg.dev" --quiet
    local image="$GCP_REGION-docker.pkg.dev/$GCP_PROJECT/$AR_REPO/primr-runner:$PRIMR_DEPLOYMENT"
    build_image "$SCRIPT_DIR/../Dockerfile" "$image" "$SCRIPT_DIR/../.."
    push_image "$image"
}

# =============================================================================
# GCS
# =============================================================================

create_gcs_bucket() {
    log_step "Creating GCS bucket: $GCS_BUCKET"
    if gsutil ls -b "gs://$GCS_BUCKET" &>/dev/null; then
        log_info "GCS bucket already exists"
    else
        gsutil mb -l "$GCP_REGION" "gs://$GCS_BUCKET"
        gsutil versioning set on "gs://$GCS_BUCKET"
        gsutil uniformbucketlevelaccess set on "gs://$GCS_BUCKET"
        log_success "GCS bucket created"
    fi
}

# =============================================================================
# FIRESTORE
# =============================================================================

create_firestore() {
    log_step "Creating Firestore database"
    if gcloud firestore databases describe --database="(default)" &>/dev/null; then
        log_info "Firestore already exists"
    else
        gcloud firestore databases create --location="$GCP_REGION" --type=firestore-native
        log_success "Firestore created"
    fi
}

# =============================================================================
# PUB/SUB
# =============================================================================

create_pubsub() {
    log_step "Creating Pub/Sub topic: $PUBSUB_TOPIC"
    if gcloud pubsub topics describe "$PUBSUB_TOPIC" &>/dev/null; then
        log_info "Pub/Sub topic already exists"
    else
        gcloud pubsub topics create "$PUBSUB_TOPIC"
        gcloud pubsub subscriptions create "$PUBSUB_SUB" --topic="$PUBSUB_TOPIC" \
            --ack-deadline=600 --message-retention-duration=7d
        log_success "Pub/Sub created"
    fi
}

# =============================================================================
# SECRET MANAGER
# =============================================================================

set_secret() {
    local name="$1"
    local value="${2:--}"
    validate_secret_name "$name" || return 1
    local secret_name="${SECRET_PREFIX}${name}"
    local secret_value
    secret_value=$(read_secret_value "$value")
    log_step "Setting secret: $secret_name"
    
    if gcloud secrets describe "$secret_name" &>/dev/null; then
        echo -n "$secret_value" | gcloud secrets versions add "$secret_name" --data-file=-
    else
        echo -n "$secret_value" | gcloud secrets create "$secret_name" --data-file=- \
            --replication-policy=automatic
    fi
    log_success "Secret set"
}

list_secrets() {
    log_step "Listing secrets with prefix: $SECRET_PREFIX"
    gcloud secrets list --filter="name:$SECRET_PREFIX" --format="table(name)"
}

# =============================================================================
# CLOUD RUN JOBS
# =============================================================================

create_cloud_run_job() {
    log_step "Creating Cloud Run Job: $JOB_NAME"
    local image="$GCP_REGION-docker.pkg.dev/$GCP_PROJECT/$AR_REPO/primr-runner:$PRIMR_DEPLOYMENT"
    
    if gcloud run jobs describe "$JOB_NAME" --region="$GCP_REGION" &>/dev/null; then
        log_info "Cloud Run Job already exists, updating..."
        gcloud run jobs update "$JOB_NAME" --region="$GCP_REGION" \
            --image="$image" --cpu=2 --memory=4Gi --task-timeout=7200s \
            --set-env-vars="DEPLOYMENT=$PRIMR_DEPLOYMENT,ARTIFACT_STORE_URL=gs://$GCS_BUCKET" \
            --set-secrets="OPENAI_API_KEY=${SECRET_PREFIX}OPENAI_API_KEY:latest"
    else
        gcloud run jobs create "$JOB_NAME" --region="$GCP_REGION" \
            --image="$image" --cpu=2 --memory=4Gi --task-timeout=7200s \
            --set-env-vars="DEPLOYMENT=$PRIMR_DEPLOYMENT,ARTIFACT_STORE_URL=gs://$GCS_BUCKET" \
            --set-secrets="OPENAI_API_KEY=${SECRET_PREFIX}OPENAI_API_KEY:latest"
        log_success "Cloud Run Job created"
    fi
}

# =============================================================================
# COMMANDS
# =============================================================================

cmd_deploy() {
    log_step "Deploying Primr to GCP"
    log_info "Deployment: $PRIMR_DEPLOYMENT"
    log_info "Project: $GCP_PROJECT"
    log_info "Region: $GCP_REGION"
    
    check_prerequisites
    create_artifact_registry
    push_to_ar
    create_gcs_bucket
    create_firestore
    create_pubsub
    create_cloud_run_job
    
    log_success "Deployment complete!"
    log_info "Next steps:"
    log_info "  1. Set LLM API keys: $0 secrets set OPENAI_API_KEY"
    log_info "  2. Validate deployment: $0 validate"
}

cmd_destroy() {
    log_step "Destroying Primr GCP deployment"
    log_warn "This will delete all resources for deployment: $PRIMR_DEPLOYMENT"
    read -p "Are you sure? (yes/no): " confirm
    [[ "$confirm" != "yes" ]] && { log_info "Aborted"; return 1; }
    
    check_prerequisites
    
    # Delete in reverse order
    gcloud run jobs delete "$JOB_NAME" --region="$GCP_REGION" --quiet 2>/dev/null || true
    gcloud pubsub subscriptions delete "$PUBSUB_SUB" --quiet 2>/dev/null || true
    gcloud pubsub topics delete "$PUBSUB_TOPIC" --quiet 2>/dev/null || true
    gsutil rm -r "gs://$GCS_BUCKET" 2>/dev/null || true
    gcloud artifacts repositories delete "$AR_REPO" --location="$GCP_REGION" --quiet 2>/dev/null || true
    
    log_success "Destroy complete"
}

cmd_validate() {
    log_step "Validating GCP deployment"
    check_prerequisites
    local errors=0
    
    gcloud artifacts repositories describe "$AR_REPO" --location="$GCP_REGION" &>/dev/null && \
        log_substep "Artifact Registry: OK" || { log_error "Artifact Registry not found"; ((errors++)); }
    gsutil ls -b "gs://$GCS_BUCKET" &>/dev/null && \
        log_substep "GCS bucket: OK" || { log_error "GCS bucket not found"; ((errors++)); }
    gcloud pubsub topics describe "$PUBSUB_TOPIC" &>/dev/null && \
        log_substep "Pub/Sub topic: OK" || { log_error "Pub/Sub topic not found"; ((errors++)); }
    gcloud run jobs describe "$JOB_NAME" --region="$GCP_REGION" &>/dev/null && \
        log_substep "Cloud Run Job: OK" || { log_error "Cloud Run Job not found"; ((errors++)); }
    
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
    print_usage_header "deploy.sh" "Deploy Primr to GCP (REFERENCE)"
    echo "Commands:"; print_usage_command "deploy" "Deploy all GCP resources"
    print_usage_command "destroy" "Tear down all GCP resources"
    print_usage_command "validate" "Validate deployed resources"
    print_usage_command "secrets" "Manage secrets (set, list)"
}

main() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -d|--deployment) PRIMR_DEPLOYMENT="$2"; shift 2 ;;
            -r|--region) GCP_REGION="$2"; PRIMR_REGION="$2"; shift 2 ;;
            -p|--project) GCP_PROJECT="$2"; shift 2 ;;
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
