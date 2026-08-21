"""REST API handler — serves historical and current data to the dashboard.

Routes:
  GET  /tanks                  → all tanks current status from DynamoDB tank-status
  GET  /tanks/{id}/history     → sensor time-series from DynamoDB sensor-history (last 6h)
  GET  /schedule               → production jobs (IN_PROGRESS + QUEUED) from DynamoDB
  GET  /rca/{tankId}           → RCA reports for a tank
  GET  /maintenance/{tankId}   → maintenance log for a tank
"""
import json
import os
import re
import boto3
from boto3.dynamodb.conditions import Key, Attr
from decimal import Decimal
from datetime import datetime, timezone, timedelta

REGION         = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
STATUS_TABLE   = os.environ.get("STATUS_TABLE",   "tank-status")
JOBS_TABLE     = os.environ.get("JOBS_TABLE",     "production-jobs")
RCA_TABLE      = os.environ.get("RCA_TABLE",      "rca-reports")
MAINT_TABLE    = os.environ.get("MAINT_TABLE",    "maintenance-log")
HISTORY_TABLE  = os.environ.get("HISTORY_TABLE",  "sensor-history")
INCIDENTS_TABLE = os.environ.get("INCIDENTS_TABLE", "incidents")
STREAM_PROCESSOR_FN = "stream-processor"   # used to discover the Kinesis ESM UUID
SIMULATOR_RULE      = "paintshop-simulator-schedule"

_esm_uuid_cache: dict = {}


def _get_esm_uuid() -> str:
    """Look up the Kinesis ESM UUID for stream-processor — works in any account."""
    if "v" not in _esm_uuid_cache:
        resp = lambda_c.list_event_source_mappings(FunctionName=STREAM_PROCESSOR_FN)
        for esm in resp.get("EventSourceMappings", []):
            if "kinesis" in esm.get("EventSourceArn", "").lower():
                _esm_uuid_cache["v"] = esm["UUID"]
                break
        else:
            raise ValueError("Kinesis ESM not found for stream-processor")
    return _esm_uuid_cache["v"]
DEMO_FAULTS_PARAM   = "/paintshop/demo_faults"   # JSON: {tank_id: {fault_type, start_ts}}

dynamodb  = boto3.resource("dynamodb", region_name=REGION)
eb        = boto3.client("events",     region_name=REGION)
lambda_c  = boto3.client("lambda",     region_name=REGION)
ssm_c     = boto3.client("ssm",        region_name=REGION)

CORS = {
    "Access-Control-Allow-Origin":  "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Authorization,Content-Type",
}


class _DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def _ok(body) -> dict:
    return {
        "statusCode": 200,
        "headers":    {**CORS, "Content-Type": "application/json"},
        "body":       json.dumps(body, cls=_DecimalEncoder),
    }


def _err(code: int, msg: str) -> dict:
    return {
        "statusCode": code,
        "headers":    {**CORS, "Content-Type": "application/json"},
        "body":       json.dumps({"error": msg}),
    }


# ── Route handlers ─────────────────────────────────────────────────────────

def get_tanks():
    resp  = dynamodb.Table(STATUS_TABLE).scan()
    tanks = resp.get("Items", [])
    # Sort by tank_id for consistent display order
    tanks.sort(key=lambda t: t.get("tank_id", ""))
    return _ok({"tanks": tanks, "count": len(tanks)})


def get_tank_history(tank_id: str, hours: int = 6):
    # Non-sensor fields to exclude from the readings list
    skip = {"tank_id", "timestamp", "ttl", "fault_type", "shift", "line_id"}
    start_ts = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    try:
        resp = dynamodb.Table(HISTORY_TABLE).query(
            KeyConditionExpression=Key("tank_id").eq(tank_id) & Key("timestamp").gte(start_ts),
            ScanIndexForward=True,
            Limit=500,
        )
        readings = []
        for item in resp.get("Items", []):
            ts = item["timestamp"]
            for k, v in item.items():
                if k not in skip and isinstance(v, Decimal):
                    readings.append({"time": ts, "metric": k, "value": float(v)})
        return _ok({"tank_id": tank_id, "hours": hours, "readings": readings})
    except Exception as exc:
        return _err(500, str(exc))


