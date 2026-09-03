import os
import glob
import joblib
import pandas as pd
from typing import Optional
from src.intelligence.context import RecoveryContext

class RecoveryPredictionModel:
    def __init__(self, model_path: Optional[str] = None):
        if not model_path:
            model_path = self._get_latest_model()
            
        if not model_path or not os.path.exists(model_path):
            raise FileNotFoundError("No trained recovery model found in models/")
            
        self.model = joblib.load(model_path)

    def _get_latest_model(self) -> Optional[str]:
        # Assumes format: models/recovery_model_vYYYYMMDD_HHMMSS.joblib
        models = glob.glob("models/recovery_model_v*.joblib")
        if not models:
            return None
        # Alphabetical sort on timestamps works
        return sorted(models)[-1]

    def predict_probability(self, context: RecoveryContext) -> float:
        """
        Predicts the probability of recovery for a given RecoveryContext.
        Returns a float between 0.0 and 1.0.
        """
        # Convert Pydantic context to flat dictionary exactly as expected by the pipeline
        data = {
            "amount": context.transaction.amount,
            "hour_of_day": context.transaction.hour_of_day,
            "day_of_week": context.transaction.day_of_week,
            "historical_success_rate": context.customer.historical_success_rate,
            "historical_recovery_rate": context.customer.historical_recovery_rate,
            "days_since_last_success": context.customer.days_since_last_success,
            "risk_score": context.customer.risk_score,
            "total_historical_payments": context.customer.total_historical_payments,
            "payment_method": context.transaction.payment_method,
            "failure_category": context.failure.category,
            "failure_severity": context.failure.severity,
            "is_retryable": int(context.failure.is_retryable)
        }
        
        # Scikit-learn pipelines expect a DataFrame
        df = pd.DataFrame([data])
        
        # predict_proba returns array of shape (n_samples, n_classes). We want class 1 (Recovery).
        prob = self.model.predict_proba(df)[0][1]
        
        return float(prob)
