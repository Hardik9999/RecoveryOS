"""
Payment listing and detail endpoints.
"""
import uuid
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.api.dependencies import get_db
from src.api.schemas.payments import (
    PaymentResponse, PaymentListResponse,
    FailureResponse, RecoveryActionResponse
)
from src.database.models import Payment, PaymentFailure, RecoveryAction, RecoveryOutcome

logger = logging.getLogger("recoveryos.api.payments")

router = APIRouter(prefix="/payments", tags=["Payments"])


def _payment_to_response(payment: Payment, db: Session) -> PaymentResponse:
    """Convert a Payment ORM object to a clean API response."""
    # Failure info
    failure_resp = None
    if payment.failures:
        f = payment.failures[0]
        failure_resp = FailureResponse(
            error_code=f.error_code,
            error_message=f.error_message,
            failure_category=f.failure_category,
            is_retryable=f.is_retryable,
            occurred_at=f.occurred_at
        )

    # Recovery actions
    action_responses = []
    for action in payment.recovery_actions:
        outcome_success = None
        amount_recovered = None
        if action.outcome:
            outcome_success = action.outcome.success
            amount_recovered = float(action.outcome.amount_recovered) if action.outcome.amount_recovered else 0.0

        action_responses.append(RecoveryActionResponse(
            id=str(action.id),
            action_type=action.action_type,
            action_status=action.action_status,
            attempt_number=action.attempt_number,
            predicted_recovery_prob=action.predicted_recovery_prob,
            policy_decision=action.policy_decision,
            policy_reason=action.policy_reason,
            attempted_at=action.attempted_at,
            outcome_success=outcome_success,
            amount_recovered=amount_recovered
        ))

    return PaymentResponse(
        id=str(payment.id),
        customer_id=str(payment.customer_id),
        merchant_id=str(payment.merchant_id),
        amount=float(payment.amount),
        currency=payment.currency,
        payment_method=payment.payment_method,
        status=payment.status,
        created_at=payment.created_at,
        failure=failure_resp,
        recovery_actions=action_responses,
        attempt_count=len(action_responses)
    )


@router.get(
    "",
    response_model=PaymentListResponse,
    summary="List payments",
    description="Returns a paginated list of payments, optionally filtered by status."
)
def list_payments(
    status: Optional[str] = Query(None, description="Filter by payment status (e.g. FAILED, SUCCESS, RECOVERED)"),
    limit: int = Query(50, ge=1, le=200, description="Number of results per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db)
):
    query = db.query(Payment)

    if status:
        query = query.filter(Payment.status == status)

    total = query.count()
    payments = query.order_by(Payment.created_at.desc()).offset(offset).limit(limit).all()

    return PaymentListResponse(
        payments=[_payment_to_response(p, db) for p in payments],
        total=total,
        limit=limit,
        offset=offset
    )


@router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
    summary="Get payment details",
    description="Returns detailed information for a single payment including failure and recovery history.",
    responses={404: {"description": "Payment not found"}}
)
def get_payment(payment_id: str, db: Session = Depends(get_db)):
    try:
        pid = uuid.UUID(payment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payment ID format")

    payment = db.get(Payment, pid)
    if not payment:
        raise HTTPException(status_code=404, detail=f"Payment {payment_id} not found")

    return _payment_to_response(payment, db)
