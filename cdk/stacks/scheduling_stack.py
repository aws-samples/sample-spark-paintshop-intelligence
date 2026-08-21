import os
from aws_cdk import (
    Stack, Duration, RemovalPolicy,
    aws_dynamodb as dynamodb,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as sfn_tasks,
    aws_lambda as lambda_,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
)
from constructs import Construct


class SchedulingStack(Stack):
    def __init__(self, scope: Construct, construct_id: str,
                 supervisor_invoker: lambda_.IFunction,
                 rca_invoker: lambda_.IFunction,
                 applier_role_arn: str, sfn_role_arn: str,
                 **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # DynamoDB table: production-jobs
        self.jobs_table = dynamodb.Table(
            self, "ProductionJobs",
            table_name="production-jobs",
            partition_key=dynamodb.Attribute(name="job_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="scheduled_time", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.DESTROY,
        )
        self.jobs_table.add_global_secondary_index(
            index_name="status-line-index",
            partition_key=dynamodb.Attribute(name="status", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="line_id", type=dynamodb.AttributeType.STRING),
        )

        # DynamoDB table: tank-status  (streams enabled for ws-broadcast)
        self.tank_status_table = dynamodb.Table(
            self, "TankStatus",
            table_name="tank-status",
            partition_key=dynamodb.Attribute(name="tank_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",
            stream=dynamodb.StreamViewType.NEW_IMAGE,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # DynamoDB table: schedule-history
        self.history_table = dynamodb.Table(
            self, "ScheduleHistory",
            table_name="schedule-history",
            partition_key=dynamodb.Attribute(name="decision_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="timestamp", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )
        self.history_table.add_global_secondary_index(
            index_name="tank-time-index",
            partition_key=dynamodb.Attribute(name="trigger_tank", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="timestamp", type=dynamodb.AttributeType.STRING),
        )

        # DynamoDB table: maintenance-log
        self.maintenance_table = dynamodb.Table(
            self, "MaintenanceLog",
            table_name="maintenance-log",
            partition_key=dynamodb.Attribute(name="tank_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="service_date", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )
        self.maintenance_table.add_global_secondary_index(
            index_name="overdue-index",
            partition_key=dynamodb.Attribute(name="overdue_flag", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="tank_id", type=dynamodb.AttributeType.STRING),
        )

        # DynamoDB table: rca-reports
        self.rca_table = dynamodb.Table(
            self, "RcaReports",
            table_name="rca-reports",
            partition_key=dynamodb.Attribute(name="report_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="timestamp", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )
        self.rca_table.add_global_secondary_index(
            index_name="tank-rca-index",
            partition_key=dynamodb.Attribute(name="tank_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="timestamp", type=dynamodb.AttributeType.STRING),
        )

        # DynamoDB table: incidents (combined MPS + RCA output per fault event)
        self.incidents_table = dynamodb.Table(
            self, "Incidents",
            table_name="incidents",
            partition_key=dynamodb.Attribute(name="incident_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="timestamp", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.DESTROY,
        )
        self.incidents_table.add_global_secondary_index(
            index_name="incidents-tank-time-index",
            partition_key=dynamodb.Attribute(name="tank_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="timestamp", type=dynamodb.AttributeType.STRING),
        )

        # Lambda: schedule-optimizer — invoked synchronously by the MPS Gateway tool.
        # Keep this physical name aligned with mps-tools OPTIMIZER_FN.
        self.optimizer = lambda_.Function(
            self, "ScheduleOptimizer",
            function_name="schedule-optimizer",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../../src/lambdas/optimizer")
            ),
            timeout=Duration.seconds(10),
        )

        # Import IAM-created roles through token-backed ARNs so CDK records the
        # dependency without adding cross-stack policies. IamStack already owns
        # every permission required by these two execution roles.
        applier_role = iam.Role.from_role_arn(
            self, "ApplierRole", applier_role_arn, mutable=False
        )

        # Lambda: schedule-applier
        self.applier = lambda_.Function(
            self, "ScheduleApplier",
            function_name="schedule-applier",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../../src/lambdas/schedule_applier")
            ),
            role=applier_role,
            timeout=Duration.seconds(30),
            environment={
                "JOBS_TABLE":    "production-jobs",
                "STATUS_TABLE":  "tank-status",
                "HISTORY_TABLE": "schedule-history",
            },
        )

        # Lambda: recommendation-validator
        self.validator = lambda_.Function(
            self, "RecommendationValidator",
            function_name="recommendation-validator",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../../src/lambdas/schedule_validator")
            ),
            timeout=Duration.seconds(10),
            environment={
                "MIN_JPH":      "45",
                "STATUS_TABLE": "tank-status",
            },
        )
        self.tank_status_table.grant_read_data(self.validator)

        # Step Functions state machine — 6-step rescheduling workflow
        sfn_role = iam.Role.from_role_arn(
            self, "SfnRole", sfn_role_arn, mutable=False
        )

        # Step 1: Update tank-status to degraded
        update_tank_status = sfn_tasks.DynamoPutItem(
            self, "UpdateTankStatus",
            table=self.tank_status_table,
            item={
                "tank_id":             sfn_tasks.DynamoAttributeValue.from_string(
                    sfn.JsonPath.string_at("$.detail.tank_id")),
                "status":              sfn_tasks.DynamoAttributeValue.from_string("degraded"),
                "last_anomaly_type":   sfn_tasks.DynamoAttributeValue.from_string(
                    sfn.JsonPath.string_at("$.detail.fault_type")),
                "anomaly_detected_at": sfn_tasks.DynamoAttributeValue.from_string(
                    sfn.JsonPath.string_at("$.time")),
            },
            result_path="$.tank_update_result",
        )

        # ── Branch A: MPS rescheduling ─────────────────────────────────────

        invoke_mps = sfn_tasks.LambdaInvoke(
            self, "InvokeMpsAgent",
            lambda_function=supervisor_invoker,
            payload=sfn.TaskInput.from_object({
                "detail.$": "$.detail",
                "time.$":   "$.time",
            }),
            result_selector={
                "projected_jph.$":  "$.Payload.projected_jph",
                "assignments.$":    "$.Payload.assignments",
                "fbo_delay_mins.$": "$.Payload.fbo_delay_mins",
                "summary.$":        "$.Payload.summary",
            },
            result_path="$.agent_result",
        )

        validate = sfn_tasks.LambdaInvoke(
            self, "ValidateRecommendation",
            lambda_function=self.validator,
            payload=sfn.TaskInput.from_object({
                "recommendation.$": "$.agent_result"
            }),
            result_path="$.validation_result",
        )

        is_valid = sfn.Choice(self, "IsRecommendationValid")

        apply_schedule = sfn_tasks.LambdaInvoke(
            self, "ApplySchedule",
            lambda_function=self.applier,
            payload=sfn.TaskInput.from_object({
                "recommendation.$": "$.agent_result",
                "trigger.$":        "$.detail",
            }),
            result_path="$.apply_result",
        )

        fallback = sfn.Pass(
            self, "FallbackSchedule",
            parameters={
                "projected_jph":  45,
                "assignments":    [],
                "fbo_delay_mins": 50,
                "summary":        "Rule-based fallback: all jobs held pending manual review.",
            },
            result_path="$.agent_result",
        )

        write_history = sfn_tasks.LambdaInvoke(
            self, "WriteScheduleHistory",
            lambda_function=self.applier,
            payload=sfn.TaskInput.from_object({
                "recommendation.$": "$.agent_result",
                "trigger.$":        "$.detail",
            }),
            result_path="$.history_result",
        )

        invoke_mps.next(validate)
        validate.next(
            is_valid
            .when(sfn.Condition.boolean_equals("$.validation_result.Payload.valid", True),
                  apply_schedule.next(write_history))
            .otherwise(fallback.next(write_history))
        )

        # ── Branch B: RCA analysis ─────────────────────────────────────────

        invoke_rca = sfn_tasks.LambdaInvoke(
            self, "InvokeRcaAgent",
            lambda_function=rca_invoker,
            payload=sfn.TaskInput.from_object({
                "detail.$": "$.detail",
                "time.$":   "$.time",
            }),
            result_selector={
                "severity.$":        "$.Payload.severity",
                "root_cause.$":      "$.Payload.root_cause",
                "recurrence_risk.$": "$.Payload.recurrence_risk",
                "recommendation.$":  "$.Payload.recommendation",
                "report_id.$":       "$.Payload.report_id",
            },
            result_path="$.rca_result",
        )

        # ── Parallel: MPS (Branch A) + RCA (Branch B) run concurrently ────

        parallel = sfn.Parallel(self, "MpsAndRcaParallel")
        parallel.branch(invoke_mps)
        parallel.branch(invoke_rca)

        # Wire the flow: UpdateTankStatus → Parallel(MPS + RCA)
        update_tank_status.next(parallel)

        self.state_machine = sfn.StateMachine(
            self, "ReschedulingWorkflow",
            state_machine_name="paintshop-rescheduling",
            definition=update_tank_status,
            role=sfn_role,
            timeout=Duration.minutes(10),
        )

        # EventBridge rule: TankAnomalyDetected -> Step Functions
        rule = events.Rule(
            self, "AnomalyToSfn",
            event_pattern=events.EventPattern(
                source=["paintshop.anomaly"],
                detail_type=["TankAnomalyDetected"],
            )
        )
        rule.add_target(targets.SfnStateMachine(self.state_machine))

        self.state_machine_arn = self.state_machine.state_machine_arn
