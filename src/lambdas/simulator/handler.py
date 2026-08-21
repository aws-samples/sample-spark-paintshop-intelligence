import json
import os
import threading
import time
from datetime import datetime, timezone, timedelta
import boto3
from boto3.dynamodb.conditions import Attr
from tank_profiles import TANK_PROFILES, generate_reading

STREAM_NAME       = os.environ.get("STREAM_NAME",  "paintshop-tank-stream")
JOBS_TABLE        = os.environ.get("JOBS_TABLE",   "production-jobs")
DEMO_FAULTS_PARAM = "/paintshop/demo_faults"   # JSON: {tank_id: {fault_type, start_ts}}

# Emit 6 readings per Lambda invocation, 10 seconds apart → ~10s sensor cadence
READINGS_PER_INVOCATION = 6
READING_INTERVAL_SECS   = 10
DRIFT_DURATION_SECS     = 90   # sensors reach full fault values after 90 seconds

KINESIS  = boto3.client("kinesis")
SSM      = boto3.client("ssm")
dynamodb = boto3.resource("dynamodb")

TANK_IDS = list(TANK_PROFILES.keys())

_JOB_CFG = {
    "PT-01": {"job_type": "hot_pre_clean",     "duration_mins": 15, "body_count": 12, "jph": 48},
    "PT-02": {"job_type": "main_cleaning",      "duration_mins": 15, "body_count": 12, "jph": 48},
    "PT-03": {"job_type": "rinse_1",            "duration_mins": 10, "body_count":  8, "jph": 48},
    "PT-04": {"job_type": "rinse_2",            "duration_mins": 10, "body_count":  8, "jph": 48},
    "PT-05": {"job_type": "activation",         "duration_mins": 12, "body_count": 10, "jph": 50},
    "PT-06": {"job_type": "zinc_phosphate",     "duration_mins": 20, "body_count": 15, "jph": 45},
    "PT-07": {"job_type": "post_rinse",         "duration_mins": 10, "body_count":  8, "jph": 48},
    "PT-08": {"job_type": "nano_seal",          "duration_mins": 12, "body_count": 10, "jph": 50},
    "ED-01": {"job_type": "electrodeposition",  "duration_mins": 25, "body_count": 20, "jph": 48},
    "ED-02": {"job_type": "uf_rinse_1",         "duration_mins": 10, "body_count":  8, "jph": 48},
    "ED-03": {"job_type": "uf_rinse_2",         "duration_mins": 10, "body_count":  8, "jph": 48},
    "ED-04": {"job_type": "di_water_rinse",     "duration_mins":  8, "body_count":  6, "jph": 50},
}

_PRIORITY = {
    "PT-01": 1, "PT-02": 1,
    "PT-03": 2, "PT-04": 2,
    "PT-05": 3, "PT-06": 3,
    "PT-07": 4, "PT-08": 4,
    "ED-01": 5, "ED-02": 6, "ED-03": 6, "ED-04": 6,
}

LINE_MAP = {t: "LINE-1" for t in TANK_IDS}


# ── Job management ──────────────────────────────────────────────────────────

def _make_job(tank_id: str, seq: int, start: datetime, status: str = "QUEUED") -> dict:
    cfg = _JOB_CFG[tank_id]
    end = start + timedelta(minutes=cfg["duration_mins"])
    job = {
        "job_id":          f"{tank_id}-J{seq:04d}",
        "scheduled_time":  start.isoformat(),
        "tank_id":         tank_id,
        "line_id":         LINE_MAP[tank_id],
        "job_type":        cfg["job_type"],
        "body_count":      cfg["body_count"],
        "priority":        _PRIORITY.get(tank_id, 5),
        "status":          status,
        "scheduled_start": start.isoformat(),
        "scheduled_end":   end.isoformat(),
        "actual_start":    None,
        "simulated_jph":   cfg["jph"],
        "version":         1,
        "ttl":             int((end + timedelta(hours=24)).timestamp()),
    }
    if status == "IN_PROGRESS":
        job["actual_start"] = start.isoformat()
    return job


