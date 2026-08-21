"""RCA Agent — lazy-init agent with direct Gateway HTTP tool calls."""
import os
import json
import logging
import boto3
import requests
from strands import Agent, tool
from strands.models import BedrockModel

log = logging.getLogger(__name__)

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

_bedrock_runtime = None


def _get_bedrock_runtime():
    global _bedrock_runtime
    if _bedrock_runtime is None:
        _bedrock_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)
    return _bedrock_runtime

_ssm = boto3.client("ssm", region_name=REGION)

_agent = None
_cfg: dict = {}


def _ssm_get(name: str, secure: bool = False) -> str:
    return _ssm.get_parameter(Name=name, WithDecryption=secure)["Parameter"]["Value"]


def _env_or_ssm(env_key: str, ssm_key: str, secure: bool = False) -> str:
    return os.environ.get(env_key) or _ssm_get(ssm_key, secure)


def _get_oauth_token(cfg: dict) -> str:
    resp = requests.post(
        cfg["token_url"],
        data=(
            f"grant_type=client_credentials"
            f"&client_id={cfg['client_id']}"
            f"&client_secret={cfg['client_secret']}"
            f"&scope={cfg['scope']}"
        ),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _call_mcp(tool_name: str, arguments: dict) -> dict:
    """Call a tool via the AgentCore Gateway MCP endpoint."""
    gw = _cfg["gateway_url"]
    token = _cfg["token"]
    resp = requests.post(
        gw,
        json={"jsonrpc": "2.0", "method": "tools/call",
              "params": {"name": tool_name, "arguments": arguments}, "id": 1},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    result = resp.json().get("result", {})
    content = result.get("content", [])
    if content and isinstance(content, list):
        text = content[0].get("text", "{}")
        try:
            return json.loads(text)
        except Exception:
            return {"result": text}
    return result


# ── RCA Tools ──────────────────────────────────────────────────────────────

@tool
def get_sensor_history(tank_id: str, hours: int = 6) -> dict:
    """Get recent sensor readings for a tank from DynamoDB sensor-history table."""
    return _call_mcp("get-sensor-history___get_sensor_history",
                     {"tank_id": tank_id, "hours": hours})


@tool
def get_fault_context(tank_id: str, fault_type: str) -> dict:
    """Get fault type details, SOP procedure, and upstream causal chain from Neptune knowledge graph."""
    return _call_mcp("get-fault-context___get_fault_context",
                     {"tank_id": tank_id, "fault_type": fault_type})


@tool
def get_maintenance_record(tank_id: str) -> dict:
    """Retrieve maintenance history and overdue service flags for a tank."""
    return _call_mcp("get-maintenance-record___get_maintenance_record",
                     {"tank_id": tank_id})


@tool
def get_fault_history(tank_id: str, fault_type: str, days: int = 30) -> dict:
    """Get the last 5 AI-generated RCA reports for this tank and fault type from DynamoDB.
    Use this to identify recurrence patterns and assess if prior remediation was effective."""
    return _call_mcp("get-fault-history___get_fault_history",
                     {"tank_id": tank_id, "fault_type": fault_type, "days": days})


@tool
def get_sop_procedure(fault_type: str, s3_doc_key: str = "", query: str = "") -> dict:
    """Retrieve the full SOP procedure text from the Bedrock Knowledge Base.

    Args:
        fault_type: e.g. 'acid_drift' — used to build the search query.
        s3_doc_key: S3 key from get_fault_context result (e.g. 'knowledge-base/sops/pt-06_acid_drift.md').
                    When provided the search is filtered to that exact document — faster and more precise.
        query: Optional override for the search query text.
    """
    kb_id = _ssm_get("/paintshop/kb_id")
    bucket = os.environ.get("BUCKET_NAME", "amzn-s3-demo-paintshop-ml")
    search_text = query if query else f"SOP procedure for {fault_type.replace('_', ' ')} fault in paint shop"

    vector_cfg: dict = {"numberOfResults": 5}
    if s3_doc_key:
        # Filter to the exact document Neptune identified — guarantees correct SOP, smaller search space
        s3_uri = f"s3://{bucket}/{s3_doc_key}"
        vector_cfg["filter"] = {
            "equals": {"key": "x-amz-bedrock-kb-source-uri", "value": s3_uri}
        }
        log.info("KB retrieve: filtered to %s", s3_uri)
    else:
        log.info("KB retrieve: semantic search only (no s3_doc_key provided)")

    try:
        resp = _get_bedrock_runtime().retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": search_text},
            retrievalConfiguration={"vectorSearchConfiguration": vector_cfg},
        )
        results = []
        for r in resp.get("retrievalResults", []):
            results.append({
                "content": r["content"]["text"],
                "score": r.get("score", 0),
                "location": r.get("location", {}).get("s3Location", {}).get("uri", ""),
            })
        return {"fault_type": fault_type, "sop_results": results, "filtered_by_s3": bool(s3_doc_key)}
    except Exception as exc:
        log.warning("KB retrieve failed: %s", exc)
        return {"fault_type": fault_type, "sop_results": [], "error": str(exc)}


@tool
def write_rca_report(
    tank_id: str,
    fault_type: str,
    severity: str,
    root_cause: str,
    recurrence_risk: str,
    recommendation: str,
    evidence_json: str = "{}",
) -> dict:
    """Persist the completed RCA report to DynamoDB and return the report_id."""
    return _call_mcp("write-rca-report___write_rca_report", {
        "tank_id": tank_id,
        "fault_type": fault_type,
        "severity": severity,
        "root_cause": root_cause,
        "recurrence_risk": recurrence_risk,
        "recommendation": recommendation,
        "evidence_json": evidence_json,
    })


RCA_SYSTEM_PROMPT = """You are a root cause analysis (RCA) specialist for an automotive paint shop.

When a tank fault is reported, perform a thorough analysis using the available tools:
1. Call get_sensor_history to examine recent sensor trends (look for drift, spikes, gradual degradation)
2. Call get_fault_context with the tank_id and fault_type to retrieve fault classification, SOP procedure metadata, and upstream causal chain from the knowledge graph
3. Call get_sop_procedure with the fault_type AND the s3_doc_key from the get_fault_context result — this filters the Knowledge Base search to the exact SOP document Neptune identified, ensuring you get the correct procedure. Extract s3_doc_key from the fault_context response (it may be nested under the fault node properties).
4. Call get_maintenance_record to check recent service history and overdue flags
5. Call get_fault_history to check how many times this fault has occurred in the last 30 days and whether prior remediations were effective
6. Based on all evidence, determine the root cause and recurrence risk:
   - If occurrence_count >= 3 in 30 days → recurrence_risk=HIGH, root cause likely systemic
   - If prior RCA reports show same root cause → prior remediation was incomplete
7. Call write_rca_report to save your findings. The recommendation argument must be non-empty and must come from the retrieved SOP procedure.
8. Return ONLY the complete JSON object below — never return an intermediate tool result, maintenance record, fault-context object, or prior RCA report:
   {
     "severity": "LOW|MEDIUM|HIGH|CRITICAL",
     "root_cause": "<one sentence>",
     "recurrence_risk": "LOW|MEDIUM|HIGH",
     "recommendation": "<specific corrective action drawn directly from the SOP — include chemical names, dosing amounts, target sensor values, and assigned technician role from the SOP content>",
     "report_id": "<from write_rca_report>",
     "occurrence_count": <integer from get_fault_history, 0 if no history>,
     "prior_occurrences": [
       {"date": "<YYYY-MM-DD>", "severity": "<severity>", "root_cause": "<brief>"},
       ... up to 3 most recent from get_fault_history result ...
     ]
   }

Severity guidelines:
  - CRITICAL: production must stop immediately
  - HIGH: production can continue but maintenance required within 4 hours
  - MEDIUM: schedule maintenance within 24 hours, monitor closely
  - LOW: log and monitor, no immediate action required
"""


def get_agent() -> Agent:
    """Return the cached agent, building it on first call."""
    global _agent, _cfg

    if _agent is not None:
        return _agent

    log.info("RCA: building agent ...")
    cfg = {
        "gateway_url":   _env_or_ssm("GATEWAY_URL",         "/paintshop/gateway_url"),
        "token_url":     _env_or_ssm("COGNITO_TOKEN_URL",   "/paintshop/cognito_token_url"),
        "scope":         _env_or_ssm("COGNITO_SCOPE",       "/paintshop/cognito_scope"),
        "client_id":     _env_or_ssm("COGNITO_CLIENT_ID",   "/paintshop/cognito_rca_client_id"),
        "client_secret": _env_or_ssm("COGNITO_CLIENT_SECRET",
                                      "/paintshop/cognito_rca_client_secret", secure=True),
    }
    cfg["token"] = _get_oauth_token(cfg)
    _cfg.update(cfg)
    log.info("RCA: OAuth token acquired, Gateway ready")

    _agent = Agent(
        model=BedrockModel(model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")),
        tools=[get_sensor_history, get_fault_context, get_sop_procedure,
               get_maintenance_record, get_fault_history, write_rca_report],
        system_prompt=RCA_SYSTEM_PROMPT,
    )
    return _agent
