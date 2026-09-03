"""
LangGraph Nodes for the Recovery Agent.
"""
from datetime import datetime, timezone
from src.agent.state import RecoveryState, AuditRecord
from src.agent.schemas import AgentActionProposal
from src.agent.llm import get_llm_provider
from src.decision.context import DecisionInput, RecoveryActionType
from src.decision.engine import decide
from src.policy.context import PolicyRequest
from src.policy.engine import PolicyEngine
from src.execution.base import RecoveryExecutor
from sqlalchemy.orm import Session
import json

def get_current_time_str() -> str:
    return datetime.now(timezone.utc).isoformat()

def create_audit_record(step: str, details: dict) -> AuditRecord:
    return {"step": step, "timestamp": get_current_time_str(), "details": details}

def load_context_node(state: RecoveryState, db_session: Session) -> RecoveryState:
    """
    Loads features, prediction, and economic decision.
    (For this phase, we mock the heavy DB feature extraction and use static dummy data,
    or we can construct a DecisionInput from state context).
    """
    # In a real app, this would use FeatureExtractor and PredictionModel.
    # We will simulate the DecisionInput based on what is in state['recovery_context'].
    ctx = state.get("recovery_context", {})
    
    # Defaults if missing for testing
    amount = ctx.get("amount", 500.0)
    prob = state.get("recovery_probability") or ctx.get("recovery_probability", 0.5)
    
    dec_input = DecisionInput(
        payment_id=state["payment_id"],
        amount=amount,
        recovery_probability=prob,
        failure_category=ctx.get("failure_category", "BANK"),
        is_retryable=ctx.get("is_retryable", True),
        failure_severity=ctx.get("failure_severity", "MEDIUM"),
        customer_risk_score=ctx.get("customer_risk_score", 0.3),
        previous_attempt_count=state.get("attempt_number", 0),
        payment_method="card"
    )
    
    decision_output = decide(dec_input)
    
    new_audit = create_audit_record("load_context", {
        "recommended_action": decision_output.recommended_action.value,
        "economic_reasoning": decision_output.decision_reason
    })
    
    return {
        **state,
        "recovery_probability": prob,
        "economic_decision": {
            "recommended_action": decision_output.recommended_action.value,
            "expected_net_value": decision_output.economics.expected_net_value,
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
    
    new_audit = create_audit_record("propose_action", {
        "action": proposal.action.value,
        "rationale": proposal.rationale,
        "confidence": proposal.confidence
    })
    
    return {
        **state,
        "proposed_action": proposal.action.value,
        "rationale": proposal.rationale,
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
        contact_attempts_last_24h=ctx.get("contact_attempts_last_24h", 0)
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
