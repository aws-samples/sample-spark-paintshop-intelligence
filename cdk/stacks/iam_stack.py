from aws_cdk import (
    Stack,
    aws_iam as iam,
    aws_s3 as s3,
)
from constructs import Construct


class IamStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        bucket: s3.IBucket,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        account = self.account
        region = self.region

        # ── SageMakerPipelineRole ──────────────────────────────────────────
        self.pipeline_role = iam.Role(
            self,
            "PipelineRole",
            role_name="PaintShopPipelineRole",
            assumed_by=iam.ServicePrincipal("sagemaker.amazonaws.com"),
            description="Allows SageMaker Pipeline to read/write the configured ML bucket and pull ECR images",
        )
        # S3: read + write scoped to the ML bucket only
        # s3:DeleteObject is intentionally omitted — training jobs only read inputs and write outputs
        self.pipeline_role.add_to_policy(iam.PolicyStatement(
            sid="S3ReadWrite",
            actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
            resources=[bucket.bucket_arn, f"{bucket.bucket_arn}/*"],
        ))
        # ECR: pull training container images (scoped to this account's repositories)
        # TODO: scope to specific repo ARNs once SageMaker training image URIs are finalised
        self.pipeline_role.add_to_policy(iam.PolicyStatement(
            sid="EcrPull",
            actions=[
                "ecr:BatchGetImage",
                "ecr:BatchCheckLayerAvailability",
                "ecr:GetDownloadUrlForLayer",
            ],
            resources=[
                f"arn:aws:ecr:{region}:{account}:repository/*",
            ],
        ))
        # ecr:GetAuthorizationToken requires * — AWS does not support resource-level scoping
        self.pipeline_role.add_to_policy(iam.PolicyStatement(
            sid="EcrAuth",
            actions=["ecr:GetAuthorizationToken"],
            resources=["*"],
        ))
        # CloudWatch Logs
        self.pipeline_role.add_to_policy(iam.PolicyStatement(
            sid="CloudWatchLogs",
            actions=["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
            resources=[f"arn:aws:logs:{region}:{account}:log-group:/aws/sagemaker/*"],
        ))
        # SageMaker Pipeline execution — create/describe training + processing jobs,
        # register models, and manage endpoint deployment
        self.pipeline_role.add_to_policy(iam.PolicyStatement(
            sid="SageMakerPipelineExecution",
            actions=[
                "sagemaker:CreateTrainingJob",    "sagemaker:DescribeTrainingJob",
                "sagemaker:StopTrainingJob",       "sagemaker:CreateProcessingJob",
                "sagemaker:DescribeProcessingJob", "sagemaker:StopProcessingJob",
                "sagemaker:CreateModel",           "sagemaker:DeleteModel",
                "sagemaker:DescribeModel",         "sagemaker:CreateModelPackage",
                "sagemaker:DescribeModelPackage",  "sagemaker:UpdateModelPackage",
                "sagemaker:ListModelPackages",     "sagemaker:CreateEndpointConfig",
                "sagemaker:DeleteEndpointConfig",  "sagemaker:CreateEndpoint",
                "sagemaker:UpdateEndpoint",        "sagemaker:DescribeEndpoint",
                "sagemaker:AddTags",               "sagemaker:ListTags",
                "sagemaker:ListPipelineExecutionSteps",
            ],
            resources=["*"],
        ))
        # iam:PassRole — pipeline must pass itself to training/processing child jobs
        self.pipeline_role.add_to_policy(iam.PolicyStatement(
            sid="IamPassRole",
            actions=["iam:PassRole"],
            resources=[
                f"arn:aws:iam::{account}:role/PaintShopPipelineRole",
                f"arn:aws:iam::{account}:role/PaintShopEndpointRole",
            ],
        ))

        # ── SageMakerEndpointRole ──────────────────────────────────────────
        self.endpoint_role = iam.Role(
            self,
            "EndpointRole",
            role_name="PaintShopEndpointRole",
            assumed_by=iam.ServicePrincipal("sagemaker.amazonaws.com"),
            description="Allows SageMaker Endpoint to read model artifacts from models/ prefix",
        )
        self.endpoint_role.add_to_policy(iam.PolicyStatement(
            sid="S3ReadModelsGetObject",
            actions=["s3:GetObject"],
            resources=[bucket.bucket_arn, f"{bucket.bucket_arn}/models/*"],
        ))
        self.endpoint_role.add_to_policy(iam.PolicyStatement(
            sid="S3ReadModelsListBucket",
            actions=["s3:ListBucket"],
            resources=[bucket.bucket_arn],
            conditions={"StringLike": {"s3:prefix": ["models/*"]}},
        ))
        # cloudwatch:PutMetricData requires * — no named CloudWatch resource ARN is valid
        self.endpoint_role.add_to_policy(iam.PolicyStatement(
            sid="CloudWatchMetrics",
            actions=["cloudwatch:PutMetricData"],
            resources=["*"],
        ))
        # ECR — pull SageMaker framework inference images (hosted in AWS-managed accounts)
        # ecr:GetAuthorizationToken has no resource-level scoping
        self.endpoint_role.add_to_policy(iam.PolicyStatement(
            sid="EcrAuth",
            actions=["ecr:GetAuthorizationToken"],
            resources=["*"],
        ))
        self.endpoint_role.add_to_policy(iam.PolicyStatement(
            sid="EcrPull",
            actions=[
                "ecr:BatchGetImage",
                "ecr:BatchCheckLayerAvailability",
                "ecr:GetDownloadUrlForLayer",
            ],
            resources=["*"],
        ))
        # CloudWatch Logs for endpoint container logs
        self.endpoint_role.add_to_policy(iam.PolicyStatement(
            sid="EndpointLogs",
            actions=["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
            resources=[f"arn:aws:logs:{region}:{account}:log-group:/aws/sagemaker/Endpoints/*"],
        ))

        # ── LambdaIngestRole ──────────────────────────────────────────────
        self.lambda_ingest_role = iam.Role(
            self,
            "LambdaIngestRole",
            role_name="PaintShopLambdaIngestRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Allows Lambda ingest to invoke SageMaker endpoint, publish SNS",
        )
        self.lambda_ingest_role.add_to_policy(iam.PolicyStatement(
            sid="SageMakerInvoke",
            actions=["sagemaker:InvokeEndpoint"],
            resources=[f"arn:aws:sagemaker:{region}:{account}:endpoint/paintshop-anomaly-detector"],
        ))
        self.lambda_ingest_role.add_to_policy(iam.PolicyStatement(
            sid="SnsPublish",
            actions=["sns:Publish"],
            resources=[f"arn:aws:sns:{region}:{account}:paintshop-alerts"],
        ))
        self.lambda_ingest_role.add_to_policy(iam.PolicyStatement(
            sid="CloudWatchLogs",
            actions=["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
            resources=[f"arn:aws:logs:{region}:{account}:log-group:/aws/lambda/*"],
        ))

        # ── ModelMonitorRole ──────────────────────────────────────────────
        self.monitor_role = iam.Role(
            self,
            "ModelMonitorRole",
            role_name="PaintShopModelMonitorRole",
            assumed_by=iam.ServicePrincipal("sagemaker.amazonaws.com"),
            description="Allows Model Monitor to read processed/ data and publish drift metrics",
        )
        self.monitor_role.add_to_policy(iam.PolicyStatement(
            sid="S3ReadProcessedGetObject",
            actions=["s3:GetObject"],
            resources=[bucket.bucket_arn, f"{bucket.bucket_arn}/processed/*"],
        ))
        self.monitor_role.add_to_policy(iam.PolicyStatement(
            sid="S3ReadProcessedListBucket",
            actions=["s3:ListBucket"],
            resources=[bucket.bucket_arn],
            conditions={"StringLike": {"s3:prefix": ["processed/*"]}},
        ))
        self.monitor_role.add_to_policy(iam.PolicyStatement(
            sid="S3WriteMonitorResults",
            actions=["s3:PutObject"],
            resources=[f"{bucket.bucket_arn}/monitoring/*"],
        ))
        # cloudwatch:PutMetricData requires * — no named CloudWatch resource ARN is valid
        self.monitor_role.add_to_policy(iam.PolicyStatement(
            sid="CloudWatchMetrics",
            actions=["cloudwatch:PutMetricData"],
            resources=["*"],
        ))
        self.monitor_role.add_to_policy(iam.PolicyStatement(
            sid="SnsPublish",
            actions=["sns:Publish"],
            resources=[f"arn:aws:sns:{region}:{account}:paintshop-alerts"],
        ))

        # ── KinesisSimulatorRole ──────────────────────────────────────────
        self.kinesis_sim_role = iam.Role(
            self, "KinesisSimulatorRole",
            role_name="PaintShopKinesisSimulatorRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ]
        )
        self.kinesis_sim_role.add_to_policy(iam.PolicyStatement(
            actions=["kinesis:PutRecord", "kinesis:PutRecords"],
            resources=[f"arn:aws:kinesis:{region}:{account}:stream/paintshop-tank-stream"]
        ))
        # Simulator reads /paintshop/demo_faults to apply active fault injections
        self.kinesis_sim_role.add_to_policy(iam.PolicyStatement(
            actions=["ssm:GetParameter"],
            resources=[f"arn:aws:ssm:{region}:{account}:parameter/paintshop/demo_faults"]
        ))
        # Simulator needs to seed and advance production-jobs + update tank-status
        self.kinesis_sim_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
                "dynamodb:Scan", "dynamodb:BatchWriteItem",
            ],
            resources=[
                f"arn:aws:dynamodb:{region}:{account}:table/production-jobs",
                f"arn:aws:dynamodb:{region}:{account}:table/production-jobs/index/*",
                f"arn:aws:dynamodb:{region}:{account}:table/tank-status",
            ]
        ))
        self.kinesis_sim_role_arn = self.kinesis_sim_role.role_arn

        # ── StreamProcessorRole ───────────────────────────────────────────
        self.stream_proc_role = iam.Role(
            self, "StreamProcessorRole",
            role_name="PaintShopStreamProcessorRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ]
        )
        self.stream_proc_role.add_to_policy(iam.PolicyStatement(
            actions=["kinesis:GetRecords", "kinesis:GetShardIterator",
                     "kinesis:DescribeStream", "kinesis:ListShards"],
            resources=[f"arn:aws:kinesis:{region}:{account}:stream/paintshop-tank-stream"]
        ))
        self.stream_proc_role.add_to_policy(iam.PolicyStatement(
            actions=["sagemaker:InvokeEndpoint"],
            resources=[f"arn:aws:sagemaker:{region}:{account}:endpoint/paintshop-anomaly-endpoint"]
        ))
        self.stream_proc_role.add_to_policy(iam.PolicyStatement(
            actions=["events:PutEvents"],
            resources=[f"arn:aws:events:{region}:{account}:event-bus/default"]
        ))
        self.stream_proc_role.add_to_policy(iam.PolicyStatement(
            actions=["ssm:GetParameter"],
            resources=[f"arn:aws:ssm:{region}:{account}:parameter/paintshop/*"]
        ))
        # Stream processor writes live sensor snapshots to tank-status
        # and reads active job JPH from production-jobs
        self.stream_proc_role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:PutItem", "dynamodb:UpdateItem"],
            resources=[f"arn:aws:dynamodb:{region}:{account}:table/tank-status"]
        ))
        self.stream_proc_role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:Scan"],
            resources=[
                f"arn:aws:dynamodb:{region}:{account}:table/production-jobs",
                f"arn:aws:dynamodb:{region}:{account}:table/production-jobs/index/*",
            ]
        ))
        # Stream processor appends time-series readings to sensor-history
        self.stream_proc_role.add_to_policy(iam.PolicyStatement(
            sid="SensorHistoryWrite",
            actions=["dynamodb:PutItem"],
            resources=[f"arn:aws:dynamodb:{region}:{account}:table/sensor-history"]
        ))
        self.stream_proc_role_arn = self.stream_proc_role.role_arn

        # ── NeptuneQueryRole ──────────────────────────────────────────────
        self.neptune_query_role = iam.Role(
            self, "NeptuneQueryRole",
            role_name="PaintShopNeptuneQueryRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaVPCAccessExecutionRole"),
            ]
        )
        self.neptune_query_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "neptune-db:ReadDataViaQuery",
                "neptune-db:WriteDataViaQuery",
                "neptune-db:GetEngineStatus",
                "neptune-db:connect",
            ],
            resources=[f"arn:aws:neptune-db:{region}:{account}:*/*"]
        ))
        # Loader reads RCA reports and schedule history from DynamoDB
        self.neptune_query_role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:Scan", "dynamodb:Query"],
            resources=[
                f"arn:aws:dynamodb:{region}:{account}:table/rca-reports",
                f"arn:aws:dynamodb:{region}:{account}:table/rca-reports/index/*",
                f"arn:aws:dynamodb:{region}:{account}:table/schedule-history",
                f"arn:aws:dynamodb:{region}:{account}:table/schedule-history/index/*",
            ]
        ))
        # SSM watermark parameter
        self.neptune_query_role.add_to_policy(iam.PolicyStatement(
            actions=["ssm:GetParameter", "ssm:PutParameter"],
            resources=[f"arn:aws:ssm:{region}:{account}:parameter/paintshop/*"]
        ))
        self.neptune_query_role_arn = self.neptune_query_role.role_arn

        # ── AgentCoreExecutionRole ────────────────────────────────────────
        self.agentcore_role = iam.Role(
            self, "AgentCoreExecutionRole",
            role_name="PaintShopAgentCoreExecutionRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ]
        )
        self.agentcore_role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            resources=["*"]
        ))
        self.agentcore_role.add_to_policy(iam.PolicyStatement(
            actions=["ecr:GetAuthorizationToken"],
            resources=["*"]
        ))
        self.agentcore_role.add_to_policy(iam.PolicyStatement(
            actions=["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"],
            resources=[
                f"arn:aws:ecr:{region}:{account}:repository/bedrock-agentcore-*",
            ]
        ))
        self.agentcore_role.add_to_policy(iam.PolicyStatement(
            actions=["lambda:InvokeFunction"],
            resources=[f"arn:aws:lambda:{region}:{account}:function:schedule-optimizer"]
        ))
        self.agentcore_role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:GetItem", "dynamodb:Query", "dynamodb:Scan"],
            resources=[
                f"arn:aws:dynamodb:{region}:{account}:table/production-jobs",
                f"arn:aws:dynamodb:{region}:{account}:table/production-jobs/index/*",
                f"arn:aws:dynamodb:{region}:{account}:table/tank-status",
                f"arn:aws:dynamodb:{region}:{account}:table/schedule-history",
                f"arn:aws:dynamodb:{region}:{account}:table/schedule-history/index/*",
                f"arn:aws:dynamodb:{region}:{account}:table/maintenance-log",
                f"arn:aws:dynamodb:{region}:{account}:table/maintenance-log/index/*",
                f"arn:aws:dynamodb:{region}:{account}:table/rca-reports",
                f"arn:aws:dynamodb:{region}:{account}:table/rca-reports/index/*",
            ]
        ))
        self.agentcore_role.add_to_policy(iam.PolicyStatement(
            actions=["ssm:GetParameter"],
            resources=[f"arn:aws:ssm:{region}:{account}:parameter/paintshop/*"]
        ))
        self.agentcore_role.add_to_policy(iam.PolicyStatement(
            sid="KbRetrieve",
            actions=["bedrock:Retrieve", "bedrock-agent-runtime:Retrieve"],
            resources=[f"arn:aws:bedrock:{region}:{account}:knowledge-base/*"]
        ))
        self.agentcore_role_arn = self.agentcore_role.role_arn

        # ── SfnExecutionRole ──────────────────────────────────────────────
        self.sfn_role = iam.Role(
            self, "SfnExecutionRole",
            role_name="PaintShopSfnExecutionRole",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
        )
        self.sfn_role.add_to_policy(iam.PolicyStatement(
            actions=["lambda:InvokeFunction"],
            resources=[
                f"arn:aws:lambda:{region}:{account}:function:schedule-validator",
                f"arn:aws:lambda:{region}:{account}:function:schedule-applier",
                f"arn:aws:lambda:{region}:{account}:function:recommendation-validator",
            ]
        ))
        self.sfn_role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:UpdateItem", "dynamodb:PutItem", "dynamodb:TransactWriteItems"],
            resources=[
                f"arn:aws:dynamodb:{region}:{account}:table/production-jobs",
                f"arn:aws:dynamodb:{region}:{account}:table/tank-status",
                f"arn:aws:dynamodb:{region}:{account}:table/schedule-history",
            ]
        ))
        self.sfn_role.add_to_policy(iam.PolicyStatement(
            actions=["lambda:InvokeFunction"],
            resources=[
                f"arn:aws:lambda:{region}:{account}:function:supervisor-invoker",
                f"arn:aws:lambda:{region}:{account}:function:rca-invoker",
                f"arn:aws:lambda:{region}:{account}:function:recommendation-validator",
                f"arn:aws:lambda:{region}:{account}:function:schedule-applier",
            ]
        ))
        self.sfn_role_arn = self.sfn_role.role_arn

        # ── SupervisorToolsRole ───────────────────────────────────────────
        self.supervisor_tools_role = iam.Role(
            self, "SupervisorToolsRole",
            role_name="PaintShopSupervisorToolsRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ]
        )
        self.supervisor_tools_role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Query", "dynamodb:Scan", "dynamodb:UpdateItem"],
            resources=[
                f"arn:aws:dynamodb:{region}:{account}:table/production-jobs",
                f"arn:aws:dynamodb:{region}:{account}:table/production-jobs/index/*",
                f"arn:aws:dynamodb:{region}:{account}:table/tank-status",
                f"arn:aws:dynamodb:{region}:{account}:table/schedule-history",
                f"arn:aws:dynamodb:{region}:{account}:table/schedule-history/index/*",
                f"arn:aws:dynamodb:{region}:{account}:table/maintenance-log",
                f"arn:aws:dynamodb:{region}:{account}:table/maintenance-log/index/*",
                f"arn:aws:dynamodb:{region}:{account}:table/rca-reports",
                f"arn:aws:dynamodb:{region}:{account}:table/rca-reports/index/*",
            ]
        ))
        # MPS tools Lambda invokes the optimizer; RCA tools Lambda invokes neptune-query
        self.supervisor_tools_role.add_to_policy(iam.PolicyStatement(
            actions=["lambda:InvokeFunction"],
            resources=[
                f"arn:aws:lambda:{region}:{account}:function:schedule-optimizer",
                f"arn:aws:lambda:{region}:{account}:function:neptune-query",
            ]
        ))
        self.supervisor_tools_role_arn = self.supervisor_tools_role.role_arn

        # ── SupervisorInvokerRole ─────────────────────────────────────────
        self.supervisor_invoker_role = iam.Role(
            self, "SupervisorInvokerRole",
            role_name="PaintShopSupervisorInvokerRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ]
        )
        self.supervisor_invoker_role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock-agentcore:InvokeAgentRuntime"],
            resources=["*"]
        ))
        self.supervisor_invoker_role.add_to_policy(iam.PolicyStatement(
            actions=["ssm:GetParameter"],
            resources=[f"arn:aws:ssm:{region}:{account}:parameter/paintshop/*"]
        ))
        self.supervisor_invoker_role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:UpdateItem"],
            resources=[f"arn:aws:dynamodb:{region}:{account}:table/incidents"]
        ))
        self.supervisor_invoker_role_arn = self.supervisor_invoker_role.role_arn

        # ── RcaInvokerRole ────────────────────────────────────────────────
        self.rca_invoker_role = iam.Role(
            self, "RcaInvokerRole",
            role_name="PaintShopRcaInvokerRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ]
        )
        self.rca_invoker_role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock-agentcore:InvokeAgentRuntime"],
            resources=["*"]
        ))
        self.rca_invoker_role.add_to_policy(iam.PolicyStatement(
            actions=["ssm:GetParameter"],
            resources=[f"arn:aws:ssm:{region}:{account}:parameter/paintshop/*"]
        ))
        self.rca_invoker_role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:UpdateItem"],
            resources=[f"arn:aws:dynamodb:{region}:{account}:table/incidents"]
        ))
        self.rca_invoker_role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:Query"],
            resources=[
                f"arn:aws:dynamodb:{region}:{account}:table/rca-reports",
                f"arn:aws:dynamodb:{region}:{account}:table/rca-reports/index/tank-rca-index",
            ]
        ))
        self.rca_invoker_role_arn = self.rca_invoker_role.role_arn

        # ── ScheduleApplierRole ───────────────────────────────────────────
        self.applier_role = iam.Role(
            self, "ScheduleApplierRole",
            role_name="PaintShopScheduleApplierRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ]
        )
        self.applier_role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:TransactWriteItems", "dynamodb:PutItem", "dynamodb:UpdateItem"],
            resources=[
                f"arn:aws:dynamodb:{region}:{account}:table/production-jobs",
                f"arn:aws:dynamodb:{region}:{account}:table/tank-status",
                f"arn:aws:dynamodb:{region}:{account}:table/schedule-history",
            ]
        ))
        self.applier_role_arn = self.applier_role.role_arn

        # ── WsConnectRole (shared by ws-connect + ws-disconnect) ──────────
        self.ws_connect_role = iam.Role(
            self, "WsConnectRole",
            role_name="PaintShopWsConnectRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ]
        )
        self.ws_connect_role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:PutItem", "dynamodb:DeleteItem", "dynamodb:GetItem"],
            resources=[f"arn:aws:dynamodb:{region}:{account}:table/ws-connections"]
        ))
        self.ws_connect_role_arn = self.ws_connect_role.role_arn

        # ── WsBroadcastRole ───────────────────────────────────────────────
        self.ws_broadcast_role = iam.Role(
            self, "WsBroadcastRole",
            role_name="PaintShopWsBroadcastRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ]
        )
        self.ws_broadcast_role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:Scan", "dynamodb:DeleteItem"],
            resources=[f"arn:aws:dynamodb:{region}:{account}:table/ws-connections"]
        ))
        # DynamoDB Streams read permission (for tank-status stream trigger)
        self.ws_broadcast_role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:GetRecords", "dynamodb:GetShardIterator",
                     "dynamodb:DescribeStream", "dynamodb:ListStreams"],
            resources=[f"arn:aws:dynamodb:{region}:{account}:table/tank-status/stream/*"]
        ))
        self.ws_broadcast_role.add_to_policy(iam.PolicyStatement(
            actions=["execute-api:ManageConnections"],
            resources=[f"arn:aws:execute-api:{region}:{account}:*/prod/POST/@connections/*"]
        ))
        # ws-broadcast invokes AgentCore Runtime for stream-agent WebSocket action
        self.ws_broadcast_role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock-agentcore:InvokeAgentRuntime"],
            resources=["*"]
        ))
        self.ws_broadcast_role.add_to_policy(iam.PolicyStatement(
            actions=["ssm:GetParameter"],
            resources=[f"arn:aws:ssm:{region}:{account}:parameter/paintshop/*"]
        ))
        self.ws_broadcast_role_arn = self.ws_broadcast_role.role_arn

        # ── AgentStreamRole ───────────────────────────────────────────────
        self.agent_stream_role = iam.Role(
            self, "AgentStreamRole",
            role_name="PaintShopAgentStreamRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ]
        )
        self.agent_stream_role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock-agentcore:InvokeAgentRuntime"],
            resources=["*"]
        ))
        self.agent_stream_role.add_to_policy(iam.PolicyStatement(
            actions=["ssm:GetParameter"],
            resources=[f"arn:aws:ssm:{region}:{account}:parameter/paintshop/*"]
        ))
        self.agent_stream_role_arn = self.agent_stream_role.role_arn

        # ── ApiHandlerRole ────────────────────────────────────────────────
        self.api_handler_role = iam.Role(
            self, "ApiHandlerRole",
            role_name="PaintShopApiHandlerRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ]
        )
        self.api_handler_role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:GetItem", "dynamodb:Scan", "dynamodb:Query"],
            resources=[
                f"arn:aws:dynamodb:{region}:{account}:table/tank-status",
                f"arn:aws:dynamodb:{region}:{account}:table/production-jobs",
                f"arn:aws:dynamodb:{region}:{account}:table/production-jobs/index/*",
                f"arn:aws:dynamodb:{region}:{account}:table/rca-reports",
                f"arn:aws:dynamodb:{region}:{account}:table/rca-reports/index/*",
                f"arn:aws:dynamodb:{region}:{account}:table/maintenance-log",
                f"arn:aws:dynamodb:{region}:{account}:table/maintenance-log/index/*",
                f"arn:aws:dynamodb:{region}:{account}:table/sensor-history",
                f"arn:aws:dynamodb:{region}:{account}:table/incidents",
                f"arn:aws:dynamodb:{region}:{account}:table/incidents/index/incidents-tank-time-index",
            ]
        ))
        self.api_handler_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "dynamodb:BatchWriteItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
            ],
            resources=[
                f"arn:aws:dynamodb:{region}:{account}:table/tank-status",
                f"arn:aws:dynamodb:{region}:{account}:table/production-jobs",
            ]
        ))
        self.api_handler_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "lambda:GetEventSourceMapping",
                "lambda:ListEventSourceMappings",
                "lambda:UpdateEventSourceMapping",
            ],
            resources=["*"]
        ))
        self.api_handler_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "events:DescribeRule",
                "events:EnableRule",
                "events:DisableRule",
            ],
            resources=[f"arn:aws:events:{region}:{account}:rule/paintshop-simulator-schedule"]
        ))
        self.api_handler_role.add_to_policy(iam.PolicyStatement(
            actions=["ssm:GetParameter", "ssm:PutParameter", "ssm:DeleteParameter"],
            resources=[f"arn:aws:ssm:{region}:{account}:parameter/paintshop/demo_faults"]
        ))
        self.api_handler_role_arn = self.api_handler_role.role_arn
