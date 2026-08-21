"""BedrockStack — ECR repos, AgentCore invoker Lambdas, and AOSS collection.

Creates:
  - ECR repos: paintshop-mps-agent, paintshop-rca-agent
  - supervisor-invoker Lambda  (calls MPS AgentCore Runtime → SFN Branch A)
  - rca-invoker Lambda         (calls RCA AgentCore Runtime → SFN Branch B)
  - OpenSearch Serverless collection (VECTORSEARCH) for the knowledge base
  - AOSS encryption, network, and data access policies
  - IAM role for Bedrock Knowledge Base (PaintShopBedrockKbRole)

NOTE: The AOSS vector index, Bedrock Knowledge Base, and data source are
created by scripts/create_kb.py (run after cdk deploy) using opensearch-py
with AWSV4SignerAuth — the same pattern used in the reference CF template.
"""
import json
import os
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    aws_ecr as ecr,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_s3 as s3,
    aws_opensearchserverless as aoss,
    aws_ssm as ssm,
)
from constructs import Construct


class BedrockStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        invoker_role_arn: str,
        rca_invoker_role_arn: str,
        bucket: s3.IBucket,
        aoss_admin_principal_arn: str | None = None,
        **kwargs,
    ):
        super().__init__(scope, construct_id, **kwargs)

        src = os.path.join(os.path.dirname(__file__), "../../src/lambdas")

        # ── ECR repositories ───────────────────────────────────────────────
        self.mps_repo = ecr.Repository(
            self, "MpsAgentRepo",
            repository_name="paintshop-mps-agent",
            removal_policy=RemovalPolicy.DESTROY,
            empty_on_delete=True,
            lifecycle_rules=[ecr.LifecycleRule(max_image_count=5)],
        )
        self.rca_repo = ecr.Repository(
            self, "RcaAgentRepo",
            repository_name="paintshop-rca-agent",
            removal_policy=RemovalPolicy.DESTROY,
            empty_on_delete=True,
            lifecycle_rules=[ecr.LifecycleRule(max_image_count=5)],
        )

        # ── supervisor-invoker Lambda (MPS agent) ──────────────────────────
        invoker_role = iam.Role.from_role_arn(self, "InvokerRole", invoker_role_arn)
        self.supervisor_invoker = lambda_.Function(
            self, "SupervisorInvoker",
            function_name="supervisor-invoker",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset(
                os.path.join(src, "supervisor_invoker")
            ),
            role=invoker_role,
            timeout=Duration.seconds(120),
            environment={
                "MPS_RUNTIME_PARAM": "/paintshop/mps_agent_runtime_arn",
                "INCIDENTS_TABLE":   "incidents",
            },
        )

        # ── rca-invoker Lambda (RCA agent) ─────────────────────────────────
        rca_role = iam.Role.from_role_arn(self, "RcaInvokerRole", rca_invoker_role_arn)
        self.rca_invoker = lambda_.Function(
            self, "RcaInvoker",
            function_name="rca-invoker",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset(
                os.path.join(src, "rca_invoker")
            ),
            role=rca_role,
            timeout=Duration.seconds(120),
            environment={
                "RCA_RUNTIME_PARAM": "/paintshop/rca_agent_runtime_arn",
                "INCIDENTS_TABLE":   "incidents",
            },
        )

        # ── IAM role for Bedrock Knowledge Base ───────────────────────────
        # Fixed name so create_kb.py can reference it without CDK tokens.
        self.kb_role = iam.Role(
            self, "BedrockKbRole",
            role_name="PaintShopBedrockKbRole",
            assumed_by=iam.ServicePrincipal(
                "bedrock.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": self.account},
                    "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock:{self.region}:{self.account}:knowledge-base/*"},
                },
            ),
        )
        self.kb_role.add_to_policy(iam.PolicyStatement(
            sid="KbS3Read",
            actions=["s3:GetObject", "s3:ListBucket"],
            resources=[bucket.bucket_arn, f"{bucket.bucket_arn}/knowledge-base/sops/*"],
        ))
        self.kb_role.add_to_policy(iam.PolicyStatement(
            sid="KbEmbedding",
            actions=["bedrock:InvokeModel"],
            resources=[f"arn:aws:bedrock:{self.region}::foundation-model/amazon.titan-embed-text-v2:0"],
        ))

        # ── OpenSearch Serverless — encryption policy ──────────────────────
        enc_policy = aoss.CfnSecurityPolicy(
            self, "KbEncryptionPolicy",
            name="paintshop-kb-enc",
            type="encryption",
            policy=json.dumps({
                "Rules": [{"ResourceType": "collection",
                           "Resource": ["collection/paintshop-sop-kb"]}],
                "AWSOwnedKey": True,
            }),
        )

        # ── OpenSearch Serverless — network policy (public so Bedrock can reach it)
        net_policy = aoss.CfnSecurityPolicy(
            self, "KbNetworkPolicy",
            name="paintshop-kb-net",
            type="network",
            policy=json.dumps([{
                "Rules": [
                    {"ResourceType": "collection",
                     "Resource": ["collection/paintshop-sop-kb"]},
                    {"ResourceType": "dashboard",
                     "Resource": ["collection/paintshop-sop-kb"]},
                ],
                "AllowFromPublic": True,
            }]),
        )

        # ── OpenSearch Serverless collection ───────────────────────────────
        self.collection = aoss.CfnCollection(
            self, "SopKbCollection",
            name="paintshop-sop-kb",
            type="VECTORSEARCH",
            description="Vector store for SPARK paint-shop SOP knowledge base",
        )
        self.collection.add_dependency(enc_policy)
        self.collection.add_dependency(net_policy)

        # ── Data access policy ─────────────────────────────────────────────
        # Fixed role names → plain string ARNs resolved at synth time.
        # AOSS CfnAccessPolicy does NOT evaluate CloudFormation intrinsics in Policy.
        _acct = os.environ.get("CDK_DEFAULT_ACCOUNT", self.account)
        _kb_role_arn = f"arn:aws:iam::{_acct}:role/PaintShopBedrockKbRole"
        _principals = [_kb_role_arn]
        if aoss_admin_principal_arn:
            if (
                not aoss_admin_principal_arn.startswith(f"arn:aws:iam::{_acct}:")
                or aoss_admin_principal_arn.endswith(":root")
            ):
                raise ValueError(
                    "AOSS_ADMIN_PRINCIPAL_ARN must be a specific IAM user or role "
                    "in the deployment account"
                )
            _principals.append(aoss_admin_principal_arn)

        data_access_policy = aoss.CfnAccessPolicy(
            self, "KbDataAccessPolicy",
            name="paintshop-kb-access",
            type="data",
            policy=json.dumps([{
                "Rules": [
                    {
                        "ResourceType": "index",
                        "Resource": ["index/paintshop-sop-kb/*"],
                        "Permission": [
                            "aoss:CreateIndex", "aoss:DeleteIndex", "aoss:UpdateIndex",
                            "aoss:DescribeIndex", "aoss:ReadDocument", "aoss:WriteDocument",
                        ],
                    },
                    {
                        "ResourceType": "collection",
                        "Resource": ["collection/paintshop-sop-kb"],
                        "Permission": [
                            "aoss:DescribeCollectionItems", "aoss:CreateCollectionItems",
                            "aoss:UpdateCollectionItems",
                        ],
                    },
                ],
                # Only the Bedrock role and the explicitly configured deployment
                # identity may create or access this collection's vector index.
                "Principal": _principals,
            }]),
        )
        # Depend only on the underlying AWS::IAM::Role. Depending on the L2 role
        # would also include its collection-referencing default policy and create
        # a cycle: access policy -> role policy -> collection -> access policy.
        data_access_policy.add_dependency(self.kb_role.node.default_child)
        self.collection.add_dependency(data_access_policy)

        # AOSS IAM permission for the KB role
        self.kb_role.add_to_policy(iam.PolicyStatement(
            sid="AossAccess",
            actions=["aoss:APIAccessAll"],
            resources=[self.collection.attr_arn],
        ))

        # ── Outputs consumed by create_kb.py ───────────────────────────────
        CfnOutput(self, "AossCollectionEndpoint",
                  value=self.collection.attr_collection_endpoint,
                  description="AOSS collection endpoint for index creation")
        CfnOutput(self, "AossCollectionArn",
                  value=self.collection.attr_arn,
                  description="AOSS collection ARN")
        CfnOutput(self, "KbRoleArn",
                  value=self.kb_role.role_arn,
                  description="IAM role ARN for Bedrock Knowledge Base")
