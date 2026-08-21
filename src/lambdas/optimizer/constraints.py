# Functional equivalence groups — only tanks within the same group can substitute.
# Tanks absent from all groups are unique; their jobs must be held for repair.
_EQUIVALENCE_GROUPS = [
    {"PT-01", "PT-02"},           # Alkaline cleaners
    {"PT-03", "PT-04", "PT-07"},  # Rinse tanks (cascade + post-rinse)
    {"ED-02", "ED-03", "ED-04"},  # ED rinse tanks (UF + DI)
]


def _substitute_tanks(tank_offline: str) -> set:
    """Return tank IDs that can functionally substitute for tank_offline."""
    for group in _EQUIVALENCE_GROUPS:
        if tank_offline in group:
            return group - {tank_offline}
    return set()  # unique tank — no substitutes available


def optimize_schedule(tank_offline: str, queued_jobs: list,
                      available_lines: list, targets: dict) -> dict:
    substitutes = _substitute_tanks(tank_offline)

    # If no substitutes exist, hold all jobs regardless of status
    if not substitutes:
        assignments = []
        for job in queued_jobs:
            entry = {"job_id": job["job_id"], "action": "hold_for_inspection", "new_tank": None}
            if "scheduled_time" in job:
                entry["scheduled_time"] = job["scheduled_time"]
            assignments.append(entry)
        return {
            "assignments":      assignments,
            "projected_jph":    targets.get("target_jph", 45),
            "fbo_delay_mins":   targets.get("fbo_target_mins", 30),
            "held_count":       len(queued_jobs),
            "rerouted_count":   0,
            "mttr_budget_mins": 42,
            "score":            0.0,
            "summary":          f"{tank_offline} performs a unique process — no substitute available. "
                                f"{len(queued_jobs)} job(s) held pending repair.",
        }

    # 1. Classify by job status:
    #    IN_PROGRESS → car is physically inside the tank, cannot be moved
    #    QUEUED      → car is waiting to enter, can be rerouted to a substitute tank
    can_reroute = [j for j in queued_jobs if j.get("status") != "IN_PROGRESS"]
    must_hold   = [j for j in queued_jobs if j.get("status") == "IN_PROGRESS"]

    # 2. Filter available_lines to substitute tanks only, score by headroom
    candidate_lines = [
        l for l in available_lines
        if l.get("line_id", l.get("tank_id", "")) in substitutes
    ]
    if not candidate_lines:
        # Substitute tanks not present in available_lines — build defaults
        candidate_lines = [{"line_id": t, "capacity_jph": 50, "current_load": 0}
                           for t in substitutes]

    for line in candidate_lines:
        line["headroom"] = line.get("capacity_jph", 50) - line.get("current_load", 0)

    best_line = max(candidate_lines, key=lambda l: l["headroom"])

    # 3. Greedy assignment of reroutable (QUEUED) jobs
    assignments = []
    for job in can_reroute:
        entry = {
            "job_id":   job["job_id"],
            "action":   "reroute",
            "new_tank": best_line["line_id"],
        }
        if "scheduled_time" in job:
            entry["scheduled_time"] = job["scheduled_time"]
        assignments.append(entry)

    # 4. Hold IN_PROGRESS jobs for inspection — car stays in the faulting tank
    for job in must_hold:
        entry = {
            "job_id":   job["job_id"],
            "action":   "hold_for_inspection",
            "new_tank": None,
        }
        if "scheduled_time" in job:
            entry["scheduled_time"] = job["scheduled_time"]
        assignments.append(entry)

    # 5. Projected JPH: average simulated_jph of rerouted jobs absorbed by the receiving line
    avg_job_jph       = (sum(j.get("simulated_jph", 45) for j in can_reroute) / len(can_reroute)) if can_reroute else 45.0
    headroom          = max(0.0, best_line["capacity_jph"] - best_line["current_load"])
    actually_absorbed = min(len(can_reroute), int(headroom / max(avg_job_jph / 10, 1)))
    capacity_blocked  = max(0, len(can_reroute) - actually_absorbed)
    total_blocked     = len(must_hold) + capacity_blocked

    projected_jph = round(min(best_line["current_load"] + avg_job_jph, best_line["capacity_jph"]), 1)

    dest_name = best_line.get("line_id", best_line.get("tank_id", ""))
    result = {
        "assignments":      assignments,
        "projected_jph":    projected_jph,
        "fbo_delay_mins":   max(0, (total_blocked * 5) - 10),
        "held_count":       len(must_hold),
        "rerouted_count":   len(can_reroute),
        "mttr_budget_mins": 42,
        "summary":          f"Rescheduled {len(can_reroute)} job(s) from {tank_offline} to {dest_name}. "
                            f"{len(must_hold)} IN_PROGRESS job(s) held for inspection.",
    }
    result["score"] = score_schedule(result, targets)
    return result


def score_schedule(result: dict, targets: dict) -> float:
    jph_score  = min(1.0, result["projected_jph"] / 60.0)
    fbo_target = targets.get("fbo_target_mins", 20)
    fbo_score  = max(0.0, 1.0 - (result["fbo_delay_mins"] / max(fbo_target * 2, 1)))
    mttr_score = max(0.0, 1.0 - (result["mttr_budget_mins"] / 90.0))
    return round(0.4 * jph_score + 0.4 * fbo_score + 0.2 * mttr_score, 4)
