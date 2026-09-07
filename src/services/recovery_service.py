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
        2. Graph Execution (which internally loads context, decides, proposes, policy checks, executes, loops)
        3. Return structured result
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

        # 2. Run the LangGraph Agent (which handles full context loading, decision, policy, execution)
        logger.info("Invoking LangGraph recovery agent", extra={"payment_id": payment_id})
        executor = DBBackedSimulatorExecutor(self.db)
        
        initial_state = {
            "payment_id": payment_id,
            "recovery_context": None,
            "recovery_probability": None,
            "economic_decision": None,
            "proposed_action": None,
            "rationale": None,
            "confidence": None,
            "policy_result": None,
            "execution_result": None,
            "recovery_outcome": None,
            "attempt_number": 0,
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

        # Build structured response from agent result
        return self._build_response(payment, result_state)

    def _build_response(self, payment, state: dict) -> Dict[str, Any]:
        """Assemble the structured API response dict from the final graph state."""
        policy_result = state.get("policy_result")
        policy_resp = None
        if policy_result:
            policy_resp = {
                "allowed": policy_result.get("allowed", False),
                "rule": policy_result.get("policy_rule"),
                "reason": policy_result.get("reason"),
            }

        execution_result = state.get("execution_result")
        execution_status = self._derive_execution_status(state)
        
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
            
        econ_decision = state.get("economic_decision", {})

        return {
            "payment_id": str(payment.id),
            "recovery_probability": round(state.get("recovery_probability") or 0.0, 4),
            "recommended_action": state.get("proposed_action") or econ_decision.get("recommended_action", "STOP"),
            "expected_recovery_value": round(econ_decision.get("gross_recovery_value", 0.0), 2),
            "intervention_cost": round(econ_decision.get("intervention_cost", 0.0), 2),
            "expected_net_value": round(econ_decision.get("expected_net_value", 0.0), 2),
            "policy": policy_resp,
            "execution": exec_resp,
            "final_status": payment.status,
            "attempt_count": state.get("attempt_number", 0),
            "audit_trail": state.get("audit_metadata", []),
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
