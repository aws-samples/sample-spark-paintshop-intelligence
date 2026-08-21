"""Isolation Forest inference handler — SageMaker SKLearn serving container."""
import json, os, joblib
import numpy as np

MODEL_DIR = os.environ.get("SM_MODEL_DIR", "/opt/ml/model")

_model        = None
_scaler       = None
_meta         = None
_features     = None
_tank_medians = None


def model_fn(model_dir):
    global _model, _scaler, _meta, _features, _tank_medians
    _model        = joblib.load(f"{model_dir}/isolation_forest.joblib")
    _scaler       = joblib.load(f"{model_dir}/scaler.joblib")
    _meta         = joblib.load(f"{model_dir}/meta.joblib")
    _tank_medians = joblib.load(f"{model_dir}/tank_medians.joblib")
    _features     = _meta["features"]
    return _model


def input_fn(request_body, content_type="application/json"):
    if content_type == "application/json":
        return json.loads(request_body)
    raise ValueError(f"Unsupported content type: {content_type}")


def predict_fn(data, model):
    tank_id = data.get("tank_id", "")
    medians = _tank_medians.get(tank_id, {})
    row     = np.array([[data.get(f, medians.get(f, 0.0)) for f in _features]])
    scaled  = _scaler.transform(row)
    raw     = float(model.decision_function(scaled)[0])

    # Normalize anchored at the decision boundary (raw=0):
    #   raw >= score_max  → if_score = 0.0  (clearly normal)
    #   raw = 0           → if_score = 0.5  (on the boundary)
    #   raw <= -score_max → if_score = 1.0  (clearly anomalous)
    # This avoids the old score_min clipping problem where normal readings
    # that score slightly below the training minimum were clipped to 1.0.
    scale    = _meta["score_max"] + 1e-9
    if_score = float(max(0.0, min(1.0, 0.5 * (1.0 - raw / scale))))

    # Use model's own calibrated threshold (predict=-1 means anomaly)
    anomaly_detected = int(model.predict(scaled)[0]) == -1

    return {"if_score": round(if_score, 4), "anomaly_detected": anomaly_detected}


def output_fn(prediction, accept="application/json"):
    return json.dumps(prediction), "application/json"
