#!/usr/bin/env bash
# =============================================================================
# Primr AWS Deployment Script
# =============================================================================
# Deploy Primr to AWS using:
# - ECR for container registry
# - Lambda for control plane API
# - SQS FIFO for job queue
# - Step Functions for job orchestration
# - Fargate for job execution
# - S3 for artifact storage
# - DynamoDB for job state
# - Secrets Manager for LLM keys (runner only)
#
# Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# =============================================================================
# CONFIGURATION
# =============================================================================

# Load configuration
load_config "$SCRIPT_DIR/deploy.conf"

# AWS-specific defaults
AWS_REGION="${PRIMR_REGION:-us-east-1}"
ECR_REPO_NAME="$(resource_name "runner")"
LAMBDA_FUNCTION_NAME="$(resource_name "api")"
SQS_QUEUE_NAME="$(resource_name "jobs").fifo"
STEP_FUNCTION_NAME="$(resource_name "orchestrator")"
ECS_CLUSTER_NAME="$(resource_name "cluster")"
ECS_TASK_FAMILY="$(resource_name "runner")"
S3_BUCKET_NAME="$(short_resource_name "artifacts" 63)"
DYNAMODB_TABLE_NAME="$(resource_name "jobs")"
SECRET_PREFIX="$(resource_name "")"

# Derived values
AWS_ACCOUNT_ID=""
ECR_REPO_URI=""

# =============================================================================
# PREREQUISITE CHECKS
# =============================================================================

check_prerequisites() {
    log_step "Checking prerequisites"
    
    check_docker || exit 1
    check_aws_cli || exit 1
    check_jq || exit 1
    
    # Get AWS account ID
    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    ECR_REPO_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}"
    
    log_success "All prerequisites met"
}

# =============================================================================
# ECR OPERATIONS
# =============================================================================

create_ecr_repo() {
    log_step "Creating ECR repository: $ECR_REPO_NAME"
    
    if aws ecr describe-repositories --repository-names "$ECR_REPO_NAME" --region "$AWS_REGION" &>/dev/null; then
        log_info "ECR repository already exists"
    else
        aws ecr create-repository \
            --repository-name "$ECR_REPO_NAME" \
            --region "$AWS_REGION" \
            --image-scanning-configuration scanOnPush=true \
            --encryption-configuration encryptionType=AES256
        
        # Add lifecycle policy to limit image count (keep last 10 images)
        aws ecr put-lifecycle-policy \
            --repository-name "$ECR_REPO_NAME" \
            --region "$AWS_REGION" \
            --lifecycle-policy-text '{
                "rules": [{
                    "rulePriority": 1,
                    "description": "Keep last 10 images",
                    "selection": {
                        "tagStatus": "any",
                        "countType": "imageCountMoreThan",
                        "countNumber": 10
                    },
                    "action": {"type": "expire"}
                }]
            }'
        
        log_success "ECR repository created with lifecycle policy"
    fi
}

push_to_ecr() {
    log_step "Building and pushing Docker image to ECR"
    
    # Login to ECR
    aws ecr get-login-password --region "$AWS_REGION" | \
        docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
    
    # Build image
    build_image "$SCRIPT_DIR/../Dockerfile" "$ECR_REPO_URI:latest" "$SCRIPT_DIR/../.."
    
    # Tag with deployment
    docker tag "$ECR_REPO_URI:latest" "$ECR_REPO_URI:$PRIMR_DEPLOYMENT"
    
    # Push
    push_image "$ECR_REPO_URI:latest"
    push_image "$ECR_REPO_URI:$PRIMR_DEPLOYMENT"
}

# =============================================================================
# S3 OPERATIONS
# =============================================================================

create_s3_bucket() {
    log_step "Creating S3 bucket: $S3_BUCKET_NAME"
    
    if aws s3api head-bucket --bucket "$S3_BUCKET_NAME" 2>/dev/null; then
        log_info "S3 bucket already exists"
    else
        # Create bucket (LocationConstraint not needed for us-east-1)
        if [[ "$AWS_REGION" == "us-east-1" ]]; then
            aws s3api create-bucket --bucket "$S3_BUCKET_NAME" --region "$AWS_REGION"
        else
            aws s3api create-bucket \
                --bucket "$S3_BUCKET_NAME" \
                --region "$AWS_REGION" \
                --create-bucket-configuration LocationConstraint="$AWS_REGION"
        fi
        
        # Enable versioning
        aws s3api put-bucket-versioning \
            --bucket "$S3_BUCKET_NAME" \
            --versioning-configuration Status=Enabled
        
        # Enable encryption
        aws s3api put-bucket-encryption \
            --bucket "$S3_BUCKET_NAME" \
            --server-side-encryption-configuration '{
                "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
            }'
        
        # Block public access
        aws s3api put-public-access-block \
            --bucket "$S3_BUCKET_NAME" \
            --public-access-block-configuration \
                "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
        
        # Add lifecycle rule to clean up old artifacts (30 days for non-current versions, 90 days for current)
        aws s3api put-bucket-lifecycle-configuration \
            --bucket "$S3_BUCKET_NAME" \
            --lifecycle-configuration '{
                "Rules": [
                    {
                        "ID": "CleanupOldArtifacts",
                        "Status": "Enabled",
                        "Filter": {"Prefix": ""},
                        "NoncurrentVersionExpiration": {"NoncurrentDays": 30},
                        "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7}
                    },
                    {
                        "ID": "TransitionToIA",
                        "Status": "Enabled",
                        "Filter": {"Prefix": ""},
                        "Transitions": [
                            {"Days": 30, "StorageClass": "STANDARD_IA"}
                        ]
                    }
                ]
            }'
        
        log_success "S3 bucket created with encryption, versioning, and lifecycle rules"
    fi
}

# =============================================================================
# DYNAMODB OPERATIONS
# =============================================================================

