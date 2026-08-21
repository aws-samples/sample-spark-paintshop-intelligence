"""Invoke the RCA Agent on AgentCore Runtime and return a structured RCA report
to the parallel Step Functions branch.

Expected event:
  {
    "detail": {
      "tank_id":    "PT-03",
      "fault_type": "FoamingExcess",
      "if_score":   0.87,
      "lstm_score": 0.72
    },
    "time": "2026-03-24T14:00:00Z"
  }

Returns (placed at $.rca_result by SFN result_selector):
  {
    "severity":         "HIGH",
    "root_cause":       "Gradual contamination build-up in rinse tank ...",
    "recurrence_risk":  "MEDIUM",
    "recommendation":   "Schedule tank drain and chemical refresh within 4 hours.",
    "report_id":        "a1b2c3d4"
  }
"""
import json
import os
import uuid
import boto3
import time
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from boto3.dynamodb.conditions import Key, Attr

REGION         = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
RUNTIME_ARN    = os.environ.get("RCA_RUNTIME_ARN", "")
RUNTIME_PARAM  = os.environ.get("RCA_RUNTIME_PARAM", "/paintshop/rca_agent_runtime_arn")

INCIDENTS_TABLE = os.environ.get("INCIDENTS_TABLE", "incidents")
RCA_TABLE       = os.environ.get("RCA_TABLE", "rca-reports")

ssm = boto3.client("ssm", region_name=REGION)

dynamodb = boto3.resource("dynamodb", region_name=REGION)

_runtime_arn_cache: dict = {}

_FALLBACK = {
    "severity":        "MEDIUM",
    "root_cause":      "RCA agent unavailable — manual investigation required.",
    "recurrence_risk": "UNKNOWN",
    "recommendation":  "Review sensor logs manually and schedule inspection.",
    "report_id":       "fallback",
}


def _get_runtime_arn() -> str:
    if RUNTIME_ARN:
        return RUNTIME_ARN
    if "v" not in _runtime_arn_cache:
        resp = ssm.get_parameter(Name=RUNTIME_PARAM)
        _runtime_arn_cache["v"] = resp["Parameter"]["Value"]
    return _runtime_arn_cache["v"]


def _invoke_runtime(runtime_arn: str, input_text: str, session_id: str) -> dict:
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


_RCA_RESULT_KEYS = (
    "severity", "root_cause", "recurrence_risk", "recommendation", "report_id",
)


def _parse_result(raw: dict | str) -> dict:
    if isinstance(raw, str):
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                raw = json.loads(raw[start:end])
            except json.JSONDecodeError:
                pass

    if isinstance(raw, dict):
        candidate = raw.get("result", raw)
        if not all(candidate.get(key) not in (None, "") for key in _RCA_RESULT_KEYS):
            output = raw.get("output", "")
            if output:
                start = output.find("{")
                end   = output.rfind("}") + 1
                if start >= 0 and end > start:
                    try:
                        candidate = json.loads(output[start:end])
                    except json.JSONDecodeError:
                        pass

        if all(candidate.get(key) not in (None, "") for key in _RCA_RESULT_KEYS):
            return _normalize(candidate)

    fallback = dict(_FALLBACK)
    fallback["root_cause"] = f"Parse failed. Raw: {str(raw)[:200]}"
    return fallback


# Severity aliases from agent output -> SFN-expected values
_SEV_MAP = {"MODERATE": "MEDIUM", "CRITICAL": "CRITICAL", "HIGH": "HIGH",
            "MEDIUM": "MEDIUM", "LOW": "LOW"}


def _normalize(d: dict) -> dict:
    """Ensure the dict has the exact fields the SFN result_selector expects."""
    # recommendation: singular string
    if "recommendation" not in d:
        recs = d.get("recommendations", [])
        if isinstance(recs, list) and recs:
            d["recommendation"] = recs[0]
        else:
            d["recommendation"] = d.get("diagnostic_summary", "See root cause.")
    # report_id: must be present
    if "report_id" not in d:
        d["report_id"] = d.get("report_id", str(uuid.uuid4())[:8])
    # severity: normalise aliases
    d["severity"] = _SEV_MAP.get(d.get("severity", "MEDIUM"), "MEDIUM")
    return d


