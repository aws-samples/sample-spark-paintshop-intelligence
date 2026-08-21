#!/usr/bin/env python3
"""
Create the AOSS vector index, Bedrock Knowledge Base, and S3 data source.

Run after `cdk deploy PaintShopBedrock` — requires opensearch-py to be installed:
  pip install opensearch-py

Usage:
  python scripts/create_kb.py
"""
import boto3
import hashlib
import json
import os
import random
import time
from threading import Event

from botocore.exceptions import ClientError, WaiterError
from botocore.waiter import WaiterModel, create_waiter_with_client
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

COLLECTION_NAME = "paintshop-sop-kb"
INDEX_NAME      = "paintshop-sops"
KB_NAME         = "paintshop-sop-kb"
DS_NAME         = "paintshop-sop-docs"
REGION          = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
BUCKET          = os.environ.get("BUCKET_NAME", "amzn-s3-demo-paintshop-ml")

EMBEDDING_MODEL_ARN = (
    f"arn:aws:bedrock:{REGION}::foundation-model/amazon.titan-embed-text-v2:0"
)

INDEX_BODY = {
    "settings": {"index.knn": True},
    "mappings": {
        "properties": {
            "bedrock-knowledge-base-default-vector": {
                "type": "knn_vector",
                "dimension": 1024,
                "method": {
                    "name": "hnsw",
                    "engine": "faiss",
                    "space_type": "l2",
                    "parameters": {"ef_construction": 512, "m": 16},
                },
            },
            "AMAZON_BEDROCK_TEXT_CHUNK": {"type": "text"},
            "AMAZON_BEDROCK_METADATA":   {"type": "text", "index": False},
        }
    },
}


def get_collection_info():
    """Return (collection_id, endpoint, arn) for the paintshop-sop-kb collection."""
    aoss = boto3.client("opensearchserverless", region_name=REGION)
    resp = aoss.batch_get_collection(names=[COLLECTION_NAME])
    details = resp.get("collectionDetails", [])
    if not details:
        raise RuntimeError(
            f"Collection '{COLLECTION_NAME}' not found. "
            "Deploy PaintShopBedrock stack first."
        )
    col = details[0]
    status = col["status"]
    if status != "ACTIVE":
        raise RuntimeError(
            f"Collection '{COLLECTION_NAME}' is not ACTIVE (status={status}). "
            "Wait for CDK deploy to complete."
        )
    endpoint = col["collectionEndpoint"]
    host = endpoint.replace("https://", "")
    return col["id"], host, col["arn"]


def create_index(host: str):
    """Create the kNN vector index using opensearch-py + AWSV4SignerAuth."""
    session     = boto3.Session(region_name=REGION)
    credentials = session.get_credentials()
    auth        = AWSV4SignerAuth(credentials, REGION, service="aoss")

    client = OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=300,
    )

    if client.indices.exists(index=INDEX_NAME):
        print(f"  Index '{INDEX_NAME}' already exists — skipping creation.")
        return

    print(f"  Creating index '{INDEX_NAME}' ...")
    resp = client.indices.create(index=INDEX_NAME, body=INDEX_BODY)
    print(f"  Index created: {resp}")

    # Index creation is acknowledged synchronously. Verify that the required
    # vector mapping is visible before Bedrock is allowed to reference it.
    mapping = client.indices.get_mapping(index=INDEX_NAME)
    properties = mapping.get(INDEX_NAME, {}).get("mappings", {}).get("properties", {})
    if "bedrock-knowledge-base-default-vector" not in properties:
        raise RuntimeError(f"Index '{INDEX_NAME}' was created without the vector mapping")
    print(f"  Index '{INDEX_NAME}' mapping is ready.")


def get_kb_role_arn() -> str:
    """Look up the KB IAM role ARN (created by CDK)."""
    iam = boto3.client("iam")
    try:
        return iam.get_role(RoleName="PaintShopBedrockKbRole")["Role"]["Arn"]
    except iam.exceptions.NoSuchEntityException:
        raise RuntimeError(
            "IAM role 'PaintShopBedrockKbRole' not found. "
            "Deploy PaintShopBedrock stack first."
        )


def _is_transient_index_visibility_error(exc: ClientError) -> bool:
    """Return True only when Bedrock has not yet observed the new AOSS index."""
    error = exc.response.get("Error", {})
    message = str(error.get("Message", "")).lower()
    return (
        error.get("Code") == "ValidationException"
        and "dependency error document status code: 404" in message
        and f"no such index [{INDEX_NAME.lower()}]" in message
    )


