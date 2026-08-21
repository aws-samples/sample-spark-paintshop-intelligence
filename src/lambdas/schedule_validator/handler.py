import json, os

MIN_JPH = int(os.environ.get("MIN_JPH", "45"))


def validate_recommendation(recommendation: dict, min_jph: int = None) -> dict:
    if min_jph is None:
        min_jph = MIN_JPH

    jph = recommendation.get("projected_jph", 0)
    if jph < min_jph:
        return {"valid": False, "reason": f"JPH {jph} below floor {min_jph}"}

    offline_tanks = set(recommendation.get("offline_tanks", []))
    raw_assignments = recommendation.get("assignments", [])
    assignments_list = list(raw_assignments.values() if isinstance(raw_assignments, dict) else raw_assignments)
    for assignment in assignments_list:
        if not isinstance(assignment, dict):
            continue
        if assignment.get("action") != "reroute":
            continue
        for req_tank in assignment.get("required_tanks", []):
            if req_tank in offline_tanks:
                return {"valid": False,
                        "reason": f"Job {assignment['job_id']} routed through offline tank {req_tank}"}

    return {"valid": True, "reason": "ok"}


def handler(event, context):
    recommendation = event.get("recommendation", {})
    result = validate_recommendation(recommendation)
    if not result["valid"]:
        # Fallback: apply rule-based schedule (hold all jobs, minimum safe JPH)
        return {
            "statusCode": 200,
            "valid": False,
            "fallback": True,
            "reason": result["reason"],
            "safe_recommendation": {
                "projected_jph":  MIN_JPH,
                "assignments":    [],
                "fbo_delay_mins": 50,
                "score": 0.3,
            }
        }
    return {"statusCode": 200, "valid": True, "recommendation": recommendation}
