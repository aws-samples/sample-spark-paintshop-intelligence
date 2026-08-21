import os
import random
from threading import Event

import boto3
from botocore.exceptions import ClientError, WaiterError
from botocore.waiter import WaiterModel, create_waiter_with_client

BUCKET = os.environ.get("BUCKET_NAME", "amzn-s3-demo-paintshop-ml")
SOP_DIR = os.path.join(os.path.dirname(__file__), "sop_docs")
PREFIX  = "knowledge-base/sops"
INDEX_NAME = "paintshop-sops"
S3  = boto3.client("s3")
SSM = boto3.client("ssm")
BDR = boto3.client("bedrock-agent")


def upload_sops():
    files = [f for f in os.listdir(SOP_DIR) if f.endswith(".md")]
    for fname in sorted(files):
        local = os.path.join(SOP_DIR, fname)
        key   = f"{PREFIX}/{fname}"
        S3.upload_file(local, BUCKET, key, ExtraArgs={"ContentType": "text/markdown"})
        print(f"Uploaded {fname} -> s3://{BUCKET}/{key}")
    print(f"Done. {len(files)} SOP documents uploaded.")


def _index_not_visible(value) -> bool:
    if isinstance(value, ClientError):
        message = str(value.response.get("Error", {}).get("Message", ""))
    else:
        message = str(value)
    message = message.lower()
    return (
        f"no such index [{INDEX_NAME}]" in message
        or ("storage configuration provided is invalid" in message and "404" in message)
    )


def _wait_before_retry(attempt: int, deadline: float):
    remaining = deadline - __import__("time").monotonic()
    if remaining <= 0:
        raise TimeoutError(
            f"Bedrock could not observe AOSS index '{INDEX_NAME}' within 10 minutes"
        )
    delay = min(remaining, min(60.0, 5.0 * (2 ** (attempt - 1))))
    delay *= random.uniform(0.8, 1.2)
    print(
        f"Bedrock ingestion cannot see index '{INDEX_NAME}' yet; "
        f"retrying in {delay:.1f}s (attempt {attempt}/10) ..."
    )
    Event().wait(delay)


def sync_knowledge_base():
    """Start ingestion and absorb the eventual-consistency window automatically."""
    kb_id = SSM.get_parameter(Name="/paintshop/kb_id")["Parameter"]["Value"]
    ds_id = SSM.get_parameter(Name="/paintshop/kb_datasource_id")["Parameter"]["Value"]

    waiter = create_waiter_with_client(
        "IngestionComplete",
        WaiterModel({
            "version": 2,
            "waiters": {
                "IngestionComplete": {
                    "operation": "GetIngestionJob",
                    "delay": 10,
                    "maxAttempts": 30,
                    "acceptors": [
                        {"state": "success", "matcher": "path", "argument": "ingestionJob.status", "expected": "COMPLETE"},
                        {"state": "failure", "matcher": "path", "argument": "ingestionJob.status", "expected": "FAILED"},
                        {"state": "failure", "matcher": "path", "argument": "ingestionJob.status", "expected": "STOPPED"},
                    ],
                }
            },
        }),
        BDR,
    )

    time_module = __import__("time")
    deadline = time_module.monotonic() + 600
    for attempt in range(1, 11):
        print(f"Starting KB ingestion job (kb={kb_id}, ds={ds_id}) ...")
        try:
            resp = BDR.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)
        except ClientError as exc:
            if not _index_not_visible(exc) or attempt == 10:
                raise
            _wait_before_retry(attempt, deadline)
            continue

        job_id = resp["ingestionJob"]["ingestionJobId"]
        try:
            waiter.wait(
                knowledgeBaseId=kb_id,
                dataSourceId=ds_id,
                ingestionJobId=job_id,
            )
            print("KB ingestion complete.")
            return
        except WaiterError as exc:
            job = exc.last_response.get("ingestionJob", {})
            status = job.get("status", "UNKNOWN")
            reasons = job.get("failureReasons", [])
            if status == "FAILED" and _index_not_visible(reasons) and attempt < 10:
                _wait_before_retry(attempt, deadline)
                continue
            if status in ("FAILED", "STOPPED"):
                raise RuntimeError(
                    f"KB ingestion ended with status {status}: {reasons}"
                ) from exc
            raise TimeoutError("KB ingestion did not complete within 5 minutes") from exc

    raise TimeoutError(f"KB ingestion retries exhausted for index '{INDEX_NAME}'")


if __name__ == "__main__":
    upload_sops()
    sync_knowledge_base()
