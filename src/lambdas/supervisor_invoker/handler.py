"""Invoke the MPS Supervisor Agent on AgentCore Runtime and return a structured
rescheduling recommendation to Step Functions.

Expected event (forwarded from Step Functions):
  {
    "detail": {
      "tank_id":       "PT-03",
      "fault_type":    "FoamingExcess",
      "anomaly_score": 0.87,
      "line_id":       "LINE-1"
    },
    "time": "2026-03-24T14:00:00Z"
  }

Returns (unwrapped by SFN result_selector into $.agent_result):
  {
    "projected_jph":  47,
    "assignments":    [...],
    "fbo_delay_mins": 28,
    "score":          0.87,
    "summary":        "Rescheduled 3 jobs from PT-03 to PT-01 ..."
  }
"""
import json
import os
import time
from decimal import Decimal
from datetime import datetime, timezone
import boto3

REGION         = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
RUNTIME_ARN    = os.environ.get("MPS_RUNTIME_ARN", "")    # set by CDK or deploy_agents.py
RUNTIME_PARAM  = os.environ.get("MPS_RUNTIME_PARAM", "/paintshop/mps_agent_runtime_arn")

ssm = boto3.client("ssm", region_name=REGION)

INCIDENTS_TABLE = os.environ.get("INCIDENTS_TABLE", "incidents")

dynamodb = boto3.resource("dynamodb", region_name=REGION)

_runtime_arn_cache: dict = {}

_FALLBACK = {
    "projected_jph":  45,
    "assignments":    [],
    "fbo_delay_mins": 60,
    "score":          0.0,
    "summary":        "MPS agent unavailable — rule-based fallback applied.",
}


def _get_runtime_arn() -> str:
    """Return the AgentCore Runtime ARN — env var takes precedence over SSM."""
    if RUNTIME_ARN:
        return RUNTIME_ARN
    if "v" not in _runtime_arn_cache:
        resp = ssm.get_parameter(Name=RUNTIME_PARAM)
        _runtime_arn_cache["v"] = resp["Parameter"]["Value"]
    return _runtime_arn_cache["v"]


def _invoke_runtime(runtime_arn: str, input_text: str, session_id: str) -> dict:
    """Call the AgentCore Runtime container and return parsed result."""
    try:
        agentcore = boto3.client("bedrock-agentcore", region_name=REGION)
        resp = agentcore.invoke_agent_runtime(
            agentRuntimeArn=runtime_arn,
            runtimeSessionId=session_id,
            payload=json.dumps({"inputText": input_text}).encode("utf-8"),
        )
        raw = resp.get("response", "")
        if hasattr(raw, "read"):
            raw = raw.read().decode("utf-8")
        return json.loads(raw) if raw else {}
    except Exception as exc:
        raise RuntimeError(f"AgentCore Runtime invocation failed: {exc}") from exc


def _parse_result(raw: dict | str) -> dict:
    """Extract the structured recommendation from the agent's response."""
    if isinstance(raw, str):
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                raw = json.loads(raw[start:end])
            except json.JSONDecodeError:
                pass

    if isinstance(raw, dict):
        # Agent may return {"result": {...}} or {"output": "...", "result": {...}}
        candidate = raw.get("result", raw)
        if "projected_jph" in candidate:
            return candidate
        # Try parsing "output" field as text containing JSON
        output = raw.get("output", "")
        if output:
            start = output.find("{")
            end   = output.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    candidate = json.loads(output[start:end])
                    if "projected_jph" in candidate:
                        return candidate
                except json.JSONDecodeError:
                    pass

    fallback = dict(_FALLBACK)
    fallback["summary"] = f"Could not parse agent result. Raw: {str(raw)[:200]}"
    return fallback


