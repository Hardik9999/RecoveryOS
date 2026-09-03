import pandas as pd
from sqlalchemy.orm import Session
from src.database.models import Payment
from src.intelligence.extractor import FeatureExtractor
from src.intelligence.context import RecoveryContext

def generate_training_dataset(db: Session) -> pd.DataFrame:
    """
    Scans the database for all initially failed payments, builds the
    RecoveryContext for each, flattens it, and extracts the final target
    (is_recovered).
    """
    extractor = FeatureExtractor(db)
    
    # We want payments that eventually reached a terminal failed/recovered state
    # but were initially failed (so they have failures).
    # Since in Phase 1 & 2 we set status to "RECOVERED" or "FAILED_TERMINAL",
    # and "FAILED" is intermediate, we will look for all payments that have at least one failure.
    
    # Query all payments that have a PaymentFailure associated with them.
    # Note: we filter out payments that are still in "PENDING" or intermediate "FAILED" 
    # to only train on resolved cases if this were prod, but for simulation all are resolved.
    failed_payments = db.query(Payment).filter(
        Payment.failures.any()
    ).order_by(Payment.created_at).all()
    
    data = []
    
    for payment in failed_payments:
        # Target variable: 1 if RECOVERED, 0 otherwise (FAILED, FAILED_TERMINAL)
        is_recovered = 1 if payment.status == "RECOVERED" else 0
        
        # Build context
        try:
            ctx = extractor.extract_context(payment.id)
        except Exception as e:
            print(f"Skipping payment {payment.id} due to context error: {e}")
            continue
            
        # Flatten context into a dict
        row = {
            "payment_id": str(payment.id),
            "created_at": payment.created_at,  # for temporal splitting
            "amount": ctx.transaction.amount,
            "currency": ctx.transaction.currency,
            "payment_method": ctx.transaction.payment_method,
            "hour_of_day": ctx.transaction.hour_of_day,
            "day_of_week": ctx.transaction.day_of_week,
            "error_code": ctx.failure.error_code,
            "failure_category": ctx.failure.category,
            "is_retryable": int(ctx.failure.is_retryable),
            "failure_severity": ctx.failure.severity,
            "historical_success_rate": ctx.customer.historical_success_rate,
            "historical_recovery_rate": ctx.customer.historical_recovery_rate,
            "days_since_last_success": ctx.customer.days_since_last_success,
            "risk_score": ctx.customer.risk_score,
            "total_historical_payments": ctx.customer.total_historical_payments,
            "is_recovered": is_recovered
        }
        data.append(row)
        
    df = pd.DataFrame(data)
    
    # Sort temporally
    if not df.empty:
        df = df.sort_values("created_at").reset_index(drop=True)
        
    return df
