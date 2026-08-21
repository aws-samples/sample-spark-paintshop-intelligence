import sys
import os
sys.path.insert(0, os.path.dirname(__file__))  # adds cdk/ to path so 'stacks.*' resolves to cdk/stacks/

import aws_cdk as cdk
from stacks.storage_stack import StorageStack
from stacks.iam_stack import IamStack
from stacks.sagemaker_stack import SageMakerStack
from stacks.ingestion_stack import IngestionStack
from stacks.neptune_stack import NeptuneStack
from stacks.bedrock_stack import BedrockStack
from stacks.scheduling_stack import SchedulingStack
from stacks.api_stack import ApiStack
from stacks.frontend_stack import FrontendStack
app = cdk.App()

env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1"),
)

storage = StorageStack(app, "PaintShopStorage", env=env)
iam = IamStack(
    app, "PaintShopIam",
    bucket=storage.bucket,
    env=env,
)
sagemaker = SageMakerStack(
    app, "PaintShopSageMaker",
    bucket=storage.bucket,
    pipeline_role=iam.pipeline_role,
    endpoint_role=iam.endpoint_role,
    env=env,
)

ingestion = IngestionStack(
    app, "PaintShopIngestion",
    bucket=storage.bucket,
    endpoint_name=sagemaker.endpoint_name,
    simulator_role_arn=iam.kinesis_sim_role_arn,
    processor_role_arn=iam.stream_proc_role_arn,
    env=env,
)
ingestion.add_dependency(iam)
ingestion.add_dependency(sagemaker)

neptune_stack = NeptuneStack(
    app, "PaintShopNeptune",
    bucket=storage.bucket,
    neptune_query_role=iam.neptune_query_role,
    env=env,
)
neptune_stack.add_dependency(storage)

bedrock_stack = BedrockStack(
    app, "PaintShopBedrock",
    invoker_role_arn=iam.supervisor_invoker_role_arn,
    rca_invoker_role_arn=iam.rca_invoker_role_arn,
    bucket=storage.bucket,
    aoss_admin_principal_arn=os.environ.get("AOSS_ADMIN_PRINCIPAL_ARN"),
    env=env,
)
bedrock_stack.add_dependency(storage)
bedrock_stack.add_dependency(iam)

scheduling = SchedulingStack(
    app, "PaintShopScheduling",
    supervisor_invoker=bedrock_stack.supervisor_invoker,
    rca_invoker=bedrock_stack.rca_invoker,
    applier_role_arn=iam.applier_role_arn,
    sfn_role_arn=iam.sfn_role_arn,
    env=env,
)
scheduling.add_dependency(iam)
scheduling.add_dependency(bedrock_stack)

api_stack = ApiStack(
    app, "PaintShopApi",
    tank_status_table=scheduling.tank_status_table,
    ws_connect_role_arn=iam.ws_connect_role_arn,
    ws_broadcast_role_arn=iam.ws_broadcast_role_arn,
    agent_stream_role_arn=iam.agent_stream_role_arn,
    api_handler_role_arn=iam.api_handler_role_arn,
    env=env,
)
api_stack.add_dependency(scheduling)

frontend_stack = FrontendStack(
    app, "PaintShopFrontend",
    web_acl_arn=api_stack.web_acl.attr_arn,
    user_pool_id=api_stack.user_pool.user_pool_id,
    user_pool_client_id=api_stack.user_pool_client.user_pool_client_id,
    identity_pool_id=api_stack.identity_pool.ref,
    ws_endpoint=f"wss://{api_stack.ws_api.api_id}.execute-api.us-east-1.amazonaws.com/prod",
    rest_api_endpoint=api_stack.http_api.api_endpoint,
    agent_stream_url=api_stack.agent_stream_url.url,
    env=env,
)
frontend_stack.add_dependency(api_stack)

app.synth()
