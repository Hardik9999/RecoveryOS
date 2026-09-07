"""
Tests for Phase 9: Closed-Loop State Reconstruction and Economic Authority.
"""
import pytest
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from src.agent.graph import create_recovery_graph
from src.agent.llm import MockLLM
from src.execution.base import RecoveryExecutor, ExecutionResult
from src.decision.context import RecoveryActionType
from src.database.models import Payment, PaymentFailure, RecoveryAction, Base, Customer, Merchant
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.agent.nodes
from unittest.mock import patch

class MockExecutor(RecoveryExecutor):
    def __init__(self, db, predefined_outcomes=None):
        self.db = db
        self.predefined_outcomes = predefined_outcomes or {}
        self.execution_calls = []

    def execute(self, payment_id: str, action: RecoveryActionType, attempt_number: int) -> ExecutionResult:
        self.execution_calls.append((action.value, attempt_number))
        
        success = self.predefined_outcomes.get(attempt_number, True)
        
        action_record = RecoveryAction(
            id=uuid.uuid4(),
            payment_id=uuid.UUID(payment_id),
            action_type=action.value,
            action_status="EXECUTED",
            attempted_at=(datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        )
        self.db.add(action_record)
        self.db.commit()

        return ExecutionResult(
            payment_id=payment_id,
            action_type=action,
            success=success,
            amount_recovered=500.0 if success else 0.0,
            gateway_response={"status": "mocked"},
            error_message=""
        )


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def mock_llm_provider():
    mock_llm = MockLLM()
    with patch.object(src.agent.nodes, 'get_llm_provider', return_value=mock_llm):
        yield mock_llm


def setup_test_db(db_session, failure_code="VISA:05", amount=500.0):
    merchant_id = str(uuid.uuid4())
    merchant = Merchant(
        id=merchant_id,
        name="Test Merchant",
        category="ecommerce"
    )
    
    customer_id = str(uuid.uuid4())
    customer = Customer(
        id=customer_id,
        merchant_id=merchant_id,
        email="test@example.com",
        risk_score=0.1
    )
    payment_id = uuid.uuid4()
    payment = Payment(
        id=payment_id,
        amount=amount,
        currency="INR",
        payment_method="card",
        status="FAILED",
        merchant_id=merchant_id,
        customer_id=customer_id,
        created_at=datetime.now(timezone.utc).isoformat()
    )
    failure = PaymentFailure(
        id=uuid.uuid4(),
        payment_id=payment_id,
        error_code=failure_code,
        error_message="Insufficient Funds"
    )
    db_session.add(merchant)
    db_session.add(customer)
    db_session.add(payment)
    db_session.add(failure)
    db_session.commit()
    return str(payment_id)


def test_closed_loop_state_reconstruction(db_session, mock_llm_provider):
    """
    Test that after a failure, the graph correctly re-queries the DB,
    identifies the new attempt count, cooldowns, and updates the state.
    """
    payment_id = setup_test_db(db_session, failure_code="VISA:05")
    
    # We want it to fail on first attempt, then succeed on second attempt.
    executor = MockExecutor(db=db_session, predefined_outcomes={1: False, 2: True})
    
    # Let LLM always propose RETRY
    mock_llm_provider.predefined_responses = {
        "BANK": {"action": "RETRY", "rationale": "try again", "confidence": 0.8}
    }
    
    graph = create_recovery_graph(executor, db_session=db_session)
    
    initial_state = {
        "payment_id": payment_id,
        "status": "PENDING"
    }
    
    result = graph.invoke(initial_state, config={"recursion_limit": 15})
    
    # Should have executed twice
    assert len(executor.execution_calls) == 2
    assert executor.execution_calls[0] == ("SEND_PAYMENT_LINK", 1)
    assert executor.execution_calls[1] == ("SEND_PAYMENT_LINK", 2)
    
    # Attempt count from the DB state at the end should be 2
    assert result["attempt_number"] == 2
    
    # Validate audit trails show the loops
    steps = [audit["step"] for audit in result["audit_metadata"]]
    assert steps == [
        "load_context", "propose_action", "policy_check", "execute_action",
        "load_context", "propose_action", "policy_check", "execute_action"
    ]


def test_economic_authority_override(db_session, mock_llm_provider):
    """
    Test that if the LLM proposes an action that is NOT economically viable,
    the propose_action_node overrides it to the economic recommendation.
    """
    payment_id = setup_test_db(db_session, failure_code="VISA:05", amount=100.0) # Small amount so ESCALATE has negative EV
    
    # ESCALATE has an intervention cost of 1000. For a 100 INR payment, it's negative EV.
    # We force the LLM to propose ESCALATE.
    mock_llm_provider.predefined_responses = {
        "BANK": {"action": "ESCALATE", "rationale": "Agent goes rogue", "confidence": 0.9}
    }
    
    executor = MockExecutor(db=db_session, predefined_outcomes={1: True})
    graph = create_recovery_graph(executor, db_session=db_session)
    
    initial_state = {
        "payment_id": payment_id,
        "status": "PENDING"
    }
    
    result = graph.invoke(initial_state, config={"recursion_limit": 15})
    
    # Check that execution call was NOT escalate!
    assert len(executor.execution_calls) == 1
    executed_action = executor.execution_calls[0][0]
    
    assert executed_action != "ESCALATE"
    assert result["proposed_action"] == executed_action
    
    # Verify the audit log explicitly mentions the override
    propose_audit = next(a for a in result["audit_metadata"] if a["step"] == "propose_action")
    assert propose_audit["details"]["original_proposal"] == "ESCALATE"
    assert "OVERRIDDEN BY ECONOMIC ENGINE" in propose_audit["details"]["rationale"]
