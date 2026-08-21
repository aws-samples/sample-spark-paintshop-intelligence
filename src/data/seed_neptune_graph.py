"""Seed the Neptune knowledge graph with automatic idempotent reconciliation."""
import base64
import json
import os
import random
from threading import Event

import boto3
from botocore.config import Config

REGION    = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
LAMBDA_FN = "neptune-query"
MAX_SEED_ATTEMPTS = 3


def _invoke_seed(lmb) -> tuple[dict, dict]:
    resp = lmb.invoke(
        FunctionName=LAMBDA_FN,
        Payload=json.dumps({"action": "seed_graph"}).encode(),
        LogType="Tail",
    )
    logs = base64.b64decode(resp.get("LogResult", "")).decode()
    result = json.loads(resp["Payload"].read())
    print("\n--- Lambda logs ---")
    print(logs)
    print("--- Result ---")
    print(json.dumps(result, indent=2))
    return resp, result


def main():
    # Keep the client timeout above the Lambda timeout so a timed-out caller
    # cannot start a second invocation while the first one is still writing.
    lmb = boto3.client(
        "lambda",
        region_name=REGION,
        config=Config(read_timeout=660, connect_timeout=10, retries={"max_attempts": 3}),
    )

    for attempt in range(1, MAX_SEED_ATTEMPTS + 1):
        print(f"Invoking {LAMBDA_FN} → seed_graph (attempt {attempt}/{MAX_SEED_ATTEMPTS}) ...")
        resp, result = _invoke_seed(lmb)

        if resp.get("FunctionError"):
            print(f"Lambda returned {resp['FunctionError']}: {result}")
        elif "error" in result:
            print(f"Seed invocation error: {result['error']}")
        elif result.get("errors", 0) == 0:
            total = sum(v for k, v in result.items() if k != "errors")
            print(f"\nSeed complete: {total} items reconciled in Neptune.")
            return 0
        else:
            print(
                f"Seed pass left {result['errors']} unresolved operation(s); "
                "the next pass will reconcile only missing graph state through idempotent upserts."
            )

        if attempt < MAX_SEED_ATTEMPTS:
            delay = random.uniform(15.0, 30.0) * attempt
            print(f"Cooling down Neptune for {delay:.1f}s before automatic retry ...")
            Event().wait(delay)

    print(f"\nFAILED: Neptune seed did not converge after {MAX_SEED_ATTEMPTS} attempts.")
    return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
