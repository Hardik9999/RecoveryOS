"""
Recovery endpoints — single payment recovery and batch recovery.
Delegates all business logic to RecoveryService which composes the existing
Phase 1–7 components.
"""
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.api.schemas.recovery import (
    RecoveryResponse, PolicyResponse, ExecutionResponse,
    BatchRecoveryRequest, BatchRecoveryResponse, BatchRecoveryItem
)
from src.services.recovery_service import (
    RecoveryService, PaymentNotFoundError, InvalidPaymentStateError
)
from src.database.models import Payment
from src.decision.economics import get_intervention_cost
from src.decision.context import RecoveryActionType

logger = logging.getLogger("recoveryos.api.recovery")

router = APIRouter(tags=["Recovery"])


@router.post(
    "/payments/{payment_id}/recover",
    response_model=RecoveryResponse,
    summary="Recover a failed payment",
    description=(
        "Invokes the full RecoveryOS pipeline for a single failed payment: "
        "feature extraction → prediction → economic decision → agent proposal → "
        "policy validation → execution → outcome."
    ),
    responses={
        404: {"description": "Payment not found"},
        409: {"description": "Payment is not in a recoverable state"},
        500: {"description": "Internal recovery error"}
    }
)
def recover_payment(payment_id: str, db: Session = Depends(get_db)):
    try:
        uuid.UUID(payment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payment ID format")

    service = RecoveryService(db)
    try:
        result = service.recover(payment_id)
    except PaymentNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.detail)
    except InvalidPaymentStateError as e:
        raise HTTPException(status_code=409, detail=e.detail)
    except Exception as e:
        logger.error("Recovery failed", extra={"payment_id": payment_id, "error": str(e)})
        raise HTTPException(status_code=500, detail=f"Recovery failed: {str(e)}")

    # Map result dict to response schema
    policy = None
    if result.get("policy"):
        policy = PolicyResponse(**result["policy"])

    execution = None
    if result.get("execution"):
        execution = ExecutionResponse(**result["execution"])

    return RecoveryResponse(
        payment_id=result["payment_id"],
        recovery_probability=result.get("recovery_probability"),
        recommended_action=result.get("recommended_action"),
        expected_recovery_value=result.get("expected_recovery_value"),
        intervention_cost=result.get("intervention_cost"),
        expected_net_value=result.get("expected_net_value"),
        policy=policy,
        execution=execution,
        final_status=result["final_status"],
        attempt_count=result.get("attempt_count", 0),
        audit_trail=result.get("audit_trail", [])
    )


@router.post(
    "/recovery/batch",
    response_model=BatchRecoveryResponse,
    summary="Run batch recovery",
    description=(
        "Processes a batch of eligible failed payments through the RecoveryOS pipeline. "
        "Maximum batch size is 500."
    )
)
def batch_recovery(request: BatchRecoveryRequest, db: Session = Depends(get_db)):
    logger.info("Batch recovery started", extra={"limit": request.limit})

    # Find eligible payments: FAILED status (not FAILED_TERMINAL, not already RECOVERED)
    eligible = db.query(Payment).filter(
        Payment.status == "FAILED"
    ).limit(request.limit).all()

    service = RecoveryService(db)
    details = []
    total_revenue_at_risk = 0.0
    total_revenue_recovered = 0.0
    total_intervention_cost = 0.0
    recovered_count = 0
    failed_count = 0
    stopped_count = 0
    policy_denied_count = 0
    intervention_count = 0

    for payment in eligible:
        pid = str(payment.id)
        total_revenue_at_risk += float(payment.amount)

        try:
            result = service.recover(pid)
            final_status = result["final_status"]
            action = result.get("recommended_action")
            is_recovered = final_status == "RECOVERED"

            if is_recovered:
                recovered_count += 1
                amt = float(payment.amount)
                total_revenue_recovered += amt

            exec_status = (result.get("execution") or {}).get("status")
            policy_allowed = (result.get("policy") or {}).get("allowed")

            if final_status == "STOPPED" or exec_status == "STOPPED":
                stopped_count += 1
            elif not is_recovered and policy_allowed is False:
                policy_denied_count += 1
            elif not is_recovered:
                failed_count += 1

            # Count intervention cost if an action was executed
            if action and action != "STOP":
                try:
                    cost = get_intervention_cost(RecoveryActionType(action))
                    total_intervention_cost += cost
                    intervention_count += 1
                except (ValueError, KeyError):
                    pass

            details.append(BatchRecoveryItem(
                payment_id=pid,
                status=final_status,
                action=action,
                recovered=is_recovered,
                amount_recovered=float(payment.amount) if is_recovered else 0.0
            ))

        except Exception as e:
            logger.error("Batch item failed", extra={"payment_id": pid, "error": str(e)})
            failed_count += 1
            details.append(BatchRecoveryItem(
                payment_id=pid,
                status="ERROR",
                action=None,
                recovered=False,
                amount_recovered=0.0
            ))

    logger.info("Batch recovery completed", extra={
        "processed": len(details),
        "recovered": recovered_count,
        "stopped": stopped_count,
    })

    return BatchRecoveryResponse(
        payments_processed=len(details),
        payments_recovered=recovered_count,
        payments_failed=failed_count,
        payments_stopped=stopped_count,
        payments_policy_denied=policy_denied_count,
        revenue_at_risk=round(total_revenue_at_risk, 2),
        revenue_recovered=round(total_revenue_recovered, 2),
        intervention_count=intervention_count,
        intervention_cost=round(total_intervention_cost, 2),
        net_recovered_value=round(total_revenue_recovered - total_intervention_cost, 2),
        details=details
    )
