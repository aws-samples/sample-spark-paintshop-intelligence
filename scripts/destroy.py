#!/usr/bin/env python3
"""Delete imperative SPARK resources before CDK destroys managed stacks."""
import os
from threading import Event

import boto3
from botocore.exceptions import ClientError
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
ACCOUNT = boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]
RUNTIME_NAMES = {"paintshop_mps_agent", "paintshop_rca_agent"}
SSM_PARAMETERS = [
    "/paintshop/mps_agent_runtime_arn", "/paintshop/rca_agent_runtime_arn",
    "/paintshop/gateway_url", "/paintshop/cognito_token_url",
    "/paintshop/cognito_scope", "/paintshop/cognito_mps_client_id",
    "/paintshop/cognito_mps_client_secret", "/paintshop/cognito_rca_client_id",
    "/paintshop/cognito_rca_client_secret", "/paintshop/kb_id",
    "/paintshop/kb_datasource_id", "/paintshop/demo_faults",
    "/paintshop/neptune_last_loaded_ts", "/spark/profiles/mps-agent-arn",
    "/spark/profiles/rca-agent-arn", "/spark/profiles/kb-embeddings-arn",
]


def _ignore_not_found(label, operation):
    try:
        operation()
        print(f"  Deleted {label}")
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code not in {
            "ResourceNotFoundException", "ParameterNotFound", "ValidationException",
            "NoSuchEntity", "NoSuchEntityException", "RepositoryNotFoundException",
        }:
            raise


def _wait_until(description, predicate, attempts=60, delay=5):
    for _ in range(attempts):
        if predicate():
            return
        Event().wait(delay)
    raise TimeoutError(f"Timed out waiting for {description}")


def delete_agentcore():
    print("\n[1/6] AgentCore runtimes and build artifacts")
    client = boto3.client("bedrock-agentcore-control", region_name=REGION)
    runtimes = client.list_agent_runtimes(maxResults=100).get("agentRuntimes", [])
    ids = []
    for runtime in runtimes:
        if runtime.get("agentRuntimeName") in RUNTIME_NAMES:
            runtime_id = runtime["agentRuntimeId"]
            try:
                client.delete_agent_runtime(agentRuntimeId=runtime_id)
                print(f"  Deleting runtime {runtime_id}")
            except client.exceptions.ResourceNotFoundException:
                pass
            ids.append(runtime_id)
    if ids:
        _wait_until(
            "AgentCore runtimes to be deleted",
            lambda: not any(
                r.get("agentRuntimeId") in ids
                for r in client.list_agent_runtimes(maxResults=100).get("agentRuntimes", [])
            ),
            attempts=90,
            delay=10,
        )

    codebuild = boto3.client("codebuild", region_name=REGION)
    for name in RUNTIME_NAMES:
        project = f"bedrock-agentcore-{name}-builder"
        try:
            codebuild.delete_project(name=project)
            print(f"  Deleted CodeBuild project {project}")
        except codebuild.exceptions.InvalidInputException:
            pass
    ecr = boto3.client("ecr", region_name=REGION)
    for name in RUNTIME_NAMES:
        _ignore_not_found(
            f"ECR repository bedrock-agentcore-{name}",
            lambda n=name: ecr.delete_repository(
                repositoryName=f"bedrock-agentcore-{n}", force=True
            ),
        )


def delete_gateway():
    print("\n[2/6] AgentCore Gateway, tools, and authentication")
    client = boto3.client("bedrock-agentcore-control", region_name=REGION)
    gateways = client.list_gateways(maxResults=100).get("items", [])
    for gateway in gateways:
        if gateway.get("name") != "paintshop-tools-gateway":
            continue
        gateway_id = gateway["gatewayId"]
        targets = client.list_gateway_targets(
            gatewayIdentifier=gateway_id, maxResults=100
        ).get("items", [])
        target_ids = {target["targetId"] for target in targets}
        for target_id in target_ids:
            client.delete_gateway_target(
                gatewayIdentifier=gateway_id, targetId=target_id
            )
        if target_ids:
            _wait_until(
                "Gateway targets to be deleted",
                lambda: not any(
                    target.get("targetId") in target_ids
                    for target in client.list_gateway_targets(
                        gatewayIdentifier=gateway_id, maxResults=100
                    ).get("items", [])
                ),
            )
        client.delete_gateway(gatewayIdentifier=gateway_id)
        print(f"  Deleting gateway {gateway_id}")
        _wait_until(
            "Gateway to be deleted",
            lambda: not any(
                item.get("gatewayId") == gateway_id
                for item in client.list_gateways(maxResults=100).get("items", [])
            ),
            attempts=60,
            delay=5,
        )

    lmb = boto3.client("lambda", region_name=REGION)
    for name in ("mps-tools", "rca-tools"):
        _ignore_not_found(name, lambda n=name: lmb.delete_function(FunctionName=n))

    cognito = boto3.client("cognito-idp", region_name=REGION)
    for pool in cognito.list_user_pools(MaxResults=60).get("UserPools", []):
        if pool.get("Name") == "paintshop-agents":
            pool_id = pool["Id"]
            _ignore_not_found(
                "Cognito domain",
                lambda: cognito.delete_user_pool_domain(
                    Domain=f"paintshop-agents-{ACCOUNT}", UserPoolId=pool_id
                ),
            )
            cognito.delete_user_pool(UserPoolId=pool_id)
            print(f"  Deleted Cognito pool {pool_id}")

    iam = boto3.client("iam", region_name=REGION)
    _ignore_not_found(
        "Gateway inline policy",
        lambda: iam.delete_role_policy(
            RoleName="PaintShopGatewayRole", PolicyName="GatewayToolsPolicy"
        ),
    )
    _ignore_not_found(
        "Gateway IAM role",
        lambda: iam.delete_role(RoleName="PaintShopGatewayRole"),
    )


