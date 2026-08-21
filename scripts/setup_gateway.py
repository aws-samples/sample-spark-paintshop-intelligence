"""Set up AgentCore Gateway with Cognito JWT authentication and Lambda tool targets.

Creates (idempotent — skips if already exists):
  1. Cognito User Pool + Domain + Resource Server + App Clients (MPS, RCA)
  2. IAM role for the Gateway
  3. Tool Lambda functions (mps-tools, rca-tools)
  4. AgentCore Gateway with JWT authorizer pointing to Cognito
  5. Gateway targets — one per tool
  6. SSM parameters consumed by the agent containers

Usage:
  python scripts/setup_gateway.py
  python scripts/setup_gateway.py --teardown
"""
import argparse
import json
import os
import sys
import zipfile
import io
import boto3
from botocore.exceptions import WaiterError
from botocore.waiter import WaiterModel, create_waiter_with_client

REGION      = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
ACCOUNT     = boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]

UP_NAME     = "paintshop-agents"
DOMAIN_PFX  = f"paintshop-agents-{ACCOUNT}"
RS_ID       = f"https://paintshop-gateway"          # resource server identifier
SCOPE       = "invoke"                               # full scope: paintshop-gateway/invoke
GW_NAME     = "paintshop-tools-gateway"
GW_ROLE     = "PaintShopGatewayRole"
MPS_FN      = "mps-tools"
RCA_FN      = "rca-tools"
OPTIMIZER_FN = os.environ.get("OPTIMIZER_FN", "schedule-optimizer")
TOOLS_ROLE  = "PaintShopSupervisorToolsRole"         # reuse — already has DynamoDB access

# SSM keys the agents read at container startup
SSM_GW_URL          = "/paintshop/gateway_url"
SSM_MPS_CLIENT_ID   = "/paintshop/cognito_mps_client_id"
SSM_MPS_CLIENT_SEC  = "/paintshop/cognito_mps_client_secret"
SSM_RCA_CLIENT_ID   = "/paintshop/cognito_rca_client_id"
SSM_RCA_CLIENT_SEC  = "/paintshop/cognito_rca_client_secret"
SSM_OAUTH_ENDPOINT_PARAM = "/paintshop/cognito_token_url"
SSM_SCOPE           = "/paintshop/cognito_scope"

cognito  = boto3.client("cognito-idp",            region_name=REGION)
iam      = boto3.client("iam",                    region_name=REGION)
lmb      = boto3.client("lambda",                 region_name=REGION)
ssm      = boto3.client("ssm",                    region_name=REGION)
agentcore = boto3.client("bedrock-agentcore-control", region_name=REGION)


# ── helpers ────────────────────────────────────────────────────────────────

def _put_ssm(name: str, value: str, secure: bool = False):
    ssm.put_parameter(
        Name=name, Value=value,
        Type="SecureString" if secure else "String",
        Overwrite=True,
    )
    print(f"  SSM: {name}")


