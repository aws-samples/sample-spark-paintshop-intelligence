import os
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_s3 as s3,
    Duration,
    RemovalPolicy,
)
from constructs import Construct


class StorageStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        audit_bucket_name = os.environ.get("CDK_AUDIT_BUCKET_NAME")
        ml_bucket_name = os.environ.get("CDK_ML_BUCKET_NAME")
        generate_bucket_names = (
            os.environ.get("CDK_GENERATE_BUCKET_NAMES", "").lower() == "true"
        )

        if generate_bucket_names:
            if audit_bucket_name or ml_bucket_name:
                raise ValueError(
                    "CDK_GENERATE_BUCKET_NAMES cannot be combined with explicit "
                    "CDK_ML_BUCKET_NAME or CDK_AUDIT_BUCKET_NAME values."
                )
        else:
            missing_names = [
                name
                for name, value in (
                    ("CDK_AUDIT_BUCKET_NAME", audit_bucket_name),
                    ("CDK_ML_BUCKET_NAME", ml_bucket_name),
                )
                if not value
            ]
            if missing_names:
                raise ValueError(
                    "Set explicit S3 bucket names before deployment: "
                    + ", ".join(missing_names)
                    + ". Existing deployments must use their current physical names "
                    "to prevent bucket replacement and data loss. For a fresh stack, "
                    "set CDK_GENERATE_BUCKET_NAMES=true."
                )

        # Audit log bucket (created first — referenced by main bucket's server access logging)
        self.audit_bucket = s3.Bucket(
            self,
            "AuditLogsBucket",
            bucket_name=audit_bucket_name,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            enforce_ssl=True,
        )

        # Bucket names are deployment inputs rather than hardcoded defaults. The
        # deployment script preserves existing physical names automatically.
        self.bucket = s3.Bucket(
            self,
            "MlPaintshopBucket",
            bucket_name=ml_bucket_name,
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            enforce_ssl=True,
            server_access_logs_bucket=self.audit_bucket,
            server_access_logs_prefix=(
                f"{ml_bucket_name}/" if ml_bucket_name else "ml-data/"
            ),
            lifecycle_rules=[
                # raw-synthetic/ → Glacier after 90 days
                s3.LifecycleRule(
                    id="archive-raw-synthetic",
                    prefix="raw-synthetic/",
                    enabled=True,
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER,
                            transition_after=Duration.days(90),
                        )
                    ],
                ),
                # processed/ → Glacier after 30 days post-training
                s3.LifecycleRule(
                    id="archive-processed",
                    prefix="processed/",
                    enabled=True,
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER,
                            transition_after=Duration.days(30),
                        )
                    ],
                ),
                # models/ retains all versions with no expiry — no lifecycle rule needed
            ],
        )

        cdk.CfnOutput(self, "BucketName", value=self.bucket.bucket_name,
                      description="ML data bucket name (used by training scripts)")
        cdk.CfnOutput(self, "AuditBucketName", value=self.audit_bucket.bucket_name,
                      description="S3 server access-log bucket name")