def _count_recent_faults(tank_id: str, fault_type: str) -> int:
    """Count rca-reports for this tank+fault_type in the last 30 days."""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        resp = dynamodb.Table(RCA_TABLE).query(
            IndexName="tank-rca-index",
            KeyConditionExpression=Key("tank_id").eq(tank_id) & Key("timestamp").gte(cutoff),
            FilterExpression=Attr("fault_type").eq(fault_type),
            Select="COUNT",
        )
        return resp.get("Count", 0)
    except Exception:
        return 0


def _recurrence_risk(count: int) -> str:
    if count >= 3:
        return "HIGH"
    if count >= 1:
        return "MEDIUM"
    return "LOW"


def _update_incident_rca(detail: dict, result: dict, event_time: str):
    """Update incidents table with RCA output. Wrapped in try/except — never breaks SFN."""
    try:
        ts = event_time or datetime.now(timezone.utc).isoformat()
        try:
            epoch = int(datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp())
        except Exception:
            epoch = int(time.time())
        incident_id = f"{detail.get('tank_id', 'UNKNOWN')}-{epoch}"
        ttl_val = int(time.time()) + 30 * 86400
        is_fallback = not result.get("root_cause") or result.get("report_id") == "fallback"
        dynamodb.Table(INCIDENTS_TABLE).update_item(
            Key={"incident_id": incident_id, "timestamp": ts},
            UpdateExpression=(
                "SET tank_id         = if_not_exists(tank_id, :tid),"
                "    fault_type      = if_not_exists(fault_type, :ft),"
                "    anomaly_score   = if_not_exists(anomaly_score, :sc),"
                "    line_id         = if_not_exists(line_id, :lid),"
                "    #ttl            = if_not_exists(#ttl, :ttlv),"
                "    mps_status      = if_not_exists(mps_status, :pend),"
                "    severity        = :sv,"
                "    root_cause      = :rc,"
                "    recurrence_risk = :rr,"
                "    recommendation  = :rd,"
                "    report_id       = :ri,"
                "    rca_status      = :rs"
            ),
            ExpressionAttributeNames={"#ttl": "ttl"},
            ExpressionAttributeValues={
                ":tid":  detail.get("tank_id", "UNKNOWN"),
                ":ft":   detail.get("fault_type", "UNKNOWN"),
                ":sc":   Decimal(str(detail.get("anomaly_score", 0))),
                ":lid":  detail.get("line_id", "LINE-1"),
                ":ttlv": ttl_val,
                ":pend": "PENDING",
                ":sv":   result.get("severity", "UNKNOWN"),
                ":rc":   result.get("root_cause", ""),
                ":rr":   result.get("recurrence_risk", ""),
                ":rd":   result.get("recommendation", ""),
                ":ri":   result.get("report_id", ""),
                ":rs":   "FALLBACK" if is_fallback else "COMPLETE",
            },
        )
    except Exception as exc:
        print(f"[rca_invoker] incident write failed (non-fatal): {exc}")


def handler(event, context):
    detail     = event.get("detail", {})
    tank_id    = detail.get("tank_id",    "UNKNOWN")
    fault_type = detail.get("fault_type", "UNKNOWN")
    if_score   = detail.get("if_score",   0.0)
    lstm_score = detail.get("lstm_score", 0.0)
    timestamp  = event.get("time", "")

    prompt = (
        f"Root cause analysis requested at {timestamp}.\n"
        f"Tank: {tank_id}  Fault: {fault_type}\n"
        f"Anomaly scores — Isolation Forest: {if_score:.2f}, LSTM: {lstm_score:.2f}\n\n"
        f"Analyse sensor history, fault patterns, and maintenance records for {tank_id}. "
        f"Determine root cause, severity, and recurrence risk. "
        f"Write an RCA report and return the JSON result."
    )

    session_id = f"sfn-rca-{tank_id}-{context.aws_request_id}"

    try:
        runtime_arn = _get_runtime_arn()
        raw         = _invoke_runtime(runtime_arn, prompt, session_id)
        result      = _parse_result(raw)
        # Override LLM recurrence_risk with deterministic count from rca-reports
        count = _count_recent_faults(tank_id, fault_type)
        result["recurrence_risk"] = _recurrence_risk(count)
        _update_incident_rca(detail, result, timestamp)
        return result
    except Exception as exc:
        fallback = dict(_FALLBACK)
        fallback["root_cause"] = f"RCA agent error: {exc}"
        _update_incident_rca(detail, fallback, timestamp)
        return fallback
