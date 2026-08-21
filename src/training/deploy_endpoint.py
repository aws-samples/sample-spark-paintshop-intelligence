"""Deploy the Multi-Container Endpoint after the pipeline execution completes.

Run AFTER `python pipeline.py --start` finishes successfully.

What this does:
  1. Finds model artifact S3 URIs from the last successful pipeline execution
  2. Creates 3 SageMaker Models (IF, LSTM, XGB) with correct inference images
  3. Creates a Multi-Container Endpoint config (direct invocation mode)
  4. Creates or updates the paintshop-anomaly-endpoint

Usage:
  python deploy_endpoint.py
  python deploy_endpoint.py --execution-arn arn:aws:sagemaker:...   # specific run
"""
import argparse, json, os, tarfile, tempfile, time
import boto3

REGION        = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
ACCOUNT       = boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]
BUCKET        = os.environ.get("BUCKET_NAME", "amzn-s3-demo-paintshop-ml")
ENDPOINT_NAME = "paintshop-anomaly-endpoint"
ENDPOINT_ROLE = f"arn:aws:iam::{ACCOUNT}:role/PaintShopEndpointRole"
PIPELINE_NAME = "PaintShopAnomalyPipeline"

sm = boto3.client("sagemaker", region_name=REGION)

# ── Inference container images (AWS DLC, us-east-1) ──────────────────────
# Account 246618743249 = AWS-managed sklearn/xgboost containers
# Account 763104351884 = AWS Deep Learning Containers (PyTorch)
SKLEARN_IMAGE  = f"683313688378.dkr.ecr.{REGION}.amazonaws.com/sagemaker-scikit-learn:1.2-1-cpu-py3"
PYTORCH_IMAGE  = f"763104351884.dkr.ecr.{REGION}.amazonaws.com/pytorch-inference:2.2.0-cpu-py310"
XGBOOST_IMAGE  = f"683313688378.dkr.ecr.{REGION}.amazonaws.com/sagemaker-xgboost:1.7-1"


def get_model_artifacts(execution_arn: str | None) -> dict:
    """Return {step_name: model_artifact_s3_uri} from the pipeline execution."""
    if execution_arn is None:
        # Find last successful execution
        resp = sm.list_pipeline_executions(
            PipelineName=PIPELINE_NAME,
            SortBy="CreationTime",
            SortOrder="Descending",
        )
        execs = [e for e in resp["PipelineExecutionSummaries"]
                 if e["PipelineExecutionStatus"] == "Succeeded"]
        if not execs:
            raise RuntimeError("No succeeded pipeline executions found.")
        execution_arn = execs[0]["PipelineExecutionArn"]
        print(f"Using execution: {execution_arn}")

    steps = sm.list_pipeline_execution_steps(
        PipelineExecutionArn=execution_arn,
        SortOrder="Ascending",
    )["PipelineExecutionSteps"]

    artifacts = {}
    for step in steps:
        name = step["StepName"]
        if step.get("StepStatus") == "Succeeded" and "TrainingJob" in step.get("Metadata", {}):
            job_name  = step["Metadata"]["TrainingJob"]["Arn"].split("/")[-1]
            job_desc  = sm.describe_training_job(TrainingJobName=job_name)
            s3_uri    = job_desc["ModelArtifacts"]["S3ModelArtifacts"]
            artifacts[name] = s3_uri
            print(f"  {name}: {s3_uri}")

    required = {"TrainIsolationForest", "TrainLSTMAutoencoder", "TrainXGBoostClassifier"}
    missing  = required - set(artifacts.keys())
    if missing:
        raise RuntimeError(f"Missing model artifacts for steps: {missing}")

    return artifacts


def upload_sourcedir(step_name: str, code_dir: str) -> str:
    """Create a sourcedir.tar.gz from inference.py + requirements.txt and upload to S3.

    sklearn/xgboost serving containers require SAGEMAKER_SUBMIT_DIRECTORY to
    point to an S3 URI of a source archive; they do NOT scan model.tar.gz/code/.
    PyTorch (TorchServe) finds code/inference.py inside model.tar.gz automatically.
    """
    import shutil
    s3 = boto3.client("s3", region_name=REGION)
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "sourcedir.tar.gz")
        with tarfile.open(archive, "w:gz") as tf:
            for fname in ["inference.py", "requirements.txt",
                          "scaler.joblib", "tank_medians.joblib"]:
                src = os.path.join(code_dir, fname)
                if os.path.exists(src):
                    tf.add(src, arcname=fname)
        s3_key = f"models/inference-code/{step_name}/sourcedir.tar.gz"
        s3.upload_file(archive, BUCKET, s3_key)
        uri = f"s3://{BUCKET}/{s3_key}"
        print(f"  Sourcedir uploaded: {uri}")
        return uri


