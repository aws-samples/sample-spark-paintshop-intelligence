"""LSTM Autoencoder inference handler — SageMaker PyTorch serving container.

Input  (application/json): {"tank_id": "ED-01", "temperature_c": 33.9, ...}
Output (application/json): {"lstm_score": 0.81}
"""
import json, os
import numpy as np
import torch
import torch.nn as nn

MODEL_DIR = os.environ.get("SM_MODEL_DIR", "/opt/ml/model")

_model = None
_meta  = None


class LSTMAutoencoder(nn.Module):
    def __init__(self, n_features: int, hidden: int = 32):
        super().__init__()
        self.encoder = nn.LSTM(n_features, hidden, num_layers=1, batch_first=True)
        self.decoder = nn.LSTM(hidden,     n_features, num_layers=1, batch_first=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, (h_n, _) = self.encoder(x)
        h_dec = h_n.permute(1, 0, 2).expand(-1, x.size(1), -1)
        out, _ = self.decoder(h_dec)
        return out


def model_fn(model_dir):
    global _model, _meta
    with open(f"{model_dir}/meta.json") as fh:
        _meta = json.load(fh)
    _model = LSTMAutoencoder(_meta["n_features"], _meta["hidden"])
    _model.load_state_dict(
        torch.load(f"{model_dir}/lstm_ae.pt", map_location="cpu", weights_only=True)
    )
    _model.eval()
    return _model


def input_fn(request_body, content_type="application/json"):
    if content_type == "application/json":
        return json.loads(request_body)
    raise ValueError(f"Unsupported content type: {content_type}")


# MinMax scaling parameters from scaler.joblib fit on training data.
# All data_min_ values are 0.0, so: scaled = raw / data_max
_SCALE_MAX = {
    "temperature_c":        63.485,
    "ph":                   12.243,
    "conductivity_us_cm":   9290.353,
    "free_acid_pts":         2.4,
    "total_acid_pts":        26.1,
    "zinc_g_per_l":          1.523,
    "accelerator_pts":       3.902,
    "meq_acid":              41.5,
    "solids_pct":            21.5,
    "voltage_v":            296.864,
    "free_alkalinity":       14.458,
    "total_alkalinity":      19.79,
    "titanium_ppm":           1.907,
    "rinse_flow":            13.686,
    "concentration_pct":      0.877,
    "pigment_binder_ratio":   0.227,
}


def predict_fn(data, model):
    features = _meta["features"]
    # Apply the same MinMax scaling used during training (all min=0, so divide by max)
    raw = np.array([data.get(f, 0.0) for f in features], dtype=np.float32)
    scale = np.array([_SCALE_MAX.get(f, 1.0) for f in features], dtype=np.float32)
    scaled = np.clip(raw / np.where(scale == 0, 1.0, scale), 0.0, 1.0)
    # Tile to match training window length (model was trained on seq_len=32)
    window = _meta.get("window", 32)
    x = torch.tensor(np.tile(scaled, (1, window, 1)).reshape(1, window, len(features)))

    with torch.no_grad():
        recon = model(x)
        err   = float(((recon - x) ** 2).mean().item())

    err_min    = _meta["err_min"]
    err_max    = _meta["err_max"]
    lstm_score = (err - err_min) / (err_max - err_min + 1e-9)
    lstm_score = float(max(0.0, min(1.0, lstm_score)))

    return {"lstm_score": round(lstm_score, 4)}


def output_fn(prediction, accept="application/json"):
    return json.dumps(prediction), "application/json"
