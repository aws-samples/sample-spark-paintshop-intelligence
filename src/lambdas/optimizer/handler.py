import json
from constraints import optimize_schedule


def handler(event, context):
    tank_offline    = event["tank_offline"]
    queued_jobs     = event.get("queued_jobs") or event.get("jobs", [])
    available_lines = event.get("available_lines") or event.get("available_tanks", [])
    targets         = event.get("targets") or {
        "target_jph":      event.get("target_jph",      45),
        "fbo_target_mins": event.get("fbo_target_mins", 20),
    }
    result = optimize_schedule(tank_offline, queued_jobs, available_lines, targets)
    return {"statusCode": 200, "body": json.dumps(result)}