def delete_knowledge_base():
    print("\n[3/6] Bedrock Knowledge Base and AOSS index")
    bedrock = boto3.client("bedrock-agent", region_name=REGION)
    matching = [
        kb for kb in bedrock.list_knowledge_bases(maxResults=100).get(
            "knowledgeBaseSummaries", []
        ) if kb.get("name") == "paintshop-sop-kb"
    ]
    for kb in matching:
        kb_id = kb["knowledgeBaseId"]
        data_sources = bedrock.list_data_sources(
            knowledgeBaseId=kb_id, maxResults=100
        ).get("dataSourceSummaries", [])
        data_source_ids = {ds["dataSourceId"] for ds in data_sources}
        for data_source_id in data_source_ids:
            bedrock.delete_data_source(
                knowledgeBaseId=kb_id, dataSourceId=data_source_id
            )
            print(f"  Deleting data source {data_source_id}")
        if data_source_ids:
            _wait_until(
                "Knowledge Base data sources to be deleted",
                lambda: not any(
                    ds.get("dataSourceId") in data_source_ids
                    for ds in bedrock.list_data_sources(
                        knowledgeBaseId=kb_id, maxResults=100
                    ).get("dataSourceSummaries", [])
                ),
                attempts=60,
                delay=5,
            )
        bedrock.delete_knowledge_base(knowledgeBaseId=kb_id)
        print(f"  Deleting knowledge base {kb_id}")

    if matching:
        ids = {kb["knowledgeBaseId"] for kb in matching}
        _wait_until(
            "Knowledge Base to be deleted",
            lambda: not any(
                kb.get("knowledgeBaseId") in ids
                for kb in bedrock.list_knowledge_bases(maxResults=100).get(
                    "knowledgeBaseSummaries", []
                )
            ),
            attempts=60,
            delay=5,
        )

    aoss = boto3.client("opensearchserverless", region_name=REGION)
    details = aoss.batch_get_collection(names=["paintshop-sop-kb"]).get(
        "collectionDetails", []
    )
    if details and details[0].get("status") == "ACTIVE":
        host = details[0]["collectionEndpoint"].replace("https://", "")
        credentials = boto3.Session(region_name=REGION).get_credentials()
        search = OpenSearch(
            hosts=[{"host": host, "port": 443}],
            http_auth=AWSV4SignerAuth(credentials, REGION, service="aoss"),
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            timeout=300,
        )
        if search.indices.exists(index="paintshop-sops"):
            search.indices.delete(index="paintshop-sops")
            print("  Deleted AOSS index paintshop-sops")


def delete_sagemaker():
    print("\n[4/6] SageMaker runtime resources")
    sm = boto3.client("sagemaker", region_name=REGION)
    endpoint = "paintshop-anomaly-endpoint"
    try:
        sm.delete_endpoint(EndpointName=endpoint)
        sm.get_waiter("endpoint_deleted").wait(
            EndpointName=endpoint, WaiterConfig={"Delay": 15, "MaxAttempts": 80}
        )
        print(f"  Deleted endpoint {endpoint}")
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ValidationException":
            raise

    for cfg in sm.list_endpoint_configs(NameContains=endpoint, MaxResults=100).get(
        "EndpointConfigs", []
    ):
        sm.delete_endpoint_config(EndpointConfigName=cfg["EndpointConfigName"])
        print(f"  Deleted endpoint config {cfg['EndpointConfigName']}")
    for model in sm.list_models(NameContains=endpoint, MaxResults=100).get("Models", []):
        sm.delete_model(ModelName=model["ModelName"])
        print(f"  Deleted model {model['ModelName']}")

    pipeline = "PaintShopAnomalyPipeline"
    try:
        executions = sm.list_pipeline_executions(
            PipelineName=pipeline, MaxResults=100
        ).get("PipelineExecutionSummaries", [])
        for execution in executions:
            if execution.get("PipelineExecutionStatus") in {"Executing", "Stopping"}:
                sm.stop_pipeline_execution(
                    PipelineExecutionArn=execution["PipelineExecutionArn"]
                )
        sm.delete_pipeline(PipelineName=pipeline)
        print(f"  Deleted pipeline {pipeline}")
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ValidationException":
            raise


def delete_profiles_and_parameters():
    print("\n[5/6] Bedrock profiles and generated parameters")
    bedrock = boto3.client("bedrock", region_name=REGION)
    names = {"spark-mps-agent", "spark-rca-agent", "spark-kb-embeddings"}
    paginator = bedrock.get_paginator("list_inference_profiles")
    for page in paginator.paginate(typeEquals="APPLICATION"):
        for profile in page.get("inferenceProfileSummaries", []):
            if profile.get("inferenceProfileName") in names:
                identifier = profile.get("inferenceProfileArn") or profile["inferenceProfileId"]
                bedrock.delete_inference_profile(
                    inferenceProfileIdentifier=identifier
                )
                print(f"  Deleted inference profile {profile['inferenceProfileName']}")

    ssm = boto3.client("ssm", region_name=REGION)
    for start in range(0, len(SSM_PARAMETERS), 10):
        ssm.delete_parameters(Names=SSM_PARAMETERS[start:start + 10])
    print("  Deleted generated SSM parameters")


def main():
    print(f"Destroying SPARK imperative resources in account {ACCOUNT}, region {REGION}")
    delete_agentcore()
    delete_gateway()
    delete_knowledge_base()
    delete_sagemaker()
    delete_profiles_and_parameters()
    print("\n[6/6] Imperative cleanup complete; CDK stacks can now be destroyed.")


if __name__ == "__main__":
    main()
