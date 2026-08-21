"""Shared constants for all training components."""
import os

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
INT_TO_LABEL = {i: label for label, i in LABEL_TO_INT.items()}

BUCKET          = os.environ.get("BUCKET_NAME", "amzn-s3-demo-paintshop-ml")
RAW_PREFIX      = "raw-synthetic"
PIPELINE_PREFIX = "pipeline-data"
MODEL_PREFIX    = "models"

ENDPOINT_NAME   = "paintshop-anomaly-endpoint"
MODEL_PKG_GROUP = "PaintShopAnomalyDetector"
PIPELINE_NAME   = "PaintShopAnomalyPipeline"