def _advance_jobs():
    """Complete overdue jobs and promote next QUEUED job per tank.
    Jobs completing on a degraded tank are marked HOLD_FOR_INSPECTION."""
    table   = dynamodb.Table(JOBS_TABLE)
    now_iso = datetime.now(timezone.utc).isoformat()

    # Fetch degraded tanks once — IN_PROGRESS jobs on these need inspection
    degraded_tanks = {
        item["tank_id"]
        for item in dynamodb.Table("tank-status").scan(
            FilterExpression=Attr("status").eq("degraded")
        ).get("Items", [])
    }

    # Expire stale QUEUED jobs — these accumulate when the simulator is offline
    stale_queued = table.scan(
        FilterExpression=Attr("status").eq("QUEUED") & Attr("scheduled_end").lt(now_iso)
    ).get("Items", [])
    for job in stale_queued:
        table.update_item(
            Key={"job_id": job["job_id"], "scheduled_time": job["scheduled_time"]},
            UpdateExpression="SET #s = :c, completed_at = :t",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":c": "COMPLETED", ":t": now_iso},
        )

    all_in_progress = table.scan(
        FilterExpression=Attr("status").eq("IN_PROGRESS")
    ).get("Items", [])

    # Deduplicate by job_id — pick the record with the latest scheduled_time
    seen_ip: dict = {}
    for job in all_in_progress:
        jid = job.get("job_id")
        if jid not in seen_ip or job.get("scheduled_time","") > seen_ip[jid].get("scheduled_time",""):
            seen_ip[jid] = job
    in_progress = list(seen_ip.values())

    # Tanks that currently have an IN_PROGRESS job
    tanks_with_in_progress = {job["tank_id"] for job in in_progress}

    for job in in_progress:
        if job.get("scheduled_end", "") > now_iso:
            continue
        final_status = (
            "HOLD_FOR_INSPECTION"
            if job.get("tank_id") in degraded_tanks
            else "COMPLETED"
        )
        table.update_item(
            Key={"job_id": job["job_id"], "scheduled_time": job["scheduled_time"]},
            UpdateExpression="SET #s = :c, completed_at = :t",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":c": final_status, ":t": now_iso},
        )
        tanks_with_in_progress.discard(job["tank_id"])
        queued = table.scan(
            FilterExpression=Attr("tank_id").eq(job["tank_id"]) & Attr("status").eq("QUEUED")
        ).get("Items", [])
        if queued:
            nxt = sorted(queued, key=lambda x: x.get("scheduled_start", ""))[0]
            table.update_item(
                Key={"job_id": nxt["job_id"], "scheduled_time": nxt["scheduled_time"]},
                UpdateExpression="SET #s = :ip, actual_start = :t",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":ip": "IN_PROGRESS", ":t": now_iso},
            )
            tanks_with_in_progress.add(job["tank_id"])

    # Promote earliest QUEUED job for any tank that has no IN_PROGRESS
    for tank_id in TANK_IDS:
        if tank_id in tanks_with_in_progress:
            continue
        queued = table.scan(
            FilterExpression=Attr("tank_id").eq(tank_id) & Attr("status").eq("QUEUED")
        ).get("Items", [])
        if queued:
            nxt = sorted(queued, key=lambda x: x.get("scheduled_start", ""))[0]
            table.update_item(
                Key={"job_id": nxt["job_id"], "scheduled_time": nxt["scheduled_time"]},
                UpdateExpression="SET #s = :ip, actual_start = :t",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":ip": "IN_PROGRESS", ":t": now_iso},
            )


