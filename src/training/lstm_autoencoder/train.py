"""LSTM Autoencoder training script — SageMaker PyTorch container.

Architecture:
  Encoder: LSTM(n_features → hidden=32)
  Decoder: LSTM(hidden=32 → n_features)
  Loss:    MSE reconstruction error on normal sensor windows

Reads:  $SM_CHANNEL_TRAIN/normal_train.csv
Writes: $SM_MODEL_DIR/lstm_ae.pt      (state dict)
        $SM_MODEL_DIR/meta.json       (scaler stats for inference normalisation)
"""
import json, os
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

TRAIN_DIR = os.environ.get("SM_CHANNEL_TRAIN", "/opt/ml/input/data/train")
MODEL_DIR = os.environ.get("SM_MODEL_DIR",     "/opt/ml/model")

WINDOW  = 32    # sequence length for each training sample
HIDDEN  = 32    # LSTM hidden dimension
EPOCHS  = 15
BATCH   = 512
LR      = 1e-3
SEED    = 42


class LSTMAutoencoder(nn.Module):
    def __init__(self, n_features: int, hidden: int = 32):
        super().__init__()
        self.n_features = n_features
        self.hidden     = hidden
        self.encoder = nn.LSTM(n_features, hidden, num_layers=1, batch_first=True)
        self.decoder = nn.LSTM(hidden,     n_features, num_layers=1, batch_first=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, seq_len, n_features)
        _, (h_n, c_n) = self.encoder(x)
        # Expand hidden state across all decoder time steps
        h_dec = h_n.permute(1, 0, 2).expand(-1, x.size(1), -1)
        out, _ = self.decoder(h_dec)
        return out                                # (batch, seq_len, n_features)


def make_windows(arr: np.ndarray, window: int) -> np.ndarray:
    """Non-overlapping windows; pads tail if needed."""
    n = len(arr)
    # Pad so that n is divisible by window
    remainder = n % window
    if remainder:
        pad = window - remainder
        arr = np.vstack([arr, np.tile(arr[-1], (pad, 1))])
    n_windows = len(arr) // window
    return arr.reshape(n_windows, window, arr.shape[1])


def main():
    torch.manual_seed(SEED)
    np.random.seed(SEED)

    df = pd.read_csv(f"{TRAIN_DIR}/normal_train.csv")
    features = list(df.columns)
    n_feat   = len(features)
    data     = df[features].values.astype(np.float32)

    print(f"LSTM AE: {len(data):,} samples, {n_feat} features, window={WINDOW}")
    windows = make_windows(data, WINDOW)
    print(f"Windows shape: {windows.shape}")

    X      = torch.tensor(windows, dtype=torch.float32)
    loader = DataLoader(TensorDataset(X), batch_size=BATCH, shuffle=True, drop_last=True)

    model     = LSTMAutoencoder(n_feat, HIDDEN)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)
    criterion = nn.MSELoss()

    model.train()
    for epoch in range(1, EPOCHS + 1):
        total = 0.0
        for (batch,) in loader:
            optimizer.zero_grad()
            recon = model(batch)
            loss  = criterion(recon, batch)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            total += loss.item()
        print(f"Epoch {epoch:02d}/{EPOCHS}  loss={total / len(loader):.6f}")

    # Compute per-window reconstruction error on training set for normalisation
    model.eval()
    errors = []
    with torch.no_grad():
        for (batch,) in DataLoader(TensorDataset(X), batch_size=BATCH):
            recon = model(batch)
            err   = ((recon - batch) ** 2).mean(dim=(1, 2))
            errors.extend(err.numpy().tolist())
    errors   = np.array(errors)
    err_min  = float(errors.min())
    err_max  = float(errors.max())
    thr_95   = float(np.percentile(errors, 95))
    print(f"Reconstruction error: min={err_min:.6f}  95th={thr_95:.6f}  max={err_max:.6f}")

    os.makedirs(MODEL_DIR, exist_ok=True)
    torch.save(model.state_dict(), f"{MODEL_DIR}/lstm_ae.pt")
    with open(f"{MODEL_DIR}/meta.json", "w") as fh:
        json.dump({
            "n_features":    n_feat,
            "hidden":        HIDDEN,
            "window":        WINDOW,
            "features":      features,
            "err_min":       err_min,
            "err_max":       err_max,
            "threshold_95":  thr_95,
        }, fh)
    print("LSTM AE saved.")


if __name__ == "__main__":
    main()