def _zip_lambda(src_path: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(src_path, "handler.py")
    return buf.getvalue()


def _lambda_role_arn() -> str:
    return iam.get_role(RoleName=TOOLS_ROLE)["Role"]["Arn"]


def _require_optimizer() -> None:
    """Fail before Gateway setup if its required optimizer is not deployed."""
    try:
        config = lmb.get_function_configuration(FunctionName=OPTIMIZER_FN)
    except lmb.exceptions.ResourceNotFoundException as exc:
        raise RuntimeError(
            f"Required Lambda '{OPTIMIZER_FN}' does not exist in {ACCOUNT}/{REGION}. "
            "Deploy the PaintShopScheduling CDK stack before setting up the Gateway."
        ) from exc
    if config.get("State", "Active") != "Active":
        raise RuntimeError(
            f"Required Lambda '{OPTIMIZER_FN}' is {config.get('State')}, expected Active."
        )
    print(f"  Optimizer dependency ready: {OPTIMIZER_FN}")


# ── Step 1 — Cognito ───────────────────────────────────────────────────────

def setup_cognito() -> dict:
    print("\n[1] Cognito User Pool")

    # Find or create User Pool
    pools = cognito.list_user_pools(MaxResults=60).get("UserPools", [])
    pool  = next((p for p in pools if p["Name"] == UP_NAME), None)
    if pool:
        pool_id = pool["Id"]
        print(f"  Reusing pool: {pool_id}")
    else:
        pool_id = cognito.create_user_pool(
            PoolName=UP_NAME,
            Policies={"PasswordPolicy": {"MinimumLength": 8, "RequireNumbers": False,
                                         "RequireSymbols": False, "RequireUppercase": False,
                                         "RequireLowercase": False}},
        )["UserPool"]["Id"]
        print(f"  Created pool: {pool_id}")

    # Domain
    try:
        cognito.create_user_pool_domain(Domain=DOMAIN_PFX, UserPoolId=pool_id)
        print(f"  Created domain: {DOMAIN_PFX}")
    except cognito.exceptions.AliasExistsException:
        print(f"  Domain exists: {DOMAIN_PFX}")
    except Exception as e:
        if "already exists" in str(e).lower():
            print(f"  Domain exists: {DOMAIN_PFX}")
        else:
            raise

    # Resource server
    try:
        cognito.create_resource_server(
            UserPoolId=pool_id,
            Identifier=RS_ID,
            Name="PaintShopGateway",
            Scopes=[{"ScopeName": SCOPE, "ScopeDescription": "Invoke gateway tools"}],
        )
        print(f"  Created resource server: {RS_ID}")
    except cognito.exceptions.InvalidParameterException as e:
        if "already exists" in str(e).lower():
            print(f"  Resource server exists: {RS_ID}")
        else:
            raise

    token_url = f"https://{DOMAIN_PFX}.auth.{REGION}.amazoncognito.com/oauth2/token"
    full_scope = f"{RS_ID}/{SCOPE}"

    def _get_or_create_client(name: str) -> tuple[str, str]:
        clients = cognito.list_user_pool_clients(UserPoolId=pool_id, MaxResults=60).get("UserPoolClients", [])
        existing = next((c for c in clients if c["ClientName"] == name), None)
        if existing:
            cid = existing["ClientId"]
            detail = cognito.describe_user_pool_client(UserPoolId=pool_id, ClientId=cid)["UserPoolClient"]
            secret = detail.get("ClientSecret", "")
            print(f"  Reusing client '{name}': {cid}")
            return cid, secret
        result = cognito.create_user_pool_client(
            UserPoolId=pool_id,
            ClientName=name,
            GenerateSecret=True,
            AllowedOAuthFlows=["client_credentials"],
            AllowedOAuthScopes=[full_scope],
            AllowedOAuthFlowsUserPoolClient=True,
            ExplicitAuthFlows=[],
        )["UserPoolClient"]
        print(f"  Created client '{name}': {result['ClientId']}")
        return result["ClientId"], result["ClientSecret"]

    mps_id, mps_sec = _get_or_create_client("paintshop-mps-agent")
    rca_id, rca_sec = _get_or_create_client("paintshop-rca-agent")

    return {
        "pool_id":    pool_id,
        "token_url":  token_url,
        "scope":      full_scope,
        "mps_id":     mps_id,
        "mps_secret": mps_sec,
        "rca_id":     rca_id,
        "rca_secret": rca_sec,
    }


# ── Step 2 — Gateway IAM role ──────────────────────────────────────────────

def setup_gateway_role() -> str:
    print("\n[2] Gateway IAM role")
    trust = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }],
    })
    try:
        role_arn = iam.create_role(
            RoleName=GW_ROLE,
            AssumeRolePolicyDocument=trust,
            Description="AgentCore Gateway execution role",
        )["Role"]["Arn"]
        print(f"  Created role: {role_arn}")
    except iam.exceptions.EntityAlreadyExistsException:
        role_arn = iam.get_role(RoleName=GW_ROLE)["Role"]["Arn"]
        print(f"  Reusing role: {role_arn}")

    # Allow invoking the tool Lambdas
    policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "lambda:InvokeFunction",
                "Resource": [
                    f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:{MPS_FN}",
                    f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:{RCA_FN}",
                ],
            },
            {
                "Effect": "Allow",
                "Action": ["logs:CreateLogGroup", "logs:CreateLogDelivery",
                           "logs:PutLogEvents", "logs:DescribeLogGroups"],
                "Resource": "*",
            },
        ],
    })
    iam.put_role_policy(RoleName=GW_ROLE, PolicyName="GatewayToolsPolicy", PolicyDocument=policy)
    print(f"  Policy attached")
    return role_arn