create_dynamodb_table() {
    log_step "Creating DynamoDB table: $DYNAMODB_TABLE_NAME"
    
    if aws dynamodb describe-table --table-name "$DYNAMODB_TABLE_NAME" --region "$AWS_REGION" &>/dev/null; then
        log_info "DynamoDB table already exists"
    else
        aws dynamodb create-table \
            --table-name "$DYNAMODB_TABLE_NAME" \
            --region "$AWS_REGION" \
            --attribute-definitions \
                AttributeName=job_id,AttributeType=S \
                AttributeName=status,AttributeType=S \
            --key-schema AttributeName=job_id,KeyType=HASH \
            --global-secondary-indexes \
                "[{\"IndexName\":\"status-index\",\"KeySchema\":[{\"AttributeName\":\"status\",\"KeyType\":\"HASH\"}],\"Projection\":{\"ProjectionType\":\"ALL\"}}]" \
            --billing-mode PAY_PER_REQUEST \
            --tags Key=Deployment,Value="$PRIMR_DEPLOYMENT"
        
        # Wait for table to be active
        aws dynamodb wait table-exists --table-name "$DYNAMODB_TABLE_NAME" --region "$AWS_REGION"
        
        # Enable TTL
        aws dynamodb update-time-to-live \
            --table-name "$DYNAMODB_TABLE_NAME" \
            --region "$AWS_REGION" \
            --time-to-live-specification Enabled=true,AttributeName=ttl
        
        log_success "DynamoDB table created with TTL enabled"
    fi
}

# =============================================================================
# SQS OPERATIONS
# =============================================================================

create_sqs_queue() {
    log_step "Creating SQS FIFO queue: $SQS_QUEUE_NAME"
    
    local queue_url
    queue_url=$(aws sqs get-queue-url --queue-name "$SQS_QUEUE_NAME" --region "$AWS_REGION" --query QueueUrl --output text 2>/dev/null || echo "")
    
    if [[ -n "$queue_url" ]]; then
        log_info "SQS queue already exists: $queue_url"
    else
        # Create dead-letter queue first
        local dlq_name="${SQS_QUEUE_NAME%.fifo}-dlq.fifo"
        local dlq_url
        dlq_url=$(aws sqs create-queue \
            --queue-name "$dlq_name" \
            --region "$AWS_REGION" \
            --attributes '{
                "FifoQueue": "true",
                "ContentBasedDeduplication": "true",
                "MessageRetentionPeriod": "1209600"
            }' \
            --tags Deployment="$PRIMR_DEPLOYMENT" \
            --query QueueUrl --output text)
        
        local dlq_arn
        dlq_arn=$(aws sqs get-queue-attributes --queue-url "$dlq_url" --region "$AWS_REGION" \
            --attribute-names QueueArn --query "Attributes.QueueArn" --output text)
        
        log_substep "Dead-letter queue created: $dlq_name"
        
        # Load queue configuration and add DLQ
        local queue_config="$SCRIPT_DIR/sqs-queue.json"
        local queue_attrs
        queue_attrs=$(cat "$queue_config" | jq --arg dlq_arn "$dlq_arn" \
            '. + {"RedrivePolicy": "{\"deadLetterTargetArn\":\"" + $dlq_arn + "\",\"maxReceiveCount\":\"3\"}"}')
        
        queue_url=$(aws sqs create-queue \
            --queue-name "$SQS_QUEUE_NAME" \
            --region "$AWS_REGION" \
            --attributes "$queue_attrs" \
            --tags Deployment="$PRIMR_DEPLOYMENT" \
            --query QueueUrl --output text)
        
        log_success "SQS FIFO queue created with DLQ: $queue_url"
    fi
    
    echo "$queue_url"
}

# =============================================================================
# ECS/FARGATE OPERATIONS
# =============================================================================

create_ecs_cluster() {
    log_step "Creating ECS cluster: $ECS_CLUSTER_NAME"
    
    if aws ecs describe-clusters --clusters "$ECS_CLUSTER_NAME" --region "$AWS_REGION" \
        --query "clusters[?status=='ACTIVE'].clusterName" --output text | grep -q "$ECS_CLUSTER_NAME"; then
        log_info "ECS cluster already exists"
    else
        aws ecs create-cluster \
            --cluster-name "$ECS_CLUSTER_NAME" \
            --region "$AWS_REGION" \
            --capacity-providers FARGATE FARGATE_SPOT \
            --default-capacity-provider-strategy \
                capacityProvider=FARGATE,weight=1 \
            --tags key=Deployment,value="$PRIMR_DEPLOYMENT"
        
        log_success "ECS cluster created"
    fi
}

create_task_definition() {
    log_step "Creating ECS task definition: $ECS_TASK_FAMILY"
    
    # Get execution role ARN
    local execution_role_arn
    execution_role_arn=$(get_or_create_execution_role)
    
    # Get task role ARN
    local task_role_arn
    task_role_arn=$(get_or_create_task_role)
    
    # Load and customize task definition
    local task_def
    task_def=$(cat "$SCRIPT_DIR/task-definition.json" | \
        jq --arg image "$ECR_REPO_URI:$PRIMR_DEPLOYMENT" \
           --arg family "$ECS_TASK_FAMILY" \
           --arg exec_role "$execution_role_arn" \
           --arg task_role "$task_role_arn" \
           --arg region "$AWS_REGION" \
           --arg bucket "$S3_BUCKET_NAME" \
           --arg deployment "$PRIMR_DEPLOYMENT" \
           --arg secret_prefix "$SECRET_PREFIX" \
           '.family = $family |
            .executionRoleArn = $exec_role |
            .taskRoleArn = $task_role |
            .containerDefinitions[0].image = $image |
            .containerDefinitions[0].environment += [
                {"name": "AWS_REGION", "value": $region},
                {"name": "ARTIFACT_STORE_URL", "value": ("s3://" + $bucket)},
                {"name": "DEPLOYMENT", "value": $deployment}
            ]')
    
    # Register task definition
    aws ecs register-task-definition \
        --region "$AWS_REGION" \
        --cli-input-json "$task_def"
    
    log_success "Task definition registered"
}

# =============================================================================
# IAM ROLES
# =============================================================================

get_or_create_execution_role() {
    local role_name="$(resource_name "ecs-execution")"
    
    if aws iam get-role --role-name "$role_name" &>/dev/null; then
        aws iam get-role --role-name "$role_name" --query Role.Arn --output text
        return
    fi
    
    log_substep "Creating ECS execution role: $role_name"
    
    # Create role with ECS trust policy
    aws iam create-role \
        --role-name "$role_name" \
        --assume-role-policy-document '{
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }]
        }'
    
    # Attach managed policy for ECR and CloudWatch
    aws iam attach-role-policy \
        --role-name "$role_name" \
        --policy-arn "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
    
    # Add Secrets Manager access for LLM keys
    aws iam put-role-policy \
        --role-name "$role_name" \
        --policy-name "SecretsAccess" \
        --policy-document "{
            \"Version\": \"2012-10-17\",
            \"Statement\": [{
                \"Effect\": \"Allow\",
                \"Action\": [\"secretsmanager:GetSecretValue\"],
                \"Resource\": \"arn:aws:secretsmanager:$AWS_REGION:$AWS_ACCOUNT_ID:secret:$SECRET_PREFIX*\"
            }]
        }"
    
    aws iam get-role --role-name "$role_name" --query Role.Arn --output text
}

