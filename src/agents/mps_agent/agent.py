"""MPS Supervisor Agent — lazy-init agent with direct Gateway HTTP tool calls."""
import os
import json
import logging
import boto3
import requests
from strands import Agent, tool
from strands.models import BedrockModel

log = logging.getLogger(__name__)

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

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


# ── MPS Tools ──────────────────────────────────────────────────────────────

@tool
def get_affected_jobs(tank_id: str) -> dict:
    """Get all IN_PROGRESS and QUEUED production jobs assigned to a tank."""
    return _call_mcp("get-affected-jobs___get_affected_jobs", {"tank_id": tank_id})


@tool
def get_line_status(line_id: str) -> dict:
    """Get current status of all tanks on a production line."""
    return _call_mcp("get-line-status___get_line_status", {"line_id": line_id})


@tool
def compute_reschedule(
    tank_offline: str,
    jobs_json: str,
    available_tanks_json: str,
    target_jph: float = 45.0,
    fbo_target_mins: float = 30.0,
) -> dict:
    """Invoke the schedule optimiser to compute the best rescheduling plan.
    jobs_json and available_tanks_json are JSON-encoded arrays."""
    return _call_mcp("compute-reschedule___compute_reschedule", {
        "tank_offline": tank_offline,
        "jobs_json": jobs_json,
        "available_tanks_json": available_tanks_json,
        "target_jph": target_jph,
        "fbo_target_mins": fbo_target_mins,
    })


@tool
def apply_schedule(tank_id: str, assignments_json: str) -> dict:
    """Commit rescheduled job assignments to DynamoDB.
    assignments_json must preserve optimizer entries as a JSON array of
    {job_id, action, new_tank, scheduled_time} objects. Use action
    'hold_for_inspection' with new_tank null for IN_PROGRESS jobs."""
    return _call_mcp("apply-schedule___apply_schedule", {
        "tank_id": tank_id,
        "assignments_json": assignments_json,
    })


MPS_SYSTEM_PROMPT = """You are the MPS (Master Production Schedule) supervisor agent for an automotive paint shop.

When a tank goes offline or degrades:
1. Call get_affected_jobs to find impacted IN_PROGRESS and QUEUED jobs.
2. Call get_line_status to identify healthy alternative tanks on the same line.
3. ALWAYS call compute_reschedule to calculate projected JPH and FBO delay, even when the jobs list is empty. Pass an empty JSON array for jobs_json when no jobs are affected.
4. Call apply_schedule only when compute_reschedule returns one or more assignments. Pass the assignments exactly as returned by compute_reschedule: preserve action, new_tank, and scheduled_time. Never convert a hold_for_inspection assignment into a reroute.
5. Return ONLY a JSON object — no surrounding text:
   {
     "tank_id": "<offline tank>",
     "projected_jph": <use the projected_jph value returned by compute_reschedule exactly>,
     "fbo_delay_mins": <use the fbo_delay_mins value returned by compute_reschedule exactly>,
     "assignments": [
       {"job_id": "<id>", "action": "reroute", "new_tank": "<new_tank>"},
       {"job_id": "<id>", "action": "hold_for_inspection", "new_tank": null}
     ],
     "summary": "<one sentence describing what was rescheduled>"
   }

IMPORTANT: projected_jph and fbo_delay_mins MUST come from compute_reschedule's response, not estimated.
Prioritise minimising MTTR impact and maintaining JPH >= 45 across all lines."""


def get_agent() -> Agent:
    """Return the cached agent, building it on first call."""
    global _agent, _cfg

    if _agent is not None:
        return _agent

    log.info("MPS: building agent ...")
    cfg = {
        "gateway_url":   _env_or_ssm("GATEWAY_URL",         "/paintshop/gateway_url"),
        "token_url":     _env_or_ssm("COGNITO_TOKEN_URL",   "/paintshop/cognito_token_url"),
        "scope":         _env_or_ssm("COGNITO_SCOPE",       "/paintshop/cognito_scope"),
        "client_id":     _env_or_ssm("COGNITO_CLIENT_ID",   "/paintshop/cognito_mps_client_id"),
        "client_secret": _env_or_ssm("COGNITO_CLIENT_SECRET",
                                      "/paintshop/cognito_mps_client_secret", secure=True),
    }
    cfg["token"] = _get_oauth_token(cfg)
    _cfg.update(cfg)
    log.info("MPS: OAuth token acquired, Gateway ready")

    _agent = Agent(
        model=BedrockModel(model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")),
        tools=[get_affected_jobs, get_line_status, compute_reschedule, apply_schedule],
        system_prompt=MPS_SYSTEM_PROMPT,
    )
    return _agent
