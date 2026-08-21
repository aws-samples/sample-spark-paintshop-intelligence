"""Demo trigger — injects a sustained fault for PT-06 to show full pipeline.

Usage:
  python scripts/demo_trigger.py              # trigger PT-06 acid_drift
  python scripts/demo_trigger.py --reset      # restore PT-06 to online
"""
import json, sys, argparse, boto3
from datetime import datetime, timezone, timedelta
from decimal import Decimal

REGION   = "us-east-1"
TANK_ID  = "PT-06"
FAULT    = "acid_drift"
LINE_ID  = "LINE-1"

eb       = boto3.client("events",   region_name=REGION)
dynamodb = boto3.resource("dynamodb", region_name=REGION)


def trigger_fault():
    now = datetime.now(timezone.utc).isoformat()

    # 1. Write degraded status directly to DynamoDB (visible on dashboard immediately)
    dynamodb.Table("tank-status").put_item(Item={
        "tank_id":          TANK_ID,
        "line_id":          LINE_ID,
        "status":           "degraded",
        "fault_type":       FAULT,
        "last_reading_ts":  now,
        "current_jph":      Decimal("0"),
        "if_score":         Decimal("0.95"),
        "lstm_score":       Decimal("0.98"),
        "sensors": {
            "free_acid_pts":     Decimal("2.1"),
            "total_acid_pts":    Decimal("28.4"),
            "zinc_g_per_l":      Decimal("0.6"),
            "conductivity_us_cm":Decimal("5200"),
            "temperature_c":     Decimal("47"),
        },
        "ttl": int(datetime.now(timezone.utc).timestamp()) + 86400,
    })
    print(f"✓ tank-status: {TANK_ID} → degraded ({FAULT})")

    # 2. Seed fresh QUEUED jobs for PT-06 (so MPS has work to reschedule)
    table = dynamodb.Table("production-jobs")
    for i, (status, offset) in enumerate([("IN_PROGRESS",0),("QUEUED",20),("QUEUED",40)], 1):
        start = datetime.now(timezone.utc) + timedelta(minutes=offset)
        item  = {
            "job_id":          f"PT-06-LIVE-{i:03d}",
            "scheduled_time":  start.isoformat(),
            "tank_id":         TANK_ID,
            "line_id":         LINE_ID,
            "job_type":        "zinc_phosphate",
            "body_count":      Decimal("15"),
            "priority":        Decimal("3"),
            "status":          status,
            "scheduled_start": start.isoformat(),
            "scheduled_end":   (start + timedelta(minutes=20)).isoformat(),
            "simulated_jph":   Decimal("45"),
            "version":         Decimal("1"),
        }
        if status == "IN_PROGRESS":
            item["actual_start"] = start.isoformat()
        table.put_item(Item=item)
    print(f"✓ production-jobs: 3 PT-06 jobs seeded (1 IN_PROGRESS + 2 QUEUED)")

    # 3. Fire EventBridge event → triggers SFN + ws-broadcast ANOMALY_ALERT
    eb.put_events(Entries=[{
        "Source":       "paintshop.anomaly",
        "DetailType":   "TankAnomalyDetected",
        "EventBusName": "default",
        "Time":         datetime.now(timezone.utc),
        "Detail": json.dumps({
            "tank_id":          TANK_ID,
            "fault_type":       FAULT,
            "if_score":         0.95,
            "lstm_score":       0.98,
            "breached_sensors": [
                {"sensor":"free_acid_pts","value":2.1,"direction":"high","range":[0.5,1.5]},
                {"sensor":"zinc_g_per_l","value":0.6,"direction":"low","range":[1.0,1.8]},
            ],
            "jph_before":       45,
            "scorer":           "demo_trigger",
        }),
    }])
    print(f"✓ EventBridge: TankAnomalyDetected fired → SFN + ws-broadcast triggered")
    print(f"\n→ Open dashboard: PT-06 should show DEGRADED with acid_drift fault")
    print(f"→ Anomaly Feed will show the alert")
    print(f"→ SFN is executing MPS + RCA agents (~30s)")


def reset():
    dynamodb.Table("tank-status").update_item(
        Key={"tank_id": TANK_ID},
        UpdateExpression="SET #s = :o, fault_type = :n",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":o": "online", ":n": "normal"},
    )
    print(f"✓ {TANK_ID} reset to online")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    reset() if args.reset else trigger_fault()
