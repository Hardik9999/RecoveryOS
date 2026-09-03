import os
import json
import joblib
import pandas as pd
from datetime import datetime
from sqlalchemy.orm import Session
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import brier_score_loss, roc_auc_score, log_loss, average_precision_score
from xgboost import XGBClassifier

from src.prediction.dataset import generate_training_dataset
from src.database.session import SessionLocal

def train_and_evaluate_model():
    print("Connecting to DB and generating dataset...")
    db = SessionLocal()
    try:
        df = generate_training_dataset(db)
    finally:
        db.close()
        
    if len(df) < 50:
        raise ValueError(f"Dataset too small for training: {len(df)} rows.")

    print(f"Dataset shape: {df.shape}")

    # Temporal split: 70% Train, 15% Calib/Val, 15% Test
    n = len(df)
    train_idx = int(n * 0.7)
    val_idx = int(n * 0.85)

    train_df = df.iloc[:train_idx]
    val_df = df.iloc[train_idx:val_idx]
    test_df = df.iloc[val_idx:]

    print(f"Splits - Train: {len(train_df)}, Val: {len(val_df)}, Test: {len(test_df)}")

    # Define features
    numeric_features = [
        "amount", "hour_of_day", "day_of_week", 
        "historical_success_rate", "historical_recovery_rate", 
        "days_since_last_success", "risk_score", "total_historical_payments"
    ]
    categorical_features = ["payment_method", "failure_category", "failure_severity"]
    boolean_features = ["is_retryable"]
    
    # Preprocessor
    numeric_transformer = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="constant", fill_value=999.0)),
        ("scaler", StandardScaler())
    ])
    categorical_transformer = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="constant", fill_value="missing")),
        ("onehot", OneHotEncoder(handle_unknown="ignore"))
    ])
    boolean_transformer = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="constant", fill_value=0))
    ])

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_transformer, numeric_features),
            ("cat", categorical_transformer, categorical_features),
            ("bool", boolean_transformer, boolean_features)
        ]
    )

    X_train = train_df[numeric_features + categorical_features + boolean_features]
    y_train = train_df["is_recovered"]
    
    X_val = val_df[numeric_features + categorical_features + boolean_features]
    y_val = val_df["is_recovered"]
    
    X_test = test_df[numeric_features + categorical_features + boolean_features]
    y_test = test_df["is_recovered"]

    # 1. Baseline Model: Logistic Regression
    print("Training Baseline Model...")
    baseline_pipeline = Pipeline(steps=[
        ("preprocessor", preprocessor),
        ("classifier", LogisticRegression(class_weight="balanced", random_state=42))
    ])
    baseline_pipeline.fit(X_train, y_train)
    y_test_pred_base = baseline_pipeline.predict_proba(X_test)[:, 1]

    base_brier = brier_score_loss(y_test, y_test_pred_base)
    base_roc = roc_auc_score(y_test, y_test_pred_base)

    # 2. XGBoost Model
    print("Training XGBoost Model...")
    xgb_pipeline = Pipeline(steps=[
        ("preprocessor", preprocessor),
        ("classifier", XGBClassifier(
            objective="binary:logistic", 
            eval_metric="logloss",
            scale_pos_weight=(len(y_train) - sum(y_train)) / sum(y_train) if sum(y_train) > 0 else 1,
            random_state=42
        ))
    ])
    xgb_pipeline.fit(X_train, y_train)

    # 3. Calibration
    print("Calibrating XGBoost Model with Isotonic Regression...")
    # Wrap the pipeline and use cv=2 on the combined train+val set
    X_train_val = pd.concat([X_train, X_val])
    y_train_val = pd.concat([y_train, y_val])
    calibrated_xgb = CalibratedClassifierCV(xgb_pipeline, method="isotonic", cv=2)
    calibrated_xgb.fit(X_train_val, y_train_val)

    # 4. Evaluation
    print("Evaluating Final Model...")
    y_test_pred_xgb = calibrated_xgb.predict_proba(X_test)[:, 1]
    
    xgb_brier = brier_score_loss(y_test, y_test_pred_xgb)
    xgb_roc = roc_auc_score(y_test, y_test_pred_xgb)
    xgb_pr = average_precision_score(y_test, y_test_pred_xgb)
    xgb_log = log_loss(y_test, y_test_pred_xgb)

    metrics = {
        "baseline_brier": base_brier,
        "baseline_roc_auc": base_roc,
        "xgboost_calibrated_brier": xgb_brier,
        "xgboost_calibrated_roc_auc": xgb_roc,
        "xgboost_calibrated_pr_auc": xgb_pr,
        "xgboost_calibrated_log_loss": xgb_log
    }

    print("\nMetrics:")
    for k, v in metrics.items():
        print(f"  {k}: {v:.4f}")

    # 5. Save model
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_path = f"models/recovery_model_v{timestamp}.joblib"
    meta_path = f"models/recovery_model_v{timestamp}_meta.json"
    
    joblib.dump(calibrated_xgb, model_path)
    with open(meta_path, "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"\nModel saved to {model_path}")

if __name__ == "__main__":
    train_and_evaluate_model()
