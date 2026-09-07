"""
LangGraph Nodes for the Recovery Agent.
"""
from datetime import datetime, timezone, timedelta
import uuid
from src.agent.state import RecoveryState, AuditRecord
from src.agent.schemas import AgentActionProposal
from src.agent.llm import get_llm_provider
from src.decision.context import DecisionInput, RecoveryActionType
from src.decision.engine import decide
from src.policy.context import PolicyRequest
from src.policy.engine import PolicyEngine
from src.execution.base import RecoveryExecutor
from sqlalchemy.orm import Session
from src.database.models import Payment, PaymentFailure, RecoveryAction
from src.intelligence.extractor import FeatureExtractor
from src.intelligence.taxonomy import get_taxonomy_info
import json

def get_current_time_str() -> str:
    return datetime.now(timezone.utc).isoformat()

def create_audit_record(step: str, details: dict) -> AuditRecord:
    return {"step": step, "timestamp": get_current_time_str(), "details": details}

def load_context_node(state: RecoveryState, db_session: Session) -> RecoveryState:
    """
    Dynamically reconstructs state from the database on every invocation.
    Ensures that retries, cooldowns, and intelligence are fresh.
    """
    payment_id = state["payment_id"]
    payment = db_session.get(Payment, uuid.UUID(payment_id))
    failure = db_session.query(PaymentFailure).filter(PaymentFailure.payment_id == payment.id).first()
    
    extractor = FeatureExtractor(db_session)
    recovery_context = extractor.extract_context(payment.id)
    
    try:
        from src.prediction.model import RecoveryPredictionModel
        model = RecoveryPredictionModel()
        prob = model.predict_probability(recovery_context)
    except FileNotFoundError:
        prob = 0.5 if failure.is_retryable else 0.1

    # Fetch attempts and last actions from DB
    previous_attempts = db_session.query(RecoveryAction).filter(
        RecoveryAction.payment_id == payment.id,
        RecoveryAction.action_status == "EXECUTED"
    ).count()

    now = datetime.now(timezone.utc)
    last_action = db_session.query(RecoveryAction).filter(
        RecoveryAction.payment_id == payment.id,
        RecoveryAction.action_status == "EXECUTED"
    ).order_by(RecoveryAction.attempted_at.desc()).first()
    
    seconds_since_last_action = None
    seconds_since_last_attempt = None
    last_action_type = None

    if last_action:
        last_action_type = last_action.action_type
        last_attempted_at = datetime.fromisoformat(last_action.attempted_at)
        if last_attempted_at.tzinfo is None:
            last_attempted_at = last_attempted_at.replace(tzinfo=timezone.utc)
        seconds_since_last_action = int((now - last_attempted_at).total_seconds())
        seconds_since_last_attempt = seconds_since_last_action
        
    twenty_four_hours_ago = now - timedelta(hours=24)
    contact_attempts_last_24h = db_session.query(RecoveryAction).filter(
        RecoveryAction.payment_id == payment.id,
        RecoveryAction.action_status == "EXECUTED",
        RecoveryAction.action_type.in_(["SEND_PAYMENT_REMINDER", "SEND_PAYMENT_LINK"]),
        RecoveryAction.attempted_at >= twenty_four_hours_ago.isoformat()
    ).count()

    tax_info = get_taxonomy_info(failure.error_code)

    agent_context = {
        "amount": float(payment.amount),
        "failure_category": tax_info["category"],
        "is_retryable": tax_info["is_retryable"],
        "failure_severity": tax_info["severity"],
        "customer_risk_score": recovery_context.customer.risk_score,
        "recovery_probability": prob,
        "seconds_since_last_attempt": seconds_since_last_attempt,
        "last_action_type": last_action_type,
        "seconds_since_last_action": seconds_since_last_action,
        "contact_attempts_last_24h": contact_attempts_last_24h,
        "error_code": failure.error_code if failure else "",
    }

    dec_input = DecisionInput(
        payment_id=payment_id,
        amount=float(payment.amount),
        error_code=failure.error_code,
        network=tax_info.get("network"),
        recovery_probability=prob,
        failure_category=tax_info["category"],
        is_retryable=tax_info["is_retryable"],
        failure_severity=tax_info["severity"],
        customer_risk_score=recovery_context.customer.risk_score,
        previous_attempt_count=previous_attempts,
        payment_method=payment.payment_method or "unknown"
    )
    
    decision_output = decide(dec_input)
    
    new_audit = create_audit_record("load_context", {
        "recommended_action": decision_output.recommended_action.value,
        "economic_reasoning": decision_output.decision_reason
    })
    
    return {
        **state,
        "recovery_context": agent_context,
        "attempt_number": previous_attempts,
        "recovery_probability": prob,
        "economic_decision": {
            "recommended_action": decision_output.recommended_action.value,
            "economically_viable_actions": [a.value for a in decision_output.economically_viable_actions],
            "expected_net_value": decision_output.economics.expected_net_value,
            "gross_recovery_value": decision_output.economics.gross_recovery_value,
            "intervention_cost": decision_output.economics.intervention_cost,
            "decision_reason": decision_output.decision_reason
        },
        "audit_metadata": state.get("audit_metadata", []) + [new_audit],
        "status": "IN_PROGRESS"
    }

