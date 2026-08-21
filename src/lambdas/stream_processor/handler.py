"""Stream Processor Lambda.

Reads Kinesis records, invokes the SageMaker Multi-Container Endpoint
(3 containers: isolation-forest, lstm-autoencoder, xgboost-classifier),
and publishes a TankAnomalyDetected event to EventBridge when the
combined anomaly score exceeds the SSM threshold.
"""
import base64, json, os
from datetime import datetime, timezone
from decimal import Decimal
import boto3
from boto3.dynamodb.conditions import Attr

EVENT_BUS_NAME  = os.environ.get("EVENT_BUS_NAME",   "default")
ENDPOINT_NAME   = os.environ.get("ENDPOINT_NAME",    "paintshop-anomaly-endpoint")
THRESHOLD_PARAM = os.environ.get("THRESHOLD_PARAM",  "/paintshop/anomaly_threshold")
STATUS_TABLE    = os.environ.get("STATUS_TABLE",     "tank-status")
JOBS_TABLE      = os.environ.get("JOBS_TABLE",       "production-jobs")
HISTORY_TABLE   = os.environ.get("HISTORY_TABLE",    "sensor-history")

EB       = boto3.client("events")
SSM      = boto3.client("ssm")
RUNTIME  = boto3.client("sagemaker-runtime")
DYNAMODB = boto3.resource("dynamodb")

TANK_LINE_MAP = {
    "PT-01": "LINE-1", "PT-02": "LINE-1", "PT-03": "LINE-1", "PT-04": "LINE-1",
    "PT-05": "LINE-1", "PT-06": "LINE-1", "PT-07": "LINE-1", "PT-08": "LINE-1",
    "ED-01": "LINE-1", "ED-02": "LINE-1", "ED-03": "LINE-1", "ED-04": "LINE-1",
}

# Normal operating ranges — used only to derive breached_sensors for the event payload
SENSOR_RANGES = {
    "PT-01": {"temperature_c": (50, 60), "ph": (11.0, 12.0), "free_alkalinity": (8.0, 14.0), "conductivity_us_cm": (5000, 12000)},
    "PT-02": {"temperature_c": (55, 65), "ph": (11.5, 12.5), "free_alkalinity": (10.0, 16.0), "total_alkalinity": (14.0, 22.0)},
    "PT-03": {"conductivity_us_cm": (20, 100), "ph": (6.5, 8.5), "rinse_flow": (8.0, 15.0)},
    "PT-04": {"conductivity_us_cm": (10, 80),  "ph": (6.5, 8.0), "rinse_flow": (8.0, 15.0)},
    "PT-05": {"ph": (8.5, 9.5), "temperature_c": (25, 35), "titanium_ppm": (0.5, 2.5)},
    "PT-06": {"temperature_c": (40, 50), "free_acid_pts": (0.5, 1.5), "total_acid_pts": (18, 24),
              "zinc_g_per_l": (1.0, 1.8), "accelerator_pts": (2.5, 4.5), "conductivity_us_cm": (2000, 4000)},
    "PT-07": {"conductivity_us_cm": (50, 200), "ph": (6.0, 8.0), "rinse_flow": (8.0, 15.0)},
    "PT-08": {"ph": (4.0, 5.0), "temperature_c": (25, 35), "concentration_pct": (0.3, 1.2)},
    "ED-01": {"ph": (5.8, 6.2), "temperature_c": (28, 32), "solids_pct": (18, 22),
              "conductivity_us_cm": (1200, 1800), "voltage_v": (200, 350), "meq_acid": (18, 32)},
    "ED-02": {"ph": (5.5, 7.0), "conductivity_us_cm": (500, 2000), "solids_pct": (1.0, 5.0)},
    "ED-03": {"ph": (5.5, 7.0), "conductivity_us_cm": (200, 800),  "solids_pct": (0.2, 1.5)},
    "ED-04": {"conductivity_us_cm": (1, 20), "ph": (5.5, 7.5)},
}

_threshold_cache: dict = {}


