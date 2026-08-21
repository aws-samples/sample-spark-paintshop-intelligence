#!/usr/bin/env bash
# deploy.sh — End-to-end bootstrap for a fresh AWS account.
# Usage:
#   bash scripts/deploy.sh                              # full deploy (incl. SageMaker training ~15 min)
#   bash scripts/deploy.sh --skip-training             # skip ML training (models already exist)
#   bash scripts/deploy.sh --with-profiles             # also create Bedrock inference profiles for cost attribution
#   bash scripts/deploy.sh --skip-training --with-profiles
set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
SKIP_TRAINING=false
WITH_PROFILES=false

for arg in "$@"; do
  [[ "$arg" == "--skip-training" ]]  && SKIP_TRAINING=true
  [[ "$arg" == "--with-profiles" ]]  && WITH_PROFILES=true
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
step()  { echo -e "\n${GREEN}==> [${1}/${TOTAL}] ${2}${NC}"; }
warn()  { echo -e "${YELLOW}WARN: ${1}${NC}"; }
die()   { echo -e "${RED}ERROR: ${1}${NC}" >&2; exit 1; }

verify_deployment() {
  local status kb_id runtime_arn runtime_id dashboard_url

  status=$(aws sagemaker describe-endpoint \
    --endpoint-name paintshop-anomaly-endpoint --region "$REGION" \
    --query EndpointStatus --output text)
  [[ "$status" == "InService" ]] || die "SageMaker endpoint status is $status"
  echo "  ✓ SageMaker endpoint: $status"

  kb_id=$(aws ssm get-parameter --name /paintshop/kb_id --region "$REGION" \
    --query Parameter.Value --output text)
  status=$(aws bedrock-agent get-knowledge-base --knowledge-base-id "$kb_id" \
    --region "$REGION" --query knowledgeBase.status --output text)
  [[ "$status" == "ACTIVE" ]] || die "Bedrock Knowledge Base status is $status"
  echo "  ✓ Bedrock Knowledge Base: $status"

  if ! status=$(aws lambda get-function-configuration \
    --function-name schedule-optimizer --region "$REGION" \
    --query State --output text 2>/dev/null); then
    die "Required Lambda schedule-optimizer is missing; PaintShopScheduling is incomplete"
  fi
  [[ "$status" == "Active" ]] || die "schedule-optimizer state is $status"
  echo "  ✓ Schedule optimizer: $status"

  for param in /paintshop/mps_agent_runtime_arn /paintshop/rca_agent_runtime_arn; do
    runtime_arn=$(aws ssm get-parameter --name "$param" --region "$REGION" \
      --query Parameter.Value --output text)
    runtime_id="${runtime_arn##*/}"
    status=$(aws bedrock-agentcore-control get-agent-runtime \
      --agent-runtime-id "$runtime_id" --region "$REGION" \
      --query status --output text)
    [[ "$status" == "READY" ]] || die "AgentCore runtime $runtime_id status is $status"
    echo "  ✓ AgentCore runtime $runtime_id: $status"
  done

  status=$(aws bedrock-agentcore-control list-gateways --region "$REGION" \
    --query "items[?name=='paintshop-tools-gateway'].status | [0]" --output text)
  [[ "$status" == "READY" ]] || die "AgentCore Gateway status is $status"
  echo "  ✓ AgentCore Gateway: $status"

  dashboard_url=$(aws cloudformation describe-stacks --stack-name PaintShopFrontend \
    --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='DashboardUrl'].OutputValue | [0]" \
    --output text)
  [[ -n "$dashboard_url" && "$dashboard_url" != "None" ]] \
    || die "Dashboard URL was not produced"
  echo "  ✓ Dashboard: $dashboard_url"
}

