"""SageMaker Pipeline — PaintShop Anomaly Detection training.

Steps:
  1. Preprocessing     (SKLearn Processing) — normalise + split data
  2a. TrainIsolationForest  (SKLearn Training)   — parallel
  2b. TrainLSTMAutoencoder  (PyTorch Training)   — parallel
  2c. TrainXGBoostClassifier (XGBoost Training)  — parallel

After the pipeline execution completes, run deploy_endpoint.py to create
the Multi-Container Endpoint from the trained model artifacts.

Usage:
  pip install sagemaker boto3
  python pipeline.py            # register / update pipeline only
  python pipeline.py --start    # register + start an execution
"""
import argparse, os
import boto3
import sagemaker
from sagemaker.workflow.pipeline import Pipeline
from sagemaker.workflow.steps import ProcessingStep, TrainingStep
from sagemaker.workflow.pipeline_context import PipelineSession
from sagemaker.processing import ProcessingInput, ProcessingOutput
from sagemaker.sklearn.processing import SKLearnProcessor
from sagemaker.sklearn.estimator import SKLearn
from sagemaker.pytorch.estimator import PyTorch
from sagemaker.xgboost.estimator import XGBoost
from sagemaker.inputs import TrainingInput

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

_sts     = boto3.client("sts", region_name=REGION)
ACCOUNT  = _sts.get_caller_identity()["Account"]

BUCKET        = os.environ.get("BUCKET_NAME", "amzn-s3-demo-paintshop-ml")
PIPELINE_ROLE = f"arn:aws:iam::{ACCOUNT}:role/PaintShopPipelineRole"
PIPELINE_NAME = "PaintShopAnomalyPipeline"

# Absolute paths to training source directories
_HERE     = os.path.dirname(os.path.abspath(__file__))
PREP_SRC  = os.path.join(_HERE, "preprocessing")
IF_SRC    = os.path.join(_HERE, "isolation_forest")
LSTM_SRC  = os.path.join(_HERE, "lstm_autoencoder")
XGB_SRC   = os.path.join(_HERE, "xgboost_classifier")

RAW_S3    = f"s3://{BUCKET}/raw-synthetic"
PROC_S3   = f"s3://{BUCKET}/pipeline-data/processed"


def build_pipeline(sess: PipelineSession) -> Pipeline:

    # ── Step 1: Preprocessing ─────────────────────────────────────────────
    sklearn_processor = SKLearnProcessor(
        framework_version="1.2-1",
        instance_type="ml.m5.2xlarge",
        instance_count=1,
        role=PIPELINE_ROLE,
        sagemaker_session=sess,
    )

    proc_step = ProcessingStep(
        name="Preprocessing",
        processor=sklearn_processor,
        code=os.path.join(PREP_SRC, "preprocess.py"),
        inputs=[
            ProcessingInput(
                source=RAW_S3,
                destination="/opt/ml/processing/input",
                s3_data_distribution_type="FullyReplicated",
            )
        ],
        outputs=[
            ProcessingOutput(
                output_name="processed",
                source="/opt/ml/processing/output",
                destination=PROC_S3,
            )
        ],
    )

    # Reference to the processed output S3 path (resolved at execution time)
    proc_out = proc_step.properties.ProcessingOutputConfig.Outputs[
        "processed"
    ].S3Output.S3Uri

    train_input = TrainingInput(s3_data=proc_out, content_type="text/csv")

    # ── Step 2a: Isolation Forest ─────────────────────────────────────────
    if_estimator = SKLearn(
        entry_point="train.py",
        source_dir=IF_SRC,
        framework_version="1.2-1",
        instance_type="ml.m5.xlarge",
        instance_count=1,
        role=PIPELINE_ROLE,
        sagemaker_session=sess,
        output_path=f"s3://{BUCKET}/models/isolation-forest",
    )

    if_step = TrainingStep(
        name="TrainIsolationForest",
        estimator=if_estimator,
        inputs={"train": train_input},
        depends_on=[proc_step],
    )

    # ── Step 2b: LSTM Autoencoder ─────────────────────────────────────────
    lstm_estimator = PyTorch(
        entry_point="train.py",
        source_dir=LSTM_SRC,
        framework_version="2.2.0",
        py_version="py310",
        instance_type="ml.m5.2xlarge",
        instance_count=1,
        role=PIPELINE_ROLE,
        sagemaker_session=sess,
        output_path=f"s3://{BUCKET}/models/lstm-autoencoder",
    )

    lstm_step = TrainingStep(
        name="TrainLSTMAutoencoder",
        estimator=lstm_estimator,
        inputs={"train": train_input},
        depends_on=[proc_step],
    )

    # ── Step 2c: XGBoost Classifier ───────────────────────────────────────
    xgb_estimator = XGBoost(
        entry_point="train.py",
        source_dir=XGB_SRC,
        framework_version="1.7-1",
        instance_type="ml.m5.xlarge",
        instance_count=1,
        role=PIPELINE_ROLE,
        sagemaker_session=sess,
        output_path=f"s3://{BUCKET}/models/xgboost-classifier",
    )

    xgb_step = TrainingStep(
        name="TrainXGBoostClassifier",
        estimator=xgb_estimator,
        inputs={"train": train_input},
        depends_on=[proc_step],
    )

    return Pipeline(
        name=PIPELINE_NAME,
        steps=[proc_step, if_step, lstm_step, xgb_step],
        sagemaker_session=sess,
    )


def main():
    parser = argparse.ArgumentParser(description="Register and optionally start the SageMaker pipeline.")
    parser.add_argument("--start", action="store_true",
                        help="Start a pipeline execution after registering")
    args = parser.parse_args()

    boto_sess = boto3.Session(region_name=REGION)
    sm_sess   = PipelineSession(boto_session=boto_sess, default_bucket=BUCKET)

    print(f"Building pipeline '{PIPELINE_NAME}' ...")
    pipeline = build_pipeline(sm_sess)
    pipeline.upsert(role_arn=PIPELINE_ROLE)
    print(f"Pipeline registered/updated: {PIPELINE_NAME}")

    if args.start:
        execution = pipeline.start()
        print(f"Execution started: {execution.arn}")
        print(
            f"Monitor: https://console.aws.amazon.com/sagemaker/home"
            f"?region={REGION}#/pipelines/{PIPELINE_NAME}/executions"
        )
    else:
        print("Run with --start to begin training.")
        print(f"Or start from console: https://console.aws.amazon.com/sagemaker/home"
              f"?region={REGION}#/pipelines/{PIPELINE_NAME}")


if __name__ == "__main__":
    main()
