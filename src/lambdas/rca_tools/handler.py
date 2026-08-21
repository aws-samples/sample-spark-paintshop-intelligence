"""RCA tool Lambda — invoked by AgentCore Gateway as MCP tool targets.

Gateway sends flat args (no tool_name key). _infer_tool() dispatches by key set.

Tools:
  get_sensor_history    → DynamoDB sensor-history (last N hours of readings)
  get_fault_context     → Neptune: FaultType + SOP + CAUSED_BY causal chain
  get_maintenance_record → Neptune: HAS_MAINTENANCE_RECORD traversal
  write_rca_report      → DynamoDB rca-reports
"""
import json
import os
import uuid
import boto3
from datetime import datetime, timezone, timedelta
from boto3.dynamodb.conditions import Key, Attr
from decimal import Decimal

REGION        = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
STATUS_TABLE  = os.environ.get("STATUS_TABLE",   "tank-status")
RCA_TABLE     = os.environ.get("RCA_TABLE",      "rca-reports")
HISTORY_TABLE = os.environ.get("HISTORY_TABLE",  "sensor-history")
NEPTUNE_FN    = os.environ.get("NEPTUNE_FN",     "neptune-query")

dynamodb = boto3.resource("dynamodb", region_name=REGION)
lmb      = boto3.client("lambda",    region_name=REGION)


def _call_neptune(action: str, params: dict) -> dict:
    payload = {"action": action, **params}
    resp    = lmb.invoke(
        FunctionName=NEPTUNE_FN,
        Payload=json.dumps(payload).encode(),
    )
    return json.loads(resp["Payload"].read())


def _get_sensor_history(params: dict) -> dict:
    tank_id  = params["tank_id"]
    hours    = int(params.get("hours", 6))
    start_ts = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    skip     = {"tank_id", "timestamp", "ttl", "fault_type", "shift", "line_id"}

    resp = dynamodb.Table(HISTORY_TABLE).query(
        KeyConditionExpression=Key("tank_id").eq(tank_id) & Key("timestamp").gte(start_ts),
        ScanIndexForward=False,
        Limit=200,
    )
    readings = []
    for item in resp.get("Items", []):
        ts = item["timestamp"]
        for k, v in item.items():
            if k not in skip and isinstance(v, Decimal):
                readings.append({"time": ts, "metric": k, "value": float(v)})

    return {"tank_id": tank_id, "hours": hours, "source": "sensor-history", "readings": readings}


def _get_fault_context(params: dict) -> dict:
    """Neptune: FaultType properties + SOP + upstream CAUSED_BY causal chain."""
    return _call_neptune("get_fault_context", {
        "tank_id":    params["tank_id"],
        "fault_type": params["fault_type"],
    })


def _get_maintenance_record(params: dict) -> dict:
    """Neptune: last 5 maintenance records via HAS_MAINTENANCE_RECORD traversal."""
    return _call_neptune("get_maintenance_history", {"tank_id": params["tank_id"]})


def _get_fault_history(params: dict) -> dict:
    """Last 5 AI-generated RCA reports for this tank+fault_type from DynamoDB."""
    tank_id    = params["tank_id"]
    fault_type = params.get("fault_type", "")
    days       = int(params.get("days", 30))
    cutoff     = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    filter_expr = Attr("tank_id").eq(tank_id) & Attr("timestamp").gt(cutoff)
    if fault_type:
        filter_expr = filter_expr & Attr("fault_type").eq(fault_type)

    items = dynamodb.Table(RCA_TABLE).scan(FilterExpression=filter_expr).get("Items", [])
    items = sorted(items, key=lambda x: x.get("timestamp", ""), reverse=True)[:5]

    return {
        "tank_id":          tank_id,
        "fault_type":       fault_type,
        "days_searched":    days,
        "occurrence_count": len(items),
        "history": [
            {
                "report_id":       r["report_id"],
                "date":            r.get("timestamp", "")[:10],
                "severity":        r.get("severity", ""),
                "root_cause":      r.get("root_cause", ""),
                "recurrence_risk": r.get("recurrence_risk", ""),
            }
            for r in items
        ],
    }


def _write_rca_report(params: dict) -> dict:
    report_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now(timezone.utc).isoformat()
    evidence_raw = params.get("evidence_json", "{}")
    try:
        evidence = json.loads(evidence_raw) if evidence_raw else {}
    except json.JSONDecodeError:
        evidence = {"raw": evidence_raw}

    dynamodb.Table(RCA_TABLE).put_item(Item={
        "report_id":       report_id,
        "timestamp":       timestamp,
        "tank_id":         params["tank_id"],
        "fault_type":      params["fault_type"],
        "severity":        params["severity"],
        "root_cause":      params["root_cause"],
        "recurrence_risk": params["recurrence_risk"],
        "recommendation":  params["recommendation"],
        "evidence":        evidence,
    })
    return {"report_id": report_id, "timestamp": timestamp, "tank_id": params["tank_id"]}


_DISPATCH = {
    "get_sensor_history":     _get_sensor_history,
    "get_fault_context":      _get_fault_context,
    "get_maintenance_record": _get_maintenance_record,
    "get_fault_history":      _get_fault_history,
    "write_rca_report":       _write_rca_report,
}


def _infer_tool(event: dict) -> str:
    """Gateway sends flat args — infer tool from key set."""
    for key in ("tool_name", "name", "toolName"):
        if event.get(key):
            return event[key]
    keys = set(event.keys())
    if "fault_type" in keys and "root_cause" in keys:
        return "write_rca_report"
    if "days" in keys:
        return "get_fault_history"
    if "fault_type" in keys:
        return "get_fault_context"
    if "hours" in keys:
        return "get_sensor_history"
    return "get_maintenance_record"


def handler(event, context):
    print("RAW_EVENT:", json.dumps(event, default=str))

    tool_name  = _infer_tool(event)
    parameters = event.get("parameters") or event.get("arguments") or event

    fn = _DISPATCH.get(tool_name)
    if not fn:
        return {"error": f"Unknown tool: {tool_name}", "available": list(_DISPATCH),
                "received_keys": list(event.keys())}
    try:
        result = fn(parameters)
        return json.loads(json.dumps(result, default=str))
    except Exception as exc:
        return {"error": str(exc), "tool": tool_name}
