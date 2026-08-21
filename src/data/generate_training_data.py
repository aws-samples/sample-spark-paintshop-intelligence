import json, os, random
from datetime import datetime, timedelta, timezone

import boto3
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from lambdas.simulator.tank_profiles import TANK_PROFILES, generate_reading, FAULT_OVERRIDES

FAULT_INJECTION_RATE = 0.03   # 3% of time windows are fault windows
FAULT_WINDOW_MINS    = 90     # each injected fault lasts 90 minutes
INTERVAL_SECS        = 5
BUCKET_NAME          = os.environ.get("BUCKET_NAME", "amzn-s3-demo-paintshop-ml")
S3 = boto3.client("s3")

TANK_FAULTS = {
    "PT-06": ["acid_drift", "zinc_depletion", "accelerator_depletion"],
    "ED-01": ["temperature_creep", "meq_acid_buildup", "ph_drift"],
    "PT-03": ["rinse_contamination"],
    "PT-04": ["rinse_contamination"],
    "PT-07": ["rinse_contamination"],
    "PT-05": ["titanium_depletion"],
    "PT-01": ["alkalinity_depletion"],
    "PT-02": ["alkalinity_depletion"],
    "PT-08": ["ph_drift"],
    "ED-02": ["rinse_contamination"],
    "ED-03": ["rinse_contamination"],
    "ED-04": ["rinse_contamination"],
}


def generate_tank_readings(tank_id: str, days: int = 180) -> list:
    total_seconds  = days * 86400
    num_readings   = total_seconds // INTERVAL_SECS
    fault_window_n = FAULT_WINDOW_MINS * 60 // INTERVAL_SECS
    start_dt       = datetime(2025, 9, 1, tzinfo=timezone.utc)

    faults_for_tank = TANK_FAULTS.get(tank_id, [])
    readings = []
    i = 0
    active_fault = None
    fault_remaining = 0

    while i < num_readings:
        ts = start_dt + timedelta(seconds=i * INTERVAL_SECS)
        if fault_remaining > 0:
            fault_remaining -= 1
            if fault_remaining == 0:
                active_fault = None
        elif faults_for_tank and random.random() < FAULT_INJECTION_RATE / (fault_window_n):
            active_fault   = random.choice(faults_for_tank)
            fault_remaining = fault_window_n

        reading = generate_reading(tank_id, fault=active_fault)
        reading["timestamp"]   = ts.isoformat()
        reading["fault_label"] = active_fault or "normal"
        reading["shift"]       = _derive_shift(ts.hour)
        reading["line_id"]     = "LINE-1"
        readings.append(reading)
        i += 1

    return readings


def _derive_shift(hour: int) -> str:
    if 6 <= hour < 14:  return "morning"
    if 14 <= hour < 22: return "afternoon"
    return "night"


def upload_to_s3(tank_id: str, df: pd.DataFrame):
    table  = pa.Table.from_pandas(df)
    prefix = f"raw-synthetic/tank_id={tank_id}/date=2025-09-01"
    local  = f"/tmp/{tank_id}_readings.parquet"
    pq.write_table(table, local)
    key = f"{prefix}/{tank_id}_6months.parquet"
    S3.upload_file(local, BUCKET_NAME, key)
    print(f"Uploaded {len(df):,} rows → s3://{BUCKET_NAME}/{key}")


def main():
    for tank_id in TANK_PROFILES:
        print(f"Generating {tank_id}...")
        readings = generate_tank_readings(tank_id, days=180)
        df = pd.DataFrame(readings)
        upload_to_s3(tank_id, df)
    print("Training data generation complete.")


if __name__ == "__main__":
    main()