def _maintain_job_pipeline():
    """Keep at least 10 active jobs per tank (1 IN_PROGRESS + 9 QUEUED).
    Degraded tanks are skipped — no new jobs assigned until tank recovers."""
    table = dynamodb.Table(JOBS_TABLE)

    # Fetch degraded tanks so we don't queue new work to faulty tanks
    degraded_tanks = {
        item["tank_id"]
        for item in dynamodb.Table("tank-status").scan(
            FilterExpression=Attr("status").eq("degraded")
        ).get("Items", [])
    }

    # Paginate fully — unpaginated scan only returns first ~400 items, causing
    # the pipeline to undercount active jobs and create duplicates indefinitely
    active_items = []
    scan_kwargs: dict = {"FilterExpression": Attr("status").is_in(["IN_PROGRESS", "QUEUED"])}
    while True:
        resp = table.scan(**scan_kwargs)
        active_items.extend(resp.get("Items", []))
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        scan_kwargs["ExclusiveStartKey"] = last

    # Deduplicate by job_id — keep record with latest scheduled_time
    seen: dict = {}
    for job in active_items:
        jid = job.get("job_id")
        if jid not in seen or job.get("scheduled_time", "") > seen[jid].get("scheduled_time", ""):
            seen[jid] = job

    by_tank: dict = {t: [] for t in TANK_IDS}
    for job in seen.values():
        tid = job.get("tank_id")
        if tid in by_tank:
            by_tank[tid].append(job)

    now   = datetime.now(timezone.utc)
    items = []
    for tank_id, jobs in by_tank.items():
        if tank_id in degraded_tanks:
            continue  # don't queue new work to a degraded tank
        needed = 10 - len(jobs)
        if needed <= 0:
            continue

        dur = _JOB_CFG[tank_id]["duration_mins"]
        if jobs:
            latest_end = max(
                datetime.fromisoformat(j.get("scheduled_end", now.isoformat()))
                for j in jobs
            )
        else:
            latest_end = now  # no existing jobs — start fresh from now

        existing_seqs = set()
        for j in jobs:
            try:
                existing_seqs.add(int(j.get("job_id", "").split("-J")[-1]))
            except ValueError:
                pass
        seq = max(existing_seqs, default=0) + 1

        first_status = "IN_PROGRESS" if not jobs else "QUEUED"
        prev_end = latest_end
        for n in range(needed):
            status = first_status if n == 0 else "QUEUED"
            job    = _make_job(tank_id, seq + n, prev_end, status=status)
            prev_end = datetime.fromisoformat(job["scheduled_end"])
            items.append(job)

    if items:
        with dynamodb.Table(JOBS_TABLE).batch_writer() as batch:
            for item in items:
                batch.put_item(Item=item)


# ── Sensor reading ──────────────────────────────────────────────────────────

def put_reading(tank_id: str, fault: str = None, drift_factor: float = 1.0):
    reading = generate_reading(tank_id, fault=fault, drift_factor=drift_factor)
    KINESIS.put_record(
        StreamName=STREAM_NAME,
        Data=json.dumps(reading).encode("utf-8"),
        PartitionKey=tank_id,
    )


# ── Demo fault helpers ──────────────────────────────────────────────────────

def _get_active_faults() -> dict:
    """Return {tank_id: {fault_type, start_ts}} from SSM, or {} if none armed."""
    try:
        val = SSM.get_parameter(Name=DEMO_FAULTS_PARAM)["Parameter"]["Value"]
        return json.loads(val)
    except SSM.exceptions.ParameterNotFound:
        return {}
    except Exception:
        return {}


def _compute_drift_factor(start_ts: str) -> float:
    """0.0 = normal readings → 1.0 = full fault values after DRIFT_DURATION_SECS."""
    try:
        start   = datetime.fromisoformat(start_ts)
        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        return min(1.0, elapsed / DRIFT_DURATION_SECS)
    except Exception:
        return 1.0


def _emit_one_cycle(active_faults: dict):
    """Send one reading per tank to Kinesis in parallel.
    Faulted tanks drift gradually; all others send clean normal readings."""
    threads = []
    for tank_id in TANK_IDS:
        fault_info = active_faults.get(tank_id)
        if fault_info:
            drift = _compute_drift_factor(fault_info["start_ts"])
            t = threading.Thread(
                target=put_reading,
                kwargs={"tank_id": tank_id, "fault": fault_info["fault_type"],
                        "drift_factor": drift},
            )
        else:
            t = threading.Thread(target=put_reading, kwargs={"tank_id": tank_id})
        threads.append(t)
        t.start()
    for t in threads:
        t.join()


# ── Handler ─────────────────────────────────────────────────────────────────

def handler(event, context):
    # Job management once per invocation
    _advance_jobs()
    _maintain_job_pipeline()

    # Read current fault state once; reuse across all cycles this invocation
    active_faults = _get_active_faults()

    # Emit READINGS_PER_INVOCATION batches spaced READING_INTERVAL_SECS apart
    for i in range(READINGS_PER_INVOCATION):
        _emit_one_cycle(active_faults)
        if i < READINGS_PER_INVOCATION - 1:
            # Intentional pacing: one simulated sensor reading every ten seconds.
            time.sleep(READING_INTERVAL_SECS)  # nosemgrep: arbitrary-sleep

    return {"statusCode": 200, "tanks_simulated": len(TANK_IDS),
            "active_faults": list(active_faults.keys()),
            "readings_per_invocation": READINGS_PER_INVOCATION}
