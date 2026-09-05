"""
RecoveryService — thin application-layer orchestrator that composes existing
RecoveryOS domain components (Intelligence, Prediction, Decision, Agent, Policy,
Execution) into a single recover() call for the API layer.

This service does NOT contain business logic. It wires together the existing
Phase 1–7 modules.
"""
import logging
import uuid
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from src.database.models import Payment, PaymentFailure, RecoveryAction, RecoveryOutcome
from src.intelligence.extractor import FeatureExtractor
from src.intelligence.taxonomy import get_taxonomy_info
from src.decision.context import DecisionInput, RecoveryActionType
from src.decision.engine import decide
from src.decision.economics import get_intervention_cost
from src.policy.context import PolicyRequest
from src.policy.engine import PolicyEngine
from src.agent.graph import create_recovery_graph
from src.agent.llm import MockLLM
from src.execution.base import ExecutionResult
from src.execution.simulator import DBBackedSimulatorExecutor

import src.agent.nodes as agent_nodes
from unittest.mock import patch

logger = logging.getLogger("recoveryos.service")


class RecoveryService:
    """Application service that orchestrates the full recovery pipeline."""

    def __init__(self, db: Session):
        self.db = db

    def recover(self, payment_id: str) -> Dict[str, Any]:
        """
        Execute the full RecoveryOS pipeline for a single payment:
        1. Load payment & validate state
        2. Extract features (Phase 3)
        3. Predict recovery probability (Phase 4)
        4. Economic decision (Phase 5)
        5. Agent proposal via LangGraph (Phase 7)
        6. Policy validation (Phase 6)
        7. Execution via simulator (Phase 2)
        8. Return structured result
        """
        logger.info("Recovery request received", extra={"payment_id": payment_id})

        # 1. Load and validate payment
        payment = self.db.get(Payment, uuid.UUID(payment_id))
        if not payment:
            raise PaymentNotFoundError(payment_id)

        if payment.status not in ("FAILED", "FAILED_TERMINAL"):
            raise InvalidPaymentStateError(payment_id, payment.status)

        failure = self.db.query(PaymentFailure).filter(
            PaymentFailure.payment_id == payment.id
        ).first()
        if not failure:
            raise PaymentNotFoundError(payment_id, detail="No failure record found")

        # 2. Extract features via existing FeatureExtractor
        logger.info("Extracting recovery context", extra={"payment_id": payment_id})
        extractor = FeatureExtractor(self.db)
        try:
            recovery_context = extractor.extract_context(payment.id)
        except Exception as e:
            logger.error("Feature extraction failed", extra={"payment_id": payment_id, "error": str(e)})
            raise

        # 3. Predict recovery probability via existing model
        logger.info("Predicting recovery probability", extra={"payment_id": payment_id})
        try:
            from src.prediction.model import RecoveryPredictionModel
            model = RecoveryPredictionModel()
            recovery_probability = model.predict_probability(recovery_context)
        except FileNotFoundError:
            # No trained model available — use a reasonable heuristic
            logger.warning("No trained model found, using heuristic probability")
            recovery_probability = 0.5 if failure.is_retryable else 0.1

        # Count previous attempts
        previous_attempts = self.db.query(RecoveryAction).filter(
            RecoveryAction.payment_id == payment.id,
            RecoveryAction.action_status == "EXECUTED"
        ).count()

        # 4. Economic Decision via existing engine
        logger.info("Computing economic decision", extra={"payment_id": payment_id})
        tax_info = get_taxonomy_info(failure.error_code)
        dec_input = DecisionInput(
            payment_id=payment_id,
            amount=float(payment.amount),
            recovery_probability=recovery_probability,
            failure_category=tax_info["category"],
            is_retryable=tax_info["is_retryable"],
            failure_severity=tax_info["severity"],
            customer_risk_score=recovery_context.customer.risk_score,
            previous_attempt_count=previous_attempts,
            payment_method=payment.payment_method or "unknown"
        )
        decision = decide(dec_input)

        # 5. If decision engine says STOP, don't invoke the agent graph
        if decision.recommended_action == RecoveryActionType.STOP:
            logger.info("Decision engine recommends STOP", extra={"payment_id": payment_id, "reason": decision.decision_reason})
            return self._build_response(
                payment=payment,
                recovery_probability=recovery_probability,
                decision=decision,
                policy_result=None,
                execution_status="NOT_EXECUTED",
                final_status=payment.status,
                attempt_count=previous_attempts,
                audit_trail=[{"step": "decision", "action": "STOP", "reason": decision.decision_reason}]
            )

        # 6. Run the LangGraph Agent (which includes policy check and execution)
        logger.info("Invoking LangGraph recovery agent", extra={"payment_id": payment_id})
        executor = DBBackedSimulatorExecutor(self.db)
        
        now = datetime.now(timezone.utc)
        
        last_action = self.db.query(RecoveryAction).filter(
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
        contact_attempts_last_24h = self.db.query(RecoveryAction).filter(
            RecoveryAction.payment_id == payment.id,
            RecoveryAction.action_status == "EXECUTED",
            RecoveryAction.action_type.in_(["SEND_PAYMENT_REMINDER", "SEND_PAYMENT_LINK"]),
            RecoveryAction.attempted_at >= twenty_four_hours_ago.isoformat()
        ).count()

        # Build agent state from real data
        agent_context = {
            "amount": float(payment.amount),
            "failure_category": tax_info["category"],
            "is_retryable": tax_info["is_retryable"],
            "failure_severity": tax_info["severity"],
            "customer_risk_score": recovery_context.customer.risk_score,
            "recovery_probability": recovery_probability,
            "seconds_since_last_attempt": seconds_since_last_attempt,
            "last_action_type": last_action_type,
            "seconds_since_last_action": seconds_since_last_action,
            "contact_attempts_last_24h": contact_attempts_last_24h,
        }

        initial_state = {
            "payment_id": payment_id,
            "recovery_context": agent_context,
            "recovery_probability": recovery_probability,
            "economic_decision": None,
            "proposed_action": None,
            "rationale": None,
            "confidence": None,
            "policy_result": None,
            "execution_result": None,
            "recovery_outcome": None,
            "attempt_number": previous_attempts,
            "status": "PENDING",
            "error": None,
            "audit_metadata": []
        }

        graph = create_recovery_graph(executor, db_session=self.db)
        result_state = graph.invoke(initial_state, config={"recursion_limit": 25})

        logger.info("Recovery agent completed", extra={
            "payment_id": payment_id,
            "final_status": result_state.get("status"),
            "outcome": result_state.get("recovery_outcome")
        })

        # Refresh payment from DB in case it was modified by execution
        self.db.refresh(payment)
        updated_attempts = self.db.query(RecoveryAction).filter(
            RecoveryAction.payment_id == payment.id,
            RecoveryAction.action_status == "EXECUTED"
        ).count()

        # Build structured response from agent result
        policy_result = result_state.get("policy_result")
        execution_result = result_state.get("execution_result")

        return self._build_response(
            payment=payment,
            recovery_probability=recovery_probability,
            decision=decision,
            policy_result=policy_result,
            execution_status=self._derive_execution_status(result_state),
            final_status=payment.status,
            attempt_count=updated_attempts,
            audit_trail=result_state.get("audit_metadata", []),
            execution_result=execution_result,
            proposed_action=result_state.get("proposed_action"),
        )

    def _build_response(self, *, payment, recovery_probability, decision,
                        policy_result, execution_status, final_status,
                        attempt_count, audit_trail, execution_result=None,
                        proposed_action=None) -> Dict[str, Any]:
        """Assemble the structured API response dict."""
        policy_resp = None
        if policy_result:
            policy_resp = {
                "allowed": policy_result.get("allowed", False),
                "rule": policy_result.get("policy_rule"),
                "reason": policy_result.get("reason"),
            }

        exec_resp = None
        if execution_result:
            exec_resp = {
                "status": "SUCCESS" if execution_result.get("success") else "FAILED",
                "amount_recovered": execution_result.get("amount_recovered", 0.0),
                "error_message": execution_result.get("error_message"),
            }
        elif execution_status:
            exec_resp = {
                "status": execution_status,
                "amount_recovered": 0.0,
                "error_message": None,
            }

        return {
            "payment_id": str(payment.id),
            "recovery_probability": round(recovery_probability, 4),
            "recommended_action": (proposed_action or decision.recommended_action.value),
            "expected_recovery_value": round(decision.economics.gross_recovery_value, 2),
            "intervention_cost": round(decision.economics.intervention_cost, 2),
            "expected_net_value": round(decision.economics.expected_net_value, 2),
            "policy": policy_resp,
            "execution": exec_resp,
            "final_status": final_status,
            "attempt_count": attempt_count,
            "audit_trail": audit_trail,
        }

    def _derive_execution_status(self, state: dict) -> str:
        status = state.get("status", "UNKNOWN")
        if status == "SUCCESS":
            return "SUCCESS"
        elif status == "STOPPED":
            return "STOPPED"
        elif state.get("error"):
            return "ERROR"
        return "FAILED"


class PaymentNotFoundError(Exception):
    def __init__(self, payment_id: str, detail: str = "Payment not found"):
        self.payment_id = payment_id
        self.detail = detail
        super().__init__(detail)


class InvalidPaymentStateError(Exception):
    def __init__(self, payment_id: str, current_status: str):
        self.payment_id = payment_id
        self.current_status = current_status
        self.detail = f"Payment {payment_id} is in state '{current_status}', expected FAILED or FAILED_TERMINAL"
        super().__init__(self.detail)