def get_schedule():
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    # IN_PROGRESS/QUEUED always show; RESCHEDULED only within last 24h to avoid stale noise
    filter_exp = (
        Attr("status").is_in(["IN_PROGRESS", "QUEUED"]) |
        (Attr("status").eq("RESCHEDULED") & Attr("scheduled_time").gte(cutoff))
    )
    all_items = []
    kwargs = {"FilterExpression": filter_exp}
    while True:
        resp = dynamodb.Table(JOBS_TABLE).scan(**kwargs)
        all_items.extend(resp.get("Items", []))
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last
    # Deduplicate by job_id — composite key allows same job_id with multiple scheduled_times.
    # Prefer RESCHEDULED over QUEUED/IN_PROGRESS; within same status pick latest scheduled_time.
    _STATUS_RANK = {"RESCHEDULED": 2, "IN_PROGRESS": 1, "QUEUED": 0}
    best: dict = {}
    for j in all_items:
        jid = j.get("job_id", "")
        existing = best.get(jid)
        if existing is None:
            best[jid] = j
        else:
            if (_STATUS_RANK.get(j.get("status"), 0) > _STATUS_RANK.get(existing.get("status"), 0) or
                    (j.get("status") == existing.get("status") and
                     j.get("scheduled_time", "") > existing.get("scheduled_time", ""))):
                best[jid] = j

    jobs = []
    for j in best.values():
        job_id = j.get("job_id", "")
        parts  = job_id.split("-")
        original_tank = f"{parts[0]}-{parts[1]}" if len(parts) >= 2 else None
        current_tank  = j.get("tank_id")
        j["original_tank"] = original_tank if (
            j.get("status") == "RESCHEDULED" and original_tank != current_tank
        ) else None
        jobs.append(j)
    jobs = sorted(jobs, key=lambda j: (j.get("scheduled_start", ""), j.get("priority", 5)))
    return _ok({"jobs": jobs, "count": len(jobs)})


def get_rca(tank_id: str):
    resp = dynamodb.Table(RCA_TABLE).query(
        IndexName="tank-rca-index",
        KeyConditionExpression=Key("tank_id").eq(tank_id),
        ScanIndexForward=False,
        Limit=10,
    )
    return _ok({"tank_id": tank_id, "reports": resp.get("Items", [])})


def get_maintenance(tank_id: str):
    resp = dynamodb.Table(MAINT_TABLE).query(
        KeyConditionExpression=Key("tank_id").eq(tank_id),
        ScanIndexForward=False,
        Limit=10,
    )
    return _ok({"tank_id": tank_id, "records": resp.get("Items", [])})


def get_incidents(days: int = 7, tank_id: str = None):
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        items = []
        if tank_id:
            # Use GSI for per-tank query — paginated
            kwargs: dict = {
                "IndexName": "incidents-tank-time-index",
                "KeyConditionExpression": Key("tank_id").eq(tank_id) & Key("timestamp").gte(cutoff),
                "ScanIndexForward": False,
            }
            while True:
                resp = dynamodb.Table(INCIDENTS_TABLE).query(**kwargs)
                items.extend(resp.get("Items", []))
                last = resp.get("LastEvaluatedKey")
                if not last:
                    break
                kwargs["ExclusiveStartKey"] = last
        else:
            # Paginated scan — same pattern as get_schedule()
            filter_exp = Attr("timestamp").gte(cutoff)
            kwargs = {"FilterExpression": filter_exp}
            while True:
                resp = dynamodb.Table(INCIDENTS_TABLE).scan(**kwargs)
                items.extend(resp.get("Items", []))
                last = resp.get("LastEvaluatedKey")
                if not last:
                    break
                kwargs["ExclusiveStartKey"] = last
            # Sort newest first
            items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return _ok({"incidents": items, "count": len(items)})
    except Exception as exc:
        return _err(500, str(exc))


# ── Demo control routes ────────────────────────────────────────────────────

FAULT_MAP = {
    "PT-01": "alkalinity_depletion", "PT-02": "alkalinity_depletion",
    "PT-03": "rinse_contamination",  "PT-04": "rinse_contamination",
    "PT-05": "titanium_depletion",   "PT-06": "acid_drift",
    "PT-07": "rinse_contamination",  "PT-08": "ph_drift",
    "ED-01": "temperature_creep",    "ED-02": "rinse_contamination",
    "ED-03": "rinse_contamination",  "ED-04": "rinse_contamination",
}
TANK_LINE_MAP = {t: "LINE-1" for t in FAULT_MAP}


def _read_faults() -> dict:
    """Read active fault map from SSM: {tank_id: {fault_type, start_ts}}"""
    try:
        val = ssm_c.get_parameter(Name=DEMO_FAULTS_PARAM)["Parameter"]["Value"]
        return json.loads(val)
    except Exception:
        return {}


def _write_faults(faults: dict):
    if faults:
        ssm_c.put_parameter(Name=DEMO_FAULTS_PARAM, Value=json.dumps(faults),
                            Type="String", Overwrite=True)
    else:
        try:
            ssm_c.delete_parameter(Name=DEMO_FAULTS_PARAM)
        except Exception:
            pass


def demo_inject(body: dict = None):
    """Arm fault injection for a tank. Status changes only when ML detects the breach."""
    from datetime import datetime, timezone
    body       = body or {}
    tank_id    = body.get("tank_id", "PT-06")
    fault_type = body.get("fault_type") or FAULT_MAP.get(tank_id, "acid_drift")
    now        = datetime.now(timezone.utc)

    # Seed 3 active jobs so MPS agent has work to reschedule when anomaly fires
    ts = now.isoformat()
    ttl_24h = int((now + timedelta(hours=24)).timestamp())
    for jid, status in [(f"{tank_id}-LIVE-001", "IN_PROGRESS"),
                        (f"{tank_id}-LIVE-002", "QUEUED"),
                        (f"{tank_id}-LIVE-003", "QUEUED")]:
        dynamodb.Table(JOBS_TABLE).put_item(Item={
            "job_id": jid, "tank_id": tank_id,
            "status": status, "simulated_jph": 45,
            "scheduled_time": ts, "color_code": "MIDNIGHT_BLACK", "priority": 2,
            "ttl": ttl_24h,
        })

    # Add this tank to the active fault map (preserves other tanks already faulted)
    faults = _read_faults()
    faults[tank_id] = {"fault_type": fault_type, "start_ts": now.isoformat()}
    _write_faults(faults)

    return _ok({"status": "armed", "tank": tank_id, "fault": fault_type,
                "active_faults": list(faults.keys())})


