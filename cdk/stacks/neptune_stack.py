import os
from aws_cdk import (
    Stack,
    Duration,
    aws_ec2 as ec2,
    aws_neptune as neptune,
    aws_iam as iam,
    aws_s3 as s3,
    aws_lambda as lambda_,
    CfnOutput,
)
from constructs import Construct


class NeptuneStack(Stack):
    def __init__(self, scope: Construct, construct_id: str,
                 bucket: s3.Bucket, neptune_query_role: iam.IRole, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        vpc = ec2.Vpc.from_lookup(self, "DefaultVPC", is_default=True)

        # Security group — Neptune port 8182, intra-VPC only
        sg = ec2.SecurityGroup(
            self, "NeptuneSG",
            vpc=vpc,
            description="Neptune cluster - allow port 8182 within VPC",
            allow_all_outbound=True,
        )
        sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(8182),
            description="Neptune Gremlin from within VPC",
        )

        subnet_group = neptune.CfnDBSubnetGroup(
            self, "NeptuneSubnetGroup",
            db_subnet_group_description="Paint Shop Neptune subnet group",
            subnet_ids=vpc.select_subnets(
                subnet_type=ec2.SubnetType.PUBLIC
            ).subnet_ids,
        )

        # S3 bulk load role
        load_role = iam.Role(
            self, "NeptuneS3LoadRole",
            role_name="PaintShopNeptuneS3LoadRole",
            assumed_by=iam.ServicePrincipal("rds.amazonaws.com"),
        )
        bucket.grant_read(load_role)

        # Neptune Serverless cluster
        self.cluster = neptune.CfnDBCluster(
            self, "NeptuneCluster",
            db_subnet_group_name=subnet_group.ref,
            vpc_security_group_ids=[sg.security_group_id],
            serverless_scaling_configuration=neptune.CfnDBCluster.ServerlessScalingConfigurationProperty(
                min_capacity=2,
                max_capacity=8,
            ),
            deletion_protection=False,
            storage_encrypted=True,
            associated_roles=[neptune.CfnDBCluster.DBClusterRoleProperty(
                role_arn=load_role.role_arn
            )],
        )

        # Neptune serverless instance (db.serverless class required for serverless clusters)
        self.instance = neptune.CfnDBInstance(
            self, "NeptuneInstance",
            db_instance_class="db.serverless",
            db_cluster_identifier=self.cluster.ref,
        )
        self.instance.add_dependency(self.cluster)

        self.cluster_endpoint = self.cluster.attr_endpoint
        self.cluster_port     = self.cluster.attr_port

        # ── Neptune Query Lambda (RCA agent tool + graph seeding) ─────────
        # Use the role construct from PaintShopIam rather than reconstructing its
        # ARN. This creates a CloudFormation cross-stack reference and guarantees
        # that IAM finishes before Lambda attempts to assume the role.
        self.query_fn = lambda_.Function(
            self, "NeptuneQuery",
            function_name="neptune-query",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../../src/lambdas/neptune_query")
            ),
            role=neptune_query_role,
            timeout=Duration.minutes(10),
            memory_size=512,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            allow_public_subnet=True,
            security_groups=[sg],
            environment={
                "NEPTUNE_ENDPOINT": self.cluster_endpoint,
                "NEPTUNE_PORT":     "8182",
            },
        )

        CfnOutput(self, "NeptuneEndpoint",  value=self.cluster_endpoint)
        CfnOutput(self, "NeptuneQueryFn",   value=self.query_fn.function_name)