get_or_create_task_role() {
    local role_name="$(resource_name "ecs-task")"
    
    if aws iam get-role --role-name "$role_name" &>/dev/null; then
        aws iam get-role --role-name "$role_name" --query Role.Arn --output text
        return
    fi
    
    log_substep "Creating ECS task role: $role_name"
    
    # Create role with ECS trust policy
    aws iam create-role \
        --role-name "$role_name" \
        --assume-role-policy-document '{
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }]
        }'
    
    # Add S3 access for artifacts
    aws iam put-role-policy \
        --role-name "$role_name" \
        --policy-name "S3ArtifactAccess" \
        --policy-document "{
            \"Version\": \"2012-10-17\",
            \"Statement\": [{
                \"Effect\": \"Allow\",
                \"Action\": [\"s3:PutObject\", \"s3:GetObject\", \"s3:ListBucket\"],
                \"Resource\": [
                    \"arn:aws:s3:::$S3_BUCKET_NAME\",
                    \"arn:aws:s3:::$S3_BUCKET_NAME/*\"
                ]
            }]
        }"
    
    aws iam get-role --role-name "$role_name" --query Role.Arn --output text
}

# =============================================================================
# STEP FUNCTIONS
# =============================================================================

create_step_function() {
    log_step "Creating Step Functions state machine: $STEP_FUNCTION_NAME"
    
    local state_machine_arn
    state_machine_arn=$(aws stepfunctions list-state-machines --region "$AWS_REGION" \
        --query "stateMachines[?name=='$STEP_FUNCTION_NAME'].stateMachineArn" --output text)
    
    if [[ -n "$state_machine_arn" ]]; then
        log_info "Step Functions state machine already exists"
        echo "$state_machine_arn"
        return
    fi
    
    # Get Step Functions role
    local sf_role_arn
    sf_role_arn=$(get_or_create_step_functions_role)
    
    # Load and customize state machine definition
    local definition
    definition=$(cat "$SCRIPT_DIR/step-function.json" | \
        jq --arg cluster "$ECS_CLUSTER_NAME" \
           --arg task_def "$ECS_TASK_FAMILY" \
           --arg table "$DYNAMODB_TABLE_NAME" \
           --arg region "$AWS_REGION" \
           '.')
    
    state_machine_arn=$(aws stepfunctions create-state-machine \
        --name "$STEP_FUNCTION_NAME" \
        --region "$AWS_REGION" \
        --definition "$definition" \
        --role-arn "$sf_role_arn" \
        --type STANDARD \
        --tags key=Deployment,value="$PRIMR_DEPLOYMENT" \
        --query stateMachineArn --output text)
    
    log_success "Step Functions state machine created"
    echo "$state_machine_arn"
}

get_or_create_step_functions_role() {
    local role_name="$(resource_name "stepfunctions")"
    
    if aws iam get-role --role-name "$role_name" &>/dev/null; then
        aws iam get-role --role-name "$role_name" --query Role.Arn --output text
        return
    fi
    
    log_substep "Creating Step Functions role: $role_name"
    
    aws iam create-role \
        --role-name "$role_name" \
        --assume-role-policy-document '{
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "states.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }]
        }'
    
    # Get role ARNs for PassRole (least privilege)
    local exec_role_arn
    exec_role_arn=$(get_or_create_execution_role)
    local task_role_arn
    task_role_arn=$(get_or_create_task_role)
    
    # Add permissions for ECS, DynamoDB - scoped to specific resources
    aws iam put-role-policy \
        --role-name "$role_name" \
        --policy-name "StepFunctionsPolicy" \
        --policy-document "{
            \"Version\": \"2012-10-17\",
            \"Statement\": [
                {
                    \"Effect\": \"Allow\",
                    \"Action\": [\"ecs:RunTask\"],
                    \"Resource\": \"arn:aws:ecs:$AWS_REGION:$AWS_ACCOUNT_ID:task-definition/$ECS_TASK_FAMILY:*\",
                    \"Condition\": {
                        \"ArnEquals\": {
                            \"ecs:cluster\": \"arn:aws:ecs:$AWS_REGION:$AWS_ACCOUNT_ID:cluster/$ECS_CLUSTER_NAME\"
                        }
                    }
                },
                {
                    \"Effect\": \"Allow\",
                    \"Action\": [\"ecs:StopTask\", \"ecs:DescribeTasks\"],
                    \"Resource\": \"arn:aws:ecs:$AWS_REGION:$AWS_ACCOUNT_ID:task/*\",
                    \"Condition\": {
                        \"ArnEquals\": {
                            \"ecs:cluster\": \"arn:aws:ecs:$AWS_REGION:$AWS_ACCOUNT_ID:cluster/$ECS_CLUSTER_NAME\"
                        }
                    }
                },
                {
                    \"Effect\": \"Allow\",
                    \"Action\": [\"iam:PassRole\"],
                    \"Resource\": [\"$exec_role_arn\", \"$task_role_arn\"]
                },
                {
                    \"Effect\": \"Allow\",
                    \"Action\": [\"dynamodb:UpdateItem\", \"dynamodb:GetItem\"],
                    \"Resource\": \"arn:aws:dynamodb:$AWS_REGION:$AWS_ACCOUNT_ID:table/$DYNAMODB_TABLE_NAME\"
                },
                {
                    \"Effect\": \"Allow\",
                    \"Action\": [\"events:PutTargets\", \"events:PutRule\", \"events:DescribeRule\"],
                    \"Resource\": \"arn:aws:events:$AWS_REGION:$AWS_ACCOUNT_ID:rule/StepFunctions*\"
                }
            ]
        }"
    
    aws iam get-role --role-name "$role_name" --query Role.Arn --output text
}

