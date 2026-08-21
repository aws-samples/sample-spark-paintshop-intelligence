"""Deploy MPS and RCA Strands agents to Amazon Bedrock AgentCore Runtime.

Uses the starter toolkit's container deployment mode. Source is uploaded for an
AWS CodeBuild build, the image is pushed to ECR, and no local Docker is required.

Usage:
  python deploy_agents.py
  python deploy_agents.py --mps-only
  python deploy_agents.py --rca-only
"""
import argparse
import os
import boto3
from bedrock_agentcore_starter_toolkit import Runtime

REGION  = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
ACCOUNT = boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]
AGENT_ROLE = f"arn:aws:iam::{ACCOUNT}:role/PaintShopAgentCoreExecutionRole"

SSM_MPS_ARN = "/paintshop/mps_agent_runtime_arn"
SSM_RCA_ARN = "/paintshop/rca_agent_runtime_arn"

# Optional inference profile ARNs — written by scripts/setup_inference_profiles.py.
# If absent, agents fall back to the hardcoded model ID in agent.py.
_SSM_MPS_PROFILE = "/spark/profiles/mps-agent-arn"
_SSM_RCA_PROFILE = "/spark/profiles/rca-agent-arn"
_FALLBACK_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC_DIR = os.path.join(REPO_ROOT, "src", "agents")

ssm      = boto3.client("ssm",                          region_name=REGION)
cb       = boto3.client("codebuild",                    region_name=REGION)
s3       = boto3.client("s3",                           region_name=REGION)

COMMON_ENV = {
    "AWS_DEFAULT_REGION": REGION,
    "BUCKET_NAME":        os.environ.get("BUCKET_NAME", "amzn-s3-demo-paintshop-ml"),
    "JOBS_TABLE":         "production-jobs",
    "STATUS_TABLE":       "tank-status",
    "HISTORY_TABLE":      "schedule-history",
}

# S3 bucket the toolkit uses for CodeBuild source zips
_CB_SOURCES_BUCKET = f"bedrock-agentcore-codebuild-sources-{ACCOUNT}-{REGION}"
_LEGACY_ROOT_FILES = [
    os.path.join(REPO_ROOT, ".bedrock_agentcore.yaml"),
    os.path.join(REPO_ROOT, "Dockerfile"),
    os.path.join(REPO_ROOT, ".dockerignore"),
]


def _remove_file(path: str, description: str):
    try:
        os.remove(path)
        print(f"  Removed {description}: {path}")
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise RuntimeError(f"Unable to remove {description} {path}: {exc}") from exc


def _purge_stale_artifacts(runtime_name: str):
    """Remove cached cloud build artifacts while preserving the runtime."""
    cb_project = f"bedrock-agentcore-{runtime_name}-builder"
    try:
        cb.delete_project(name=cb_project)
        print(f"  Deleted CodeBuild project: {cb_project}")
    except cb.exceptions.InvalidInputException:
        pass  # project didn't exist
    except Exception as exc:
        print(f"  Warning (codebuild delete): {exc}")

    s3_key = f"{runtime_name}/source.zip"
    try:
        s3.delete_object(Bucket=_CB_SOURCES_BUCKET, Key=s3_key)
        print(f"  Deleted S3 source: s3://{_CB_SOURCES_BUCKET}/{s3_key}")
    except Exception as exc:
        print(f"  Warning (s3 delete): {exc}")


def deploy_agent(agent_name: str, env_vars: dict) -> str:
    """Deploy one agent from an isolated toolkit working directory."""
    agent_dir = os.path.abspath(os.path.join(SRC_DIR, agent_name))
    runtime_name = f"paintshop_{agent_name}"
    state_file = os.path.join(agent_dir, ".bedrock_agentcore.yaml")

    print(f"  Purging stale artifacts for {runtime_name} ...")
    _purge_stale_artifacts(runtime_name)
    _remove_file(state_file, "agent-specific toolkit state")

    # The starter toolkit derives its Docker build context, generated files, and
    # YAML binding from the current directory. Running configure+launch inside
    # the agent's own directory prevents RCA from reusing MPS source (and vice
    # versa). Both operations must remain inside this directory.
    previous_cwd = os.getcwd()
    try:
        os.chdir(agent_dir)
        print(f"  Configuring {runtime_name} from {agent_dir} ...")
        rt = Runtime()
        rt.configure(
            entrypoint="server.py",
            execution_role=AGENT_ROLE,
            agent_name=runtime_name,
            requirements_file="requirements.txt",
            region=REGION,
            auto_create_ecr=True,
            memory_mode="NO_MEMORY",
            non_interactive=True,
        )

        print(f"  Launching {runtime_name} ...")
        result = rt.launch(
            env_vars={**COMMON_ENV, **env_vars},
            auto_update_on_conflict=True,
        )
    finally:
        os.chdir(previous_cwd)

    arn = result.agent_arn
    print(f"  ARN: {arn}")
    return arn


def _get_model_id(profile_param: str) -> str:
    """Resolve the shared user override, application profile ARN, or default."""
    override = os.environ.get("SPARK_BEDROCK_MODEL_ID")
    if override:
        return override

    try:
        return ssm.get_parameter(Name=profile_param)["Parameter"]["Value"]
    except ssm.exceptions.ParameterNotFound:
        return _FALLBACK_MODEL_ID


def save_ssm(param: str, value: str):
    ssm.put_parameter(Name=param, Value=value, Type="String", Overwrite=True)
    print(f"  SSM: {param} = {value}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mps-only", action="store_true")
    parser.add_argument("--rca-only", action="store_true")
    args = parser.parse_args()

    print("=== AgentCore Runtime Deployment (container via AWS CodeBuild + ECR) ===")
    print(f"Account: {ACCOUNT}  Region: {REGION}")

    deploy_mps = not args.rca_only
    deploy_rca = not args.mps_only

    if deploy_mps:
        print("\n[MPS Agent]")
        mps_arn = deploy_agent("mps_agent", {
            "AGENT_MODULE":    "mps_agent",
            "OPTIMIZER_FN":    "schedule-optimizer",
            "BEDROCK_MODEL_ID": _get_model_id(_SSM_MPS_PROFILE),
        })
        save_ssm(SSM_MPS_ARN, mps_arn)

    if deploy_rca:
        print("\n[RCA Agent]")
        rca_arn = deploy_agent("rca_agent", {
            "AGENT_MODULE":    "rca_agent",
            "MAINT_TABLE":     "maintenance-log",
            "RCA_TABLE":       "rca-reports",
            "TIMESTREAM_DB":   "paintshop_telemetry",
            "TIMESTREAM_TBL":  "tank_readings",
            "BEDROCK_MODEL_ID": _get_model_id(_SSM_RCA_PROFILE),
        })
        save_ssm(SSM_RCA_ARN, rca_arn)

    print("\nDone.")


if __name__ == "__main__":
    main()