activate_data_pipeline() {
  local stream_arn mapping_uuid mapping_state rule_state

  stream_arn=$(aws kinesis describe-stream-summary \
    --stream-name paintshop-tank-stream --region "$REGION" \
    --query StreamDescriptionSummary.StreamARN --output text)
  [[ -n "$stream_arn" && "$stream_arn" != "None" ]] \
    || die "Kinesis stream paintshop-tank-stream was not found"

  mapping_uuid=$(aws lambda list-event-source-mappings \
    --function-name stream-processor --event-source-arn "$stream_arn" \
    --region "$REGION" --query "EventSourceMappings[0].UUID" --output text)
  [[ -n "$mapping_uuid" && "$mapping_uuid" != "None" ]] \
    || die "Stream processor event source mapping was not found"

  mapping_state=$(aws lambda get-event-source-mapping --uuid "$mapping_uuid" \
    --region "$REGION" --query State --output text)
  if [[ "$mapping_state" != "Enabled" ]]; then
    [[ "$mapping_state" == "Disabled" ]] \
      || die "Stream processor event source mapping is $mapping_state; expected Disabled"
    aws lambda update-event-source-mapping --uuid "$mapping_uuid" --enabled \
      --region "$REGION" >/dev/null

    for _ in {1..60}; do
      mapping_state=$(aws lambda get-event-source-mapping --uuid "$mapping_uuid" \
        --region "$REGION" --query State --output text)
      [[ "$mapping_state" == "Enabled" ]] && break
      [[ "$mapping_state" == "Enabling" || "$mapping_state" == "Updating" ]] \
        || die "Stream processor event source mapping entered state $mapping_state"
      sleep 2
    done
  fi
  [[ "$mapping_state" == "Enabled" ]] \
    || die "Stream processor event source mapping did not become Enabled"
  echo "  ✓ Stream processor event source mapping: $mapping_state"

  # Start data generation only after the processor and every downstream service
  # have passed readiness checks, preventing fresh-account startup races.
  aws events enable-rule --name paintshop-simulator-schedule --region "$REGION"
  rule_state=$(aws events describe-rule --name paintshop-simulator-schedule \
    --region "$REGION" --query State --output text)
  [[ "$rule_state" == "ENABLED" ]] \
    || die "Simulator schedule state is $rule_state"
  echo "  ✓ Simulator schedule: $rule_state"
}

TOTAL=13
[[ "$SKIP_TRAINING" == "true" ]] && TOTAL=10
[[ "$WITH_PROFILES"  == "true" ]] && TOTAL=$((TOTAL + 1))

# ── Prerequisite checks ───────────────────────────────────────────────────────
echo -e "${GREEN}Checking prerequisites...${NC}"
command -v aws     >/dev/null 2>&1 || die "aws CLI not found. Install from https://aws.amazon.com/cli/"
command -v cdk     >/dev/null 2>&1 || die "AWS CDK not found. Run: npm install -g aws-cdk"
command -v python3 >/dev/null 2>&1 || die "python3 not found."
command -v node    >/dev/null 2>&1 || die "node not found."
# Note: Docker is NOT required — agent images are built by AWS CodeBuild in the cloud.

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
CALLER_ARN=$(aws sts get-caller-identity --query Arn --output text)

# Bucket names are explicit CDK inputs. Preserve the deployed physical names on
# updates; changing either name replaces the bucket and can delete its contents.
EXISTING_ML_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name PaintShopStorage --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue | [0]" \
  --output text 2>/dev/null || true)
