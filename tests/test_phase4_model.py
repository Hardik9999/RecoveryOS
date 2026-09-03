import pytest
import os
import uuid
from datetime import datetime
from src.intelligence.context import RecoveryContext, TransactionContext, FailureContext, CustomerContext
from src.prediction.model import RecoveryPredictionModel

@pytest.fixture(scope="module")
def mock_context():
    return RecoveryContext(
        payment_id=str(uuid.uuid4()),
        timestamp=datetime.now(),
        transaction=TransactionContext(
            amount=100.50,
            currency="INR",
            payment_method="card",
            hour_of_day=14,
            day_of_week=2
        ),
        failure=FailureContext(
            error_code="INSUFFICIENT_FUNDS",
            category="USER",
            is_retryable=True,
            severity="MEDIUM"
        ),
        customer=CustomerContext(
            historical_success_rate=0.8,
            historical_recovery_rate=0.5,
            days_since_last_success=5,
            risk_score=0.2,
            total_historical_payments=10
        )
    )

def test_model_loading_and_prediction(mock_context):
    # Ensure a model exists before running this test
    # (train.py must be run before tests)
    model = RecoveryPredictionModel()
    
    # 1. Pipeline Test
    prob = model.predict_probability(mock_context)
    
    assert isinstance(prob, float)
    assert 0.0 <= prob <= 1.0

def test_model_determinism(mock_context):
    model = RecoveryPredictionModel()
    
    prob1 = model.predict_probability(mock_context)
    prob2 = model.predict_probability(mock_context)
    
    assert prob1 == prob2, "Model is not deterministic for the exact same input"

def test_model_handles_nulls():
    model = RecoveryPredictionModel()
    
    null_context = RecoveryContext(
        payment_id=str(uuid.uuid4()),
        timestamp=datetime.now(),
        transaction=TransactionContext(
            amount=50.0,
            currency="INR",
            payment_method="upi",
            hour_of_day=1,
            day_of_week=1
        ),
        failure=FailureContext(
            error_code="UNKNOWN",
            category="UNKNOWN",
            is_retryable=False,
            severity="TERMINAL"
        ),
        customer=CustomerContext(
            historical_success_rate=0.0,
            historical_recovery_rate=0.0,
            days_since_last_success=None, # Missing value
            risk_score=0.5,
            total_historical_payments=0
        )
    )
    
    prob = model.predict_probability(null_context)
    assert isinstance(prob, float)
    assert 0.0 <= prob <= 1.0
