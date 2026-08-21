"""FrontendStack — S3 + CloudFront + WAF for the React paint shop dashboard."""
import os

from aws_cdk import (
    Stack,
    RemovalPolicy,
    CfnOutput,
    aws_s3 as s3,
    aws_cloudfront as cf,
    aws_cloudfront_origins as origins,
)
from constructs import Construct


class FrontendStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        web_acl_arn: str,
        user_pool_id: str,
        user_pool_client_id: str,
        identity_pool_id: str,
        ws_endpoint: str,
        rest_api_endpoint: str,
        agent_stream_url: str,
        **kwargs,
    ):
        super().__init__(scope, construct_id, **kwargs)

        # ── S3 bucket for React app ────────────────────────────────────────
        frontend_bucket_name = os.environ.get("CDK_FRONTEND_BUCKET_NAME")
        frontend_generation_mode = os.environ.get(
            "CDK_GENERATE_FRONTEND_BUCKET_NAME"
        )
        generate_bucket_name = (
            frontend_generation_mode
            if frontend_generation_mode is not None
            else os.environ.get("CDK_GENERATE_BUCKET_NAMES", "")
        ).lower() == "true"

        if generate_bucket_name:
            if frontend_bucket_name:
                raise ValueError(
                    "Generated frontend bucket mode cannot be combined with "
                    "CDK_FRONTEND_BUCKET_NAME."
                )
        elif not frontend_bucket_name:
            raise ValueError(
                "Set CDK_FRONTEND_BUCKET_NAME to the current physical name for "
                "an existing stack, or enable generated bucket names for a fresh stack."
            )

        self.bucket = s3.Bucket(
            self, "DashboardBucket",
            bucket_name=frontend_bucket_name,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        # ── Origin Access Identity (CloudFront → S3) ───────────────────────
        oai = cf.OriginAccessIdentity(self, "DashboardOai",
            comment="PaintShop dashboard OAI",
        )
        self.bucket.grant_read(oai)

        # ── CloudFront Function for SPA routing ───────────────────────────
        spa_fn = cf.Function(
            self, "SpaRouter",
            function_name="paintshop-spa-router",
            code=cf.FunctionCode.from_inline(
                "function handler(event){"
                "var r=event.request,u=r.uri;"
                "if(u.lastIndexOf('.')<u.lastIndexOf('/'))r.uri='/index.html';"
                "return r;}"
            ),
        )

        # ── CloudFront Distribution ────────────────────────────────────────
        self.distribution = cf.Distribution(
            self, "DashboardCdn",
            default_root_object="index.html",
            web_acl_id=web_acl_arn,
            default_behavior=cf.BehaviorOptions(
                origin=origins.S3Origin(self.bucket, origin_access_identity=oai),
                viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cf.CachePolicy.CACHING_OPTIMIZED,
                function_associations=[
                    cf.FunctionAssociation(
                        function=spa_fn,
                        event_type=cf.FunctionEventType.VIEWER_REQUEST,
                    )
                ],
            ),
            additional_behaviors={
                "/config.json": cf.BehaviorOptions(
                    origin=origins.S3Origin(self.bucket, origin_access_identity=oai),
                    viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=cf.CachePolicy.CACHING_DISABLED,
                ),
            },
        )

        # ── Outputs ────────────────────────────────────────────────────────
        CfnOutput(self, "BucketName",      value=self.bucket.bucket_name)
        CfnOutput(self, "DistributionId",  value=self.distribution.distribution_id)
        CfnOutput(self, "DashboardUrl",    value=f"https://{self.distribution.distribution_domain_name}")