def repackage_artifacts(artifacts: dict) -> dict:
    """For PyTorch: embed code/inference.py inside model.tar.gz (TorchServe finds it there).
    For sklearn/xgboost: upload a separate sourcedir.tar.gz and store its S3 URI
    so create_mce_model can set SAGEMAKER_SUBMIT_DIRECTORY.

    Returns artifacts dict unchanged (model URIs stay the same);
    populates the module-level SOURCEDIR_URIS dict as a side-effect.
    """
    import shutil
    s3 = boto3.client("s3", region_name=REGION)
    src_dir = os.path.dirname(__file__)

    model_map = {
        "TrainIsolationForest":   "isolation_forest",
        "TrainLSTMAutoencoder":   "lstm_autoencoder",
        "TrainXGBoostClassifier": "xgboost_classifier",
    }
    # sklearn/xgboost: need separate sourcedir
    for step_name in ("TrainIsolationForest", "TrainXGBoostClassifier"):
        code_dir = os.path.join(src_dir, model_map[step_name])
        print(f"Uploading sourcedir for {step_name} ...")
        SOURCEDIR_URIS[step_name] = upload_sourcedir(step_name, code_dir)

    # Isolation Forest + XGBoost: bundle scaler.joblib + tank_medians.joblib into model.tar.gz
    # so model_fn can load them from model_dir at inference time (no NAT/network needed)
    xgb_code_dir = os.path.join(src_dir, "xgboost_classifier")
    for step_name in ("TrainIsolationForest", "TrainXGBoostClassifier"):
        original_uri = artifacts[step_name]
        print(f"Bundling scaler into {step_name} model.tar.gz ...")
        without_proto = original_uri[len("s3://"):]
        bucket, key   = without_proto.split("/", 1)
        with tempfile.TemporaryDirectory() as tmp:
            local_tar   = os.path.join(tmp, "model.tar.gz")
            extract_dir = os.path.join(tmp, "model")
            os.makedirs(extract_dir)
            s3.download_file(bucket, key, local_tar)
            with tarfile.open(local_tar, "r:gz") as tf:
                tf.extractall(extract_dir, filter="data")
            # Copy scaler artifacts from XGBoost code dir (shared preprocessing output)
            for fname in ["scaler.joblib", "tank_medians.joblib"]:
                src_file = os.path.join(xgb_code_dir, fname)
                if os.path.exists(src_file):
                    shutil.copy(src_file, os.path.join(extract_dir, fname))
                    print(f"  Added {fname}")
                else:
                    print(f"  WARNING: {fname} not found in {xgb_code_dir} — skipping")
            new_tar = os.path.join(tmp, "model-with-scaler.tar.gz")
            with tarfile.open(new_tar, "w:gz") as tf:
                for item in os.listdir(extract_dir):
                    tf.add(os.path.join(extract_dir, item), arcname=item)
            new_key = key.replace("output/model.tar.gz", "output/model-with-scaler.tar.gz")
            s3.upload_file(new_tar, bucket, new_key)
            artifacts = dict(artifacts)
            artifacts[step_name] = f"s3://{bucket}/{new_key}"
            print(f"  Uploaded: {artifacts[step_name]}")

    # PyTorch (LSTM): repack model.tar.gz to include code/inference.py
    step_name = "TrainLSTMAutoencoder"
    code_dir  = os.path.join(src_dir, model_map[step_name])
    original_uri = artifacts[step_name]
    print(f"Repackaging {step_name} with code/ ...")
    without_proto = original_uri[len("s3://"):]
    bucket, key   = without_proto.split("/", 1)
    with tempfile.TemporaryDirectory() as tmp:
        local_tar   = os.path.join(tmp, "model.tar.gz")
        extract_dir = os.path.join(tmp, "model")
        os.makedirs(extract_dir)
        s3.download_file(bucket, key, local_tar)
        with tarfile.open(local_tar, "r:gz") as tf:
            tf.extractall(extract_dir, filter="data")
        code_out = os.path.join(extract_dir, "code")
        os.makedirs(code_out, exist_ok=True)
        for fname in ["inference.py", "requirements.txt"]:
            src = os.path.join(code_dir, fname)
            if os.path.exists(src):
                shutil.copy(src, os.path.join(code_out, fname))
        new_tar = os.path.join(tmp, "model-with-code.tar.gz")
        with tarfile.open(new_tar, "w:gz") as tf:
            for item in os.listdir(extract_dir):
                tf.add(os.path.join(extract_dir, item), arcname=item)
        new_key = key.replace("output/model.tar.gz", "output/model-with-code.tar.gz")
        s3.upload_file(new_tar, bucket, new_key)
        artifacts = dict(artifacts)
        artifacts[step_name] = f"s3://{bucket}/{new_key}"
        print(f"  Uploaded: {artifacts[step_name]}")

    return artifacts


# populated by repackage_artifacts; used by create_mce_model
SOURCEDIR_URIS: dict = {}