if [[ -n "$EXISTING_ML_BUCKET" && "$EXISTING_ML_BUCKET" != "None" ]]; then
  [[ "${CDK_GENERATE_BUCKET_NAMES:-false}" != "true" ]] \
    || die "CDK_GENERATE_BUCKET_NAMES cannot be used for an existing stack."

  EXISTING_AUDIT_BUCKET=$(aws s3api get-bucket-logging \
    --bucket "$EXISTING_ML_BUCKET" --region "$REGION" \
    --query "LoggingEnabled.TargetBucket" --output text 2>/dev/null || true)
  [[ -n "$EXISTING_AUDIT_BUCKET" && "$EXISTING_AUDIT_BUCKET" != "None" ]] \
    || die "Could not discover the existing audit bucket; refusing a potentially destructive deployment."

  if [[ -n "${CDK_ML_BUCKET_NAME:-}" && "$CDK_ML_BUCKET_NAME" != "$EXISTING_ML_BUCKET" ]] \
      || [[ -n "${CDK_AUDIT_BUCKET_NAME:-}" && "$CDK_AUDIT_BUCKET_NAME" != "$EXISTING_AUDIT_BUCKET" ]]; then
    [[ "${ALLOW_BUCKET_REPLACEMENT:-false}" == "true" ]] \
      || die "Bucket-name change detected. Preserve existing names or explicitly set ALLOW_BUCKET_REPLACEMENT=true after completing a data-migration plan."
  fi

  CDK_ML_BUCKET_NAME="${CDK_ML_BUCKET_NAME:-$EXISTING_ML_BUCKET}"
  CDK_AUDIT_BUCKET_NAME="${CDK_AUDIT_BUCKET_NAME:-$EXISTING_AUDIT_BUCKET}"
  CDK_GENERATE_BUCKET_NAMES=false
  export CDK_ML_BUCKET_NAME CDK_AUDIT_BUCKET_NAME
  echo "  Preserving existing S3 bucket physical names."
else
  if [[ "${CDK_ML_BUCKET_NAME:-}" == amzn-s3-demo-* \
      || "${CDK_AUDIT_BUCKET_NAME:-}" == amzn-s3-demo-* ]]; then
    warn "Ignoring reserved example bucket names from the previous configuration."
    unset CDK_ML_BUCKET_NAME CDK_AUDIT_BUCKET_NAME
  fi

  if [[ -n "${CDK_ML_BUCKET_NAME:-}" || -n "${CDK_AUDIT_BUCKET_NAME:-}" ]]; then
    [[ -n "${CDK_ML_BUCKET_NAME:-}" && -n "${CDK_AUDIT_BUCKET_NAME:-}" ]] \
      || die "Set both CDK_ML_BUCKET_NAME and CDK_AUDIT_BUCKET_NAME, or neither."
    [[ "${CDK_GENERATE_BUCKET_NAMES:-false}" != "true" ]] \
      || die "Explicit bucket names cannot be combined with CDK_GENERATE_BUCKET_NAMES=true."
    CDK_GENERATE_BUCKET_NAMES=false
    export CDK_ML_BUCKET_NAME CDK_AUDIT_BUCKET_NAME
  else
    CDK_GENERATE_BUCKET_NAMES=true
    unset CDK_ML_BUCKET_NAME CDK_AUDIT_BUCKET_NAME
    echo "  CloudFormation will generate globally unique S3 bucket names."
  fi
fi
export CDK_GENERATE_BUCKET_NAMES

# Preserve an existing dashboard bucket independently from the storage stack.
# This also supports partial deployments where only one stack already exists.
EXISTING_FRONTEND_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name PaintShopFrontend --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue | [0]" \
  --output text 2>/dev/null || true)
if [[ -n "$EXISTING_FRONTEND_BUCKET" && "$EXISTING_FRONTEND_BUCKET" != "None" ]]; then
  if [[ -n "${CDK_FRONTEND_BUCKET_NAME:-}" \
      && "$CDK_FRONTEND_BUCKET_NAME" != "$EXISTING_FRONTEND_BUCKET" ]]; then
    [[ "${ALLOW_BUCKET_REPLACEMENT:-false}" == "true" ]] \
      || die "Frontend bucket-name change detected. Preserve the existing name or explicitly set ALLOW_BUCKET_REPLACEMENT=true after completing a migration plan."
  fi

  CDK_FRONTEND_BUCKET_NAME="${CDK_FRONTEND_BUCKET_NAME:-$EXISTING_FRONTEND_BUCKET}"
  CDK_GENERATE_FRONTEND_BUCKET_NAME=false
  export CDK_FRONTEND_BUCKET_NAME
  echo "  Preserving existing frontend S3 bucket physical name."
