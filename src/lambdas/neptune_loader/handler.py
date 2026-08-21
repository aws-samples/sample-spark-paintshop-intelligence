"""Neptune Fault History Loader — lightweight graph loader.

Graph model (IDs + timestamps only — no text content):
  (Tank {tank_id})
  (FaultEvent  {report_id, tank_id, fault_type, severity, timestamp})
  (ScheduleDecision {decision_id, trigger_tank, projected_jph, fbo_delay_mins, timestamp})

  (Tank)-[:HAD_FAULT]->(FaultEvent)
  (Tank)-[:TRIGGERED_RESCHEDULE]->(ScheduleDecision)

Text content (root_cause, recommendation) stays in DynamoDB — Neptune holds
only the relationship graph for pattern/history queries.
"""
import http.client
import json
import os
import re
import ssl
import boto3

REGION           = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
NEPTUNE_ENDPOINT = os.environ.get("NEPTUNE_ENDPOINT", "")
NEPTUNE_PORT     = os.environ.get("NEPTUNE_PORT", "8182")
RCA_TABLE        = os.environ.get("RCA_TABLE",     "rca-reports")
HISTORY_TABLE    = os.environ.get("HISTORY_TABLE", "schedule-history")
LAST_TS_PARAM    = os.environ.get("LAST_TS_PARAM", "/paintshop/neptune_last_loaded_ts")
_NEPTUNE_HOST_RE = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"neptune\.amazonaws\.com(?:\.cn)?$"
)

ALL_TANKS = ["PT-01","PT-02","PT-03","PT-04","PT-05","PT-06","PT-07","PT-08",
             "ED-01","ED-02","ED-03","ED-04"]

dynamodb = boto3.resource("dynamodb", region_name=REGION)
ssm      = boto3.client("ssm",      region_name=REGION)


def _validated_neptune_target() -> tuple[str, int]:
    """Return a validated AWS Neptune hostname and service port."""
    endpoint = NEPTUNE_ENDPOINT.strip().rstrip(".")
    if not _NEPTUNE_HOST_RE.fullmatch(endpoint):
        raise RuntimeError("NEPTUNE_ENDPOINT must be an AWS Neptune DNS hostname")
    try:
        port = int(NEPTUNE_PORT)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("NEPTUNE_PORT must be an integer") from exc
    if port != 8182:
        raise RuntimeError("NEPTUNE_PORT must be the Neptune service port 8182")
    return endpoint, port