# =============================================================================
# RECONCILER (LAMBDA + EVENTBRIDGE)
# =============================================================================

RECONCILER_FUNCTION_NAME="$(resource_name "reconciler")"
EVENTBRIDGE_RULE_NAME="$(resource_name "reconciler-schedule")"

get_or_create_reconciler_role() {
    local role_name="$(resource_name "reconciler-lambda")"
    
    if aws iam get-role --role-name "$role_name" &>/dev/null; then
        aws iam get-role --role-name "$role_name" --query Role.Arn --output text
        return
    fi
    
    log_substep "Creating reconciler Lambda role: $role_name"
    
    # Create role with Lambda trust policy
    aws iam create-role \
        --role-name "$role_name" \
        --assume-role-policy-document '{
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }]
        }'
    
    # Attach basic Lambda execution policy (CloudWatch Logs)
    aws iam attach-role-policy \
        --role-name "$role_name" \
        --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
    
    # Attach X-Ray write access for tracing
    aws iam attach-role-policy \
        --role-name "$role_name" \
        --policy-arn "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"
    
    # Add DynamoDB access for job store
    aws iam put-role-policy \
        --role-name "$role_name" \
        --policy-name "DynamoDBAccess" \
        --policy-document "{
            \"Version\": \"2012-10-17\",
            \"Statement\": [{
                \"Effect\": \"Allow\",
                \"Action\": [
                    \"dynamodb:Query\",
                    \"dynamodb:GetItem\",
                    \"dynamodb:UpdateItem\",
                    \"dynamodb:Scan\"
                ],
                \"Resource\": [
                    \"arn:aws:dynamodb:$AWS_REGION:$AWS_ACCOUNT_ID:table/$DYNAMODB_TABLE_NAME\",
                    \"arn:aws:dynamodb:$AWS_REGION:$AWS_ACCOUNT_ID:table/$DYNAMODB_TABLE_NAME/index/*\"
                ]
            }]
        }"
    
    # Add S3 access for manifest checks
    aws iam put-role-policy \
        --role-name "$role_name" \
        --policy-name "S3ManifestAccess" \
        --policy-document "{
            \"Version\": \"2012-10-17\",
            \"Statement\": [{
                \"Effect\": \"Allow\",
                \"Action\": [\"s3:GetObject\", \"s3:ListBucket\"],
                \"Resource\": [
                    \"arn:aws:s3:::$S3_BUCKET_NAME\",
                    \"arn:aws:s3:::$S3_BUCKET_NAME/*\"
                ]
            }]
        }"
    
    # Wait for role to propagate
    sleep 10
    
    aws iam get-role --role-name "$role_name" --query Role.Arn --output text
}

create_reconciler_lambda() {
    log_step "Creating reconciler Lambda function: $RECONCILER_FUNCTION_NAME"
    
    # Check if function exists
    if aws lambda get-function --function-name "$RECONCILER_FUNCTION_NAME" --region "$AWS_REGION" &>/dev/null; then
        log_info "Reconciler Lambda already exists, updating..."
        update_reconciler_lambda
        return
    fi
    
    # Get role ARN
    local role_arn
    role_arn=$(get_or_create_reconciler_role)
    
    # Create inline Python code for the Lambda handler
    # This wraps the reconciler module
    local handler_code='
import json
import os
import boto3
from deploy.control_plane.reconciler import Reconciler, ReconciliationConfig
from deploy.control_plane.job_store import DynamoDBStore
from deploy.storage import S3Store

def handler(event, context):
    """Lambda handler for reconciliation."""
    # Get configuration from environment
    table_name = os.environ.get("DYNAMODB_TABLE_NAME")
    bucket_name = os.environ.get("S3_BUCKET_NAME")
    deployment = os.environ.get("DEPLOYMENT", "prod")
    region = os.environ.get("AWS_REGION", "us-east-1")
    
    # Create stores
    job_store = DynamoDBStore(table_name=table_name, region=region)
    artifact_store = S3Store(bucket=bucket_name, deployment=deployment, region=region)
    
    # Create reconciler with config
    config = ReconciliationConfig(
        max_duration_seconds=7200,  # 2 hours
        cancellation_grace_seconds=300,  # 5 minutes
        heartbeat_stale_seconds=600,  # 10 minutes
    )
    reconciler = Reconciler(job_store, artifact_store, config)
    
    # Run reconciliation
    result = reconciler.reconcile()
    
    return {
        "statusCode": 200,
        "body": json.dumps(result.to_dict())
    }
'
    
    # Create a deployment package
    local temp_dir
    temp_dir=$(mktemp -d)
    
    # Copy the deploy module
    cp -r "$SCRIPT_DIR/../" "$temp_dir/deploy"
    
    # Create handler file
    echo "$handler_code" > "$temp_dir/lambda_handler.py"
    
    # Create zip
    local zip_file="$temp_dir/reconciler.zip"
    (cd "$temp_dir" && zip -r "$zip_file" . -x "*.pyc" -x "__pycache__/*")
    
    # Create Lambda function with X-Ray tracing enabled
    aws lambda create-function \
        --function-name "$RECONCILER_FUNCTION_NAME" \
        --region "$AWS_REGION" \
        --runtime python3.12 \
        --role "$role_arn" \
        --handler "lambda_handler.handler" \
        --zip-file "fileb://$zip_file" \
        --timeout 300 \
        --memory-size 256 \
        --tracing-config Mode=Active \
        --environment "Variables={DYNAMODB_TABLE_NAME=$DYNAMODB_TABLE_NAME,S3_BUCKET_NAME=$S3_BUCKET_NAME,DEPLOYMENT=$PRIMR_DEPLOYMENT,AWS_REGION=$AWS_REGION}" \
        --tags Deployment="$PRIMR_DEPLOYMENT"
    
    # Clean up
    rm -rf "$temp_dir"
    
    log_success "Reconciler Lambda created with X-Ray tracing"
}