def _cleanup_tank_jobs(tank_id: str):
    """Delete all LIVE seed jobs and RESCHEDULED records originating from this tank."""
    table     = dynamodb.Table(JOBS_TABLE)
    prefix    = f"{tank_id}-"
    # Match both LIVE seed jobs (PT-03-LIVE-*) and regular rescheduled jobs (PT-03-J*)
    kwargs = {
        "FilterExpression": (
            Attr("job_id").begins_with(prefix) &
            Attr("status").is_in(["IN_PROGRESS", "QUEUED", "RESCHEDULED", "HOLD_FOR_INSPECTION"])
        ),
        "ProjectionExpression": "job_id, scheduled_time",
    }
    to_delete = []
    while True:
        resp = table.scan(**kwargs)
        to_delete.extend(resp.get("Items", []))
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last
    with table.batch_writer() as batch:
        for item in to_delete:
            batch.delete_item(Key={"job_id": item["job_id"], "scheduled_time": item["scheduled_time"]})


def demo_reset(body: dict = None):
    """Remove a tank from the fault map. The simulator will resume normal readings
    and the ML model will detect recovery naturally — no direct DynamoDB write."""
    body    = body or {}
    tank_id = body.get("tank_id", "PT-06")

    # Remove only this tank from the fault map; other tanks keep their faults
    faults = _read_faults()
    faults.pop(tank_id, None)
    _write_faults(faults)

    # Clean up all jobs originating from this tank (LIVE seeds + rescheduled J-format jobs)
    _cleanup_tank_jobs(tank_id)

    return _ok({"status": "reset", "tank": tank_id,
                "remaining_faults": list(faults.keys())})


def demo_telemetry(body: dict):
    """Start or stop live telemetry (simulator + stream processor)."""
    action = body.get("action", "start")
    enable = action == "start"

    # Toggle Kinesis ESM
    lambda_c.update_event_source_mapping(
        UUID=_get_esm_uuid(),
        Enabled=enable,
    )
    # Toggle simulator schedule
    if enable:
        eb.enable_rule(Name=SIMULATOR_RULE)
    else:
        eb.disable_rule(Name=SIMULATOR_RULE)

    return _ok({"status": action, "telemetry": "started" if enable else "stopped"})


def demo_status():
    """Return current state of telemetry controls."""
    esm   = lambda_c.get_event_source_mapping(UUID=_get_esm_uuid())
    rule  = eb.describe_rule(Name=SIMULATOR_RULE)
    return _ok({
        "kinesis_enabled":   esm["State"] in ("Enabled", "Enabling"),
        "simulator_enabled": rule["State"] == "ENABLED",
    })


# ── Router ─────────────────────────────────────────────────────────────────

def handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    path   = event.get("rawPath", event.get("path", "/"))
    params = event.get("queryStringParameters") or {}

    if method == "OPTIONS":
        return {"statusCode": 200, "headers": CORS, "body": ""}

    # ── Demo controls ───────────────────────────────────────────────────────
    if path == "/demo/inject" and method == "POST":
        try:
            body = json.loads(event.get("body") or "{}")
        except Exception:
            body = {}
        return demo_inject(body)
    if path == "/demo/reset" and method == "POST":
        try:
            body = json.loads(event.get("body") or "{}")
        except Exception:
            body = {}
        return demo_reset(body)
    if path == "/demo/telemetry" and method == "POST":
        try:
            body = json.loads(event.get("body") or "{}")
        except Exception:
            body = {}
        return demo_telemetry(body)
    if path == "/demo/status":
        return demo_status()

    if path == "/tanks" or path == "/tanks/":
        return get_tanks()

    m = re.match(r"^/tanks/([^/]+)/history$", path)
    if m:
        hours = int(params.get("hours", 6))
        return get_tank_history(m.group(1), hours)

    if path == "/schedule" or path == "/schedule/":
        return get_schedule()

    m = re.match(r"^/rca/([^/]+)$", path)
    if m:
        return get_rca(m.group(1))

    m = re.match(r"^/maintenance/([^/]+)$", path)
    if m:
        return get_maintenance(m.group(1))

    if path == "/incidents" or path == "/incidents/":
        days    = int(params.get("days", 7))
        tank_id = params.get("tank_id")
        return get_incidents(days, tank_id)

    return _err(404, f"Route not found: {method} {path}")
