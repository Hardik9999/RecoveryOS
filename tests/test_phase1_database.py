import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database.base import Base
from src.database.models import Merchant, Customer, Payment, PaymentFailure, RecoveryAction, RecoveryOutcome, AuditLog
import uuid
import json

# Setup test DB
TEST_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(scope="session")
def engine():
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def db_session(engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

def test_database_connection(db_session):
    assert db_session is not None

def test_merchant_creation(db_session):
    merchant = Merchant(id=uuid.uuid4(), name="Test Merchant", category="Test")
    db_session.add(merchant)
    db_session.commit()
    
    saved_merchant = db_session.query(Merchant).filter_by(name="Test Merchant").first()
    assert saved_merchant is not None
    assert saved_merchant.category == "Test"

def test_full_recovery_flow(db_session):
    # 1. Merchant
    merchant = Merchant(id=uuid.uuid4(), name="Flow Merchant")
    db_session.add(merchant)
    
    # 2. Customer
    customer = Customer(id=uuid.uuid4(), merchant_id=merchant.id, email="flow@example.com")
    db_session.add(customer)
    
    # 3. Payment
    payment = Payment(
        id=uuid.uuid4(),
        customer_id=customer.id,
        merchant_id=merchant.id,
        amount=100.0,
        status="FAILED"
    )
    db_session.add(payment)
    db_session.commit()
    
    # 4. Failure
    failure = PaymentFailure(
        id=uuid.uuid4(),
        payment_id=payment.id,
        error_code="TEST_FAIL",
        is_retryable=True
    )
    db_session.add(failure)
    db_session.commit()
    
    # 5. Recovery Action
    action = RecoveryAction(
        id=uuid.uuid4(),
        payment_id=payment.id,
        action_type="RETRY",
        action_status="EXECUTED"
    )
    db_session.add(action)
    db_session.commit()
    
    # 6. Outcome
    outcome = RecoveryOutcome(
        id=uuid.uuid4(),
        recovery_action_id=action.id,
        success=True,
        amount_recovered=100.0
    )
    db_session.add(outcome)
    
    # 7. Audit Log
    log = AuditLog(
        id=uuid.uuid4(),
        payment_id=payment.id,
        event_type="TEST_EVENT",
        actor="Test",
        decision_context={"reason": "test"}
    )
    db_session.add(log)
    db_session.commit()
    
    # Verify relationships
    saved_payment = db_session.query(Payment).get(payment.id)
    assert saved_payment.failures[0].error_code == "TEST_FAIL"
    assert saved_payment.recovery_actions[0].action_type == "RETRY"
    assert saved_payment.recovery_actions[0].outcome.success is True
    assert saved_payment.audit_logs[0].event_type == "TEST_EVENT"

def test_base_repository(db_session):
    from src.repositories.base import BaseRepository
    repo = BaseRepository(Merchant)
    
    # create
    m = repo.create(db_session, {"id": uuid.uuid4(), "name": "Repo Merchant"})
    assert m.name == "Repo Merchant"
    
    # get
    fetched = repo.get(db_session, m.id)
    assert fetched.id == m.id
    
    # update
    repo.update(db_session, fetched, {"name": "Updated Merchant"})
    assert fetched.name == "Updated Merchant"
    
    # remove
    repo.remove(db_session, fetched.id)
    assert repo.get(db_session, m.id) is None
