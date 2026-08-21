"""Bedrock Application Inference Profiles for SPARK cost attribution.

Creates per-component inference profiles so costs appear in Cost Explorer
broken down by paintshop workflow (Capability tag) and environment.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

_HAIKU_MODEL_ID    = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
_TITAN_EMBED_ID    = "amazon.titan-embed-text-v2:0"
_FALLBACK_MODEL_ID = _HAIKU_MODEL_ID


def _inference_profile_arn(region: str, model_id: str) -> str:
    return f"arn:aws:bedrock:{region}::inference-profile/{model_id}"


def _foundation_model_arn(region: str, model_id: str) -> str:
    return f"arn:aws:bedrock:{region}::foundation-model/{model_id}"


@dataclass
class ProfileDefinition:
    name: str
    description: str
    model_source_arn: str
    tags: dict = field(default_factory=dict)


def get_default_profiles(env: str, cost_center: str, region: str) -> list[ProfileDefinition]:
    """Return the three default SPARK inference profile definitions.

    Args:
        env:         Deployment environment, e.g. "dev" or "prod".
        cost_center: Cost center identifier passed through to billing tags.
        region:      AWS region, e.g. "us-east-1".

    Returns:
        List of ProfileDefinition ready to pass to create_inference_profiles().
    """
    base_tags = {
        "Project":     "spark-paintshop-intelligence",
        "Environment": env,
        "CostCenter":  cost_center,
        "Application": "spark",
    }

    return [
        ProfileDefinition(
            name="spark-mps-agent",
            description="SPARK MPS supervisor agent — production scheduling inference",
            model_source_arn=_inference_profile_arn(region, _HAIKU_MODEL_ID),
            tags={**base_tags, "Capability": "production-scheduling", "Component": "mps-agent", "UsageType": "synchronous-inference"},
        ),
        ProfileDefinition(
            name="spark-rca-agent",
            description="SPARK RCA agent — root cause analysis inference",
            model_source_arn=_inference_profile_arn(region, _HAIKU_MODEL_ID),
            tags={**base_tags, "Capability": "root-cause-analysis", "Component": "rca-agent", "UsageType": "synchronous-inference"},
        ),
        ProfileDefinition(
            name="spark-kb-embeddings",
            description="SPARK knowledge base — SOP document embeddings",
            model_source_arn=_foundation_model_arn(region, _TITAN_EMBED_ID),
            tags={**base_tags, "Capability": "root-cause-analysis", "Component": "kb-embeddings", "UsageType": "embedding"},
        ),
    ]


def create_inference_profiles(boto3_client, profiles: list[ProfileDefinition]) -> dict[str, str]:
    """Create Bedrock Application Inference Profiles and return their ARNs.

    Idempotent: if a profile with the same name already exists it is reused.

    Args:
        boto3_client: A boto3 bedrock client (boto3.client("bedrock")).
        profiles:     List of ProfileDefinition from get_default_profiles().

    Returns:
        Dict mapping profile name to inferenceProfileArn.
    """
    arns: dict[str, str] = {}

    for p in profiles:
        tags_list = [{"key": k, "value": v} for k, v in p.tags.items()]
        try:
            resp = boto3_client.create_inference_profile(
                inferenceProfileName=p.name,
                description=p.description,
                modelSource={"copyFrom": p.model_source_arn},
                tags=tags_list,
            )
            arn = resp["inferenceProfileArn"]
            log.info("Created inference profile %s → %s", p.name, arn)
        except boto3_client.exceptions.ConflictException:
            arn = _find_existing_arn(boto3_client, p.name)
            log.info("Inference profile %s already exists → %s", p.name, arn)

        arns[p.name] = arn

    return arns


def _find_existing_arn(boto3_client, name: str) -> str:
    """Look up the ARN of an existing application inference profile by name."""
    paginator = boto3_client.get_paginator("list_inference_profiles")
    for page in paginator.paginate(typeEquals="APPLICATION"):
        for profile in page.get("inferenceProfileSummaries", []):
            if profile["inferenceProfileName"] == name:
                return profile["inferenceProfileArn"]
    raise RuntimeError(f"Inference profile '{name}' reported as existing but not found in list.")
