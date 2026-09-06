import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from src.database.models import Payment, PaymentFailure, Customer
from src.intelligence.context import RecoveryContext, FailureContext, CustomerContext, TransactionContext
from src.intelligence.taxonomy import get_taxonomy_info

class FeatureExtractor:
    def __init__(self, db: Session):
        self.db = db

    def extract_context(self, payment_id: uuid.UUID) -> RecoveryContext:
        """
        Extracts a deterministic RecoveryContext for a given failed payment.
        Calculates historical features ensuring no data leakage from future payments.
        """
        payment = self.db.get(Payment, payment_id)
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")

        # Assume the payment has exactly one failure since it's in a failed state
        if not payment.failures:
            raise ValueError(f"Payment {payment_id} has no failure records")
        
        failure_record = payment.failures[0]
        customer = self.db.get(Customer, payment.customer_id)

        # 1. Failure Context
        tax_info = get_taxonomy_info(failure_record.error_code)
        failure_ctx = FailureContext(
            error_code=failure_record.error_code,
            category=tax_info["category"],
            is_retryable=tax_info["is_retryable"],
            severity=tax_info["severity"],
            network=tax_info.get("network"),
            description=tax_info.get("description")
        )

        # 2. Transaction Context
        # Convert created_at (iso string) to datetime to extract hour/day
        dt = datetime.fromisoformat(payment.created_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        tx_ctx = TransactionContext(
            amount=float(payment.amount),
            currency=payment.currency,
            payment_method=payment.payment_method or "unknown",
            hour_of_day=dt.hour,
            day_of_week=dt.weekday()
        )

        # 3. Customer Context (Anti-Leakage Calculation)
        # We query the DB for payments BEFORE this payment's created_at timestamp
        historical_payments = self.db.query(Payment).filter(
            Payment.customer_id == customer.id,
            Payment.created_at < payment.created_at
        ).all()

        total_historical = len(historical_payments)
        
        if total_historical == 0:
            hist_success_rate = 0.0
            hist_recovery_rate = 0.0
            days_since_last_success = None
        else:
            success_payments = [p for p in historical_payments if p.status == "SUCCESS"]
            recovered_payments = [p for p in historical_payments if p.status == "RECOVERED"]
            failed_terminal_payments = [p for p in historical_payments if p.status in ("FAILED", "FAILED_TERMINAL")]
            
            hist_success_rate = len(success_payments) / total_historical
            
            total_failed_initially = len(recovered_payments) + len(failed_terminal_payments)
            if total_failed_initially > 0:
                hist_recovery_rate = len(recovered_payments) / total_failed_initially
            else:
                hist_recovery_rate = 0.0
                
            if success_payments:
                # Sort by created_at desc
                success_payments.sort(key=lambda x: x.created_at, reverse=True)
                last_success_dt = datetime.fromisoformat(success_payments[0].created_at)
                if last_success_dt.tzinfo is None:
                    last_success_dt = last_success_dt.replace(tzinfo=timezone.utc)
                delta = dt - last_success_dt
                days_since_last_success = delta.days
            else:
                days_since_last_success = None

        cust_ctx = CustomerContext(
            historical_success_rate=hist_success_rate,
            historical_recovery_rate=hist_recovery_rate,
            days_since_last_success=days_since_last_success,
            risk_score=customer.risk_score,
            total_historical_payments=total_historical
        )

        # 4. Assemble final context
        return RecoveryContext(
            payment_id=str(payment.id),
            timestamp=dt,
            transaction=tx_ctx,
            failure=failure_ctx,
            customer=cust_ctx
        )
