import os
from aws_cdk import (
    Stack, Duration, RemovalPolicy,
    aws_kinesis as kinesis,
    aws_kinesisfirehose as firehose,
    aws_glue as glue,
    aws_lambda as lambda_,
    aws_lambda_event_sources as event_sources,
    aws_ssm as ssm,
    aws_s3 as s3,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets,
    aws_dynamodb as dynamodb,
)
from constructs import Construct


class IngestionStack(Stack):
    def __init__(self, scope: Construct, construct_id: str,
                 bucket: s3.IBucket, endpoint_name: str,
                 simulator_role_arn: str, processor_role_arn: str,
                 **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # sensor-history DynamoDB table — time-series store for dashboard charts
        self.history_table = dynamodb.Table(
            self, "SensorHistory",
            table_name="sensor-history",
            partition_key=dynamodb.Attribute(name="tank_id",   type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(     name="timestamp", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.RETAIN,
        )

        # Kinesis Data Stream — 12 shards (1 per tank)
        self.stream = kinesis.Stream(
            self, "TankStream",
            stream_name="paintshop-tank-stream",
            shard_count=12,
            retention_period=Duration.hours(24),
        )

        # Glue Data Catalog — tank reading schema
        glue_db = glue.CfnDatabase(
            self, "GlueDatabase",
            catalog_id=self.account,
            database_input=glue.CfnDatabase.DatabaseInputProperty(
                name="paintshop_raw"
            )
        )

        glue_table = glue.CfnTable(
            self, "GlueTable",
            catalog_id=self.account,
            database_name="paintshop_raw",
            table_input=glue.CfnTable.TableInputProperty(
                name="tank_readings",
                storage_descriptor=glue.CfnTable.StorageDescriptorProperty(
                    columns=[
                        glue.CfnTable.ColumnProperty(name="tank_id", type="string"),
                        glue.CfnTable.ColumnProperty(name="timestamp", type="string"),
                        glue.CfnTable.ColumnProperty(name="temperature_c", type="double"),
                        glue.CfnTable.ColumnProperty(name="ph", type="double"),
                        glue.CfnTable.ColumnProperty(name="conductivity_us_cm", type="double"),
                        glue.CfnTable.ColumnProperty(name="free_acid_pts", type="double"),
                        glue.CfnTable.ColumnProperty(name="total_acid_pts", type="double"),
                        glue.CfnTable.ColumnProperty(name="zinc_g_per_l", type="double"),
                        glue.CfnTable.ColumnProperty(name="accelerator_pts", type="double"),
                        glue.CfnTable.ColumnProperty(name="meq_acid", type="double"),
                        glue.CfnTable.ColumnProperty(name="solids_pct", type="double"),
                        glue.CfnTable.ColumnProperty(name="voltage_v", type="double"),
                        glue.CfnTable.ColumnProperty(name="shift", type="string"),
                        glue.CfnTable.ColumnProperty(name="line_id", type="string"),
                    ],
                    input_format="org.apache.hadoop.mapred.TextInputFormat",
                    output_format="org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
                    serde_info=glue.CfnTable.SerdeInfoProperty(
                        serialization_library="org.openx.data.jsonserde.JsonSerDe"
                    ),
                    location=f"s3://{bucket.bucket_name}/raw-synthetic/",
                ),
                partition_keys=[
                    glue.CfnTable.ColumnProperty(name="tank_id_partition", type="string"),
                    glue.CfnTable.ColumnProperty(name="date_partition", type="string"),
                ],
                table_type="EXTERNAL_TABLE",
            )
        )
        glue_table.add_dependency(glue_db)

        # Firehose delivery role — all permissions baked in at creation to avoid
        # IAM propagation race when Firehose validates the role on creation.
        firehose_role = iam.Role(
            self, "FirehoseRole",
            assumed_by=iam.ServicePrincipal("firehose.amazonaws.com"),
            inline_policies={
                "FirehoseAccess": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=[
                            "kinesis:DescribeStream",
                            "kinesis:GetShardIterator",
                            "kinesis:GetRecords",
                            "kinesis:ListShards",
                        ],
                        resources=[self.stream.stream_arn],
                    ),
                    iam.PolicyStatement(
                        actions=[
                            "s3:AbortMultipartUpload",
                            "s3:GetBucketLocation",
                            "s3:GetObject",
                            "s3:ListBucket",
                            "s3:ListBucketMultipartUploads",
                            "s3:PutObject",
                        ],
                        resources=[
                            bucket.bucket_arn,
                            f"{bucket.bucket_arn}/*",
                        ],
                    ),
                    iam.PolicyStatement(
                        actions=["glue:GetTable", "glue:GetTableVersion", "glue:GetTableVersions"],
                        resources=["*"],
                    ),
                ])
            },
        )

        # Kinesis Firehose — JSON -> Parquet via Glue schema
        # Explicit dependency ensures Firehose is created AFTER the role (incl. inline policies)
        self.delivery_stream = firehose.CfnDeliveryStream(
            self, "TankFirehose",
            delivery_stream_name="paintshop-tank-firehose",
            delivery_stream_type="KinesisStreamAsSource",
            kinesis_stream_source_configuration=firehose.CfnDeliveryStream.KinesisStreamSourceConfigurationProperty(
                kinesis_stream_arn=self.stream.stream_arn,
                role_arn=firehose_role.role_arn,
            ),
            extended_s3_destination_configuration=firehose.CfnDeliveryStream.ExtendedS3DestinationConfigurationProperty(
                bucket_arn=bucket.bucket_arn,
                role_arn=firehose_role.role_arn,
                prefix="raw-synthetic/tank_id=!{partitionKeyFromQuery:tank_id}/date=!{timestamp:yyyy-MM-dd}/",
                error_output_prefix="raw-synthetic-errors/",
                buffering_hints=firehose.CfnDeliveryStream.BufferingHintsProperty(
                    interval_in_seconds=300,
                    size_in_m_bs=128,
                ),
                data_format_conversion_configuration=firehose.CfnDeliveryStream.DataFormatConversionConfigurationProperty(
                    enabled=True,
                    input_format_configuration=firehose.CfnDeliveryStream.InputFormatConfigurationProperty(
                        deserializer=firehose.CfnDeliveryStream.DeserializerProperty(
                            open_x_json_ser_de=firehose.CfnDeliveryStream.OpenXJsonSerDeProperty()
                        )
                    ),
                    output_format_configuration=firehose.CfnDeliveryStream.OutputFormatConfigurationProperty(
                        serializer=firehose.CfnDeliveryStream.SerializerProperty(
                            parquet_ser_de=firehose.CfnDeliveryStream.ParquetSerDeProperty()
                        )
                    ),
                    schema_configuration=firehose.CfnDeliveryStream.SchemaConfigurationProperty(
                        catalog_id=self.account,
                        database_name="paintshop_raw",
                        table_name="tank_readings",
                        region=self.region,
                        role_arn=firehose_role.role_arn,
                        version_id="LATEST",
                    )
                ),
                # MetadataExtraction processor is required when dynamic partitioning is enabled
                processing_configuration=firehose.CfnDeliveryStream.ProcessingConfigurationProperty(
                    enabled=True,
                    processors=[
                        firehose.CfnDeliveryStream.ProcessorProperty(
                            type="MetadataExtraction",
                            parameters=[
                                firehose.CfnDeliveryStream.ProcessorParameterProperty(
                                    parameter_name="MetadataExtractionQuery",
                                    parameter_value="{tank_id:.tank_id}",
                                ),
                                firehose.CfnDeliveryStream.ProcessorParameterProperty(
                                    parameter_name="JsonParsingEngine",
                                    parameter_value="JQ-1.6",
                                ),
                            ],
                        )
                    ],
                ),
                dynamic_partitioning_configuration=firehose.CfnDeliveryStream.DynamicPartitioningConfigurationProperty(
                    enabled=True,
                    retry_options=firehose.CfnDeliveryStream.RetryOptionsProperty(duration_in_seconds=300)
                ),
            )
        )

        self.delivery_stream.node.add_dependency(firehose_role)
        self.delivery_stream.add_dependency(glue_table)

        # SSM threshold parameter
        ssm.StringParameter(
            self, "AnomalyThreshold",
            parameter_name="/paintshop/anomaly_threshold",
            string_value="0.7",
            description="Anomaly score threshold — tunable without redeploy",
        )

        # Import IAM-created roles through token-backed ARNs so CDK records the
        # cross-stack dependency. Keep imports immutable: all runtime permissions
        # are defined in IamStack, avoiding policy attachments in this stack.
        sim_role = iam.Role.from_role_arn(
            self, "SimRole", simulator_role_arn, mutable=False
        )
        self.simulator = lambda_.Function(
            self, "Simulator",
            function_name="tank-simulator",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../../src/lambdas/simulator")
            ),
            role=sim_role,
            timeout=Duration.minutes(5),
            environment={
                "STREAM_NAME":  self.stream.stream_name,
                "JOBS_TABLE":   "production-jobs",
                "STATUS_TABLE": "tank-status",
            },
        )

        # deploy.sh enables this only after tables, endpoint, KB, and agents are ready.
        simulator_rule = events.Rule(
            self, "SimulatorSchedule",
            rule_name="paintshop-simulator-schedule",
            schedule=events.Schedule.rate(Duration.minutes(1)),
            enabled=False,
        )
        simulator_rule.add_target(targets.LambdaFunction(self.simulator))

        proc_role = iam.Role.from_role_arn(
            self, "ProcRole", processor_role_arn, mutable=False
        )
        self.processor = lambda_.Function(
            self, "StreamProcessor",
            function_name="stream-processor",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../../src/lambdas/stream_processor")
            ),
            role=proc_role,
            timeout=Duration.minutes(1),
            environment={
                "ENDPOINT_NAME":   endpoint_name,
                "EVENT_BUS_NAME":  "default",
                "THRESHOLD_PARAM": "/paintshop/anomaly_threshold",
                "STATUS_TABLE":    "tank-status",
                "JOBS_TABLE":      "production-jobs",
                "HISTORY_TABLE":   "sensor-history",
            },
        )
        self.processor.add_event_source(
            event_sources.KinesisEventSource(
                self.stream,
                starting_position=lambda_.StartingPosition.LATEST,
                batch_size=100,
                bisect_batch_on_error=True,
                enabled=False,
            )
        )

        self.stream_arn = self.stream.stream_arn
