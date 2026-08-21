import json, os, uuid
from datetime import datetime, timezone
import boto3

DYNAMODB      = boto3.resource("dynamodb")
JOBS_TABLE    = os.environ.get("JOBS_TABLE",    "production-jobs")
STATUS_TABLE  = os.environ.get("STATUS_TABLE",  "tank-status")
HISTORY_TABLE = os.environ.get("HISTORY_TABLE", "schedule-history")


def handler(event, context):
    recommendation = event["recommendation"]
    trigger        = event["trigger"]
    raw            = recommendation.get("assignments", [])
    # Normalise: agent may return dict {tank_id: [job_ids]} or list [{job_id, action, ...}]
    if isinstance(raw, dict):
        assignments = [{"job_id": jid, "action": "reroute", "new_tank": tank}
                       for tank, jobs in raw.items() for jid in (jobs if isinstance(jobs, list) else [jobs])]
    else:
        assignments = [a for a in raw if isinstance(a, dict)]

    # Build TransactWrite items
    transact_items = []

    # Update job statuses — only when scheduled_time (sort key) is present
    for assignment in assignments:
        scheduled_time = assignment.get("scheduled_time")
        if not scheduled_time:
            continue  # can't update without composite key; agent tool handles this separately
        action = assignment.get("action", "reroute")
        status = {"reroute": "rescheduled", "hold_for_repair": "on_hold",
                  "defer_to_next_shift": "rescheduled"}.get(action, "queued")
        dest = assignment.get("to_line") or assignment.get("new_tank") or "HOLD"
        transact_items.append({
            "Update": {
                "TableName": JOBS_TABLE,
                "Key": {"job_id": {"S": assignment["job_id"]},
                        "scheduled_time": {"S": scheduled_time}},
                "UpdateExpression": "SET #s = :s, line_id = :l",
                "ExpressionAttributeNames": {"#s": "status"},
                "ExpressionAttributeValues": {
                    ":s": {"S": status},
                    ":l": {"S": dest},
                }
            }
        })

    # Update tank-status
    transact_items.append({
        "Put": {
            "TableName": STATUS_TABLE,
            "Item": {
                "tank_id":             {"S": trigger["tank_id"]},
                "status":              {"S": "degraded"},
                "last_anomaly_type":   {"S": trigger.get("fault_type", "unknown")},
                "anomaly_detected_at": {"S": datetime.now(timezone.utc).isoformat()},
            }
        }
    })

    # Write schedule-history audit record
    decision_id = str(uuid.uuid4())
    now_iso     = datetime.now(timezone.utc).isoformat()
    history_item = {
        "decision_id":         {"S": decision_id},
        "timestamp":           {"S": now_iso},
        "trigger_tank":        {"S": trigger["tank_id"]},
        "fault_type":          {"S": trigger.get("fault_type", "unknown")},
        "affected_jobs":       {"N": str(len(assignments))},
        "jph_before":          {"N": str(trigger.get("jph_before", 41))},
        "jph_after":           {"N": str(recommendation.get("projected_jph", 45))},
        "fbo_delay_mins":      {"N": str(recommendation.get("fbo_delay_mins", 50))},
        "recommendation_text": {"S": recommendation.get("summary", "")},
        "applied_by":          {"S": "agent"},
    }
    transact_items.append({"Put": {"TableName": HISTORY_TABLE, "Item": history_item}})

    # Execute atomic TransactWrite
    client = boto3.client("dynamodb")
    client.transact_write_items(TransactItems=transact_items)

    return {"statusCode": 200, "decision_id": decision_id}