def _gremlin(query: str) -> dict:
    endpoint, port = _validated_neptune_target()
    connection = http.client.HTTPSConnection(
        endpoint, port=port, timeout=10, context=ssl.create_default_context()
    )
    try:
        connection.request(
            "POST",
            "/gremlin",
            body=json.dumps({"gremlin": query}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        status = response.status
        raw_body = response.read().decode("utf-8")
    finally:
        connection.close()

    if not 200 <= status < 300:
        raise RuntimeError(f"Gremlin {status}: {raw_body}")
    return json.loads(raw_body)


def _e(s: str) -> str:
    return str(s).replace("'", "\\'").replace("\\", "\\\\")


def _get_last_ts() -> str:
    try:
        return ssm.get_parameter(Name=LAST_TS_PARAM)["Parameter"]["Value"]
    except ssm.exceptions.ParameterNotFound:
        return "1970-01-01T00:00:00Z"


def _save_last_ts(ts: str):
    ssm.put_parameter(Name=LAST_TS_PARAM, Value=ts, Type="String", Overwrite=True)


def _ensure_tanks():
    """Upsert all 12 tank vertices in one pass at startup."""
    for tank_id in ALL_TANKS:
        _gremlin(
            f"g.V().has('Tank','tank_id','{tank_id}')"
            f".fold().coalesce(unfold(),"
            f"addV('Tank').property('tank_id','{tank_id}'))"
        )


def _drop_all():
    """Drop all non-Tank vertices (for clean reload)."""
    _gremlin("g.V().hasLabel('FaultEvent','ScheduleDecision').drop()")


def _load_fault_event(r: dict) -> str:
    """Upsert FaultEvent vertex + HAD_FAULT edge. Returns timestamp."""
    rid  = _e(r.get("report_id", ""))
    tid  = _e(r.get("tank_id",   ""))
    ft   = _e(r.get("fault_type","unknown"))
    sev  = _e(r.get("severity",  "MEDIUM"))
    ts   = _e(r.get("timestamp", ""))
    risk = _e(r.get("recurrence_risk", ""))

    # Upsert vertex + edge in one traversal
    _gremlin(
        f"g.V().has('Tank','tank_id','{tid}').as('t')"
        f".coalesce("
        f"  __.V().has('FaultEvent','report_id','{rid}'),"
        f"  __.addV('FaultEvent')"
        f"    .property('report_id','{rid}')"
        f"    .property('tank_id','{tid}')"
        f"    .property('fault_type','{ft}')"
        f"    .property('severity','{sev}')"
        f"    .property('recurrence_risk','{risk}')"
        f"    .property('timestamp','{ts}')"
        f"    .as('f')"
        f"    .addE('HAD_FAULT').from('t').to('f')"
        f"    .select('f')"
        f")"
    )
    return r.get("timestamp", "")


def _load_schedule_decision(d: dict) -> str:
    """Upsert ScheduleDecision vertex + TRIGGERED_RESCHEDULE edge. Returns timestamp."""
    did  = _e(d.get("decision_id",   ""))
    tid  = _e(d.get("trigger_tank",  ""))
    jph  = float(d.get("projected_jph",  0) or 0)
    fbo  = float(d.get("fbo_delay_mins", 0) or 0)
    ts   = _e(d.get("timestamp", ""))

    _gremlin(
        f"g.V().has('Tank','tank_id','{tid}').as('t')"
        f".coalesce("
        f"  __.V().has('ScheduleDecision','decision_id','{did}'),"
        f"  __.addV('ScheduleDecision')"
        f"    .property('decision_id','{did}')"
        f"    .property('trigger_tank','{tid}')"
        f"    .property('projected_jph',{jph})"
        f"    .property('fbo_delay_mins',{fbo})"
        f"    .property('timestamp','{ts}')"
        f"    .as('sd')"
        f"    .addE('TRIGGERED_RESCHEDULE').from('t').to('sd')"
        f"    .select('sd')"
        f")"
    )
    return d.get("timestamp", "")


def handler(event, context):
    if not NEPTUNE_ENDPOINT:
        print("NEPTUNE_ENDPOINT not set — skipping")
        return {"loaded": 0}

    drop_first = event.get("drop_first", False)
    last_ts    = event.get("last_ts") or _get_last_ts()
    print(f"Loading records newer than {last_ts}  drop_first={drop_first}")

    # Ensure tank vertices exist
    _ensure_tanks()

    if drop_first:
        print("Dropping existing FaultEvent and ScheduleDecision vertices...")
        _drop_all()

    # Scan DynamoDB for new records
    rca_items  = [r for r in dynamodb.Table(RCA_TABLE).scan().get("Items", [])
                  if r.get("timestamp", "") > last_ts]
    hist_items = [d for d in dynamodb.Table(HISTORY_TABLE).scan().get("Items", [])
                  if d.get("timestamp", "") > last_ts]

    print(f"  RCA reports:        {len(rca_items)}")
    print(f"  Schedule decisions: {len(hist_items)}")

    max_ts = last_ts
    errors = 0

    for r in rca_items:
        try:
            ts = _load_fault_event(r)
            if ts > max_ts:
                max_ts = ts
        except Exception as exc:
            print(f"  [WARN] report {r.get('report_id')}: {exc}")
            errors += 1

    for d in hist_items:
        try:
            ts = _load_schedule_decision(d)
            if ts > max_ts:
                max_ts = ts
        except Exception as exc:
            print(f"  [WARN] decision {d.get('decision_id')}: {exc}")
            errors += 1

    if max_ts > last_ts:
        _save_last_ts(max_ts)

    loaded = len(rca_items) + len(hist_items) - errors
    print(f"Loaded {loaded} records. Errors: {errors}. Watermark: {max_ts}")
    return {"loaded": loaded, "errors": errors}