update_reconciler_lambda() {
    log_substep "Updating reconciler Lambda code"
    
    # Create a deployment package (same as create)
    local temp_dir
    temp_dir=$(mktemp -d)
    
    local handler_code='
import json
import os
import boto3
from deploy.control_plane.reconciler import Reconciler, ReconciliationConfig
from deploy.control_plane.job_store import DynamoDBStore
from deploy.storage import S3Store

def handler(event, context):
    """Lambda handler for reconciliation."""
    table_name = os.environ.get("DYNAMODB_TABLE_NAME")
    bucket_name = os.environ.get("S3_BUCKET_NAME")
    deployment = os.environ.get("DEPLOYMENT", "prod")
    region = os.environ.get("AWS_REGION", "us-east-1")
    
    job_store = DynamoDBStore(table_name=table_name, region=region)
    artifact_store = S3Store(bucket=bucket_name, deployment=deployment, region=region)
    
    config = ReconciliationConfig(
        max_duration_seconds=7200,
        cancellation_grace_seconds=300,
        heartbeat_stale_seconds=600,
    )
    reconciler = Reconciler(job_store, artifact_store, config)
    result = reconciler.reconcile()
    
    return {
        "statusCode": 200,
        "body": json.dumps(result.to_dict())
    }
'
    
    cp -r "$SCRIPT_DIR/../" "$temp_dir/deploy"
    echo "$handler_code" > "$temp_dir/lambda_handler.py"
    
    local zip_file="$temp_dir/reconciler.zip"
    (cd "$temp_dir" && zip -r "$zip_file" . -x "*.pyc" -x "__pycache__/*")
    
    aws lambda update-function-code \
        --function-name "$RECONCILER_FUNCTION_NAME" \
        --region "$AWS_REGION" \
        --zip-file "fileb://$zip_file"
    
    rm -rf "$temp_dir"
    
    log_success "Reconciler Lambda updated"
}

create_eventbridge_rule() {
    log_step "Creating EventBridge scheduled rule: $EVENTBRIDGE_RULE_NAME"
    
    # Check if rule exists
    if aws events describe-rule --name "$EVENTBRIDGE_RULE_NAME" --region "$AWS_REGION" &>/dev/null; then
        log_info "EventBridge rule already exists"
        return
    fi
    
    # Create rule that runs every 5 minutes
    aws events put-rule \
        --name "$EVENTBRIDGE_RULE_NAME" \
        --region "$AWS_REGION" \
        --schedule-expression "rate(5 minutes)" \
        --state ENABLED \
        --description "Triggers reconciler Lambda every 5 minutes" \
        --tags Key=Deployment,Value="$PRIMR_DEPLOYMENT"
    
    # Get Lambda ARN
    local lambda_arn
    lambda_arn=$(aws lambda get-function --function-name "$RECONCILER_FUNCTION_NAME" --region "$AWS_REGION" \
        --query Configuration.FunctionArn --output text)
    
    # Add Lambda as target
    aws events put-targets \
        --rule "$EVENTBRIDGE_RULE_NAME" \
        --region "$AWS_REGION" \
        --targets "Id=reconciler-target,Arn=$lambda_arn"
    
    # Add permission for EventBridge to invoke Lambda
    aws lambda add-permission \
        --function-name "$RECONCILER_FUNCTION_NAME" \
        --region "$AWS_REGION" \
        --statement-id "eventbridge-invoke" \
        --action "lambda:InvokeFunction" \
        --principal "events.amazonaws.com" \
        --source-arn "arn:aws:events:$AWS_REGION:$AWS_ACCOUNT_ID:rule/$EVENTBRIDGE_RULE_NAME" \
        2>/dev/null || true  # Ignore if permission already exists
    
    log_success "EventBridge rule created (runs every 5 minutes)"
}

# =============================================================================
# CLOUDWATCH ALARMS
# =============================================================================

