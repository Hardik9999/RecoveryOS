"""
Analytics endpoint — computes aggregate recovery metrics from the database.
"""
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.api.dependencies import get_db
from src.api.schemas.analytics import AnalyticsSummaryResponse
from src.database.models import Payment, RecoveryAction, RecoveryOutcome
from src.decision.economics import INTERVENTION_COSTS
from src.decision.context import RecoveryActionType

logger = logging.getLogger("recoveryos.api.analytics")

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get(
    "/summary",
    response_model=AnalyticsSummaryResponse,
    summary="Recovery analytics summary",
    description="Returns aggregate recovery metrics computed from actual database records."
)
def analytics_summary(db: Session = Depends(get_db)):
    # Total payments
    total_payments = db.query(func.count(Payment.id)).scalar() or 0

    # Failed payments (FAILED + FAILED_TERMINAL)
    total_failed = db.query(func.count(Payment.id)).filter(
        Payment.status.in_(["FAILED", "FAILED_TERMINAL"])
    ).scalar() or 0

    # Recovered payments
    total_recovered = db.query(func.count(Payment.id)).filter(
        Payment.status == "RECOVERED"
    ).scalar() or 0

    # Terminal payments
    total_terminal = db.query(func.count(Payment.id)).filter(
        Payment.status == "FAILED_TERMINAL"
    ).scalar() or 0

    # Revenue at risk: sum of amounts for all non-SUCCESS payments
    revenue_at_risk_result = db.query(func.sum(Payment.amount)).filter(
        Payment.status.in_(["FAILED", "FAILED_TERMINAL", "RECOVERED"])
    ).scalar()
    revenue_at_risk = float(revenue_at_risk_result) if revenue_at_risk_result else 0.0

    # Revenue recovered: sum of amounts for RECOVERED payments
    revenue_recovered_result = db.query(func.sum(Payment.amount)).filter(
        Payment.status == "RECOVERED"
    ).scalar()
    revenue_recovered = float(revenue_recovered_result) if revenue_recovered_result else 0.0

    # Recovery rate
    recovery_denominator = total_failed + total_recovered  # all payments that were ever failed
    recovery_rate = (total_recovered / recovery_denominator) if recovery_denominator > 0 else None

    # Interventions: count of executed recovery actions
    interventions = db.query(func.count(RecoveryAction.id)).filter(
        RecoveryAction.action_status == "EXECUTED"
    ).scalar() or 0

    # Escalations
    escalations = db.query(func.count(RecoveryAction.id)).filter(
        RecoveryAction.action_status == "EXECUTED",
        RecoveryAction.action_type == "ESCALATE"
    ).scalar() or 0

    # STOP actions: FAILED_TERMINAL payments with no EXECUTED actions
    payments_with_executed_actions = db.query(RecoveryAction.payment_id).filter(
        RecoveryAction.action_status == "EXECUTED"
    ).distinct().subquery()
    
    stopped_payments = db.query(func.count(Payment.id)).filter(
        Payment.status == "FAILED_TERMINAL",
        ~Payment.id.in_(db.query(payments_with_executed_actions))
    ).scalar() or 0

    # Policy Denied
    policy_denied_count = db.query(func.count(RecoveryAction.id)).filter(
        RecoveryAction.action_status == "POLICY_DENIED"
    ).scalar() or 0
    # Interventions avoided: failed payments that were never acted on
    payments_with_actions = db.query(RecoveryAction.payment_id).distinct().subquery()
    interventions_avoided = db.query(func.count(Payment.id)).filter(
        Payment.status.in_(["FAILED", "FAILED_TERMINAL"]),
        ~Payment.id.in_(db.query(payments_with_actions))
    ).scalar() or 0

    # Intervention cost: compute from action types × cost model
    executed_actions = db.query(RecoveryAction.action_type).filter(
        RecoveryAction.action_status == "EXECUTED"
    ).all()
    intervention_cost = 0.0
    for (action_type,) in executed_actions:
        try:
            intervention_cost += INTERVENTION_COSTS.get(RecoveryActionType(action_type), 0.0)
        except (ValueError, KeyError):
            pass

    net_recovered_value = revenue_recovered - intervention_cost

    # Average attempts per recovered payment
    if total_recovered > 0:
        total_attempts = db.query(func.count(RecoveryAction.id)).filter(
            RecoveryAction.action_status == "EXECUTED",
            RecoveryAction.payment_id.in_(
                db.query(Payment.id).filter(Payment.status == "RECOVERED")
            )
        ).scalar() or 0
        average_attempts = total_attempts / total_recovered
    else:
        average_attempts = None

    return AnalyticsSummaryResponse(
        total_payments=total_payments,
        total_failed=total_failed,
        total_recovered=total_recovered,
        total_terminal=total_terminal,
        revenue_at_risk=round(revenue_at_risk, 2),
        revenue_recovered=round(revenue_recovered, 2),
        recovery_rate=round(recovery_rate, 4) if recovery_rate is not None else None,
        interventions=interventions,
        interventions_avoided=interventions_avoided,
        escalations=escalations,
        stopped_payments=stopped_payments,
        policy_denied_count=policy_denied_count,
        intervention_cost=round(intervention_cost, 2),
        net_recovered_value=round(net_recovered_value, 2),
        average_attempts=round(average_attempts, 2) if average_attempts is not None else None
    )