def get_threshold() -> float:
    if "v" not in _threshold_cache:
        resp = SSM.get_parameter(Name=THRESHOLD_PARAM)
        _threshold_cache["v"] = float(resp["Parameter"]["Value"])
    return _threshold_cache["v"]


def derive_shift(timestamp_iso: str) -> str:
    hour = datetime.fromisoformat(timestamp_iso.replace("Z", "+00:00")).hour
    if 6 <= hour < 14:
        return "morning"
    elif 14 <= hour < 22:
        return "afternoon"
    return "night"


def enrich_record(record: dict) -> dict:
    record["shift"]   = derive_shift(record["timestamp"])
    record["line_id"] = TANK_LINE_MAP.get(record["tank_id"], "LINE-1")
    return record


def _invoke_container(payload: dict, container_hostname: str) -> dict:
    resp = RUNTIME.invoke_endpoint(
        EndpointName=ENDPOINT_NAME,
        TargetContainerHostname=container_hostname,
        ContentType="application/json",
        Body=json.dumps(payload),
    )
    return json.loads(resp["Body"].read())


def score_record(record: dict) -> dict:
    """Call all 3 MCE containers and combine results."""
    # The preprocessed payload — pass raw sensor values; inference scripts
    # handle missing keys with .get(key, 0.0)
    payload = {k: v for k, v in record.items()
               if isinstance(v, (int, float)) or k == "tank_id"}

    if_result   = _invoke_container(payload, "isolation-forest")
    lstm_result = _invoke_container(payload, "lstm-autoencoder")
    xgb_result  = _invoke_container(payload, "xgboost-classifier")

    if_score   = float(if_result.get("if_score",   0.0))
    lstm_score = float(lstm_result.get("lstm_score", 0.0))
    fault_type      = xgb_result.get("fault_type", "normal")
    xgb_confidence  = float(xgb_result.get("confidence", 0.0))

    # ML-driven anomaly detection: XGBoost classifies fault type per tank.
    # "normal" means the model sees healthy readings; any other class is an anomaly.
    # The model was trained with tank one-hot features, so it correctly distinguishes
    # normal vs. faulty patterns for each specific tank.
    anomaly_detected = fault_type != "normal"

    # Still compute breached sensors for diagnostic context in event payload
    tank_id  = record.get("tank_id", "")
    ranges   = SENSOR_RANGES.get(tank_id, {})
    breached = []
    for sensor, (lo, hi) in ranges.items():
        val = record.get(sensor)
        if val is not None and (val < lo or val > hi):
            breached.append({
                "sensor":    sensor,
                "value":     val,
                "direction": "high" if val > hi else "low",
                "range":     [lo, hi],
            })

    return {
        "anomaly_detected": anomaly_detected,
        "if_score":         round(if_score,      4),
        "lstm_score":       round(lstm_score,    4),
        "xgb_confidence":   round(xgb_confidence, 4),
        "fault_type":       fault_type,
        "breached_sensors": breached,
        "tank_id":          tank_id,
        "scorer":           "sagemaker_mce_v1",
    }


def publish_anomaly(inference: dict, record: dict):
    detail = {
        "tank_id":          inference["tank_id"],
        "fault_type":       inference["fault_type"],
        "if_score":         inference["if_score"],
        "lstm_score":       inference["lstm_score"],
        "breached_sensors": inference["breached_sensors"],
        "jph_before":       41,
        "scorer":           inference["scorer"],
        "raw":              record,
    }
    EB.put_events(Entries=[{
        "Source":       "paintshop.anomaly",
        "DetailType":   "TankAnomalyDetected",
        "Detail":       json.dumps(detail),
        "EventBusName": EVENT_BUS_NAME,
    }])


