"""XGBoost Fault Classifier inference handler — SageMaker XGBoost serving container.

Input  (application/json): {"tank_id": "PT-06", "free_acid_pts": 1.92, ...}
Output (application/json): {"fault_type": "acid_drift", "confidence": 0.94}
"""
import json, os
import numpy as np
import joblib
import xgboost as xgb

MODEL_DIR = os.environ.get("SM_MODEL_DIR", "/opt/ml/model")
# Scaler/medians are bundled in model.tar.gz (same dir as xgb_model.ubj)
# Fallback to /opt/ml/code if missing from model dir (sourcedir bundle)
CODE_DIR  = os.path.dirname(os.path.abspath(__file__))

_model        = None
_meta         = None
_features     = None
_scaler       = None
_tank_medians = None

SENSOR_FEATURES = [
    "temperature_c", "ph", "conductivity_us_cm",
    "free_acid_pts", "total_acid_pts", "zinc_g_per_l", "accelerator_pts",
    "meq_acid", "solids_pct", "voltage_v",
    "free_alkalinity", "total_alkalinity",
    "titanium_ppm", "rinse_flow", "concentration_pct", "pigment_binder_ratio",
]


def model_fn(model_dir):
    global _model, _meta, _features, _scaler, _tank_medians
    _model = xgb.XGBClassifier()
    _model.load_model(f"{model_dir}/xgb_model.ubj")
    with open(f"{model_dir}/meta.json") as fh:
        _meta = json.load(fh)
    _features = _meta["feature_cols"]
    # Load scaler and tank medians — look in model_dir first (bundled in model.tar.gz),
    # then fall back to /opt/ml/code (sourcedir extract location)
    for candidate_dir in [model_dir, "/opt/ml/code", CODE_DIR]:
        scaler_path  = os.path.join(candidate_dir, "scaler.joblib")
        medians_path = os.path.join(candidate_dir, "tank_medians.joblib")
        if os.path.exists(scaler_path) and os.path.exists(medians_path):
            print(f"[inference] Loading scaler from: {candidate_dir}", flush=True)
            _scaler       = joblib.load(scaler_path)
            _tank_medians = joblib.load(medians_path)
            break
    if _scaler is None:
        raise RuntimeError(f"scaler.joblib not found in {[model_dir, '/opt/ml/code', CODE_DIR]}")
    return _model


def input_fn(request_body, content_type="application/json"):
    if content_type == "application/json":
        return json.loads(request_body)
    raise ValueError(f"Unsupported content type: {content_type}")


def predict_fn(data, model):
    tank_id = data.get("tank_id", "")
    medians = _tank_medians.get(tank_id, {})

    # 1. Build scaled sensor feature vector (same MinMax scaler used in training)
    raw_sensors = np.array(
        [[data.get(f, medians.get(f, 0.0)) for f in SENSOR_FEATURES]],
        dtype=np.float32,
    )
    scaled_sensors = _scaler.transform(raw_sensors)[0]  # shape: (16,)

    # 2. Build full feature row: scaled sensors + tank one-hot columns
    scaled_dict = dict(zip(SENSOR_FEATURES, scaled_sensors))
    row = []
    for f in _features:
        if f == f"tank_{tank_id}":
            row.append(1.0)
        elif f in scaled_dict:
            row.append(float(scaled_dict[f]))
        else:
            row.append(0.0)
    row  = np.array([row])

    pred = int(model.predict(row)[0])
    prob = model.predict_proba(row)[0]

    # int_to_label keys may have been serialised as strings by json.dump
    int_to_label = {int(k): v for k, v in _meta["int_to_label"].items()}
    fault_type   = int_to_label.get(pred, "unknown")
    confidence   = float(prob[pred])

    return {"fault_type": fault_type, "confidence": round(confidence, 4)}


def output_fn(prediction, accept="application/json"):
    return json.dumps(prediction), "application/json"
