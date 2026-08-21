"""XGBoost Fault Classifier training script — SageMaker XGBoost container.

10-class multi-class classifier:
  0=normal  1=acid_drift  2=zinc_depletion  3=accelerator_depletion
  4=temperature_creep  5=meq_acid_buildup  6=ph_drift
  7=rinse_contamination  8=titanium_depletion  9=alkalinity_depletion

Reads:  $SM_CHANNEL_TRAIN/xgb_train.csv   (all labelled rows, label_int column last)
        $SM_CHANNEL_TRAIN/xgb_test.csv
Writes: $SM_MODEL_DIR/xgb_model.ubj
        $SM_MODEL_DIR/meta.json
"""
import json, os
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import accuracy_score, classification_report

TRAIN_DIR = os.environ.get("SM_CHANNEL_TRAIN", "/opt/ml/input/data/train")
MODEL_DIR = os.environ.get("SM_MODEL_DIR",     "/opt/ml/model")

INT_TO_LABEL = {
    0: "normal",              1: "acid_drift",
    2: "zinc_depletion",      3: "accelerator_depletion",
    4: "temperature_creep",   5: "meq_acid_buildup",
    6: "ph_drift",            7: "rinse_contamination",
    8: "titanium_depletion",  9: "alkalinity_depletion",
}
N_CLASSES = len(INT_TO_LABEL)


def main():
    train = pd.read_csv(f"{TRAIN_DIR}/xgb_train.csv")
    test  = pd.read_csv(f"{TRAIN_DIR}/xgb_test.csv")

    # Exclude label and any remaining string columns (e.g. tank_id carried over from preprocessing)
    feature_cols = [c for c in train.columns
                    if c != "label_int" and train[c].dtype != object]
    X_train, y_train = train[feature_cols].values, train["label_int"].values
    X_test,  y_test  = test[feature_cols].values,  test["label_int"].values

    print(f"XGBoost: train={X_train.shape}, test={X_test.shape}, classes={N_CLASSES}")
    print(f"Class distribution:\n{pd.Series(y_train).value_counts().sort_index().to_string()}")

    model = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.1,
        objective="multi:softmax",
        num_class=N_CLASSES,
        eval_metric="mlogloss",
        subsample=0.8,
        colsample_bytree=0.8,
        n_jobs=-1,
        random_state=42,
    )
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=50,
    )

    y_pred = model.predict(X_test)
    acc    = accuracy_score(y_test, y_pred)
    print(f"\nTest accuracy: {acc:.4f}")
    print(classification_report(
        y_test, y_pred,
        target_names=[INT_TO_LABEL[i] for i in range(N_CLASSES)],
        zero_division=0,
    ))

    os.makedirs(MODEL_DIR, exist_ok=True)
    model.save_model(f"{MODEL_DIR}/xgb_model.ubj")
    with open(f"{MODEL_DIR}/meta.json", "w") as fh:
        json.dump({
            "feature_cols":  feature_cols,
            "int_to_label":  INT_TO_LABEL,
            "n_classes":     N_CLASSES,
            "test_accuracy": round(float(acc), 4),
        }, fh)
    print(f"XGBoost model saved to {MODEL_DIR}")


if __name__ == "__main__":
    main()