def create_knowledge_base(collection_arn: str, kb_role_arn: str) -> str:
    """Create (or reuse) the Bedrock KB. Returns kb_id."""
    bdr = boto3.client("bedrock-agent", region_name=REGION)

    # Check if KB already exists
    for kb in bdr.list_knowledge_bases(maxResults=100).get("knowledgeBaseSummaries", []):
        if kb["name"] == KB_NAME:
            kb_id = kb["knowledgeBaseId"]
            print(f"  Knowledge base '{KB_NAME}' already exists: {kb_id}")
            return kb_id

    print(f"  Creating knowledge base '{KB_NAME}' ...")
    request = {
        "name": KB_NAME,
        "description": "SOP procedures for 12 paint-shop tanks — 9 fault types",
        "roleArn": kb_role_arn,
        "knowledgeBaseConfiguration": {
            "type": "VECTOR",
            "vectorKnowledgeBaseConfiguration": {
                "embeddingModelArn": EMBEDDING_MODEL_ARN,
            },
        },
        "storageConfiguration": {
            "type": "OPENSEARCH_SERVERLESS",
            "opensearchServerlessConfiguration": {
                "collectionArn": collection_arn,
                "vectorIndexName": INDEX_NAME,
                "fieldMapping": {
                    "vectorField": "bedrock-knowledge-base-default-vector",
                    "textField": "AMAZON_BEDROCK_TEXT_CHUNK",
                    "metadataField": "AMAZON_BEDROCK_METADATA",
                },
            },
        },
    }
    # Reuse one deterministic token across retries so a delayed successful
    # request cannot create a duplicate knowledge base.
    token_payload = json.dumps(request, sort_keys=True, separators=(",", ":"))
    request["clientToken"] = hashlib.sha256(token_payload.encode("utf-8")).hexdigest()

    deadline = time.monotonic() + 120
    max_attempts = 10
    for attempt in range(1, max_attempts + 1):
        try:
            resp = bdr.create_knowledge_base(**request)
            break
        except ClientError as exc:
            if not _is_transient_index_visibility_error(exc):
                raise

            remaining = deadline - time.monotonic()
            if attempt == max_attempts or remaining <= 0:
                raise RuntimeError(
                    f"Bedrock could not observe AOSS index '{INDEX_NAME}' within 120 seconds"
                ) from exc

            base_delay = min(10.0, float(2 ** (attempt - 1)))
            delay = min(remaining, base_delay * random.uniform(0.8, 1.2))
            print(
                f"  Bedrock cannot see index '{INDEX_NAME}' yet; "
                f"retrying in {delay:.1f}s (attempt {attempt}/{max_attempts}) ..."
            )
            Event().wait(delay)

    kb_id = resp["knowledgeBase"]["knowledgeBaseId"]
    print(f"  Knowledge base created: {kb_id}")

    waiter = create_waiter_with_client(
        "KnowledgeBaseActive",
        WaiterModel({
            "version": 2,
            "waiters": {
                "KnowledgeBaseActive": {
                    "operation": "GetKnowledgeBase",
                    "delay": 5,
                    "maxAttempts": 30,
                    "acceptors": [
                        {"state": "success", "matcher": "path", "argument": "knowledgeBase.status", "expected": "ACTIVE"},
                        {"state": "failure", "matcher": "path", "argument": "knowledgeBase.status", "expected": "FAILED"},
                        {"state": "failure", "matcher": "path", "argument": "knowledgeBase.status", "expected": "DELETE_UNSUCCESSFUL"},
                    ],
                }
            },
        }),
        bdr,
    )
    try:
        waiter.wait(knowledgeBaseId=kb_id)
    except WaiterError as exc:
        status = exc.last_response.get("knowledgeBase", {}).get("status", "UNKNOWN")
        raise RuntimeError(
            f"Knowledge base {kb_id} did not become ACTIVE (last status: {status})"
        ) from exc

    print("  Knowledge base is ACTIVE.")
    return kb_id


def create_data_source(kb_id: str) -> str:
    """Create (or reuse) the S3 data source. Returns ds_id."""
    bdr = boto3.client("bedrock-agent", region_name=REGION)

    for ds in bdr.list_data_sources(knowledgeBaseId=kb_id, maxResults=100).get("dataSourceSummaries", []):
        if ds["name"] == DS_NAME:
            ds_id = ds["dataSourceId"]
            print(f"  Data source '{DS_NAME}' already exists: {ds_id}")
            return ds_id

    bucket_arn = f"arn:aws:s3:::{BUCKET}"
    print(f"  Creating data source '{DS_NAME}' pointing to {bucket_arn}/knowledge-base/sops/ ...")
    resp = bdr.create_data_source(
        knowledgeBaseId=kb_id,
        name=DS_NAME,
        dataSourceConfiguration={
            "type": "S3",
            "s3Configuration": {
                "bucketArn": bucket_arn,
                "inclusionPrefixes": ["knowledge-base/sops/"],
            },
        },
        vectorIngestionConfiguration={
            "chunkingConfiguration": {
                "chunkingStrategy": "FIXED_SIZE",
                "fixedSizeChunkingConfiguration": {
                    "maxTokens": 512,
                    "overlapPercentage": 20,
                },
            },
        },
    )
    ds_id = resp["dataSource"]["dataSourceId"]
    print(f"  Data source created: {ds_id}")
    return ds_id


def write_ssm(kb_id: str, ds_id: str):
    """Write /paintshop/kb_id and /paintshop/kb_datasource_id to SSM."""
    ssm = boto3.client("ssm", region_name=REGION)
    for name, value in [
        ("/paintshop/kb_id", kb_id),
        ("/paintshop/kb_datasource_id", ds_id),
    ]:
        ssm.put_parameter(
            Name=name, Value=value, Type="String",
            Overwrite=True, Description=f"Bedrock KB — {name}",
        )
        print(f"  SSM {name} = {value}")


def main():
    print("=== Step 1: Get AOSS collection info ===")
    col_id, host, col_arn = get_collection_info()
    print(f"  Collection: {col_id}  endpoint: {host}")

    print("\n=== Step 2: Create AOSS vector index ===")
    create_index(host)

    print("\n=== Step 3: Get KB IAM role ===")
    kb_role_arn = get_kb_role_arn()
    print(f"  KB role: {kb_role_arn}")

    print("\n=== Step 4: Create Bedrock Knowledge Base ===")
    kb_id = create_knowledge_base(col_arn, kb_role_arn)

    print("\n=== Step 5: Create S3 data source ===")
    ds_id = create_data_source(kb_id)

    print("\n=== Step 6: Write SSM parameters ===")
    write_ssm(kb_id, ds_id)

    print(f"\n✓ Done.  KB ID: {kb_id}  DS ID: {ds_id}")


if __name__ == "__main__":
    main()
