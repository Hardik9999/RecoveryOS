"""
Tests for Phase 9: Closed-Loop State Reconstruction and Economic Authority.
"""
import pytest
import uuid
import datetime
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

class Clock:
    def __init__(self):
        self.current = datetime.datetime.now(datetime.timezone.utc)
    def advance(self, minutes=0):
        self.current += datetime.timedelta(minutes=minutes)
    def now(self, tz=None):
        return self.current

@pytest.fixture
def mock_clock():
    clock = Clock()
    with patch('src.agent.nodes.datetime') as mock_dt:
        mock_dt.now.side_effect = clock.now
        mock_dt.fromisoformat = datetime.datetime.fromisoformat
        mock_dt.timezone = datetime.timezone
        mock_dt.timedelta = datetime.timedelta
        yield clock

class MockExecutor(RecoveryExecutor):
    def __init__(self, db, clock, predefined_outcomes=None):
        self.db = db
        self.clock = clock
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
            attempted_at=self.clock.now(datetime.timezone.utc).isoformat()
        )
        self.db.add(action_record)
        
        if success:
            payment = self.db.get(Payment, uuid.UUID(payment_id))
            payment.status = "RECOVERED"
            
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
        created_at=datetime.datetime.now(datetime.timezone.utc).isoformat()
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


def test_closed_loop_step_by_step(db_session, mock_llm_provider, mock_clock):
    """
    Test A, B, C, E, F, G behavior step-by-step.
    """
    payment_id = setup_test_db(db_session, failure_code="VISA:05")
    executor = MockExecutor(db=db_session, clock=mock_clock, predefined_outcomes={1: False, 2: True})
    mock_llm_provider.predefined_responses = {
        "BANK": {"action": "SEND_PAYMENT_LINK", "rationale": "try again", "confidence": 0.8}
    }
    
    # Step 1: Load Context
    state1 = src.agent.nodes.load_context_node({"payment_id": payment_id}, db_session)
    assert state1["attempt_number"] == 0
    assert state1["recovery_context"]["last_action_type"] is None
    
    # Step 2: Propose Action & Policy Check & Execute
    state2 = src.agent.nodes.propose_action_node(state1)
    state3 = src.agent.nodes.policy_check_node(state2)
    assert state3["policy_result"]["allowed"] is True
    
    state4 = src.agent.nodes.execute_action_node(state3, executor)
    assert state4["status"] == "IN_PROGRESS"
    assert state4["attempt_number"] == 1
    
    # Immediately Load Context Again (No clock advance)
    state5 = src.agent.nodes.load_context_node(state4, db_session)
    # Test A: Attempt count updated
    assert state5["attempt_number"] == 1
    # Test B: Last action updated
    assert state5["recovery_context"]["last_action_type"] == "SEND_PAYMENT_LINK"
    # Test F & G: Economics and prediction refreshed (they are recalculated)
    assert state5["economic_decision"] is not None
    
    # Propose Action & Policy Check
    state6 = src.agent.nodes.propose_action_node(state5)
    state7 = src.agent.nodes.policy_check_node(state6)
    
    # Test C: Cooldown block
    assert state7["policy_result"]["allowed"] is False
    assert state7["policy_result"]["policy_rule"] == "IDEMPOTENCY"
    
    # Advance time by 6 minutes to bypass cooldown
    mock_clock.advance(minutes=6)
    
    state8 = src.agent.nodes.load_context_node(state7, db_session)
    state9 = src.agent.nodes.propose_action_node(state8)
    state10 = src.agent.nodes.policy_check_node(state9)
    assert state10["policy_result"]["allowed"] is True
    
    # Execute (MockExecutor returns success for attempt 2)
    state11 = src.agent.nodes.execute_action_node(state10, executor)
    assert state11["status"] == "SUCCESS"
    
    # Test E: Payment Status
    payment = db_session.get(Payment, uuid.UUID(payment_id))
    assert payment.status == "RECOVERED"


def test_contact_frequency(db_session, mock_llm_provider, mock_clock):
    """Test D: Contact Frequency Policy"""
    payment_id = setup_test_db(db_session, failure_code="VISA:05")
    executor = MockExecutor(db=db_session, clock=mock_clock, predefined_outcomes={1: False, 2: False, 3: False})
    
    mock_llm_provider.predefined_responses = {
        "BANK": {"action": "SEND_PAYMENT_LINK", "rationale": "spam", "confidence": 0.8}
    }
    
    # Patch policy constant for test so we can hit it before max attempts
    with patch('src.policy.rules.POLICY_MAX_CONTACT_PER_24H', 2):
        # Run 2 times, advancing clock by 1 hour each time to bypass cooldown but stay in 24h window
        state = {"payment_id": payment_id}
        
        for i in range(1, 3):
            state = src.agent.nodes.load_context_node(state, db_session)
            state = src.agent.nodes.propose_action_node(state)
            state = src.agent.nodes.policy_check_node(state)
            assert state["policy_result"]["allowed"] is True, f"Failed at loop {i}"
            state = src.agent.nodes.execute_action_node(state, executor)
            mock_clock.advance(minutes=60)
            
        # 3rd attempt should be blocked by frequency rule
        state = src.agent.nodes.load_context_node(state, db_session)
        assert state["recovery_context"]["contact_attempts_last_24h"] == 2
        
        state = src.agent.nodes.propose_action_node(state)
        state = src.agent.nodes.policy_check_node(state)
        
        assert state["policy_result"]["allowed"] is False
        assert state["policy_result"]["policy_rule"] == "CONTACT_FREQUENCY"

def test_economic_authority_override(db_session, mock_llm_provider, mock_clock):
    """
    Test that if the LLM proposes an action that is NOT economically viable,
    the propose_action_node overrides it to the economic recommendation.
    """
    payment_id = setup_test_db(db_session, failure_code="VISA:05", amount=100.0) 
    
    # ESCALATE has an intervention cost of 15. For a 100 INR payment, it's negative EV if prob is low, but we'll force LLM to choose it.
    # Actually wait, 100 * prob - 15. If prob is 0.1, EV is 10 - 15 = -5. So it's negative EV.
    # We force the LLM to propose ESCALATE.
    mock_llm_provider.predefined_responses = {
        "BANK": {"action": "ESCALATE", "rationale": "Agent goes rogue", "confidence": 0.9}
    }
    
    executor = MockExecutor(db=db_session, clock=mock_clock, predefined_outcomes={1: True})
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

