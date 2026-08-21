"""Isolation Forest training script — SageMaker SKLearn container.

Reads:  $SM_CHANNEL_TRAIN/normal_train.csv   (normal rows only)
        $SM_CHANNEL_TRAIN/normal_test.csv    (for evaluation)
Writes: $SM_MODEL_DIR/isolation_forest.joblib
        $SM_MODEL_DIR/meta.joblib            (score range + feature list)
"""
import os, joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

TRAIN_DIR = os.environ.get("SM_CHANNEL_TRAIN", "/opt/ml/input/data/train")
MODEL_DIR = os.environ.get("SM_MODEL_DIR",     "/opt/ml/model")


def main():
    train = pd.read_csv(f"{TRAIN_DIR}/normal_train.csv")
    test  = pd.read_csv(f"{TRAIN_DIR}/normal_test.csv")
    features = list(train.columns)
    print(f"Training IsolationForest: {len(train):,} samples, {len(features)} features")

    model = IsolationForest(
        n_estimators=200,
        contamination=0.03,   # matches fault injection rate
        max_samples="auto",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(train[features])

    # Score range on training data — used to normalise inference scores to [0, 1]
    train_scores = model.decision_function(train[features])
    score_min = float(train_scores.min())
    score_max = float(train_scores.max())

    # Evaluation
    anomaly_rate = (model.predict(test[features]) == -1).mean()
    print(f"Test anomaly rate (expected ~3%): {anomaly_rate:.1%}")
    print(f"Decision function range: [{score_min:.4f}, {score_max:.4f}]")

    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(model, f"{MODEL_DIR}/isolation_forest.joblib")
    joblib.dump(
        {"score_min": score_min, "score_max": score_max, "features": features},
        f"{MODEL_DIR}/meta.joblib",
    )
    print(f"Model saved to {MODEL_DIR}")


if __name__ == "__main__":
    main()
