"""Neptune Query Lambda — Gremlin queries against the static knowledge graph.

Actions:
  seed_graph             — idempotently seed static knowledge graph
  get_fault_context      — FaultType + SOP + causal chain for a tank+fault_type
  get_maintenance_history — last 5 maintenance records for a tank
"""
import http.client
import json
import os
import random
import re
import ssl
from threading import Event

NEPTUNE_ENDPOINT = os.environ.get("NEPTUNE_ENDPOINT", "")
NEPTUNE_PORT     = os.environ.get("NEPTUNE_PORT", "8182")
_NEPTUNE_HOST_RE = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"neptune\.amazonaws\.com(?:\.cn)?$"
)


# ── Gremlin HTTP helper ────────────────────────────────────────────────────

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


def _gremlin(query: str) -> list:
    endpoint, port = _validated_neptune_target()
    tls_context = ssl.create_default_context()
    payload = json.dumps({"gremlin": query}).encode()
    retryable_codes = {
        "ConcurrentModificationException",
        "MemoryLimitExceededException",
    }
    max_attempts = 8

    for attempt in range(1, max_attempts + 1):
        # HTTPSConnection validates the certificate and hostname and does not
        # follow redirects, keeping requests pinned to the configured cluster.
        connection = http.client.HTTPSConnection(
            endpoint, port=port, timeout=30, context=tls_context
        )
        try:
            connection.request(
                "POST",
                "/gremlin",
                body=payload,
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            status = response.status
            raw_body = response.read().decode("utf-8")
        finally:
            connection.close()

        if 200 <= status < 300:
            body = json.loads(raw_body)
            return body.get("result", {}).get("data", {}).get("@value", [])

        try:
            error_code = json.loads(raw_body).get("code", "")
        except json.JSONDecodeError:
            error_code = ""

        if error_code not in retryable_codes or attempt == max_attempts:
            raise RuntimeError(f"Gremlin {status}: {raw_body}")

        # Neptune memory pressure needs a meaningful cooldown; sub-second
        # retries amplify contention while a Serverless cluster is scaling.
        base_delay = min(30.0, float(2 ** (attempt - 1)))
        if error_code == "MemoryLimitExceededException":
            base_delay = max(5.0, base_delay)
        delay = random.uniform(base_delay / 2, base_delay)
        print(
            f"Retryable Neptune error {error_code}; retrying in {delay:.2f}s "
            f"(attempt {attempt}/{max_attempts})"
        )
        Event().wait(delay)

    raise RuntimeError("Gremlin retry loop exhausted unexpectedly")


def _esc(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace("'", "\\'")


# ── Static knowledge graph data ────────────────────────────────────────────

LINES = [
    {"line_id": "LINE-A", "name": "Pre-Treatment", "capacity_jph": 60, "status": "operational"},
    {"line_id": "LINE-B", "name": "E-Coat",         "capacity_jph": 55, "status": "operational"},
]

TANKS = [
    # Pre-Treatment
    {"tank_id": "PT-01", "name": "Hot Pre-Clean",       "tank_type": "PT", "line_id": "LINE-A",
     "sequence_order": 1, "normal_ranges": "Temp 50-60C, pH 11-12"},
    {"tank_id": "PT-02", "name": "Main Cleaner",         "tank_type": "PT", "line_id": "LINE-A",
     "sequence_order": 2, "normal_ranges": "Temp 55-65C, pH 11.5-12.5"},
    {"tank_id": "PT-03", "name": "Rinse 1 (cascade)",    "tank_type": "PT", "line_id": "LINE-A",
     "sequence_order": 3, "normal_ranges": "Conductivity <100 uS/cm"},
    {"tank_id": "PT-04", "name": "Rinse 2 (cascade)",    "tank_type": "PT", "line_id": "LINE-A",
     "sequence_order": 4, "normal_ranges": "Conductivity <100 uS/cm"},
    {"tank_id": "PT-05", "name": "Activation",           "tank_type": "PT", "line_id": "LINE-A",
     "sequence_order": 5, "normal_ranges": "pH 8.5-9.5, Temp 25-35C"},
    {"tank_id": "PT-06", "name": "Zinc Phosphate",       "tank_type": "PT", "line_id": "LINE-A",
     "sequence_order": 6, "normal_ranges": "Temp 40-50C, Free acid 0.5-1.5 pts, Zinc 1.0-1.8 g/L"},
    {"tank_id": "PT-07", "name": "Post-Rinse",           "tank_type": "PT", "line_id": "LINE-A",
     "sequence_order": 7, "normal_ranges": "Conductivity <200 uS/cm"},
    {"tank_id": "PT-08", "name": "Nano-Seal/Passivation","tank_type": "PT", "line_id": "LINE-A",
     "sequence_order": 8, "normal_ranges": "pH 4-5, Temp 25-35C"},
    # E-Coat
    {"tank_id": "ED-01", "name": "E-Coat Bath",          "tank_type": "ED", "line_id": "LINE-B",
     "sequence_order": 1, "normal_ranges": "pH 5.8-6.2, Temp 28-32C, Solids 18-22%"},
    {"tank_id": "ED-02", "name": "UF Rinse 1",           "tank_type": "ED", "line_id": "LINE-B",
     "sequence_order": 2, "normal_ranges": "Conductivity 500-2000 uS/cm"},
    {"tank_id": "ED-03", "name": "UF Rinse 2",           "tank_type": "ED", "line_id": "LINE-B",
     "sequence_order": 3, "normal_ranges": "Conductivity 200-800 uS/cm"},
    {"tank_id": "ED-04", "name": "DI Water Final Rinse", "tank_type": "ED", "line_id": "LINE-B",
     "sequence_order": 4, "normal_ranges": "Conductivity <20 uS/cm"},
]

# (from_tank, to_tank) process sequence
FEEDS_INTO = [
    ("PT-01","PT-02"),("PT-02","PT-03"),("PT-03","PT-04"),("PT-04","PT-05"),
    ("PT-05","PT-06"),("PT-06","PT-07"),("PT-07","PT-08"),("PT-08","ED-01"),
    ("ED-01","ED-02"),("ED-02","ED-03"),("ED-03","ED-04"),
]

# fault_id, tank_id, severity_level, affected_sensors, avg_detection_mins, avg_resolution_mins
FAULT_TYPES = [
    ("pt-01.alkalinity_depletion",  "PT-01","MEDIUM","free_alkalinity,pH",35,55),
    ("pt-02.alkalinity_depletion",  "PT-02","MEDIUM","free_alkalinity,total_alkalinity",38,50),
    ("pt-02.temperature_high",      "PT-02","HIGH",  "temperature_c",20,40),
    ("pt-03.rinse_contamination",   "PT-03","HIGH",  "conductivity,pH,rinse_flow",25,35),
    ("pt-04.rinse_contamination",   "PT-04","HIGH",  "conductivity,pH,rinse_flow",25,35),
    ("pt-05.ph_high",               "PT-05","MEDIUM","pH,temperature_c",30,45),
    ("pt-05.titanium_depletion",    "PT-05","HIGH",  "pH,titanium_ppm",40,60),
    ("pt-06.acid_drift",            "PT-06","HIGH",  "free_acid_pts,total_acid_pts,conductivity_us_cm",47,42),
    ("pt-06.zinc_depletion",        "PT-06","HIGH",  "zinc_g_per_l,free_acid_pts",52,50),
    ("pt-06.accelerator_depletion", "PT-06","MEDIUM","accelerator_pts,free_acid_pts",55,45),
    ("pt-06.total_acid_rise",       "PT-06","HIGH",  "total_acid_pts,free_acid_pts",40,55),
    ("pt-06.conductivity_spike",    "PT-06","HIGH",  "conductivity_us_cm",15,30),
    ("pt-06.temperature_deviation", "PT-06","MEDIUM","temperature_c",20,35),
    ("pt-07.flow_drop",             "PT-07","MEDIUM","rinse_flow,conductivity",25,40),
    ("pt-07.rinse_contamination",   "PT-07","HIGH",  "conductivity,pH,rinse_flow",25,35),
    ("pt-08.concentration_low",     "PT-08","MEDIUM","concentration_pct,pH",45,50),
    ("pt-08.passivation_failure",   "PT-08","CRITICAL","pH,temperature_c",30,90),
    ("pt-08.ph_drift",              "PT-08","HIGH",  "pH,concentration_pct",35,45),
    ("ed-01.temperature_creep",     "ED-01","HIGH",  "temperature_c",60,45),
    ("ed-01.meq_acid_buildup",      "ED-01","HIGH",  "meq_acid,pH",50,60),
    ("ed-01.ph_drift",              "ED-01","HIGH",  "pH,conductivity_us_cm",45,50),
    ("ed-01.solids_depletion",      "ED-01","HIGH",  "solids_pct,conductivity_us_cm",55,65),
    ("ed-01.conductivity_rise",     "ED-01","HIGH",  "conductivity_us_cm,pH",35,40),
    ("ed-01.pigment_binder_drift",  "ED-01","CRITICAL","pigment_binder_ratio,solids_pct",70,120),
    ("ed-01.voltage_fluctuation",   "ED-01","CRITICAL","voltage_v",10,30),
    ("ed-02.membrane_fouling",      "ED-02","MEDIUM","conductivity,solids_pct",90,180),
    ("ed-02.solids_high",           "ED-02","MEDIUM","solids_pct,conductivity",60,90),
    ("ed-02.rinse_contamination",   "ED-02","HIGH",  "conductivity_us_cm,solids_pct",30,60),
    ("ed-03.membrane_fouling",      "ED-03","MEDIUM","conductivity,solids_pct",90,180),
    ("ed-03.rinse_contamination",   "ED-03","HIGH",  "conductivity_us_cm,solids_pct",30,55),
    ("ed-04.conductivity_spike",    "ED-04","HIGH",  "conductivity",20,45),
    ("ed-04.di_resin_exhaustion",   "ED-04","HIGH",  "conductivity",120,240),
    ("ed-04.rinse_contamination",   "ED-04","HIGH",  "conductivity_us_cm",25,50),
]

# (fault_id, caused_by_fault_id) — upstream causal chains
CAUSED_BY_EDGES = [
    ("pt-06.acid_drift",         "pt-06.zinc_depletion"),
    ("pt-06.acid_drift",         "pt-03.rinse_contamination"),
    ("pt-06.acid_drift",         "pt-04.rinse_contamination"),
    ("pt-06.zinc_depletion",     "pt-06.accelerator_depletion"),
    ("pt-06.total_acid_rise",    "pt-06.acid_drift"),
    ("pt-05.titanium_depletion", "pt-03.rinse_contamination"),
    ("pt-05.titanium_depletion", "pt-04.rinse_contamination"),
    ("pt-08.passivation_failure","pt-06.acid_drift"),
    ("pt-08.passivation_failure","pt-07.rinse_contamination"),
    ("ed-01.ph_drift",           "ed-01.temperature_creep"),
    ("ed-01.solids_depletion",   "ed-01.meq_acid_buildup"),
    ("ed-02.membrane_fouling",   "ed-01.conductivity_rise"),
    ("ed-03.membrane_fouling",   "ed-01.conductivity_rise"),
    ("ed-04.di_resin_exhaustion","ed-02.membrane_fouling"),
    # New 12-tank faults — causal chains
    ("pt-08.ph_drift",           "pt-07.rinse_contamination"),
    ("pt-08.ph_drift",           "pt-08.concentration_low"),
    ("ed-02.rinse_contamination","ed-01.conductivity_rise"),
    ("ed-03.rinse_contamination","ed-02.rinse_contamination"),
    ("ed-04.rinse_contamination","ed-03.rinse_contamination"),
]

# sop_id, fault_id, title, s3_doc_key, estimated_fix_mins, recommended_technician
SOPS = [
    ("SOP-PT01-001","pt-01.alkalinity_depletion","Alkalinity Depletion — PT-01","knowledge-base/sops/pt-01_alkalinity_depletion.md",55,"T-02"),
    ("SOP-PT02-001","pt-02.alkalinity_depletion","Alkalinity Depletion — PT-02","knowledge-base/sops/pt-02_alkalinity_depletion.md",50,"T-02"),
    ("SOP-PT02-002","pt-02.temperature_high",    "Temperature High — PT-02",    "knowledge-base/sops/pt-02_temperature_high.md",   40,"T-01"),
    ("SOP-PT03-001","pt-03.rinse_contamination", "Rinse Contamination — PT-03", "knowledge-base/sops/pt-03_rinse_contamination.md",35,"T-03"),
    ("SOP-PT04-001","pt-04.rinse_contamination", "Rinse Contamination — PT-04", "knowledge-base/sops/pt-04_rinse_contamination.md",35,"T-03"),
    ("SOP-PT05-001","pt-05.ph_high",             "pH High — PT-05",             "knowledge-base/sops/pt-05_ph_high.md",            45,"T-02"),
    ("SOP-PT05-002","pt-05.titanium_depletion",  "Titanium Depletion — PT-05",  "knowledge-base/sops/pt-05_titanium_depletion.md", 60,"T-04"),
    ("SOP-PT06-001","pt-06.acid_drift",          "Free Acid Drift — PT-06",     "knowledge-base/sops/pt-06_acid_drift.md",         42,"T-04"),
    ("SOP-PT06-002","pt-06.zinc_depletion",      "Zinc Depletion — PT-06",      "knowledge-base/sops/pt-06_zinc_depletion.md",     50,"T-04"),
    ("SOP-PT06-003","pt-06.accelerator_depletion","Accelerator Depletion — PT-06","knowledge-base/sops/pt-06_accelerator_depletion.md",45,"T-04"),
    ("SOP-PT06-004","pt-06.total_acid_rise",     "Total Acid Rise — PT-06",     "knowledge-base/sops/pt-06_total_acid_rise.md",    55,"T-04"),
    ("SOP-PT06-005","pt-06.conductivity_spike",  "Conductivity Spike — PT-06",  "knowledge-base/sops/pt-06_conductivity_spike.md", 30,"T-04"),
    ("SOP-PT06-006","pt-06.temperature_deviation","Temperature Deviation — PT-06","knowledge-base/sops/pt-06_temperature_deviation.md",35,"T-01"),
    ("SOP-PT07-001","pt-07.flow_drop",           "Flow Drop — PT-07",           "knowledge-base/sops/pt-07_flow_drop.md",          40,"T-03"),
    ("SOP-PT07-002","pt-07.rinse_contamination", "Rinse Contamination — PT-07", "knowledge-base/sops/pt-07_rinse_contamination.md",35,"T-03"),
    ("SOP-PT08-001","pt-08.concentration_low",   "Concentration Low — PT-08",   "knowledge-base/sops/pt-08_concentration_low.md",  50,"T-02"),
    ("SOP-PT08-002","pt-08.passivation_failure", "Passivation Failure — PT-08", "knowledge-base/sops/pt-08_passivation_failure.md",90,"T-04"),
    ("SOP-PT08-003","pt-08.ph_drift",            "pH Drift — PT-08",            "knowledge-base/sops/pt-08_ph_drift.md",           45,"T-02"),
    ("SOP-ED01-001","ed-01.temperature_creep",   "Temperature Creep — ED-01",   "knowledge-base/sops/ed-01_temperature_creep.md",  45,"T-01"),
    ("SOP-ED01-002","ed-01.meq_acid_buildup",    "MEQ Acid Buildup — ED-01",    "knowledge-base/sops/ed-01_meq_acid_buildup.md",   60,"T-04"),
    ("SOP-ED01-003","ed-01.ph_drift",            "pH Drift — ED-01",            "knowledge-base/sops/ed-01_ph_drift.md",           50,"T-04"),
    ("SOP-ED01-004","ed-01.solids_depletion",    "Solids Depletion — ED-01",    "knowledge-base/sops/ed-01_solids_depletion.md",   65,"T-04"),
    ("SOP-ED01-005","ed-01.conductivity_rise",   "Conductivity Rise — ED-01",   "knowledge-base/sops/ed-01_conductivity_rise.md",  40,"T-01"),
    ("SOP-ED01-006","ed-01.pigment_binder_drift","Pigment/Binder Drift — ED-01","knowledge-base/sops/ed-01_pigment_binder_drift.md",120,"T-04"),
    ("SOP-ED01-007","ed-01.voltage_fluctuation", "Voltage Fluctuation — ED-01", "knowledge-base/sops/ed-01_voltage_fluctuation.md",30,"T-05"),
    ("SOP-ED02-001","ed-02.membrane_fouling",    "Membrane Fouling — ED-02",    "knowledge-base/sops/ed-02_membrane_fouling.md",   180,"T-05"),
    ("SOP-ED02-002","ed-02.solids_high",         "Solids High — ED-02",         "knowledge-base/sops/ed-02_solids_high.md",        90,"T-05"),
    ("SOP-ED02-003","ed-02.rinse_contamination", "Rinse Contamination — ED-02", "knowledge-base/sops/ed-02_rinse_contamination.md",60,"T-05"),
    ("SOP-ED03-001","ed-03.membrane_fouling",    "Membrane Fouling — ED-03",    "knowledge-base/sops/ed-03_membrane_fouling.md",   180,"T-05"),
    ("SOP-ED03-002","ed-03.rinse_contamination", "Rinse Contamination — ED-03", "knowledge-base/sops/ed-03_rinse_contamination.md",55,"T-05"),
    ("SOP-ED04-001","ed-04.conductivity_spike",  "Conductivity Spike — ED-04",  "knowledge-base/sops/ed-04_conductivity_spike.md", 45,"T-03"),
    ("SOP-ED04-002","ed-04.di_resin_exhaustion", "DI Resin Exhaustion — ED-04", "knowledge-base/sops/ed-04_di_resin_exhaustion.md",240,"T-05"),
    ("SOP-ED04-003","ed-04.rinse_contamination", "Rinse Contamination — ED-04", "knowledge-base/sops/ed-04_rinse_contamination.md",50,"T-03"),
]

# tank_id → list of {record_id, service_date, technician_id, fault_observed, action_taken, resolution_mins, overdue_flag}
MAINTENANCE_RECORDS = {
    "PT-01": [
        {"record_id":"MR-PT01-001","service_date":"2026-02-10","technician_id":"T-02","fault_observed":"alkalinity_depletion","action_taken":"Added NaOH 2kg, recalibrated dosing pump","resolution_mins":50,"overdue_flag":"N"},
        {"record_id":"MR-PT01-002","service_date":"2026-01-05","technician_id":"T-02","fault_observed":"alkalinity_depletion","action_taken":"Dosed alkalinity booster 3L, cleaned spray nozzles","resolution_mins":55,"overdue_flag":"N"},
        {"record_id":"MR-PT01-003","service_date":"2025-11-18","technician_id":"T-01","fault_observed":"temperature_drift","action_taken":"Replaced heat exchanger gasket, recalibrated thermostat","resolution_mins":80,"overdue_flag":"N"},
    ],
    "PT-02": [
        {"record_id":"MR-PT02-001","service_date":"2026-02-20","technician_id":"T-02","fault_observed":"alkalinity_depletion","action_taken":"Dosed NaOH 3kg, tested bath chemistry every 30min","resolution_mins":48,"overdue_flag":"N"},
        {"record_id":"MR-PT02-002","service_date":"2026-01-12","technician_id":"T-01","fault_observed":"temperature_high","action_taken":"Cleaned heat exchanger tubes, checked coolant flow","resolution_mins":38,"overdue_flag":"N"},
        {"record_id":"MR-PT02-003","service_date":"2025-12-03","technician_id":"T-02","fault_observed":"alkalinity_depletion","action_taken":"Full bath dump 20%, replenished with fresh concentrate","resolution_mins":90,"overdue_flag":"N"},
    ],
    "PT-03": [
        {"record_id":"MR-PT03-001","service_date":"2026-02-25","technician_id":"T-03","fault_observed":"rinse_contamination","action_taken":"Replaced cascade water, cleaned filters, checked DI supply","resolution_mins":32,"overdue_flag":"N"},
        {"record_id":"MR-PT03-002","service_date":"2026-01-18","technician_id":"T-03","fault_observed":"rinse_contamination","action_taken":"Filter replacement (all 3 stages), DI water flush","resolution_mins":35,"overdue_flag":"N"},
        {"record_id":"MR-PT03-003","service_date":"2025-12-10","technician_id":"T-03","fault_observed":"rinse_contamination","action_taken":"Cleaned nozzles, replaced 50% bath water","resolution_mins":28,"overdue_flag":"N"},
    ],
    "PT-04": [
        {"record_id":"MR-PT04-001","service_date":"2026-02-25","technician_id":"T-03","fault_observed":"rinse_contamination","action_taken":"Full bath replacement, descaled spray bars","resolution_mins":40,"overdue_flag":"N"},
        {"record_id":"MR-PT04-002","service_date":"2026-01-20","technician_id":"T-03","fault_observed":"rinse_contamination","action_taken":"Cleaned filters, replaced 30% bath water","resolution_mins":30,"overdue_flag":"N"},
        {"record_id":"MR-PT04-003","service_date":"2025-11-28","technician_id":"T-03","fault_observed":"flow_restriction","action_taken":"Cleared blocked spray nozzles (4 of 12)","resolution_mins":45,"overdue_flag":"N"},
    ],
    "PT-05": [
        {"record_id":"MR-PT05-001","service_date":"2026-02-15","technician_id":"T-04","fault_observed":"titanium_depletion","action_taken":"Dosed Fixodine Z8 2L, pH adjusted to 9.0","resolution_mins":55,"overdue_flag":"N"},
        {"record_id":"MR-PT05-002","service_date":"2026-01-08","technician_id":"T-02","fault_observed":"ph_high","action_taken":"Added dilute HNO3 to reduce pH, verified titanium levels","resolution_mins":42,"overdue_flag":"N"},
        {"record_id":"MR-PT05-003","service_date":"2025-12-20","technician_id":"T-04","fault_observed":"titanium_depletion","action_taken":"Full bath refresh, replaced aging Fixodine concentrate","resolution_mins":70,"overdue_flag":"Y"},
    ],
    "PT-06": [
        {"record_id":"MR-PT06-001","service_date":"2026-03-01","technician_id":"T-04","fault_observed":"acid_drift","action_taken":"Dosed Bonder 958 2.5L, verified zinc 1.4 g/L, titrated to spec","resolution_mins":42,"overdue_flag":"N"},
        {"record_id":"MR-PT06-002","service_date":"2026-02-10","technician_id":"T-04","fault_observed":"zinc_depletion","action_taken":"Added ZnO 4kg, adjusted accelerator 1.2L, rechecked bath","resolution_mins":50,"overdue_flag":"N"},
        {"record_id":"MR-PT06-003","service_date":"2026-01-15","technician_id":"T-04","fault_observed":"accelerator_depletion","action_taken":"Dosed accelerator concentrate 3L, verified points at 3.8","resolution_mins":38,"overdue_flag":"N"},
        {"record_id":"MR-PT06-004","service_date":"2025-12-08","technician_id":"T-04","fault_observed":"acid_drift","action_taken":"Partial bath dump 8%, refilled DI + salts, dosed phosphate","resolution_mins":65,"overdue_flag":"N"},
    ],
    "PT-07": [
        {"record_id":"MR-PT07-001","service_date":"2026-02-28","technician_id":"T-03","fault_observed":"flow_drop","action_taken":"Replaced pump impeller, cleaned all 8 spray nozzles","resolution_mins":38,"overdue_flag":"N"},
        {"record_id":"MR-PT07-002","service_date":"2026-01-22","technician_id":"T-03","fault_observed":"rinse_contamination","action_taken":"Full bath drain, DI water refill, cleaned tank walls","resolution_mins":32,"overdue_flag":"N"},
        {"record_id":"MR-PT07-003","service_date":"2025-12-14","technician_id":"T-03","fault_observed":"flow_drop","action_taken":"Cleared scale from flow meter, replaced 2 spray heads","resolution_mins":45,"overdue_flag":"N"},
    ],
    "PT-08": [
        {"record_id":"MR-PT08-001","service_date":"2026-02-18","technician_id":"T-02","fault_observed":"concentration_low","action_taken":"Dosed Bonderite NT-1 1.5L, pH verified at 4.3","resolution_mins":48,"overdue_flag":"N"},
        {"record_id":"MR-PT08-002","service_date":"2026-01-28","technician_id":"T-04","fault_observed":"passivation_failure","action_taken":"Full bath replacement, surface reactivation check on test panel","resolution_mins":85,"overdue_flag":"N"},
        {"record_id":"MR-PT08-003","service_date":"2025-12-02","technician_id":"T-02","fault_observed":"concentration_low","action_taken":"Replenished sealant concentrate, verified coating adhesion","resolution_mins":52,"overdue_flag":"Y"},
    ],
    "ED-01": [
        {"record_id":"MR-ED01-001","service_date":"2026-03-05","technician_id":"T-04","fault_observed":"meq_acid_buildup","action_taken":"Adjusted solvent balance, added DI water 200L, pH to 6.1","resolution_mins":58,"overdue_flag":"N"},
        {"record_id":"MR-ED01-002","service_date":"2026-02-12","technician_id":"T-04","fault_observed":"temperature_creep","action_taken":"Cleaned chiller coils, replaced coolant temp sensor","resolution_mins":44,"overdue_flag":"N"},
        {"record_id":"MR-ED01-003","service_date":"2026-01-20","technician_id":"T-05","fault_observed":"voltage_fluctuation","action_taken":"Replaced rectifier module 3, re-torqued bus bar connections","resolution_mins":28,"overdue_flag":"N"},
        {"record_id":"MR-ED01-004","service_date":"2025-12-15","technician_id":"T-04","fault_observed":"ph_drift","action_taken":"Dosed AnaCoat pH buffer 2L, verified solids at 20.1%","resolution_mins":50,"overdue_flag":"N"},
    ],
    "ED-02": [
        {"record_id":"MR-ED02-001","service_date":"2026-02-22","technician_id":"T-05","fault_observed":"membrane_fouling","action_taken":"Chemical cleaning UF membranes with NaOH 0.5%, rinsed 3x","resolution_mins":175,"overdue_flag":"N"},
        {"record_id":"MR-ED02-002","service_date":"2025-12-20","technician_id":"T-05","fault_observed":"membrane_fouling","action_taken":"Replaced 2 UF membrane modules (end of life)","resolution_mins":200,"overdue_flag":"N"},
        {"record_id":"MR-ED02-003","service_date":"2025-10-05","technician_id":"T-05","fault_observed":"solids_high","action_taken":"Increased permeate flow, cleaned concentrate recycle valve","resolution_mins":88,"overdue_flag":"N"},
    ],
    "ED-03": [
        {"record_id":"MR-ED03-001","service_date":"2026-02-22","technician_id":"T-05","fault_observed":"membrane_fouling","action_taken":"Chemical cleaning, citric acid flush, DI water rinse","resolution_mins":170,"overdue_flag":"N"},
        {"record_id":"MR-ED03-002","service_date":"2026-01-10","technician_id":"T-05","fault_observed":"membrane_fouling","action_taken":"Replaced 1 UF membrane, verified permeate conductivity <400 uS/cm","resolution_mins":185,"overdue_flag":"N"},
        {"record_id":"MR-ED03-003","service_date":"2025-11-08","technician_id":"T-05","fault_observed":"membrane_fouling","action_taken":"Backflush cycle, NaOH clean, normalised after 2hr","resolution_mins":160,"overdue_flag":"Y"},
    ],
    "ED-04": [
        {"record_id":"MR-ED04-001","service_date":"2026-03-10","technician_id":"T-03","fault_observed":"di_resin_exhaustion","action_taken":"Replaced DI resin bed (both cation and anion), verified <15 uS/cm","resolution_mins":230,"overdue_flag":"N"},
        {"record_id":"MR-ED04-002","service_date":"2026-01-05","technician_id":"T-03","fault_observed":"conductivity_spike","action_taken":"Regenerated resin, flush cycle, confirmed <10 uS/cm","resolution_mins":42,"overdue_flag":"N"},
        {"record_id":"MR-ED04-003","service_date":"2025-11-20","technician_id":"T-05","fault_observed":"di_resin_exhaustion","action_taken":"Emergency resin replacement mid-shift, downtime 4hr","resolution_mins":240,"overdue_flag":"Y"},
    ],
}


# ── Seed action ────────────────────────────────────────────────────────────

def _upsert(label: str, key_prop: str, key_val: str, props: dict) -> None:
    prop_setters = "".join(
        f".property('{_esc(k)}','{_esc(str(v))}')" for k, v in props.items()
    )
    # Keep coalesce limited to element selection/creation, then update properties
    # once and terminate with iterate() so Neptune does not materialize results.
    q = (
        f"g.V().has('{label}','{key_prop}','{_esc(key_val)}')"
        f".fold().coalesce(unfold(),"
        f"addV('{label}').property('{key_prop}','{_esc(key_val)}'))"
        f"{prop_setters}.iterate()"
    )
    _gremlin(q)


def _upsert_edge(from_label: str, from_key: str, from_val: str,
                 to_label: str,   to_key: str,   to_val: str,
                 edge_label: str) -> None:
    q = (
        f"g.V().has('{from_label}','{from_key}','{_esc(from_val)}').as('a')"
        f".V().has('{to_label}','{to_key}','{_esc(to_val)}').as('b')"
        f".coalesce("
        f"  __.select('a').outE('{edge_label}').where(inV().as('b')).limit(1),"
        f"  __.addE('{edge_label}').from('a').to('b')"
        f").iterate()"
    )
    _gremlin(q)


def seed_graph() -> dict:
    counts = {"lines": 0, "tanks": 0, "fault_types": 0, "sops": 0,
              "maintenance_records": 0, "edges": 0, "errors": 0}

    # Lines
    for l in LINES:
        try:
            _upsert("Line", "line_id", l["line_id"],
                    {"name": l["name"], "capacity_jph": l["capacity_jph"], "status": l["status"]})
            counts["lines"] += 1
        except Exception as e:
            print(f"WARN Line {l['line_id']}: {e}")
            counts["errors"] += 1

    # Tanks + PART_OF + FEEDS_INTO
    for t in TANKS:
        try:
            _upsert("Tank", "tank_id", t["tank_id"],
                    {"name": t["name"], "tank_type": t["tank_type"],
                     "line_id": t["line_id"], "sequence_order": t["sequence_order"],
                     "normal_ranges": t["normal_ranges"]})
            counts["tanks"] += 1
            _upsert_edge("Tank", "tank_id", t["tank_id"], "Line", "line_id", t["line_id"], "PART_OF")
            counts["edges"] += 1
        except Exception as e:
            print(f"WARN Tank {t['tank_id']}: {e}")
            counts["errors"] += 1

    for (src, dst) in FEEDS_INTO:
        try:
            _upsert_edge("Tank", "tank_id", src, "Tank", "tank_id", dst, "FEEDS_INTO")
            counts["edges"] += 1
        except Exception as e:
            print(f"WARN FEEDS_INTO {src}->{dst}: {e}")
            counts["errors"] += 1

    # FaultTypes + HAS_FAULT_TYPE edges
    for (fault_id, tank_id, severity, sensors, det_mins, res_mins) in FAULT_TYPES:
        fault_name = fault_id.split(".", 1)[1]
        try:
            _upsert("FaultType", "fault_id", fault_id,
                    {"fault_name": fault_name, "tank_id": tank_id,
                     "severity_level": severity, "affected_sensors": sensors,
                     "avg_detection_mins": det_mins, "avg_resolution_mins": res_mins})
            counts["fault_types"] += 1
            _upsert_edge("Tank", "tank_id", tank_id, "FaultType", "fault_id", fault_id, "HAS_FAULT_TYPE")
            counts["edges"] += 1
        except Exception as e:
            print(f"WARN FaultType {fault_id}: {e}")
            counts["errors"] += 1

    # CAUSED_BY edges
    for (child, parent) in CAUSED_BY_EDGES:
        try:
            _upsert_edge("FaultType", "fault_id", child, "FaultType", "fault_id", parent, "CAUSED_BY")
            counts["edges"] += 1
        except Exception as e:
            print(f"WARN CAUSED_BY {child}->{parent}: {e}")
            counts["errors"] += 1

    # SOPs + HAS_SOP edges
    for (sop_id, fault_id, title, s3_key, fix_mins, tech) in SOPS:
        try:
            _upsert("SOP", "sop_id", sop_id,
                    {"title": title, "s3_doc_key": s3_key,
                     "estimated_fix_mins": fix_mins, "recommended_technician": tech})
            counts["sops"] += 1
            _upsert_edge("FaultType", "fault_id", fault_id, "SOP", "sop_id", sop_id, "HAS_SOP")
            counts["edges"] += 1
        except Exception as e:
            print(f"WARN SOP {sop_id}: {e}")
            counts["errors"] += 1

    # MaintenanceRecords + HAS_MAINTENANCE_RECORD edges
    for tank_id, records in MAINTENANCE_RECORDS.items():
        for rec in records:
            try:
                _upsert("MaintenanceRecord", "record_id", rec["record_id"], {
                    "tank_id":          tank_id,
                    "service_date":     rec["service_date"],
                    "technician_id":    rec["technician_id"],
                    "fault_observed":   rec["fault_observed"],
                    "action_taken":     rec["action_taken"],
                    "resolution_mins":  rec["resolution_mins"],
                    "overdue_flag":     rec["overdue_flag"],
                })
                counts["maintenance_records"] += 1
                _upsert_edge("Tank", "tank_id", tank_id,
                             "MaintenanceRecord", "record_id", rec["record_id"],
                             "HAS_MAINTENANCE_RECORD")
                counts["edges"] += 1
            except Exception as e:
                print(f"WARN MaintenanceRecord {rec['record_id']}: {e}")
                counts["errors"] += 1

    print(f"Seed complete: {counts}")
    return counts


# ── Query actions ──────────────────────────────────────────────────────────

def _unwrap(v):
    """Unwrap a GraphSON 2.0 typed value to a Python scalar."""
    if isinstance(v, dict):
        if v.get("@type") in ("g:List", "g:Set"):
            inner = v["@value"]
            return inner[0] if len(inner) == 1 else inner
        if "@value" in v:
            return v["@value"]
    if isinstance(v, list):
        return v[0] if len(v) == 1 else v
    return v


def _extract_props(value_map_result: list) -> list[dict]:
    """Convert Gremlin valueMap result (GraphSON 2.0) to plain Python dicts.

    Neptune returns valueMap as g:Map with an alternating [key, value, ...] @value list.
    """
    out = []
    for item in value_map_result:
        if not isinstance(item, dict):
            continue
        props = {}
        # GraphSON 2.0: {"@type": "g:Map", "@value": [k, v, k, v, ...]}
        if item.get("@type") == "g:Map":
            pairs = item.get("@value", [])
            it = iter(pairs)
            for k in it:
                v = next(it, None)
                props[k] = _unwrap(v)
        else:
            for k, v in item.items():
                props[k] = _unwrap(v)
        if props:
            out.append(props)
    return out


def get_fault_context(tank_id: str, fault_type: str) -> dict:
    """Return FaultType properties, SOP info, and upstream CAUSED_BY chain."""
    fault_id = f"{tank_id.lower()}.{fault_type.lower()}"

    # FaultType vertex
    ft_result = _gremlin(
        f"g.V().has('FaultType','fault_id','{_esc(fault_id)}').valueMap()"
    )
    ft_props = _extract_props(ft_result)
    if not ft_props:
        return {"tank_id": tank_id, "fault_type": fault_type,
                "error": f"FaultType not found: {fault_id}"}

    ft = ft_props[0]

    # SOP via HAS_SOP
    sop_result = _gremlin(
        f"g.V().has('FaultType','fault_id','{_esc(fault_id)}')"
        f".out('HAS_SOP').valueMap()"
    )
    sops = _extract_props(sop_result)

    # CAUSED_BY upstream chain (2 hops)
    cause_result = _gremlin(
        f"g.V().has('FaultType','fault_id','{_esc(fault_id)}')"
        f".repeat(out('CAUSED_BY')).times(2).emit().valueMap()"
    )
    causes = _extract_props(cause_result)

    return {
        "tank_id":           tank_id,
        "fault_type":        fault_type,
        "severity":          ft.get("severity_level", "UNKNOWN"),
        "affected_sensors":  ft.get("affected_sensors", ""),
        "avg_detection_mins":ft.get("avg_detection_mins", 0),
        "avg_resolution_mins":ft.get("avg_resolution_mins", 0),
        "sop":               sops[0] if sops else {},
        "causal_chain":      causes,
    }


def get_maintenance_history(tank_id: str) -> dict:
    """Return last 5 maintenance records for the tank."""
    result = _gremlin(
        f"g.V().has('Tank','tank_id','{_esc(tank_id)}')"
        f".out('HAS_MAINTENANCE_RECORD')"
        f".order().by('service_date',desc)"
        f".limit(5).valueMap()"
    )
    records = _extract_props(result)
    overdue = any(r.get("overdue_flag") == "Y" for r in records)
    return {
        "tank_id":      tank_id,
        "records":      records,
        "overdue":      overdue,
        "last_service": records[0].get("service_date") if records else None,
    }


# ── Lambda entry point ─────────────────────────────────────────────────────

def handler(event, context):
    if not NEPTUNE_ENDPOINT:
        return {"error": "NEPTUNE_ENDPOINT not configured"}

    action = event.get("action", "")

    if action == "seed_graph":
        return seed_graph()

    if action == "get_fault_context":
        tank_id    = event.get("tank_id", "")
        fault_type = event.get("fault_type", "")
        if not tank_id or not fault_type:
            return {"error": "tank_id and fault_type required"}
        return get_fault_context(tank_id, fault_type)

    if action == "get_maintenance_history":
        tank_id = event.get("tank_id", "")
        if not tank_id:
            return {"error": "tank_id required"}
        return get_maintenance_history(tank_id)

    return {"error": f"Unknown action: {action}",
            "available": ["seed_graph", "get_fault_context", "get_maintenance_history"]}
