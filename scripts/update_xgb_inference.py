"""Update the XGBoost inference code in the live SageMaker MCE endpoint.

This uploads the fixed xgboost_classifier/inference.py as a new sourcedir.tar.gz,
recreates the MCE SageMaker Model definition pointing to it (all three containers),
and updates the endpoint — WITHOUT retraining the models.

Usage:
  python scripts/update_xgb_inference.py
"""
import json, os, tarfile, tempfile, time
import boto3

REGION        = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
ACCOUNT       = boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]
BUCKET        = os.environ.get("BUCKET_NAME", "amzn-s3-demo-paintshop-ml")
ENDPOINT_NAME = "paintshop-anomaly-endpoint"
ENDPOINT_ROLE = f"arn:aws:iam::{ACCOUNT}:role/PaintShopEndpointRole"

sm = boto3.client("sagemaker",  region_name=REGION)
s3 = boto3.client("s3",         region_name=REGION)

SKLEARN_IMAGE = f"683313688378.dkr.ecr.{REGION}.amazonaws.com/sagemaker-scikit-learn:1.2-1-cpu-py3"
PYTORCH_IMAGE = f"763104351884.dkr.ecr.{REGION}.amazonaws.com/pytorch-inference:2.2.0-cpu-py310"
XGBOOST_IMAGE = f"683313688378.dkr.ecr.{REGION}.amazonaws.com/sagemaker-xgboost:1.7-1"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR    = os.path.join(SCRIPT_DIR, "..", "src", "training")


def upload_sourcedir(subdir: str, s3_key: str) -> str:
    code_dir = os.path.join(SRC_DIR, subdir)
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "sourcedir.tar.gz")
        with tarfile.open(archive, "w:gz") as tf:
            for fname in ["inference.py", "requirements.txt",
                          "scaler.joblib", "tank_medians.joblib"]:
                src = os.path.join(code_dir, fname)
                if os.path.exists(src):
                    tf.add(src, arcname=fname)
        s3.upload_file(archive, BUCKET, s3_key)
    uri = f"s3://{BUCKET}/{s3_key}"
    print(f"  Uploaded: {uri}")
    return uri


def get_current_containers() -> list:
    """Return the full container definitions currently deployed in the endpoint."""
    desc = sm.describe_endpoint(EndpointName=ENDPOINT_NAME)
    config_name = desc["EndpointConfigName"]
    config = sm.describe_endpoint_config(EndpointConfigName=config_name)
    model_name = config["ProductionVariants"][0]["ModelName"]
    model_desc = sm.describe_model(ModelName=model_name)
    containers = model_desc["Containers"]
    print("Current containers:")
    for c in containers:
        uri = c.get("ModelDataUrl") or c.get("ModelDataSource", {}).get("S3DataSource", {}).get("S3Uri", "?")
        print(f"  {c['ContainerHostname']}: {uri}")
    return containers


def main():
    print("=== XGBoost Inference Code Update ===")

    # 1. Upload updated sourcedirs for sklearn-based containers (IF + XGBoost)
    print("\n[1] Uploading updated sourcedirs...")
    if_sourcedir  = upload_sourcedir("isolation_forest",   "models/inference-code/TrainIsolationForest/sourcedir.tar.gz")
    xgb_sourcedir = upload_sourcedir("xgboost_classifier", "models/inference-code/TrainXGBoostClassifier/sourcedir.tar.gz")

    # 2. Get current container definitions from running endpoint
    print("\n[2] Getting current container definitions...")
    existing = get_current_containers()
    # Index by hostname
    by_host = {c["ContainerHostname"]: c for c in existing}

    def make_data_source(c: dict) -> dict:
        """Preserve the ModelDataSource format (S3DataSource) used by existing containers."""
        if "ModelDataSource" in c:
            return {"ModelDataSource": c["ModelDataSource"]}
        return {"ModelDataUrl": c["ModelDataUrl"]}

    # 3. Recreate the MCE SageMaker Model with updated sourcedirs
    print("\n[3] Recreating MCE model...")
    model_name = f"{ENDPOINT_NAME}-model"
    try:
        sm.delete_model(ModelName=model_name)
        print(f"  Deleted existing model: {model_name}")
    except Exception:
        pass

    sm.create_model(
        ModelName=model_name,
        ExecutionRoleArn=ENDPOINT_ROLE,
        Containers=[
            {
                "ContainerHostname": "isolation-forest",
                "Image":             SKLEARN_IMAGE,
                **make_data_source(by_host["isolation-forest"]),
                "Environment": {
                    "SAGEMAKER_PROGRAM":          "inference.py",
                    "SAGEMAKER_SUBMIT_DIRECTORY": if_sourcedir,
                },
            },
            {
                "ContainerHostname": "lstm-autoencoder",
                "Image":             PYTORCH_IMAGE,
                **make_data_source(by_host["lstm-autoencoder"]),
                "Environment": {"SAGEMAKER_PROGRAM": "inference.py"},
            },
            {
                "ContainerHostname": "xgboost-classifier",
                "Image":             XGBOOST_IMAGE,
                **make_data_source(by_host["xgboost-classifier"]),
                "Environment": {
                    "SAGEMAKER_PROGRAM":          "inference.py",
                    "SAGEMAKER_SUBMIT_DIRECTORY": xgb_sourcedir,
                },
            },
        ],
        InferenceExecutionConfig={"Mode": "Direct"},
    )
    print(f"  Created model: {model_name}")

    # 4. Recreate endpoint config
    print("\n[4] Recreating endpoint config...")
    config_name = f"{ENDPOINT_NAME}-config"
    try:
        sm.delete_endpoint_config(EndpointConfigName=config_name)
        print(f"  Deleted existing config: {config_name}")
    except Exception:
        pass

    sm.create_endpoint_config(
        EndpointConfigName=config_name,
        ProductionVariants=[{
            "VariantName":          "primary",
            "ModelName":            model_name,
            "InstanceType":         "ml.m5.xlarge",
            "InitialInstanceCount": 1,
        }],
    )
    print(f"  Created config: {config_name}")

    # 5. Update the endpoint
    print(f"\n[5] Updating endpoint {ENDPOINT_NAME}...")
    sm.update_endpoint(EndpointName=ENDPOINT_NAME, EndpointConfigName=config_name)
    print("  Update triggered — waiting for InService (~10 min)...")

    waiter = sm.get_waiter("endpoint_in_service")
    waiter.wait(EndpointName=ENDPOINT_NAME, WaiterConfig={"Delay": 30, "MaxAttempts": 40})
    print(f"\nEndpoint {ENDPOINT_NAME} is InService with updated XGBoost inference code.")


if __name__ == "__main__":
    main()