create_cloudwatch_alarms() {
    log_step "Creating CloudWatch alarms for monitoring"
    
    local alarm_prefix="$(resource_name "alarm")"
    
    # Alarm: Reconciler Lambda errors
    if ! aws cloudwatch describe-alarms --alarm-names "${alarm_prefix}-reconciler-errors" --region "$AWS_REGION" \
        --query "MetricAlarms[0].AlarmName" --output text 2>/dev/null | grep -q "${alarm_prefix}"; then
        aws cloudwatch put-metric-alarm \
            --alarm-name "${alarm_prefix}-reconciler-errors" \
            --region "$AWS_REGION" \
            --alarm-description "Reconciler Lambda function errors" \
            --metric-name Errors \
            --namespace AWS/Lambda \
            --statistic Sum \
            --period 300 \
            --threshold 1 \
            --comparison-operator GreaterThanOrEqualToThreshold \
            --evaluation-periods 2 \
            --dimensions Name=FunctionName,Value="$RECONCILER_FUNCTION_NAME" \
            --treat-missing-data notBreaching \
            --tags Key=Deployment,Value="$PRIMR_DEPLOYMENT"
        log_substep "Created reconciler error alarm"
    fi
    
    # Alarm: DynamoDB throttling
    if ! aws cloudwatch describe-alarms --alarm-names "${alarm_prefix}-dynamodb-throttle" --region "$AWS_REGION" \
        --query "MetricAlarms[0].AlarmName" --output text 2>/dev/null | grep -q "${alarm_prefix}"; then
        aws cloudwatch put-metric-alarm \
            --alarm-name "${alarm_prefix}-dynamodb-throttle" \
            --region "$AWS_REGION" \
            --alarm-description "DynamoDB read/write throttling" \
            --metric-name ThrottledRequests \
            --namespace AWS/DynamoDB \
            --statistic Sum \
            --period 300 \
            --threshold 5 \
            --comparison-operator GreaterThanOrEqualToThreshold \
            --evaluation-periods 2 \
            --dimensions Name=TableName,Value="$DYNAMODB_TABLE_NAME" \
            --treat-missing-data notBreaching \
            --tags Key=Deployment,Value="$PRIMR_DEPLOYMENT"
        log_substep "Created DynamoDB throttle alarm"
    fi
    
    # Alarm: SQS DLQ messages (failed jobs)
    local dlq_name="${SQS_QUEUE_NAME%.fifo}-dlq.fifo"
    if ! aws cloudwatch describe-alarms --alarm-names "${alarm_prefix}-dlq-messages" --region "$AWS_REGION" \
        --query "MetricAlarms[0].AlarmName" --output text 2>/dev/null | grep -q "${alarm_prefix}"; then
        aws cloudwatch put-metric-alarm \
            --alarm-name "${alarm_prefix}-dlq-messages" \
            --region "$AWS_REGION" \
            --alarm-description "Messages in dead-letter queue (failed jobs)" \
            --metric-name ApproximateNumberOfMessagesVisible \
            --namespace AWS/SQS \
            --statistic Average \
            --period 300 \
            --threshold 1 \
            --comparison-operator GreaterThanOrEqualToThreshold \
            --evaluation-periods 1 \
            --dimensions Name=QueueName,Value="$dlq_name" \
            --treat-missing-data notBreaching \
            --tags Key=Deployment,Value="$PRIMR_DEPLOYMENT"
        log_substep "Created DLQ message alarm"
    fi
    
    # Alarm: SQS queue age (jobs waiting too long)
    if ! aws cloudwatch describe-alarms --alarm-names "${alarm_prefix}-queue-age" --region "$AWS_REGION" \
        --query "MetricAlarms[0].AlarmName" --output text 2>/dev/null | grep -q "${alarm_prefix}"; then
        aws cloudwatch put-metric-alarm \
            --alarm-name "${alarm_prefix}-queue-age" \
            --region "$AWS_REGION" \
            --alarm-description "Jobs waiting in queue too long (>30 min)" \
            --metric-name ApproximateAgeOfOldestMessage \
            --namespace AWS/SQS \
            --statistic Maximum \
            --period 300 \
            --threshold 1800 \
            --comparison-operator GreaterThanOrEqualToThreshold \
            --evaluation-periods 2 \
            --dimensions Name=QueueName,Value="$SQS_QUEUE_NAME" \
            --treat-missing-data notBreaching \
            --tags Key=Deployment,Value="$PRIMR_DEPLOYMENT"
        log_substep "Created queue age alarm"
    fi
    
    log_success "CloudWatch alarms created"
}

# =============================================================================
# SECRETS MANAGEMENT
# =============================================================================

set_secret() {
    local name="$1"
    local value="${2:--}"
    
    validate_secret_name "$name" || return 1
    
    local secret_name="${SECRET_PREFIX}${name}"
    local secret_value
    secret_value=$(read_secret_value "$value")
    
    log_step "Setting secret: $secret_name"
    
    # Check if secret exists
    if aws secretsmanager describe-secret --secret-id "$secret_name" --region "$AWS_REGION" &>/dev/null; then
        # Update existing secret
        aws secretsmanager put-secret-value \
            --secret-id "$secret_name" \
            --region "$AWS_REGION" \
            --secret-string "$secret_value"
        log_success "Secret updated"
    else
        # Create new secret
        aws secretsmanager create-secret \
            --name "$secret_name" \
            --region "$AWS_REGION" \
            --secret-string "$secret_value" \
            --tags Key=Deployment,Value="$PRIMR_DEPLOYMENT"
        log_success "Secret created"
    fi
}

get_secret() {
    local name="$1"
    local secret_name="${SECRET_PREFIX}${name}"
    
    aws secretsmanager get-secret-value \
        --secret-id "$secret_name" \
        --region "$AWS_REGION" \
        --query SecretString --output text
}

list_secrets() {
    log_step "Listing secrets with prefix: $SECRET_PREFIX"
    
    aws secretsmanager list-secrets \
        --region "$AWS_REGION" \
        --filters Key=name,Values="$SECRET_PREFIX" \
        --query "SecretList[].Name" --output table
}

delete_secret() {
    local name="$1"
    local secret_name="${SECRET_PREFIX}${name}"
    
    log_step "Deleting secret: $secret_name"
    
    aws secretsmanager delete-secret \
        --secret-id "$secret_name" \
        --region "$AWS_REGION" \
        --force-delete-without-recovery
    
    log_success "Secret deleted"
}

# =============================================================================
# DEPLOY COMMAND
# =============================================================================

cmd_deploy() {
    log_step "Deploying Primr to AWS"
    log_info "Deployment: $PRIMR_DEPLOYMENT"
    log_info "Region: $AWS_REGION"
    
    check_prerequisites
    
    # Create infrastructure
    create_ecr_repo
    push_to_ecr
    create_s3_bucket
    create_dynamodb_table
    create_sqs_queue
    create_ecs_cluster
    create_task_definition
    create_step_function
    
    # Create reconciler (Lambda + EventBridge)
    create_reconciler_lambda
    create_eventbridge_rule
    
    # Create monitoring alarms
    create_cloudwatch_alarms
    
    log_success "Deployment complete!"
    log_info ""
    log_info "Next steps:"
    log_info "  1. Set LLM API keys: $0 secrets set OPENAI_API_KEY"
    log_info "  2. Validate deployment: $0 validate"
}

# =============================================================================
# DESTROY COMMAND
# =============================================================================