# ── Step 3 — Tool Lambda functions ─────────────────────────────────────────

def setup_tool_lambdas() -> dict:
    print("\n[3] Tool Lambda functions")
    base    = os.path.join(os.path.dirname(__file__), "..", "src", "lambdas")
    role_arn = _lambda_role_arn()
    arns    = {}

    for fn_name, src_rel in [(MPS_FN, "mps_tools/handler.py"), (RCA_FN, "rca_tools/handler.py")]:
        src_path = os.path.join(base, src_rel)
        code     = _zip_lambda(src_path)

        try:
            resp = lmb.create_function(
                FunctionName=fn_name,
                Runtime="python3.12",
                Role=role_arn,
                Handler="handler.handler",
                Code={"ZipFile": code},
                Timeout=30,
                Environment={"Variables": {
                    "JOBS_TABLE":   "production-jobs",
                    "STATUS_TABLE": "tank-status",
                    "HISTORY_TABLE": "schedule-history",
                    "MAINT_TABLE":  "maintenance-log",
                    "RCA_TABLE":    "rca-reports",
                    "OPTIMIZER_FN": OPTIMIZER_FN,
                    
                    "HISTORY_TABLE": "sensor-history",
                }},
            )
            arns[fn_name] = resp["FunctionArn"]
            print(f"  Created {fn_name}: {resp['FunctionArn']}")
            lmb.get_waiter("function_active_v2").wait(
                FunctionName=fn_name,
                WaiterConfig={"Delay": 2, "MaxAttempts": 30},
            )
        except lmb.exceptions.ResourceConflictException:
            lmb.update_function_code(FunctionName=fn_name, ZipFile=code)
            lmb.get_waiter("function_updated_v2").wait(
                FunctionName=fn_name,
                WaiterConfig={"Delay": 2, "MaxAttempts": 30},
            )
            arn = lmb.get_function_configuration(FunctionName=fn_name)["FunctionArn"]
            arns[fn_name] = arn
            print(f"  Updated {fn_name}: {arn}")

        # Grant AgentCore Gateway service principal permission to invoke this Lambda.
        # The IAM role alone is not sufficient — the Lambda resource policy must also
        # allow the bedrock-agentcore service to call it.
        try:
            lmb.add_permission(
                FunctionName=fn_name,
                StatementId="allow-agentcore-gateway",
                Action="lambda:InvokeFunction",
                Principal="bedrock-agentcore.amazonaws.com",
            )
            print(f"  Resource policy added for {fn_name}")
        except lmb.exceptions.ResourceConflictException:
            print(f"  Resource policy already exists for {fn_name}")

    return arns


# ── Step 4 — AgentCore Gateway ─────────────────────────────────────────────

MCP_TOOL_SPECS = {
    # MPS tools
    "get_affected_jobs": {
        "fn": MPS_FN,
        "description": "Get all IN_PROGRESS and QUEUED production jobs assigned to a tank.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tank_id": {"type": "string", "description": "Tank identifier, e.g. PT-01"},
            },
            "required": ["tank_id"],
        },
    },
    "get_line_status": {
        "fn": MPS_FN,
        "description": "Get current status of all tanks on a production line.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "line_id": {"type": "string", "description": "Line identifier, e.g. LINE-1"},
            },
            "required": ["line_id"],
        },
    },
    "compute_reschedule": {
        "fn": MPS_FN,
        "description": "Invoke the schedule optimiser to compute the best rescheduling plan.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tank_offline":         {"type": "string"},
                "jobs_json":            {"type": "string", "description": "JSON array of affected jobs"},
                "available_tanks_json": {"type": "string", "description": "JSON array of available tanks"},
                "target_jph":           {"type": "number", "default": 45},
                "fbo_target_mins":      {"type": "number", "default": 30},
            },
            "required": ["tank_offline", "jobs_json", "available_tanks_json"],
        },
    },
    "apply_schedule": {
        "fn": MPS_FN,
        "description": "Commit optimizer assignments to DynamoDB without changing action semantics.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tank_id":         {"type": "string"},
                "assignments_json": {"type": "string", "description": "JSON array of {job_id, action, new_tank, scheduled_time}"},
            },
            "required": ["tank_id", "assignments_json"],
        },
    },
    # RCA tools
    "get_sensor_history": {
        "fn": RCA_FN,
        "description": "Get recent sensor readings for a tank from DynamoDB sensor-history table.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tank_id": {"type": "string"},
                "hours":   {"type": "integer", "default": 6},
            },
            "required": ["tank_id"],
        },
    },
    "get_fault_context": {
        "fn": RCA_FN,
        "description": "Get fault type details, SOP procedure, and upstream causal chain from Neptune knowledge graph.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tank_id":    {"type": "string"},
                "fault_type": {"type": "string"},
            },
            "required": ["tank_id", "fault_type"],
        },
    },
    "get_maintenance_record": {
        "fn": RCA_FN,
        "description": "Retrieve maintenance history and overdue service flags for a tank.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tank_id": {"type": "string"},
            },
            "required": ["tank_id"],
        },
    },
    "get_fault_history": {
        "fn": RCA_FN,
        "description": "Get last 5 AI-generated RCA reports for this tank+fault_type to identify recurrence patterns.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tank_id":    {"type": "string"},
                "fault_type": {"type": "string"},
                "days":       {"type": "integer", "default": 30},
            },
            "required": ["tank_id", "fault_type"],
        },
    },
    "write_rca_report": {
        "fn": RCA_FN,
        "description": "Persist the completed RCA report to DynamoDB.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tank_id":         {"type": "string"},
                "fault_type":      {"type": "string"},
                "severity":        {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]},
                "root_cause":      {"type": "string"},
                "recurrence_risk": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
                "recommendation":  {"type": "string"},
                "evidence_json":   {"type": "string", "default": "{}"},
            },
            "required": ["tank_id", "fault_type", "severity", "root_cause",
                         "recurrence_risk", "recommendation"],
        },
    },
}


