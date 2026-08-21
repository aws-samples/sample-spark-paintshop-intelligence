# Post-Deploy Verification

Use these commands to confirm all components are running after deployment.

```bash
# Check SageMaker endpoint is InService
aws sagemaker describe-endpoint --endpoint-name paintshop-anomaly-endpoint \
  --query EndpointStatus --output text

# Check AgentCore runtimes are READY
aws bedrock-agentcore-control list-agent-runtimes \
  --query "agentRuntimes[*].{name:agentRuntimeName,status:status}"

# Check Bedrock Knowledge Base is ACTIVE
aws bedrock-agent get-knowledge-base \
  --knowledge-base-id $(aws ssm get-parameter --name /paintshop/kb_id --query Parameter.Value --output text) \
  --query 'knowledgeBase.status' --output text

# Get dashboard URL
aws cloudformation describe-stacks --stack-name PaintShopFrontend \
  --query "Stacks[0].Outputs[?OutputKey=='DashboardUrl'].OutputValue" --output text
```

## Key DynamoDB Tables

| Table | Purpose |
|-------|---------|
| `tank-status` | Live sensor snapshot + ML scores per tank |
| `production-jobs` | Paint-line job queue (IN_PROGRESS / QUEUED / RESCHEDULED) |
| `rca-reports` | Root-cause analysis reports written by the RCA agent |
| `ws-connections` | Active WebSocket connection IDs |

## Key SSM Parameters

| Parameter | Value |
|-----------|-------|
| `/paintshop/mps_agent_runtime_arn` | MPS AgentCore runtime ARN |
| `/paintshop/rca_agent_runtime_arn` | RCA AgentCore runtime ARN |
| `/paintshop/kb_id` | Bedrock Knowledge Base ID |
| `/paintshop/kb_datasource_id` | Bedrock KB S3 data source ID |
| `/paintshop/gateway_url` | AgentCore Gateway MCP endpoint URL |
| `/paintshop/demo_faults` | JSON map of active fault injections `{tank_id: {fault_type, start_ts}}` |
| `/spark/profiles/mps-agent-arn` | MPS inference profile ARN (written by `setup_inference_profiles.py`) |
| `/spark/profiles/rca-agent-arn` | RCA inference profile ARN (written by `setup_inference_profiles.py`) |
| `/spark/profiles/kb-embeddings-arn` | KB embeddings inference profile ARN (written by `setup_inference_profiles.py`) |
