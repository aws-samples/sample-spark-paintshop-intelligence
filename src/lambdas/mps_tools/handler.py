"""MPS tool Lambda — invoked by AgentCore Gateway as MCP tool targets.

Each tool is dispatched by the 'tool_name' key in the event.
Gateway sends: {"tool_name": "<name>", "parameters": {...}}
"""
import json
import os
import boto3
from decimal import Decimal
from boto3.dynamodb.conditions import Attr, Key

REGION       = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
JOBS_TABLE   = os.environ.get("JOBS_TABLE",   "production-jobs")
STATUS_TABLE = os.environ.get("STATUS_TABLE", "tank-status")
OPTIMIZER_FN = os.environ.get("OPTIMIZER_FN", "schedule-optimizer")

dynamodb = boto3.resource("dynamodb", region_name=REGION)
lambda_c = boto3.client("lambda",     region_name=REGION)


class _DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        return float(o) if isinstance(o, Decimal) else super().default(o)


def _get_affected_jobs(params: dict) -> dict:
    tank_id = params["tank_id"]
    table   = dynamodb.Table(JOBS_TABLE)
    filter_expr = Attr("tank_id").eq(tank_id) & Attr("status").is_in(["IN_PROGRESS", "QUEUED"])
    items = []
    kwargs = {"FilterExpression": filter_expr}
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key
    return {"tank_id": tank_id, "jobs": items}


def _get_line_status(params: dict) -> dict:
    line_id = params["line_id"]
    table   = dynamodb.Table(STATUS_TABLE)
    resp    = table.scan(
        FilterExpression=Attr("line_id").eq(line_id),
    )
    return {"line_id": line_id, "tanks": resp.get("Items", [])}


def _compute_reschedule(params: dict) -> dict:
    raw_tanks = json.loads(params.get("available_tanks_json", "[]"))
    available_lines = []
    for t in raw_tanks:
        if isinstance(t, str):
            available_lines.append({"line_id": t, "capacity_jph": 50, "current_load": 0})
        elif isinstance(t, dict):
            available_lines.append({
                "line_id":      t.get("tank_id", t.get("line_id", "UNKNOWN")),
                "capacity_jph": 50.0,
                "current_load": float(t.get("current_jph", 0) or 0),
            })

    payload = {
        "tank_offline":    params["tank_offline"],
        "jobs":            json.loads(params.get("jobs_json", "[]")),
        "available_lines": available_lines,
        "target_jph":      float(params.get("target_jph", 45.0)),
        "fbo_target_mins": float(params.get("fbo_target_mins", 30.0)),
    }
    resp = lambda_c.invoke(
        FunctionName=OPTIMIZER_FN,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode(),
    )
    result = json.loads(resp["Payload"].read())
    if resp.get("FunctionError"):
        raise RuntimeError(f"Optimizer invocation failed: {result}")

    # The optimizer Lambda uses the API-style {statusCode, body} contract.
    # Return its body directly so the agent receives assignments and metrics,
    # rather than a JSON string nested inside another response object.
    if isinstance(result, dict) and "body" in result:
        if int(result.get("statusCode", 200)) >= 400:
            raise RuntimeError(f"Optimizer returned an error: {result['body']}")
        body = result["body"]
        return json.loads(body) if isinstance(body, str) else body
    return result


def _lookup_scheduled_time(table, job_id: str, status: str = None) -> str | None:
    """Look up scheduled_time for a job_id — needed when agent omits it from assignments."""
    kwargs = {"KeyConditionExpression": Key("job_id").eq(job_id)}
    if status:
        kwargs["FilterExpression"] = Attr("status").eq(status)
    resp  = table.query(**kwargs)
    items = resp.get("Items", [])
    if not items:
        # retry without status filter
        resp  = table.query(KeyConditionExpression=Key("job_id").eq(job_id))
        items = resp.get("Items", [])
    return items[0]["scheduled_time"] if items else None


def _apply_schedule(params: dict) -> dict:
    tank_id     = params["tank_id"]
    assignments = json.loads(params.get("assignments_json", "[]"))
    table       = dynamodb.Table(JOBS_TABLE)
    rerouted    = 0
    held        = 0
    for a in assignments:
        # Preserve optimizer semantics even if the model omits ``action``:
        # a null destination means the job must remain on the faulted tank.
        action = a.get("action") or (
            "hold_for_inspection" if not a.get("new_tank") else "reroute"
        )
        # Resolve scheduled_time if the agent omitted or nulled it
        if not a.get("scheduled_time"):
            a["scheduled_time"] = _lookup_scheduled_time(
                table, a["job_id"],
                status=None if action == "hold_for_inspection" else "QUEUED"
            )
        if not a.get("scheduled_time"):
            continue  # can't update without composite key
        try:
            if action == "hold_for_inspection":
                # Car is mid-process in faulting tank — update status only, keep tank_id
                table.update_item(
                    Key={"job_id": a["job_id"], "scheduled_time": a["scheduled_time"]},
                    UpdateExpression="SET #s = :s",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={":s": "HOLD_FOR_INSPECTION"},
                )
                held += 1
            else:
                # QUEUED job — move to new tank and mark rescheduled
                table.update_item(
                    Key={"job_id": a["job_id"], "scheduled_time": a["scheduled_time"]},
                    UpdateExpression="SET tank_id = :t, #s = :s",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={":t": a["new_tank"], ":s": "RESCHEDULED"},
                )
                rerouted += 1
        except Exception:
            pass

    # Catch-all: reschedule any QUEUED jobs still on the faulted tank that the
    # agent/optimizer missed (e.g. LIVE seed jobs with non-standard job_id formats)
    if rerouted > 0:
        # Determine target tank from the majority of explicit assignments
        from collections import Counter
        target_counts = Counter(
            a.get("new_tank") for a in assignments
            if a.get("new_tank") and a.get("action") != "hold_for_inspection"
        )
        fallback_tank = target_counts.most_common(1)[0][0] if target_counts else None
        if fallback_tank:
            remaining = table.scan(
                FilterExpression=Attr("tank_id").eq(tank_id) & Attr("status").eq("QUEUED")
            ).get("Items", [])
            for job in remaining:
                try:
                    table.update_item(
                        Key={"job_id": job["job_id"], "scheduled_time": job["scheduled_time"]},
                        UpdateExpression="SET tank_id = :t, #s = :s",
                        ExpressionAttributeNames={"#s": "status"},
                        ExpressionAttributeValues={":t": fallback_tank, ":s": "RESCHEDULED"},
                    )
                    rerouted += 1
                except Exception:
                    pass

    return {"tank_id": tank_id, "rerouted": rerouted, "held": held}


_DISPATCH = {
    "get_affected_jobs":  _get_affected_jobs,
    "get_line_status":    _get_line_status,
    "compute_reschedule": _compute_reschedule,
    "apply_schedule":     _apply_schedule,
}


def _infer_tool(event: dict) -> str:
    """Infer tool name from event keys — Gateway sends flat args with no tool_name."""
    for key in ("tool_name", "name", "toolName"):
        if event.get(key):
            return event[key]
    keys = set(event.keys())
    if "line_id" in keys:
        return "get_line_status"
    if "tank_offline" in keys or "jobs_json" in keys:
        return "compute_reschedule"
    if "assignments_json" in keys:
        return "apply_schedule"
    # fall back: only tank_id → get affected jobs
    return "get_affected_jobs"


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
        return json.loads(json.dumps(result, cls=_DecimalEncoder))
    except Exception as exc:
        return {"error": str(exc), "tool": tool_name}