def propose_action_node(state: RecoveryState) -> RecoveryState:
    """LLM node to propose the next action."""
    llm = get_llm_provider()
    
    # Build a concise summary for the LLM
    context_summary = json.dumps({
        "payment_id": state["payment_id"],
        "context": state["recovery_context"],
        "probability": state["recovery_probability"],
        "economic_decision": state["economic_decision"],
        "attempt_number": state["attempt_number"],
        "previous_policy_result": state.get("policy_result")
    }, indent=2)
    
    proposal = llm.propose_action(context_summary, AgentActionProposal)
    proposed_action_value = proposal.action.value
    
    # ENFORCE ECONOMIC AUTHORITY
    viable_actions = state["economic_decision"].get("economically_viable_actions", [])
    
    # Always allow the LLM to STOP (abort the recovery safely)
    if "STOP" not in viable_actions:
        viable_actions = viable_actions + ["STOP"]

    # Fallback to recommended action if the proposed one isn't economically viable
    if proposed_action_value not in viable_actions:
        fallback_action = state["economic_decision"]["recommended_action"]
        audit_details = {
            "action": fallback_action,
            "original_proposal": proposed_action_value,
            "rationale": "OVERRIDDEN BY ECONOMIC ENGINE. Proposal was not economically viable.",
            "confidence": proposal.confidence
        }
        proposed_action_value = fallback_action
        rationale = audit_details["rationale"]
    else:
        audit_details = {
            "action": proposed_action_value,
            "rationale": proposal.rationale,
            "confidence": proposal.confidence
        }
        rationale = proposal.rationale

    new_audit = create_audit_record("propose_action", audit_details)
    
    return {
        **state,
        "proposed_action": proposed_action_value,
        "rationale": rationale,
        "confidence": proposal.confidence,
        "audit_metadata": state.get("audit_metadata", []) + [new_audit]
    }

def policy_check_node(state: RecoveryState) -> RecoveryState:
    """Validates the LLM's proposed action against the deterministic Policy Engine."""
    ctx = state.get("recovery_context", {})
    
    req = PolicyRequest(
        payment_id=state["payment_id"],
        proposed_action=RecoveryActionType(state["proposed_action"]),
        amount=ctx.get("amount", 500.0),
        failure_category=ctx.get("failure_category", "BANK"),
        is_retryable=ctx.get("is_retryable", True),
        failure_severity=ctx.get("failure_severity", "MEDIUM"),
        customer_risk_score=ctx.get("customer_risk_score", 0.3),
        previous_attempt_count=state.get("attempt_number", 0),
        seconds_since_last_attempt=ctx.get("seconds_since_last_attempt"),
        last_action_type=ctx.get("last_action_type"),
        seconds_since_last_action=ctx.get("seconds_since_last_action"),
        contact_attempts_last_24h=ctx.get("contact_attempts_last_24h", 0),
        payment_method="unknown",
        error_code=state["recovery_context"].get("error_code", "")
    )
    
    engine = PolicyEngine()
    result = engine.evaluate(req)
    
    result_dict = {
        "allowed": result.allowed,
        "action": result.action.value,
        "reason": result.reason,
        "policy_rule": result.policy_rule,
        "violations": [{"rule": v.rule, "reason": v.reason} for v in result.violations]
    }
    
    new_audit = create_audit_record("policy_check", result_dict)
    
    return {
        **state,
        "policy_result": result_dict,
        "audit_metadata": state.get("audit_metadata", []) + [new_audit]
    }

def execute_action_node(state: RecoveryState, executor: RecoveryExecutor) -> RecoveryState:
    """Executes the action IF policy allowed it."""
    # Hard safety check
    if not state.get("policy_result", {}).get("allowed", False):
        new_audit = create_audit_record("execute_action", {"error": "Bypassed execution due to policy DENY"})
        return {
            **state,
            "status": "STOPPED",
            "error": "Policy DENY prevented execution",
            "audit_metadata": state.get("audit_metadata", []) + [new_audit]
        }
        
    action_type = RecoveryActionType(state["proposed_action"])
    
    # STOP action does not execute anything against gateway
    if action_type == RecoveryActionType.STOP:
        new_audit = create_audit_record("execute_action", {"note": "Action was STOP. Halting."})
        return {
            **state,
            "status": "STOPPED",
            "recovery_outcome": "STOPPED",
            "audit_metadata": state.get("audit_metadata", []) + [new_audit]
        }

    attempt_number = state.get("attempt_number", 0) + 1
    
    res = executor.execute(state["payment_id"], action_type, attempt_number)
    
    result_dict = {
        "success": res.success,
        "amount_recovered": res.amount_recovered,
        "error_message": res.error_message,
        "gateway_response": res.gateway_response
    }
    
    new_audit = create_audit_record("execute_action", result_dict)
    
    return {
        **state,
        "execution_result": result_dict,
        "attempt_number": attempt_number,
        "recovery_outcome": "SUCCESS" if res.success else "FAILURE",
        "status": "SUCCESS" if res.success else "IN_PROGRESS",
        "audit_metadata": state.get("audit_metadata", []) + [new_audit]
    }