def setup_gateway(cognito_cfg: dict, gateway_role_arn: str, lambda_arns: dict) -> str:
    print("\n[4] AgentCore Gateway")

    pool_id      = cognito_cfg["pool_id"]
    jwks_url     = (f"https://cognito-idp.{REGION}.amazonaws.com/{pool_id}"
                    f"/.well-known/openid-configuration")
    audiences    = [cognito_cfg["mps_id"], cognito_cfg["rca_id"]]

    # Find or create gateway
    gateways = agentcore.list_gateways().get("items", [])
    gw       = next((g for g in gateways if g["name"] == GW_NAME), None)

    if gw:
        gw_id = gw["gatewayId"]
        print(f"  Reusing gateway: {gw_id}")
    else:
        resp  = agentcore.create_gateway(
            name=GW_NAME,
            roleArn=gateway_role_arn,
            protocolType="MCP",
            authorizerType="CUSTOM_JWT",
            authorizerConfiguration={
                "customJWTAuthorizer": {
                    "discoveryUrl": jwks_url,
                    # allowedAudience intentionally omitted — Cognito M2M tokens
                    # have client_id but no aud claim; use allowedClients instead
                    "allowedClients": audiences,
                }
            },
        )
        gw_id = resp["gatewayId"]
        print(f"  Created gateway: {gw_id}")

        waiter = create_waiter_with_client(
            "GatewayReady",
            WaiterModel({
                "version": 2,
                "waiters": {
                    "GatewayReady": {
                        "operation": "GetGateway",
                        "delay": 5,
                        "maxAttempts": 30,
                        "acceptors": [
                            {"state": "success", "matcher": "path", "argument": "status", "expected": "READY"},
                            {"state": "failure", "matcher": "path", "argument": "status", "expected": "FAILED"},
                            {"state": "failure", "matcher": "path", "argument": "status", "expected": "DELETING"},
                        ],
                    }
                },
            }),
            agentcore,
        )
        try:
            waiter.wait(gatewayIdentifier=gw_id)
        except WaiterError as exc:
            status = exc.last_response.get("status", "UNKNOWN")
            raise RuntimeError(
                f"Gateway {gw_id} did not become READY (last status: {status})"
            ) from exc

    gw_detail    = agentcore.get_gateway(gatewayIdentifier=gw_id)
    gateway_url  = gw_detail.get("gatewayUrl", "")
    print(f"  Gateway URL: {gateway_url}")

    # Register targets
    print("\n[5] Gateway targets")
    existing_targets = agentcore.list_gateway_targets(gatewayIdentifier=gw_id).get("items", [])
    existing_names   = {t["name"] for t in existing_targets}

    for tool_name, spec in MCP_TOOL_SPECS.items():
        target_name = tool_name.replace("_", "-")
        if target_name in existing_names:
            print(f"  Exists: {target_name}")
            continue

        fn_name  = spec["fn"]
        fn_arn   = lambda_arns[fn_name]

        # Strip description/default from property definitions — API only accepts type/properties/required/items
        raw_props = spec["inputSchema"].get("properties", {})
        clean_props = {
            k: {fk: fv for fk, fv in v.items() if fk in ("type", "properties", "required", "items")}
            for k, v in raw_props.items()
        }
        input_schema = {
            "type": spec["inputSchema"]["type"],
            "properties": clean_props,
        }
        if "required" in spec["inputSchema"]:
            input_schema["required"] = spec["inputSchema"]["required"]

        agentcore.create_gateway_target(
            gatewayIdentifier=gw_id,
            name=target_name,
            targetConfiguration={
                "mcp": {
                    "lambda": {
                        "lambdaArn": fn_arn,
                        "toolSchema": {
                            "inlinePayload": [
                                {
                                    "name":        tool_name,
                                    "description": spec["description"],
                                    "inputSchema": input_schema,
                                }
                            ]
                        },
                    }
                }
            },
            credentialProviderConfigurations=[{
                "credentialProviderType": "GATEWAY_IAM_ROLE",
            }],
        )
        print(f"  Registered: {target_name} -> {fn_name}")

    return gateway_url


