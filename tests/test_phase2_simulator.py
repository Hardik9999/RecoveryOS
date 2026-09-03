import pytest
import uuid
from src.simulation.simulator import PaymentSimulator
from src.simulation.rules import FAILURE_RULES
from src.simulation.adapter import SimulationAdapter
from src.database.models import Merchant, Customer, Payment, RecoveryAction
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database.base import Base

def test_determinism():
    simulator = PaymentSimulator(global_seed=123)
    payment_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    
    # Run simulation 10 times, should yield exact same result
    results = []
    for _ in range(10):
        is_success, rule, response = simulator.process_initial_payment(
            payment_id=payment_id,
            risk_score=0.5,
            base_failure_rate=1.0 # Force a failure
        )
        results.append((is_success, rule.error_code, response))
        
    first_result = results[0]
    for result in results:
        assert result == first_result, "Determinism failed! Results varied."

def test_fraud_is_non_retryable():
    simulator = PaymentSimulator(global_seed=42)
    payment_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    rule = FAILURE_RULES["FRAUD_SUSPECTED"]
    
    is_success, response = simulator.process_recovery_attempt(
        payment_id=payment_id,
        rule=rule,
        risk_score=0.1,
        action_type="RETRY",
        attempt_number=1
    )
    
    assert is_success is False
    assert response["error_code"] == "NON_RETRYABLE"

# Setup test DB for adapter tests
TEST_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(scope="function")
def db_session():
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)

def test_adapter_state_transitions(db_session):
    # Setup data
    merchant = Merchant(id=uuid.uuid4(), name="Test")
    db_session.add(merchant)
    customer = Customer(id=uuid.uuid4(), merchant_id=merchant.id, risk_score=0.1)
    db_session.add(customer)
    payment = Payment(id=uuid.uuid4(), customer_id=customer.id, merchant_id=merchant.id, amount=100.0, status="PENDING")
    db_session.add(payment)
    db_session.commit()

    simulator = PaymentSimulator(global_seed=999)
    adapter = SimulationAdapter(db=db_session, simulator=simulator)

    # Force failure by manipulating simulator or we just test whatever happens
    # Let's mock the simulator to guarantee a failure for testing state transition
    original_process = simulator.process_initial_payment
    simulator.process_initial_payment = lambda *args, **kwargs: (False, FAILURE_RULES["INSUFFICIENT_FUNDS"], {"message": "failed", "status": "failed"})
    
    adapter.execute_initial_payment(payment.id)
    
    assert payment.status == "FAILED"
    assert len(payment.failures) == 1
    assert payment.failures[0].error_code == "INSUFFICIENT_FUNDS"

    # Restore simulator
    simulator.process_initial_payment = original_process

    # Now test recovery
    action = RecoveryAction(
        id=uuid.uuid4(),
        payment_id=payment.id,
        action_type="RETRY",
        action_status="PENDING",
        attempt_number=1
    )
    db_session.add(action)
    db_session.commit()

    # Mock simulator to guarantee success on recovery
    simulator.process_recovery_attempt = lambda *args, **kwargs: (True, {"status": "success", "message": "recovered"})

    outcome = adapter.execute_recovery_action(action.id)
    
    assert outcome.success is True
    assert payment.status == "RECOVERED"
    assert action.action_status == "EXECUTED"
