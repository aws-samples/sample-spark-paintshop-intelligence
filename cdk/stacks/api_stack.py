"""ApiStack — real-time WebSocket API, HTTP streaming Function URL, REST API, and Cognito.

Creates:
  - Cognito User Pool + App Client + Identity Pool (dashboard auth)
  - ws-connections DynamoDB table (active WebSocket connection store)
  - WebSocket API (API GW v2): $connect / $disconnect / $default routes
  - ws-broadcast Lambda: triggered by DynamoDB Streams on tank-status + EventBridge anomaly
  - agent-stream Lambda Function URL (RESPONSE_STREAM): streams agent reasoning as SSE
  - HTTP API (API GW v2): REST endpoints for tanks / schedule / history / rca
  - EventBridge rule: TankAnomalyDetected → ws-broadcast (push anomaly alert to dashboard)
"""
import os
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    aws_cognito as cognito,
    aws_dynamodb as dynamodb,
    aws_lambda as lambda_,
    aws_lambda_event_sources as event_sources,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as integrations,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_wafv2 as waf,
)
from constructs import Construct


class ApiStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        tank_status_table: dynamodb.Table,
        ws_connect_role_arn: str,
        ws_broadcast_role_arn: str,
        agent_stream_role_arn: str,
        api_handler_role_arn: str,
        **kwargs,
    ):
        super().__init__(scope, construct_id, **kwargs)

        src = os.path.join(os.path.dirname(__file__), "../../src/lambdas")

        # ── Cognito User Pool ──────────────────────────────────────────────
        self.user_pool = cognito.UserPool(
            self, "PaintShopUserPool",
            user_pool_name="paintshop-users",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True, username=True),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True),
            ),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_digits=True,
                require_symbols=False,
                require_uppercase=True,
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )

        self.user_pool_client = self.user_pool.add_client(
            "DashboardClient",
            user_pool_client_name="paintshop-dashboard",
            auth_flows=cognito.AuthFlow(user_srp=True, user_password=True),
            generate_secret=False,
            supported_identity_providers=[cognito.UserPoolClientIdentityProvider.COGNITO],
        )

        # Cognito Identity Pool — allows authenticated users to call Lambda Function URL
        self.identity_pool = cognito.CfnIdentityPool(
            self, "PaintShopIdentityPool",
            identity_pool_name="paintshop_dashboard",
            allow_unauthenticated_identities=False,
            cognito_identity_providers=[cognito.CfnIdentityPool.CognitoIdentityProviderProperty(
                client_id=self.user_pool_client.user_pool_client_id,
                provider_name=self.user_pool.user_pool_provider_name,
            )],
        )

        id_pool_auth_role = iam.Role(
            self, "IdPoolAuthRole",
            assumed_by=iam.FederatedPrincipal(
                "cognito-identity.amazonaws.com",
                conditions={
                    "StringEquals":          {"cognito-identity.amazonaws.com:aud": self.identity_pool.ref},
                    "ForAnyValue:StringLike": {"cognito-identity.amazonaws.com:amr": "authenticated"},
                },
                assume_role_action="sts:AssumeRoleWithWebIdentity",
            ),
        )

        cognito.CfnIdentityPoolRoleAttachment(
            self, "IdPoolRoles",
            identity_pool_id=self.identity_pool.ref,
            roles={"authenticated": id_pool_auth_role.role_arn},
        )

        # ── WebSocket connection store ─────────────────────────────────────
        self.ws_connections = dynamodb.Table(
            self, "WsConnections",
            table_name="ws-connections",
            partition_key=dynamodb.Attribute(name="connection_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ── WebSocket Lambdas ──────────────────────────────────────────────
        ws_connect_role = iam.Role.from_role_arn(self, "WsConnectRole", ws_connect_role_arn)
        connect_fn = lambda_.Function(
            self, "WsConnect",
            function_name="ws-connect",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset(os.path.join(src, "ws_connect")),
            role=ws_connect_role,
            timeout=Duration.seconds(10),
            environment={
                "WS_CONNECTIONS_TABLE": "ws-connections",
                "USER_POOL_ID":         self.user_pool.user_pool_id,
                "USER_POOL_CLIENT_ID":  self.user_pool_client.user_pool_client_id,
            },
        )

        disconnect_fn = lambda_.Function(
            self, "WsDisconnect",
            function_name="ws-disconnect",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset(os.path.join(src, "ws_disconnect")),
            role=ws_connect_role,  # same permissions as connect
            timeout=Duration.seconds(10),
            environment={"WS_CONNECTIONS_TABLE": "ws-connections"},
        )

        # ── WebSocket API ──────────────────────────────────────────────────
        self.ws_api = apigwv2.WebSocketApi(
            self, "TankStreamWs",
            api_name="paintshop-ws",
            connect_route_options=apigwv2.WebSocketRouteOptions(
                integration=integrations.WebSocketLambdaIntegration("ConnectInt", connect_fn)
            ),
            disconnect_route_options=apigwv2.WebSocketRouteOptions(
                integration=integrations.WebSocketLambdaIntegration("DisconnectInt", disconnect_fn)
            ),
        )

        ws_stage = apigwv2.WebSocketStage(
            self, "WsStage",
            web_socket_api=self.ws_api,
            stage_name="prod",
            auto_deploy=True,
        )

        ws_endpoint = f"https://{self.ws_api.api_id}.execute-api.{self.region}.amazonaws.com/prod"

        # ── ws-broadcast Lambda ────────────────────────────────────────────
        broadcast_role = iam.Role.from_role_arn(self, "BroadcastRole", ws_broadcast_role_arn)
        self.broadcast_fn = lambda_.Function(
            self, "WsBroadcast",
            function_name="ws-broadcast",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset(os.path.join(src, "ws_broadcast")),
            role=broadcast_role,
            timeout=Duration.seconds(120),
            environment={
                "WS_CONNECTIONS_TABLE": "ws-connections",
                "WS_ENDPOINT":          ws_endpoint,
                "MPS_RUNTIME_PARAM":    "/paintshop/mps_agent_runtime_arn",
                "RCA_RUNTIME_PARAM":    "/paintshop/rca_agent_runtime_arn",
            },
        )

        # DynamoDB Streams on tank-status → ws-broadcast (real-time tank updates)
        self.broadcast_fn.add_event_source(
            event_sources.DynamoEventSource(
                tank_status_table,
                starting_position=lambda_.StartingPosition.LATEST,
                batch_size=10,
                bisect_batch_on_error=True,
            )
        )

        # $default route — handles stream-agent WebSocket messages from dashboard
        self.ws_api.add_route(
            "$default",
            integration=integrations.WebSocketLambdaIntegration("DefaultInt", self.broadcast_fn),
        )

        # EventBridge rule: TankAnomalyDetected → ws-broadcast (anomaly alert push)
        anomaly_rule = events.Rule(
            self, "AnomalyToBroadcast",
            event_pattern=events.EventPattern(
                source=["paintshop.anomaly"],
                detail_type=["TankAnomalyDetected"],
            ),
        )
        anomaly_rule.add_target(targets.LambdaFunction(self.broadcast_fn))

        # Grant Identity Pool auth role to invoke Function URL (added after agent_stream creation)
        # ── agent-stream Lambda Function URL (Response Streaming) ──────────
        stream_role = iam.Role.from_role_arn(self, "StreamRole", agent_stream_role_arn)
        self.agent_stream_fn = lambda_.Function(
            self, "AgentStream",
            function_name="agent-stream",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset(os.path.join(src, "agent_stream")),
            role=stream_role,
            timeout=Duration.seconds(120),
            environment={
                "MPS_RUNTIME_PARAM": "/paintshop/mps_agent_runtime_arn",
                "RCA_RUNTIME_PARAM": "/paintshop/rca_agent_runtime_arn",
            },
        )

        self.agent_stream_url = self.agent_stream_fn.add_function_url(
            auth_type=lambda_.FunctionUrlAuthType.AWS_IAM,
            invoke_mode=lambda_.InvokeMode.RESPONSE_STREAM,
            cors=lambda_.FunctionUrlCorsOptions(
                allowed_origins=["*"],
                allowed_methods=[lambda_.HttpMethod.POST],
                allowed_headers=["*"],
            ),
        )

        # Allow Identity Pool authenticated users to call the streaming Function URL
        id_pool_auth_role.add_to_policy(iam.PolicyStatement(
            actions=["lambda:InvokeFunctionUrl"],
            resources=[self.agent_stream_fn.function_arn],
        ))

        # ── REST API Lambda ────────────────────────────────────────────────
        api_handler_role = iam.Role.from_role_arn(self, "ApiHandlerRole", api_handler_role_arn)
        self.api_handler_fn = lambda_.Function(
            self, "ApiHandler",
            function_name="api-handler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset(os.path.join(src, "api_handler")),
            role=api_handler_role,
            timeout=Duration.seconds(30),
            environment={
                "STATUS_TABLE":   "tank-status",
                "JOBS_TABLE":     "production-jobs",
                "RCA_TABLE":      "rca-reports",
                "MAINT_TABLE":    "maintenance-log",
                "HISTORY_TABLE":  "sensor-history",
                "INCIDENTS_TABLE": "incidents",
            },
        )

        # ── HTTP API (REST) ────────────────────────────────────────────────
        self.http_api = apigwv2.HttpApi(
            self, "PaintShopRestApi",
            api_name="paintshop-api",
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_origins=["*"],
                allow_methods=[apigwv2.CorsHttpMethod.GET, apigwv2.CorsHttpMethod.POST, apigwv2.CorsHttpMethod.OPTIONS],
                allow_headers=["Authorization", "Content-Type"],
            ),
        )

        # Cognito JWT authorizer — attached to routes via CfnRoute authorizer_id
        jwt_authorizer = apigwv2.CfnAuthorizer(
            self, "CognitoJwtAuth",
            api_id=self.http_api.api_id,
            authorizer_type="JWT",
            name="cognito-jwt",
            identity_source=["$request.header.Authorization"],
            jwt_configuration=apigwv2.CfnAuthorizer.JWTConfigurationProperty(
                audience=[self.user_pool_client.user_pool_client_id],
                issuer=f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool.user_pool_id}",
            ),
        )

        api_integration = integrations.HttpLambdaIntegration(
            "ApiIntegration", self.api_handler_fn
        )

        for path, method in [
            ("/tanks",               apigwv2.HttpMethod.GET),
            ("/tanks/{id}/history",  apigwv2.HttpMethod.GET),
            ("/schedule",            apigwv2.HttpMethod.GET),
            ("/rca/{tankId}",        apigwv2.HttpMethod.GET),
            ("/maintenance/{tankId}", apigwv2.HttpMethod.GET),
            ("/demo/status",         apigwv2.HttpMethod.GET),
            ("/incidents",            apigwv2.HttpMethod.GET),
            ("/demo/inject",         apigwv2.HttpMethod.POST),
            ("/demo/reset",          apigwv2.HttpMethod.POST),
            ("/demo/telemetry",      apigwv2.HttpMethod.POST),
        ]:
            safe_id = f"Route{path.replace('/', '_').replace('{', '').replace('}', '')}"
            route = apigwv2.HttpRoute(
                self, safe_id,
                http_api=self.http_api,
                route_key=apigwv2.HttpRouteKey.with_(path, method),
                integration=api_integration,
            )
            # Attach Cognito JWT authorizer via L1 escape hatch
            cfn_route = route.node.default_child
            cfn_route.authorization_type = "JWT"
            cfn_route.authorizer_id      = jwt_authorizer.ref

        # ── WAF WebACL (for CloudFront — Phase 5) ─────────────────────────
        self.web_acl = waf.CfnWebACL(
            self, "DashboardWaf",
            name="paintshop-dashboard-waf",
            scope="CLOUDFRONT",
            default_action=waf.CfnWebACL.DefaultActionProperty(allow={}),
            visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name="paintshop-dashboard-waf",
                sampled_requests_enabled=True,
            ),
            rules=[
                waf.CfnWebACL.RuleProperty(
                    name="AWSManagedRulesCommonRuleSet",
                    priority=1,
                    override_action=waf.CfnWebACL.OverrideActionProperty(none={}),
                    statement=waf.CfnWebACL.StatementProperty(
                        managed_rule_group_statement=waf.CfnWebACL.ManagedRuleGroupStatementProperty(
                            vendor_name="AWS",
                            name="AWSManagedRulesCommonRuleSet",
                        )
                    ),
                    visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="CommonRuleSet",
                        sampled_requests_enabled=True,
                    ),
                ),
            ],
        )

        # ── Outputs ────────────────────────────────────────────────────────
        CfnOutput(self, "UserPoolId",         value=self.user_pool.user_pool_id)
        CfnOutput(self, "UserPoolClientId",   value=self.user_pool_client.user_pool_client_id)
        CfnOutput(self, "IdentityPoolId",     value=self.identity_pool.ref)
        CfnOutput(self, "WsEndpoint",         value=f"wss://{self.ws_api.api_id}.execute-api.{self.region}.amazonaws.com/prod")
        CfnOutput(self, "RestApiEndpoint",    value=self.http_api.api_endpoint)
        CfnOutput(self, "AgentStreamUrl",     value=self.agent_stream_url.url)
        CfnOutput(self, "WebAclArn",          value=self.web_acl.attr_arn)