# ── Step 6 — Store config in SSM ───────────────────────────────────────────

def store_ssm(cognito_cfg: dict, gateway_url: str):
    print("\n[6] SSM parameters")
    _put_ssm(SSM_GW_URL,         gateway_url)
    _put_ssm(SSM_OAUTH_ENDPOINT_PARAM, cognito_cfg["token_url"])
    _put_ssm(SSM_SCOPE,          cognito_cfg["scope"])
    _put_ssm(SSM_MPS_CLIENT_ID,  cognito_cfg["mps_id"])
    _put_ssm(SSM_RCA_CLIENT_ID,  cognito_cfg["rca_id"])
    _put_ssm(SSM_MPS_CLIENT_SEC, cognito_cfg["mps_secret"], secure=True)
    _put_ssm(SSM_RCA_CLIENT_SEC, cognito_cfg["rca_secret"], secure=True)


# ── Teardown ───────────────────────────────────────────────────────────────

def teardown():
    print("=== Teardown ===")
    # Gateways
    for gw in agentcore.list_gateways().get("items", []):
        if gw["name"] == GW_NAME:
            gw_id = gw["gatewayId"]
            for t in agentcore.list_gateway_targets(gatewayIdentifier=gw_id).get("items", []):
                agentcore.delete_gateway_target(gatewayIdentifier=gw_id, targetId=t["targetId"])
            agentcore.delete_gateway(gatewayIdentifier=gw_id)
            print(f"  Deleted gateway {gw_id}")
    # Lambdas
    for fn in [MPS_FN, RCA_FN]:
        try:
            lmb.delete_function(FunctionName=fn)
            print(f"  Deleted Lambda {fn}")
        except Exception:
            pass
    # Cognito
    pools = cognito.list_user_pools(MaxResults=60).get("UserPools", [])
    for p in pools:
        if p["Name"] == UP_NAME:
            cognito.delete_user_pool(UserPoolId=p["Id"])
            print(f"  Deleted User Pool {p['Id']}")
    print("Done.")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--teardown", action="store_true")
    args = parser.parse_args()

    if args.teardown:
        teardown()
        return

    print(f"=== AgentCore Gateway Setup ===")
    print(f"Account: {ACCOUNT}  Region: {REGION}")
    _require_optimizer()

    cognito_cfg    = setup_cognito()
    gateway_role   = setup_gateway_role()
    lambda_arns    = setup_tool_lambdas()
    gateway_url    = setup_gateway(cognito_cfg, gateway_role, lambda_arns)
    store_ssm(cognito_cfg, gateway_url)

    print("\n=== Done ===")
    print(f"Gateway URL : {gateway_url}")
    print(f"Token URL   : {cognito_cfg['token_url']}")
    print(f"Scope       : {cognito_cfg['scope']}")
    print(f"MPS Client  : {cognito_cfg['mps_id']}")
    print(f"RCA Client  : {cognito_cfg['rca_id']}")


if __name__ == "__main__":
    main()
