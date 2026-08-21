"""SageMaker Processing job — normalise + split training data.

Inputs  (mounted at INPUT_DIR):  raw Parquet files under tank_id=*/date=*/*.parquet
Outputs (written to OUTPUT_DIR):
  normal_train.csv   — normal rows, 80% split  (Isolation Forest + LSTM AE training)
  normal_test.csv    — normal rows, 20% split
  xgb_train.csv      — all labelled rows, 80%  (XGBoost training)
  xgb_test.csv       — all labelled rows, 20%
  scaler.joblib      — fitted MinMaxScaler
  tank_medians.joblib— per-tank median imputation values
  feature_cols.json  — ordered feature + tank-dummy column names
"""
import json, os, joblib
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler

INPUT_DIR  = os.environ.get("SM_INPUT_DIR",  "/opt/ml/processing/input")
OUTPUT_DIR = os.environ.get("SM_OUTPUT_DIR", "/opt/ml/processing/output")

FEATURES = [
    "temperature_c", "ph", "conductivity_us_cm",
    "free_acid_pts", "total_acid_pts", "zinc_g_per_l", "accelerator_pts",
    "meq_acid", "solids_pct", "voltage_v",
    "free_alkalinity", "total_alkalinity",
    "titanium_ppm", "rinse_flow", "concentration_pct", "pigment_binder_ratio",
]

TANK_IDS = [
    "PT-01", "PT-02", "PT-03", "PT-04", "PT-05", "PT-06",
    "PT-07", "PT-08", "ED-01", "ED-02", "ED-03", "ED-04",
]

FAULT_LABELS = [
    "normal", "acid_drift", "zinc_depletion", "accelerator_depletion",
    "temperature_creep", "meq_acid_buildup", "ph_drift",
    "rinse_contamination", "titanium_depletion", "alkalinity_depletion",
]
LABEL_TO_INT = {label: i for i, label in enumerate(FAULT_LABELS)}

SAMPLE_PER_TANK = 80_000   # 80k × 12 tanks = 960k rows total — fast to train
RANDOM_SEED     = 42


def load_all_data() -> pd.DataFrame:
    dfs = []
    # Support both flat input and Hive-partitioned subdirectories
    parquet_files = list(Path(INPUT_DIR).glob("**/*.parquet"))
    print(f"Found {len(parquet_files)} parquet files under {INPUT_DIR}")
    for pf in parquet_files:
        df = pd.read_parquet(pf)
        # Infer tank_id from path if not in columns
        if "tank_id" not in df.columns:
            parts = pf.parts
            tank_part = next((p for p in parts if p.startswith("tank_id=")), None)
            df["tank_id"] = tank_part.split("=")[1] if tank_part else "unknown"
        # Sample to keep size manageable
        sample_n = min(SAMPLE_PER_TANK, len(df))
        df = df.sample(sample_n, random_state=RANDOM_SEED)
        dfs.append(df)
        print(f"  {pf.name}: {sample_n:,} rows (tank={df['tank_id'].iloc[0]})")
    return pd.concat(dfs, ignore_index=True)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("Loading data...")
    df = load_all_data()
    print(f"Total rows after sampling: {len(df):,}")

    # Live Firehose data has no fault_label column — treat as normal
    if "fault_label" not in df.columns:
        df["fault_label"] = "normal"
    else:
        df["fault_label"] = df["fault_label"].fillna("normal")

    # ── Per-tank median imputation ────────────────────────────────────────
    tank_medians: dict = {}
    for feat in FEATURES:
        for tank_id in TANK_IDS:
            mask = df["tank_id"] == tank_id
            median_val = df.loc[mask, feat].median()
            tank_medians.setdefault(tank_id, {})[feat] = (
                float(median_val) if not np.isnan(median_val) else 0.0
            )
            df.loc[mask & df[feat].isna(), feat] = median_val

    # Any remaining NaN (sensor not present in that tank) → 0
    df[FEATURES] = df[FEATURES].fillna(0.0)

    # ── Global MinMax scaling ─────────────────────────────────────────────
    scaler = MinMaxScaler()
    df[FEATURES] = scaler.fit_transform(df[FEATURES])

    # ── Tank one-hot (for XGBoost) ────────────────────────────────────────
    tank_dummies = pd.get_dummies(df["tank_id"], prefix="tank")
    df = pd.concat([df, tank_dummies], axis=1)
    # Exclude the original tank_id string column — keep only the one-hot dummies
    tank_cols = [c for c in df.columns if c.startswith("tank_") and c != "tank_id"]

    # ── Label encoding ────────────────────────────────────────────────────
    df["label_int"] = df["fault_label"].map(LABEL_TO_INT).fillna(0).astype(int)

    # ── Splits ────────────────────────────────────────────────────────────
    normal_mask = df["fault_label"] == "normal"
    df_normal   = df[normal_mask].copy()
    df_all      = df.copy()

    norm_train, norm_test = train_test_split(
        df_normal, test_size=0.2, random_state=RANDOM_SEED)
    all_train, all_test   = train_test_split(
        df_all, test_size=0.2, random_state=RANDOM_SEED,
        stratify=df_all["fault_label"])

    feature_cols = FEATURES + tank_cols

    # ── Write outputs ─────────────────────────────────────────────────────
    norm_train[FEATURES].to_csv(f"{OUTPUT_DIR}/normal_train.csv", index=False)
    norm_test[FEATURES].to_csv(f"{OUTPUT_DIR}/normal_test.csv",  index=False)
    all_train[feature_cols + ["label_int"]].to_csv(f"{OUTPUT_DIR}/xgb_train.csv", index=False)
    all_test[feature_cols  + ["label_int"]].to_csv(f"{OUTPUT_DIR}/xgb_test.csv",  index=False)

    joblib.dump(scaler,       f"{OUTPUT_DIR}/scaler.joblib")
    joblib.dump(tank_medians, f"{OUTPUT_DIR}/tank_medians.joblib")
    with open(f"{OUTPUT_DIR}/feature_cols.json", "w") as fh:
        json.dump({"features": FEATURES, "tank_cols": tank_cols, "feature_cols": feature_cols}, fh)

    print(f"Normal  train={len(norm_train):,}  test={len(norm_test):,}")
    print(f"XGB     train={len(all_train):,}   test={len(all_test):,}")
    print(f"Class distribution:\n{df_all['fault_label'].value_counts().to_string()}")
    print("Preprocessing complete.")


if __name__ == "__main__":
    main()