cmd_destroy() {
    local force="${1:-}"
    
    log_step "Destroying Primr AWS deployment"
    log_warn "This will delete all resources for deployment: $PRIMR_DEPLOYMENT"
    
    if [[ "$force" != "--force" ]]; then
        read -p "Are you sure? (yes/no): " confirm
        if [[ "$confirm" != "yes" ]]; then
            log_info "Aborted"
            return 1
        fi
    fi
    
    check_prerequisites
    
    # Delete in reverse order of dependencies
    
    # CloudWatch alarms
    local alarm_prefix="$(resource_name "alarm")"
    local alarms
    alarms=$(aws cloudwatch describe-alarms --alarm-name-prefix "$alarm_prefix" --region "$AWS_REGION" \
        --query "MetricAlarms[].AlarmName" --output text 2>/dev/null || echo "")
    if [[ -n "$alarms" ]]; then
        log_substep "Deleting CloudWatch alarms"
        for alarm in $alarms; do
            aws cloudwatch delete-alarms --alarm-names "$alarm" --region "$AWS_REGION" 2>/dev/null || true
        done
    fi
    
    # EventBridge rule (must remove targets first)
    if aws events describe-rule --name "$EVENTBRIDGE_RULE_NAME" --region "$AWS_REGION" &>/dev/null; then
        log_substep "Deleting EventBridge rule"
        aws events remove-targets --rule "$EVENTBRIDGE_RULE_NAME" --region "$AWS_REGION" --ids "reconciler-target" 2>/dev/null || true
        aws events delete-rule --name "$EVENTBRIDGE_RULE_NAME" --region "$AWS_REGION"
    fi
    
    # Reconciler Lambda
    if aws lambda get-function --function-name "$RECONCILER_FUNCTION_NAME" --region "$AWS_REGION" &>/dev/null; then
        log_substep "Deleting reconciler Lambda"
        aws lambda delete-function --function-name "$RECONCILER_FUNCTION_NAME" --region "$AWS_REGION"
    fi
    
    # Step Functions
    local state_machine_arn
    state_machine_arn=$(aws stepfunctions list-state-machines --region "$AWS_REGION" \
        --query "stateMachines[?name=='$STEP_FUNCTION_NAME'].stateMachineArn" --output text)
    if [[ -n "$state_machine_arn" ]]; then
        log_substep "Deleting Step Functions state machine"
        aws stepfunctions delete-state-machine --state-machine-arn "$state_machine_arn" --region "$AWS_REGION"
    fi
    
    # ECS cluster (must stop all tasks first)
    if aws ecs describe-clusters --clusters "$ECS_CLUSTER_NAME" --region "$AWS_REGION" \
        --query "clusters[?status=='ACTIVE'].clusterName" --output text | grep -q "$ECS_CLUSTER_NAME"; then
        log_substep "Deleting ECS cluster"
        aws ecs delete-cluster --cluster "$ECS_CLUSTER_NAME" --region "$AWS_REGION"
    fi
    
    # SQS queue
    local queue_url
    queue_url=$(aws sqs get-queue-url --queue-name "$SQS_QUEUE_NAME" --region "$AWS_REGION" --query QueueUrl --output text 2>/dev/null || echo "")
    if [[ -n "$queue_url" ]]; then
        log_substep "Deleting SQS queue"
        aws sqs delete-queue --queue-url "$queue_url" --region "$AWS_REGION"
    fi
    
    # DynamoDB table
    if aws dynamodb describe-table --table-name "$DYNAMODB_TABLE_NAME" --region "$AWS_REGION" &>/dev/null; then
        log_substep "Deleting DynamoDB table"
        aws dynamodb delete-table --table-name "$DYNAMODB_TABLE_NAME" --region "$AWS_REGION"
    fi
    
    # S3 bucket (must empty first)
    if aws s3api head-bucket --bucket "$S3_BUCKET_NAME" 2>/dev/null; then
        log_substep "Emptying and deleting S3 bucket"
        aws s3 rm "s3://$S3_BUCKET_NAME" --recursive
        aws s3api delete-bucket --bucket "$S3_BUCKET_NAME" --region "$AWS_REGION"
    fi
    
    # ECR repository
    if aws ecr describe-repositories --repository-names "$ECR_REPO_NAME" --region "$AWS_REGION" &>/dev/null; then
        log_substep "Deleting ECR repository"
        aws ecr delete-repository --repository-name "$ECR_REPO_NAME" --region "$AWS_REGION" --force
    fi
    
    # IAM roles (delete policies first, then roles)
    local roles=(
        "$(resource_name "ecs-execution")"
        "$(resource_name "ecs-task")"
        "$(resource_name "stepfunctions")"
        "$(resource_name "reconciler-lambda")"
    )
    
    for role_name in "${roles[@]}"; do
        if aws iam get-role --role-name "$role_name" &>/dev/null; then
            log_substep "Deleting IAM role: $role_name"
            
            # Detach managed policies
            local policies
            policies=$(aws iam list-attached-role-policies --role-name "$role_name" --query "AttachedPolicies[].PolicyArn" --output text 2>/dev/null || echo "")
            for policy_arn in $policies; do
                aws iam detach-role-policy --role-name "$role_name" --policy-arn "$policy_arn" 2>/dev/null || true
            done
            
            # Delete inline policies
            local inline_policies
            inline_policies=$(aws iam list-role-policies --role-name "$role_name" --query "PolicyNames[]" --output text 2>/dev/null || echo "")
            for policy_name in $inline_policies; do
                aws iam delete-role-policy --role-name "$role_name" --policy-name "$policy_name" 2>/dev/null || true
            done
            
            # Delete the role
            aws iam delete-role --role-name "$role_name" 2>/dev/null || true
        fi
    done
    
    log_success "Destroy complete - all resources cleaned up"
}

# =============================================================================
# VALIDATE COMMAND
# =============================================================================

