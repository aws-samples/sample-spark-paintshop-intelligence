# Step-by-Step Deployment

> For most use cases, the one-command deploy in the main [README](../README.md#installation) is sufficient.
> Use this guide if you need to run individual steps, resume a failed deploy, or understand what each step does.

---

### 1. Bootstrap CDK

```bash
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
cdk bootstrap aws://${ACCOUNT}/us-east-1
```

### 2. Deploy all 9 CDK stacks

Bucket names are deployment inputs. For a fresh deployment, have CloudFormation generate globally unique physical names:

```bash
unset CDK_ML_BUCKET_NAME CDK_AUDIT_BUCKET_NAME CDK_FRONTEND_BUCKET_NAME
unset CDK_GENERATE_FRONTEND_BUCKET_NAME
export CDK_GENERATE_BUCKET_NAMES=true
```

Do not use the reserved `amzn-s3-demo-` prefix for deployable buckets; AWS reserves it for documentation examples and rejects bucket creation. For existing `PaintShopStorage` and `PaintShopFrontend` stacks, unset generation mode and set all bucket variables to their **current physical bucket names** instead. Changing a value replaces that bucket and can delete its contents. The recommended `scripts/deploy.sh` command discovers and preserves each existing bucket independently, generates names for missing stacks, and rejects accidental replacements.

```bash
# Clear any cached lookups from a previous account
echo '{}' > cdk.context.json

cdk deploy --all --require-approval never
```

Stacks deployed (in dependency order):

| Stack | What it creates |
|-------|----------------|
| `PaintShopStorage` | Deployment-configured ML data and audit-log S3 buckets |
| `PaintShopIam` | All IAM roles |
| `PaintShopSageMaker` | SageMaker domain + execution role |
| `PaintShopIngestion` | Kinesis stream + DynamoDB tables |
| `PaintShopNeptune` | Neptune serverless cluster + query Lambda |
| `PaintShopBedrock` | ECR repos + AgentCore invoker Lambdas + AOSS collection |
| `PaintShopScheduling` | EventBridge + Step Functions |
| `PaintShopApi` | REST API + WebSocket API + Cognito + WAF |
| `PaintShopFrontend` | CloudFront + S3 frontend bucket |

After CDK deploy, export the ML bucket name for the training steps:

```bash
export BUCKET_NAME=$(aws cloudformation describe-stacks --stack-name PaintShopStorage \
  --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue" --output text)
echo "ML bucket: $BUCKET_NAME"
```

### 3. Generate synthetic training data

```bash
python src/data/generate_training_data.py
```

Uploads 6 months × 12 tanks of labelled sensor readings to S3 (~960k rows).

### 4. Run the SageMaker training pipeline

```bash
python src/training/pipeline.py --start
```

Runs three parallel training jobs: Isolation Forest, LSTM Autoencoder, XGBoost classifier (~15 min). Wait for status `Succeeded` before continuing:

```bash
aws sagemaker list-pipeline-executions \
  --pipeline-name PaintShopAnomalyPipeline \
  --sort-by CreationTime --sort-order Descending --max-results 1 \
  --query "PipelineExecutionSummaries[0].PipelineExecutionStatus" --output text
```

### 5. Deploy the SageMaker Multi-Container Endpoint

```bash
python src/training/deploy_endpoint.py
```

Creates `paintshop-anomaly-endpoint` (`InferenceExecutionConfig: Direct`, ml.m5.xlarge). Takes ~10 min.

### 6. Create the AOSS vector index and Bedrock Knowledge Base

```bash
python scripts/create_kb.py
```

Creates the OpenSearch Serverless vector index and Bedrock Knowledge Base using `opensearch-py` with `AWSV4SignerAuth`. Writes KB ID and data source ID to SSM (`/paintshop/kb_id`, `/paintshop/kb_datasource_id`). Must run before uploading SOP documents.

### 7. Upload SOP documents and sync the Bedrock Knowledge Base

```bash
python src/data/upload_sop_docs.py
```

Uploads all 33 SOP markdown files to `s3://$BUCKET_NAME/knowledge-base/sops/`, then triggers a Bedrock Knowledge Base ingestion job that chunks and embeds the documents into OpenSearch Serverless (~2 min). The RCA agent calls the KB at analysis time to retrieve step-by-step remediation procedures.

### 8. Set up AgentCore Gateway

```bash
python scripts/setup_gateway.py
```

Creates Cognito M2M clients, AgentCore Gateway with JWT authoriser, and Lambda tool targets for both agents.

### 9. Deploy AI agents

```bash
python src/training/deploy_agents.py
```

Triggers AWS CodeBuild to build ARM64 Docker images and deploy MPS + RCA agents to Bedrock AgentCore. **Local Docker is not required** — the build runs in CodeBuild in the cloud (~5 min per agent).

### Optional: Enable Bedrock Cost Attribution

SPARK supports per-workflow cost tagging in AWS Cost Explorer using Bedrock Application Inference Profiles. The application runs normally without this step — it is purely additive and can be run at any time before or after initial deployment.

> A re-deploy of the agents (step 9) is required after running the script for the profile ARNs to take effect.

**Step 1 — Activate cost allocation tags** (one-time, AWS Billing console)

In the AWS Billing console go to **Cost allocation tags** and activate the following keys:

`Project` · `Environment` · `CostCenter` · `Application` · `Capability` · `Component` · `UsageType`

> There is a ~24 hr delay before newly activated tags appear in Cost Explorer.

**Step 2 — Create inference profiles**

```bash
python scripts/setup_inference_profiles.py --env dev --cost-center cc-paint-shop
```

- `--env` — deployment environment: `dev` or `prod`
- `--cost-center` — the cost center identifier your finance team uses for this project (e.g. `cc-paint-shop`, `8421`). This becomes the `CostCenter` tag value in Cost Explorer.
- `--region` — optional; defaults to `AWS_DEFAULT_REGION` if set, otherwise `us-east-1`

Creates three Bedrock Application Inference Profiles (MPS agent, RCA agent, KB embeddings) and writes their ARNs to SSM. Safe to re-run — existing profiles are reused.

**Step 3 — Redeploy agents**

```bash
python src/training/deploy_agents.py
```

The agents pick up the inference profile ARNs from SSM and use them for all subsequent Bedrock calls.

**Viewing costs in Cost Explorer**

Start with a base filter on all SPARK Bedrock costs:
- **Service** = `Amazon Bedrock`
- **Tag: Project** = `spark-paintshop-intelligence`

Then use the views below depending on what you want to see:

| View | Group by | Filter by | What you get |
|------|----------|-----------|--------------|
| Cost by workflow | Tag: Capability | _(base only)_ | `production-scheduling` vs `root-cause-analysis` totals |
| Total RCA cost (agent + KB) | Tag: Component | Tag: Capability = `root-cause-analysis` | `rca-agent` + `kb-embeddings` combined, with per-component split |
| Dev vs prod split | Tag: Environment | _(base only)_ | Cost breakdown by environment |
| All SPARK components | Tag: Component | _(base only)_ | Per-component breakdown across all workflows |

### 10. Seed the Neptune knowledge graph

```bash
python src/data/seed_neptune_graph.py
```

Seeds 12 tank vertices, 33 fault-type vertices with SOPs and `s3_doc_key` pointers, and causal chain edges. This gives the RCA agent its fault context and enables metadata-filtered KB lookups.

### 11. Build and deploy the React dashboard

```bash
bash scripts/deploy_frontend.sh
```

Reads CDK outputs to generate `public/config.json`, builds the Vite app, syncs to S3, and invalidates CloudFront.

### 12. Create a Cognito user

Retrieve strong, unique values from your approved secret manager, or generate them securely for this shell session without printing them:

```bash
TEMPORARY_PASSWORD="$(openssl rand -base64 32)"
PERMANENT_PASSWORD="$(openssl rand -base64 32)"
export TEMPORARY_PASSWORD PERMANENT_PASSWORD

POOL_ID=$(aws cloudformation describe-stacks --stack-name PaintShopApi \
  --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" --output text)

aws cognito-idp admin-create-user \
  --user-pool-id $POOL_ID \
  --username admin@example.com \
  --temporary-password "$TEMPORARY_PASSWORD" \
  --user-attributes Name=email,Value=admin@example.com Name=email_verified,Value=true

aws cognito-idp admin-set-user-password \
  --user-pool-id $POOL_ID \
  --username admin@example.com \
  --password "$PERMANENT_PASSWORD" \
  --permanent
```