else
  if [[ "${CDK_FRONTEND_BUCKET_NAME:-}" == amzn-s3-demo-* ]]; then
    warn "Ignoring a reserved example frontend bucket name."
    unset CDK_FRONTEND_BUCKET_NAME
  fi

  if [[ -n "${CDK_FRONTEND_BUCKET_NAME:-}" ]]; then
    CDK_GENERATE_FRONTEND_BUCKET_NAME=false
    export CDK_FRONTEND_BUCKET_NAME
  else
    CDK_GENERATE_FRONTEND_BUCKET_NAME=true
    unset CDK_FRONTEND_BUCKET_NAME
    echo "  CloudFormation will generate a globally unique frontend bucket name."
  fi
fi
export CDK_GENERATE_FRONTEND_BUCKET_NAME

if [[ -z "${AOSS_ADMIN_PRINCIPAL_ARN:-}" ]]; then
  if [[ "$CALLER_ARN" == arn:aws:sts::*:assumed-role/* ]]; then
    ROLE_AND_SESSION="${CALLER_ARN#*:assumed-role/}"
    ROLE_NAME="${ROLE_AND_SESSION%%/*}"
    AOSS_ADMIN_PRINCIPAL_ARN=$(aws iam get-role --role-name "$ROLE_NAME" \
      --query Role.Arn --output text) \
      || die "Set AOSS_ADMIN_PRINCIPAL_ARN to the IAM role that creates the AOSS index."
  elif [[ "$CALLER_ARN" == arn:aws:iam::*:role/* || "$CALLER_ARN" == arn:aws:iam::*:user/* ]]; then
    AOSS_ADMIN_PRINCIPAL_ARN="$CALLER_ARN"
  else
    die "Set AOSS_ADMIN_PRINCIPAL_ARN to a specific IAM user or role ARN."
  fi
fi
export AOSS_ADMIN_PRINCIPAL_ARN

echo "  Account : $ACCOUNT"
echo "  Region  : $REGION"
echo "  AOSS admin principal: $AOSS_ADMIN_PRINCIPAL_ARN"

# ── Step 1: CDK Bootstrap ─────────────────────────────────────────────────────
step 1 "CDK Bootstrap"
cdk bootstrap "aws://${ACCOUNT}/${REGION}"

# ── Step 2: Deploy all CDK stacks ─────────────────────────────────────────────
step 2 "Deploy CDK stacks (all 9)"
cd "$ROOT_DIR"
# Clear any cached account-specific VPC lookups
echo '{}' > cdk.context.json
cdk deploy --all --require-approval never --region "$REGION"

# Export bucket name from CDK output so all training scripts use the correct bucket
BUCKET_NAME=$(aws cloudformation describe-stacks --stack-name PaintShopStorage \
  --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue" \
  --output text --region "$REGION")
export BUCKET_NAME
echo "  ML bucket: $BUCKET_NAME"

# ── Step 3: Generate synthetic training data ──────────────────────────────────
if [[ "$SKIP_TRAINING" == "false" ]]; then
  step 3 "Generate synthetic training data"
  PYTHONPATH="$ROOT_DIR/src" python3 "$ROOT_DIR/src/data/generate_training_data.py"
fi

# ── Step 4: Run SageMaker training pipeline ───────────────────────────────────
if [[ "$SKIP_TRAINING" == "false" ]]; then
  step 4 "Run SageMaker training pipeline (~15 min)"
  python3 "$ROOT_DIR/src/training/pipeline.py" --start
  echo "  Waiting for pipeline execution to complete..."
  PIPELINE_ARN=$(aws sagemaker list-pipeline-executions \
    --pipeline-name PaintShopAnomalyPipeline \
    --sort-by CreationTime --sort-order Descending \
    --max-results 1 \
    --query "PipelineExecutionSummaries[0].PipelineExecutionArn" \
    --output text --region "$REGION")
  while true; do
    STATUS=$(aws sagemaker describe-pipeline-execution \
      --pipeline-execution-arn "$PIPELINE_ARN" \
      --query PipelineExecutionStatus --output text --region "$REGION")
    echo "  Pipeline status: $STATUS"
    [[ "$STATUS" == "Succeeded" ]] && break
    [[ "$STATUS" == "Failed" || "$STATUS" == "Stopped" ]] && die "Pipeline $STATUS"
    sleep 30
  done
fi

# ── Step 5: Deploy SageMaker Multi-Container Endpoint ─────────────────────────
if [[ "$SKIP_TRAINING" == "false" ]]; then
  step 5 "Deploy SageMaker endpoint"
  python3 "$ROOT_DIR/src/training/deploy_endpoint.py"
  echo "  Waiting for endpoint to be InService..."
  aws sagemaker wait endpoint-in-service \
    --endpoint-name paintshop-anomaly-endpoint --region "$REGION"
  echo "  Endpoint is InService."
fi

# ── Step 6: Create AOSS index + Bedrock Knowledge Base ───────────────────────
STEP=$( [[ "$SKIP_TRAINING" == "true" ]] && echo 3 || echo 6 )
step $STEP "Create AOSS vector index and Bedrock Knowledge Base"
python3 "$ROOT_DIR/scripts/create_kb.py"

# ── Step 7: Upload SOP documents ──────────────────────────────────────────────
STEP=$( [[ "$SKIP_TRAINING" == "true" ]] && echo 4 || echo 7 )
step $STEP "Upload SOP documents to Bedrock Knowledge Base"
python3 "$ROOT_DIR/src/data/upload_sop_docs.py"

# ── Step 8: Set up AgentCore Gateway ──────────────────────────────────────────
STEP=$( [[ "$SKIP_TRAINING" == "true" ]] && echo 5 || echo 8 )
step $STEP "Set up AgentCore Gateway (Cognito M2M + Lambda tools)"
python3 "$ROOT_DIR/scripts/setup_gateway.py"

# ── Step 9 (optional): Create Bedrock inference profiles ─────────────────────
# Profiles must exist before agent deployment so deploy_agents.py can resolve
# their SSM ARNs during this same end-to-end run.
PROFILES_OFFSET=0
if [[ "$WITH_PROFILES" == "true" ]]; then
  STEP=$( [[ "$SKIP_TRAINING" == "true" ]] && echo 6 || echo 9 )
  step $STEP "Create Bedrock inference profiles for cost attribution"
  python3 "$ROOT_DIR/scripts/setup_inference_profiles.py" \
    --env "${SPARK_ENV:-dev}" \
    --cost-center "${SPARK_COST_CENTER:-spark}"
  PROFILES_OFFSET=1
fi

# ── Step 9/10: Deploy AI agents ───────────────────────────────────────────────
STEP=$( [[ "$SKIP_TRAINING" == "true" ]] && echo $((6 + PROFILES_OFFSET)) || echo $((9 + PROFILES_OFFSET)) )
step $STEP "Deploy MPS + RCA agents to Bedrock AgentCore"
python3 "$ROOT_DIR/src/training/deploy_agents.py"

# ── Step 10: Seed Neptune graph ───────────────────────────────────────────────
PROFILES_OFFSET=$( [[ "$WITH_PROFILES" == "true" ]] && echo 1 || echo 0 )
STEP=$( [[ "$SKIP_TRAINING" == "true" ]] && echo $((7 + PROFILES_OFFSET)) || echo $((10 + PROFILES_OFFSET)) )
step $STEP "Seed Neptune knowledge graph"
python3 "$ROOT_DIR/src/data/seed_neptune_graph.py"

# ── Step 11: Build and deploy frontend ────────────────────────────────────────
STEP=$( [[ "$SKIP_TRAINING" == "true" ]] && echo $((8 + PROFILES_OFFSET)) || echo $((11 + PROFILES_OFFSET)) )
step $STEP "Build and deploy React dashboard"
bash "$SCRIPT_DIR/deploy_frontend.sh"

# ── Step 12: Create Cognito user ──────────────────────────────────────────────
STEP=$( [[ "$SKIP_TRAINING" == "true" ]] && echo $((9 + PROFILES_OFFSET)) || echo $((12 + PROFILES_OFFSET)) )
step $STEP "Create Cognito admin user"
POOL_ID=$(aws cloudformation describe-stacks --stack-name PaintShopApi \
  --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" \
  --output text --region "$REGION")

ADMIN_USERNAME="${SPARK_ADMIN_USERNAME:-spark-admin}"
DEFAULT_EMAIL="${SPARK_ADMIN_EMAIL:-admin@example.com}"
DEFAULT_PASS="${SPARK_ADMIN_PASSWORD:-}"
[[ -n "$DEFAULT_PASS" ]] || die "SPARK_ADMIN_PASSWORD must be set to a strong, unique password."

[[ -n "$POOL_ID" && "$POOL_ID" != "None" ]] || die "PaintShopApi did not return a valid UserPoolId."
echo "  User pool: $POOL_ID"

if USER_LOOKUP=$(aws cognito-idp admin-get-user \
  --user-pool-id "$POOL_ID" \
  --username "$ADMIN_USERNAME" \
  --region "$REGION" 2>&1); then
  echo "  User $ADMIN_USERNAME already exists."
else
  if [[ "$USER_LOOKUP" != *"UserNotFoundException"* ]]; then
    die "Unable to check Cognito user $ADMIN_USERNAME: $USER_LOOKUP"
  fi

  echo "  Creating Cognito user $ADMIN_USERNAME with email alias $DEFAULT_EMAIL ..."
  aws cognito-idp admin-create-user \
    --user-pool-id "$POOL_ID" \
    --username "$ADMIN_USERNAME" \
    --temporary-password "$DEFAULT_PASS" \
    --message-action SUPPRESS \
    --user-attributes \
      Name=email,Value="$DEFAULT_EMAIL" \
      Name=email_verified,Value=true \
    --region "$REGION" || die "Failed to create Cognito admin user."
fi

aws cognito-idp admin-set-user-password \
  --user-pool-id "$POOL_ID" \
  --username "$ADMIN_USERNAME" \
  --password "$DEFAULT_PASS" \
  --permanent \
  --region "$REGION" || die "Failed to set permanent Cognito admin password."

USER_STATUS=$(aws cognito-idp admin-get-user \
  --user-pool-id "$POOL_ID" \
  --username "$ADMIN_USERNAME" \
  --query UserStatus --output text --region "$REGION")
[[ "$USER_STATUS" == "CONFIRMED" ]] || die "Cognito user status is $USER_STATUS, expected CONFIRMED."
echo "  Cognito user confirmed; sign in with email alias $DEFAULT_EMAIL."

# ── Final step: Verify all deployed services ─────────────────────────────────
STEP=$( [[ "$SKIP_TRAINING" == "true" ]] && echo $((10 + PROFILES_OFFSET)) || echo $((13 + PROFILES_OFFSET)) )
step $STEP "Verify deployment readiness"
verify_deployment
activate_data_pipeline

# ── Summary ───────────────────────────────────────────────────────────────────
DASHBOARD_URL=$(aws cloudformation describe-stacks --stack-name PaintShopFrontend \
  --query "Stacks[0].Outputs[?OutputKey=='DashboardUrl'].OutputValue | [0]" \
  --output text --region "$REGION" 2>/dev/null || echo "(check PaintShopFrontend stack outputs)")
WS_ENDPOINT=$(aws cloudformation describe-stacks --stack-name PaintShopApi \
  --query "Stacks[0].Outputs[?OutputKey=='WsEndpoint'].OutputValue | [0]" \
  --output text --region "$REGION" 2>/dev/null || echo "(check PaintShopApi stack outputs)")

echo ""
echo -e "${GREEN}═══ Deployment Complete ═══${NC}"
echo "Frontend URL     : $DASHBOARD_URL"
echo "WebSocket        : $WS_ENDPOINT"
echo "Demo login email : $DEFAULT_EMAIL"
echo "Demo password    : configured from SPARK_ADMIN_PASSWORD (not displayed)"
echo ""
