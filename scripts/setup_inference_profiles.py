"""Opt-in setup script: create Bedrock Application Inference Profiles for SPARK cost tagging.

Run this script once (before or after initial deployment) to enable per-workflow
cost attribution in AWS Cost Explorer. Safe to re-run — existing profiles are reused.

After running this script, redeploy the agent stacks so the profile ARNs are
injected into the agent containers:

    python scripts/setup_inference_profiles.py --env dev --cost-center <your-cost-center>
    python src/training/deploy_agents.py

Then activate the cost allocation tags in the AWS Billing console:
    Project, Environment, CostCenter, Application, Capability, Component, UsageType
"""
import argparse
import logging
import os
import sys

import boto3

# Allow running from repo root without installing the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app_profiles import get_default_profiles, create_inference_profiles

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

SSM_MPS_PROFILE_ARN      = "/spark/profiles/mps-agent-arn"
SSM_RCA_PROFILE_ARN      = "/spark/profiles/rca-agent-arn"
SSM_KB_EMBEDDINGS_ARN    = "/spark/profiles/kb-embeddings-arn"

_PROFILE_SSM_KEYS = {
    "spark-mps-agent":    SSM_MPS_PROFILE_ARN,
    "spark-rca-agent":    SSM_RCA_PROFILE_ARN,
    "spark-kb-embeddings": SSM_KB_EMBEDDINGS_ARN,
}


def main():
    parser = argparse.ArgumentParser(description="Create SPARK Bedrock inference profiles.")
    parser.add_argument("--env",         required=True,  help="Deployment environment, e.g. dev or prod")
    parser.add_argument("--cost-center", required=True,  help="Cost center identifier for billing tags")
    parser.add_argument("--region",      default=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
    args = parser.parse_args()

    log.info("Creating SPARK inference profiles — env=%s region=%s", args.env, args.region)

    bedrock = boto3.client("bedrock", region_name=args.region)
    ssm     = boto3.client("ssm",     region_name=args.region)

    profiles = get_default_profiles(
        env=args.env,
        cost_center=args.cost_center,
        region=args.region,
    )

    arns = create_inference_profiles(bedrock, profiles)

    for name, arn in arns.items():
        param = _PROFILE_SSM_KEYS[name]
        ssm.put_parameter(Name=param, Value=arn, Type="String", Overwrite=True)
        log.info("SSM: %s = %s", param, arn)

    log.info("")
    log.info("Inference profile setup complete.")
    log.info("Activate these cost allocation tags in the AWS Billing console:")
    log.info("Project, Environment, CostCenter, Application, Capability, Component, UsageType")
    log.info("")
    log.info("Note: spark-kb-embeddings ARN written to SSM but CDK wiring for the")
    log.info("Knowledge Base is a separate future step — see app_profiles/ README.")


if __name__ == "__main__":
    main()