def create_mce_model(artifacts: dict) -> str:
    model_name = f"{ENDPOINT_NAME}-model"
    try:
        sm.delete_model(ModelName=model_name)
        print(f"Deleted existing model: {model_name}")
    except sm.exceptions.ClientError:
        pass

    sm.create_model(
        ModelName=model_name,
        ExecutionRoleArn=ENDPOINT_ROLE,
        InferenceExecutionConfig={"Mode": "Direct"},   # Required for TargetContainerHostname
        Containers=[
            {
                "ContainerHostname": "isolation-forest",
                "Image":             SKLEARN_IMAGE,
                "ModelDataUrl":      artifacts["TrainIsolationForest"],
                "Environment": {
                    "SAGEMAKER_PROGRAM":          "inference.py",
                    "SAGEMAKER_SUBMIT_DIRECTORY": SOURCEDIR_URIS["TrainIsolationForest"],
                },
            },
            {
                "ContainerHostname": "lstm-autoencoder",
                "Image":             PYTORCH_IMAGE,
                "ModelDataUrl":      artifacts["TrainLSTMAutoencoder"],
                "Environment": {"SAGEMAKER_PROGRAM": "inference.py"},
            },
            {
                "ContainerHostname": "xgboost-classifier",
                "Image":             XGBOOST_IMAGE,
                "ModelDataUrl":      artifacts["TrainXGBoostClassifier"],
                "Environment": {
                    "SAGEMAKER_PROGRAM":          "inference.py",
                    "SAGEMAKER_SUBMIT_DIRECTORY": SOURCEDIR_URIS["TrainXGBoostClassifier"],
                },
            },
        ],
    )
    print(f"Created MCE model: {model_name}")
    return model_name


def create_endpoint_config(model_name: str) -> str:
    config_name = f"{ENDPOINT_NAME}-config"
    try:
        sm.delete_endpoint_config(EndpointConfigName=config_name)
        print(f"Deleted existing endpoint config: {config_name}")
    except sm.exceptions.ClientError:
        pass

    sm.create_endpoint_config(
        EndpointConfigName=config_name,
        ProductionVariants=[{
            "VariantName":        "primary",
            "ModelName":          model_name,
            "InstanceType":       "ml.m5.xlarge",
            "InitialInstanceCount": 1,
        }],
    )
    print(f"Created endpoint config: {config_name}")
    return config_name


def create_or_update_endpoint(config_name: str):
    try:
        sm.describe_endpoint(EndpointName=ENDPOINT_NAME)
        # Endpoint exists — update it
        sm.update_endpoint(EndpointName=ENDPOINT_NAME, EndpointConfigName=config_name)
        print(f"Updating endpoint: {ENDPOINT_NAME} ...")
    except sm.exceptions.ClientError:
        # Endpoint does not exist — create it
        sm.create_endpoint(EndpointName=ENDPOINT_NAME, EndpointConfigName=config_name)
        print(f"Creating endpoint: {ENDPOINT_NAME} ...")

    # Wait for InService
    print("Waiting for endpoint to be InService ...")
    waiter = sm.get_waiter("endpoint_in_service")
    waiter.wait(EndpointName=ENDPOINT_NAME, WaiterConfig={"Delay": 30, "MaxAttempts": 40})
    print(f"Endpoint ready: {ENDPOINT_NAME}")


def refresh_scaler_from_s3():
    """Download latest scaler.joblib and tank_medians.joblib from S3 preprocessing output."""
    s3c = boto3.client("s3", region_name=REGION)
    xgb_dir = os.path.join(os.path.dirname(__file__), "xgboost_classifier")
    for fname in ["scaler.joblib", "tank_medians.joblib"]:
        s3c.download_file(BUCKET, f"pipeline-data/processed/{fname}",
                          os.path.join(xgb_dir, fname))
        print(f"  Downloaded {fname} from S3")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-arn", default=None,
                        help="Specific pipeline execution ARN (default: last succeeded)")
    parser.add_argument("--if-artifact",   default=None, help="S3 URI for Isolation Forest model.tar.gz")
    parser.add_argument("--lstm-artifact", default=None, help="S3 URI for LSTM Autoencoder model.tar.gz")
    parser.add_argument("--xgb-artifact",  default=None, help="S3 URI for XGBoost model.tar.gz")
    args = parser.parse_args()

    print("=== Paint Shop — MCE Endpoint Deployment ===")

    if args.if_artifact and args.lstm_artifact and args.xgb_artifact:
        artifacts = {
            "TrainIsolationForest":    args.if_artifact,
            "TrainLSTMAutoencoder":    args.lstm_artifact,
            "TrainXGBoostClassifier":  args.xgb_artifact,
        }
        print(f"Using explicit artifact URIs:")
        for k, v in artifacts.items():
            print(f"  {k}: {v}")
    else:
        artifacts = get_model_artifacts(args.execution_arn)

    print("\nRefreshing scaler from S3 preprocessing output...")
    refresh_scaler_from_s3()

    artifacts   = repackage_artifacts(artifacts)
    model_name  = create_mce_model(artifacts)
    config_name = create_endpoint_config(model_name)
    create_or_update_endpoint(config_name)
    print(f"\nDone. Endpoint '{ENDPOINT_NAME}' is ready for inference.")


if __name__ == "__main__":
    main()
