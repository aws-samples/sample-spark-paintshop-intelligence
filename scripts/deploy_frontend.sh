#!/usr/bin/env bash
# deploy_frontend.sh — build React app, generate config.json, sync to S3, invalidate CloudFront
set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
STACK_NAME="PaintShopApi"
FRONTEND_STACK="PaintShopFrontend"
FRONTEND_DIR="$(cd "$(dirname "$0")/../frontend" && pwd)"
CONFIG_FILE="$FRONTEND_DIR/public/config.json"

# config.json contains deployment-specific public identifiers. Keep it out of
# source archives and remove it on both successful and failed deployments.
cleanup_config() {
  rm -f "$CONFIG_FILE"
}
trap cleanup_config EXIT

echo "==> Fetching stack outputs..."

get_output() {
  aws cloudformation describe-stacks \
    --stack-name "$1" \
    --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue" \
    --output text
}

USER_POOL_ID=$(get_output "$STACK_NAME"  "UserPoolId")
CLIENT_ID=$(get_output    "$STACK_NAME"  "UserPoolClientId")
IDENTITY_POOL=$(get_output "$STACK_NAME" "IdentityPoolId")
WS_ENDPOINT=$(get_output   "$STACK_NAME" "WsEndpoint")
REST_API=$(get_output      "$STACK_NAME" "RestApiEndpoint")
AGENT_URL=$(get_output     "$STACK_NAME" "AgentStreamUrl")
BUCKET=$(get_output        "$FRONTEND_STACK" "BucketName")
DIST_ID=$(get_output       "$FRONTEND_STACK" "DistributionId")

echo "  UserPoolId:    $USER_POOL_ID"
echo "  ClientId:      $CLIENT_ID"
echo "  IdentityPool:  $IDENTITY_POOL"
echo "  WsEndpoint:    $WS_ENDPOINT"
echo "  RestApi:       $REST_API"
echo "  Bucket:        $BUCKET"
echo "  Distribution:  $DIST_ID"

echo "==> Writing config.json..."
cat > "$FRONTEND_DIR/public/config.json" <<EOF
{
  "userPoolId":       "$USER_POOL_ID",
  "userPoolClientId": "$CLIENT_ID",
  "identityPoolId":   "$IDENTITY_POOL",
  "wsEndpoint":       "$WS_ENDPOINT",
  "restApiEndpoint":  "$REST_API",
  "agentStreamUrl":   "$AGENT_URL",
  "region":           "$REGION"
}
EOF

echo "==> Installing npm dependencies..."
cd "$FRONTEND_DIR"
npm ci

echo "==> Building React app..."
npm run build

echo "==> Syncing to S3..."
aws s3 sync dist/ "s3://$BUCKET/" \
  --delete \
  --region "$REGION" \
  --cache-control "public,max-age=31536000,immutable" \
  --exclude "index.html" \
  --exclude "config.json"

# index.html and config.json must not be cached
aws s3 cp dist/index.html "s3://$BUCKET/index.html" \
  --region "$REGION" \
  --cache-control "no-cache,no-store,must-revalidate"

aws s3 cp "$FRONTEND_DIR/public/config.json" "s3://$BUCKET/config.json" \
  --region "$REGION" \
  --cache-control "no-cache,no-store,must-revalidate"

echo "==> Invalidating CloudFront distribution $DIST_ID..."
aws cloudfront create-invalidation \
  --distribution-id "$DIST_ID" \
  --paths "/*" \
  --region "$REGION"

echo "==> Done! Dashboard:"
aws cloudformation describe-stacks \
  --stack-name "$FRONTEND_STACK" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='DashboardUrl'].OutputValue" \
  --output text
