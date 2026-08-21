import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_iam as iam,
    aws_s3 as s3,
    aws_sagemaker as sagemaker,
)
from constructs import Construct

# Endpoint name constant — referenced by IngestionStack (stream-processor Lambda env var).
# The actual endpoint + endpoint config are created by the training pipeline after models
# are trained; CDK only provisions the Model Registry Group here.
_ENDPOINT_NAME = "paintshop-anomaly-endpoint"


class SageMakerStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        bucket: s3.IBucket,
        pipeline_role: iam.IRole,
        endpoint_role: iam.IRole,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── Model Registry Group ──────────────────────────────────────────
        # Central registry for Isolation Forest + LSTM + XGBoost model versions.
        # Training pipeline registers models here; approval gate gates deployment.
        self._model_package_group = sagemaker.CfnModelPackageGroup(
            self,
            "ModelPackageGroup",
            model_package_group_name="PaintShopAnomalyDetector",
            model_package_group_description=(
                "Paint shop anomaly detection: Isolation Forest + LSTM Autoencoder + "
                "XGBoost Fault Classifier. Approval: PendingManualApproval -> Approved -> Deployed."
            ),
        )

        # endpoint_name exposed so IngestionStack can reference it before the endpoint exists
        self.endpoint_name = _ENDPOINT_NAME

    @property
    def model_package_group_name(self) -> str:
        return self._model_package_group.model_package_group_name