def _write_incident_mps(detail: dict, result: dict, event_time: str):
    """Write MPS output to incidents table. Wrapped in try/except — never breaks SFN."""
    try:
        ts = event_time or datetime.now(timezone.utc).isoformat()
        try:
            epoch = int(datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp())
        except Exception:
            epoch = int(time.time())
        incident_id = f"{detail.get('tank_id', 'UNKNOWN')}-{epoch}"
        ttl_val = int(time.time()) + 30 * 86400
        # Normalise assignments: add action field; unify to_tank → new_tank
        raw_asgn = result.get("assignments", [])
        assignments = []
        for a in raw_asgn:
            item = dict(a)
            if not item.get("action"):
                item["action"] = "reroute"
            if "to_tank" in item and "new_tank" not in item:
                item["new_tank"] = item.pop("to_tank")
            assignments.append(item)

        is_fallback = (
            not assignments or
            result.get("summary", "").startswith("MPS agent")
        )
        dynamodb.Table(INCIDENTS_TABLE).update_item(
            Key={"incident_id": incident_id, "timestamp": ts},
            UpdateExpression=(
                "SET tank_id            = if_not_exists(tank_id, :tid),"
                "    fault_type         = if_not_exists(fault_type, :ft),"
                "    anomaly_score      = if_not_exists(anomaly_score, :sc),"
                "    line_id            = if_not_exists(line_id, :lid),"
                "    #ttl               = if_not_exists(#ttl, :ttlv),"
                "    rca_status         = if_not_exists(rca_status, :pend),"
                "    projected_jph      = :jph,"
                "    fbo_delay_mins     = :fbo,"
                "    mps_summary        = :ms,"
                "    supervisor_summary = :ss,"
                "    cascade_warning    = :cw,"
                "    at_risk_tanks      = :art,"
                "    priority_notes     = :pn,"
                "    assignments        = :asgn,"
                "    mps_status         = :mst"
            ),
            ExpressionAttributeNames={"#ttl": "ttl"},
            ExpressionAttributeValues={
                ":tid":  detail.get("tank_id", "UNKNOWN"),
                ":ft":   detail.get("fault_type", "UNKNOWN"),
                ":sc":   Decimal(str(detail.get("anomaly_score", 0))),
                ":lid":  detail.get("line_id", "LINE-1"),
                ":ttlv": ttl_val,
                ":pend": "PENDING",
                ":jph":  Decimal(str(result.get("projected_jph", 45))),
                ":fbo":  Decimal(str(result.get("fbo_delay_mins", 0))),
                ":ms":   result.get("summary", ""),
                ":ss":   result.get("supervisor_summary", ""),
                ":cw":   result.get("cascade_warning") or "",
                ":art":  result.get("at_risk_tanks", []),
                ":pn":   result.get("priority_notes", ""),
                ":asgn": assignments,
                ":mst":  "FALLBACK" if is_fallback else "COMPLETE",
            },
        )
    except Exception as exc:
        print(f"[supervisor_invoker] incident write failed (non-fatal): {exc}")


def handler(event, context):
    detail     = event.get("detail", {})
    tank_id    = detail.get("tank_id",       "UNKNOWN")
    fault_type = detail.get("fault_type",    "UNKNOWN")
    score      = detail.get("anomaly_score", 0.0)
    line_id    = detail.get("line_id",       "LINE-1")
    timestamp  = event.get("time", "")

    prompt = (
        f"Tank anomaly detected at {timestamp}.\n"
        f"Tank: {tank_id}  Line: {line_id}  Fault: {fault_type}  Score: {score:.2f}\n\n"
        f"Reschedule all affected jobs from {tank_id} to healthy tanks on {line_id}. "
        f"Maintain JPH >= 45 and minimise FBO delay. "
        f"Follow the prescribed tool sequence and return the JSON recommendation."
    )

    session_id = f"sfn-mps-{tank_id}-{context.aws_request_id}"

    try:
        runtime_arn = _get_runtime_arn()
        raw         = _invoke_runtime(runtime_arn, prompt, session_id)
        result      = _parse_result(raw)
        _write_incident_mps(detail, result, timestamp)
        return result
    except Exception as exc:
        fallback = dict(_FALLBACK)
        fallback["summary"] = f"MPS agent error: {exc}"
        _write_incident_mps(detail, fallback, timestamp)
        return fallback