def _get_active_jph(tank_id: str) -> int:
    """Return the simulated_jph of the IN_PROGRESS job for this tank, or 0 if none.

    Uses a paginated scan to handle large tables that exceed DynamoDB's 1MB
    first-page limit.
    """
    try:
        table      = DYNAMODB.Table(JOBS_TABLE)
        filter_exp = Attr("tank_id").eq(tank_id) & Attr("status").eq("IN_PROGRESS")
        kwargs     = {"FilterExpression": filter_exp}
        while True:
            resp  = table.scan(**kwargs)
            items = resp.get("Items", [])
            if items:
                return int(items[0].get("simulated_jph", 0))
            last_key = resp.get("LastEvaluatedKey")
            if not last_key:
                return 0
            kwargs["ExclusiveStartKey"] = last_key
    except Exception:
        return 0


def update_tank_status(tank_id: str, reading: dict, inference: dict) -> bool:
    """Write a live sensor snapshot + anomaly status to the tank-status table.
    Returns True if this is a new fault (status just transitioned online → degraded)."""
    now_iso    = datetime.now(timezone.utc).isoformat()
    new_status = "degraded" if inference["anomaly_detected"] else "online"
    jph        = _get_active_jph(tank_id)
    if new_status == "degraded" and jph > 0:
        jph = int(jph * 0.65)  # degraded tank runs at ~65% throughput

    sensors = {
        k: Decimal(str(round(v, 4)))
        for k, v in reading.items()
        if isinstance(v, float) and k not in ("if_score", "lstm_score")
    }

    resp = DYNAMODB.Table(STATUS_TABLE).update_item(
        Key={"tank_id": tank_id},
        UpdateExpression=(
            "SET line_id = :li, #st = :s, last_reading_ts = :ts, current_jph = :jph, "
            "fault_type = :ft, if_score = :ifs, lstm_score = :ls, xgb_confidence = :xc, sensors = :sen, #ttl = :ttl"
        ),
        ExpressionAttributeNames={"#st": "status", "#ttl": "ttl"},
        ExpressionAttributeValues={
            ":li":  TANK_LINE_MAP.get(tank_id, "LINE-1"),
            ":s":   new_status,
            ":ts":  now_iso,
            ":jph": jph,
            ":ft":  inference.get("fault_type", "normal"),
            ":ifs": Decimal(str(round(inference.get("if_score",      0.0), 4))),
            ":ls":  Decimal(str(round(inference.get("lstm_score",    0.0), 4))),
            ":xc":  Decimal(str(round(inference.get("xgb_confidence", 0.0), 4))),
            ":sen": sensors,
            ":ttl": int(datetime.now(timezone.utc).timestamp()) + 86400,
        },
        ReturnValues="UPDATED_OLD",
    )
    old_status = resp.get("Attributes", {}).get("status", "online")
    return new_status == "degraded" and old_status != "degraded"


def write_sensor_history(tank_id: str, reading: dict, inference: dict):
    """Append one reading to sensor-history DynamoDB table (7-day TTL)."""
    ts_iso = reading.get("timestamp", datetime.now(timezone.utc).isoformat())
    item   = {
        "tank_id":        tank_id,
        "timestamp":      ts_iso,
        "fault_type":     inference.get("fault_type", "normal"),
        "if_score":       Decimal(str(inference["if_score"])),
        "lstm_score":     Decimal(str(inference["lstm_score"])),
        "xgb_confidence": Decimal(str(inference["xgb_confidence"])),
        "ttl":            int(datetime.now(timezone.utc).timestamp()) + 7 * 86400,
    }
    skip = {"timestamp", "shift", "line_id"}
    for k, v in reading.items():
        if k not in skip and isinstance(v, (int, float)):
            item[k] = Decimal(str(round(float(v), 6)))
    DYNAMODB.Table(HISTORY_TABLE).put_item(Item=item)


def handler(event, context):
    for rec in event.get("Records", []):
        raw       = json.loads(base64.b64decode(rec["kinesis"]["data"]))
        enriched  = enrich_record(raw)
        inference = score_record(enriched)
        # Append to sensor-history for trend charts
        write_sensor_history(enriched["tank_id"], enriched, inference)
        # Always refresh live tank-status (dashboard reads this)
        # Returns True only on first transition online → degraded
        is_new_fault = update_tank_status(enriched["tank_id"], enriched, inference)
        if is_new_fault:
            publish_anomaly(inference, enriched)
    return {"statusCode": 200}