cmd_validate() {
    log_step "Validating AWS deployment"
    
    check_prerequisites
    
    local errors=0
    
    # Check ECR
    if aws ecr describe-repositories --repository-names "$ECR_REPO_NAME" --region "$AWS_REGION" &>/dev/null; then
        log_substep "ECR repository: OK"
    else
        log_error "ECR repository not found"
        ((errors++))
    fi
    
    # Check S3
    if aws s3api head-bucket --bucket "$S3_BUCKET_NAME" 2>/dev/null; then
        log_substep "S3 bucket: OK"
    else
        log_error "S3 bucket not found"
        ((errors++))
    fi
    
    # Check DynamoDB
    if aws dynamodb describe-table --table-name "$DYNAMODB_TABLE_NAME" --region "$AWS_REGION" &>/dev/null; then
        log_substep "DynamoDB table: OK"
    else
        log_error "DynamoDB table not found"
        ((errors++))
    fi
    
    # Check SQS
    if aws sqs get-queue-url --queue-name "$SQS_QUEUE_NAME" --region "$AWS_REGION" &>/dev/null; then
        log_substep "SQS queue: OK"
    else
        log_error "SQS queue not found"
        ((errors++))
    fi
    
    # Check ECS cluster
    if aws ecs describe-clusters --clusters "$ECS_CLUSTER_NAME" --region "$AWS_REGION" \
        --query "clusters[?status=='ACTIVE'].clusterName" --output text | grep -q "$ECS_CLUSTER_NAME"; then
        log_substep "ECS cluster: OK"
    else
        log_error "ECS cluster not found"
        ((errors++))
    fi
    
    # Check Reconciler Lambda
    if aws lambda get-function --function-name "$RECONCILER_FUNCTION_NAME" --region "$AWS_REGION" &>/dev/null; then
        log_substep "Reconciler Lambda: OK"
    else
        log_error "Reconciler Lambda not found"
        ((errors++))
    fi
    
    # Check EventBridge rule
    if aws events describe-rule --name "$EVENTBRIDGE_RULE_NAME" --region "$AWS_REGION" &>/dev/null; then
        log_substep "EventBridge rule: OK"
    else
        log_error "EventBridge rule not found"
        ((errors++))
    fi
    
    if [[ $errors -eq 0 ]]; then
        log_success "All resources validated"
    else
        log_error "$errors resource(s) missing"
        return 1
    fi
}

# =============================================================================
# SECRETS COMMAND
# =============================================================================

cmd_secrets() {
    local action="${1:-list}"
    shift || true
    
    case "$action" in
        set)
            if [[ $# -lt 1 ]]; then
                log_error "Usage: $0 secrets set <name> [value|-]"
                log_info "If value is '-' or omitted, reads from stdin"
                return 1
            fi
            set_secret "$1" "${2:--}"
            ;;
        get)
            if [[ $# -lt 1 ]]; then
                log_error "Usage: $0 secrets get <name>"
                return 1
            fi
            get_secret "$1"
            ;;
        list)
            list_secrets
            ;;
        delete)
            if [[ $# -lt 1 ]]; then
                log_error "Usage: $0 secrets delete <name>"
                return 1
            fi
            delete_secret "$1"
            ;;
        *)
            log_error "Unknown secrets action: $action"
            log_info "Available actions: set, get, list, delete"
            return 1
            ;;
    esac
}

# =============================================================================
# USAGE
# =============================================================================

usage() {
    print_usage_header "deploy.sh" "Deploy Primr to AWS"
    
    echo "Commands:"
    print_usage_command "deploy" "Deploy all AWS resources"
    print_usage_command "destroy [--force]" "Tear down all AWS resources (--force skips confirmation)"
    print_usage_command "validate" "Validate deployed resources"
    print_usage_command "secrets" "Manage secrets (set, get, list, delete)"
    echo ""
    
    echo "Options:"
    print_usage_option "-d, --deployment" "Deployment name (default: dev)"
    print_usage_option "-r, --region" "AWS region (default: us-east-1)"
    print_usage_option "-h, --help" "Show this help"
    echo ""
    
    echo "Environment variables:"
    print_usage_option "PRIMR_DEPLOYMENT" "Deployment name"
    print_usage_option "PRIMR_REGION" "AWS region"
    print_usage_option "PRIMR_PREFIX" "Resource name prefix (default: primr)"
    echo ""
    
    echo "Examples:"
    echo "  $0 deploy                    # Deploy to dev"
    echo "  $0 -d prod deploy            # Deploy to prod"
    echo "  $0 secrets set OPENAI_API_KEY  # Set secret from stdin"
    echo "  $0 secrets list              # List all secrets"
    echo "  $0 validate                  # Check deployment"
    echo "  $0 destroy                   # Tear down"
}

# =============================================================================
# MAIN
# =============================================================================

main() {
    # Parse options
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -d|--deployment)
                PRIMR_DEPLOYMENT="$2"
                shift 2
                ;;
            -r|--region)
                AWS_REGION="$2"
                PRIMR_REGION="$2"
                shift 2
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            -*)
                log_error "Unknown option: $1"
                usage
                exit 1
                ;;
            *)
                break
                ;;
        esac
    done
    
    # Validate deployment name
    validate_deployment "$PRIMR_DEPLOYMENT" || exit 1
    
    # Update derived names after parsing options
    ECR_REPO_NAME="$(resource_name "runner")"
    LAMBDA_FUNCTION_NAME="$(resource_name "api")"
    SQS_QUEUE_NAME="$(resource_name "jobs").fifo"
    STEP_FUNCTION_NAME="$(resource_name "orchestrator")"
    ECS_CLUSTER_NAME="$(resource_name "cluster")"
    ECS_TASK_FAMILY="$(resource_name "runner")"
    S3_BUCKET_NAME="$(short_resource_name "artifacts" 63)"
    DYNAMODB_TABLE_NAME="$(resource_name "jobs")"
    SECRET_PREFIX="$(resource_name "")"
    
    # Get command
    local cmd="${1:-}"
    shift || true
    
    case "$cmd" in
        deploy)
            cmd_deploy
            ;;
        destroy)
            cmd_destroy "${1:-}"
            ;;
        validate)
            cmd_validate
            ;;
        secrets)
            cmd_secrets "$@"
            ;;
        "")
            usage
            exit 1
            ;;
        *)
            log_error "Unknown command: $cmd"
            usage
            exit 1
            ;;
    esac
}

main "$@"
