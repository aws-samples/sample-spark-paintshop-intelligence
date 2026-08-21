#!/usr/bin/env bash
# One-command teardown for all SPARK resources created by scripts/deploy.sh.
set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ASSUME_YES=false
[[ "${1:-}" == "--yes" ]] && ASSUME_YES=true

command -v aws >/dev/null 2>&1 || { echo "ERROR: aws CLI not found." >&2; exit 1; }
command -v cdk >/dev/null 2>&1 || { echo "ERROR: AWS CDK not found." >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found." >&2; exit 1; }

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
echo "This will permanently delete the SPARK deployment and data."
echo "Account: $ACCOUNT  Region: $REGION"
if [[ "$ASSUME_YES" != "true" ]]; then
  read -r -p "Type DELETE to continue: " CONFIRM
  [[ "$CONFIRM" == "DELETE" ]] || { echo "Cancelled."; exit 0; }
fi

cd "$ROOT_DIR"
python3 "$SCRIPT_DIR/destroy.py"

# CDK only needs the stack definitions for destruction; CloudFormation tracks
# the deployed physical bucket names. Avoid requiring or reconstructing them.
unset CDK_ML_BUCKET_NAME CDK_AUDIT_BUCKET_NAME CDK_FRONTEND_BUCKET_NAME
unset CDK_GENERATE_FRONTEND_BUCKET_NAME
export CDK_GENERATE_BUCKET_NAMES=true
cdk destroy --all --force --region "$REGION"
rm -rf cdk.out

echo "SPARK deployment destroyed successfully."
