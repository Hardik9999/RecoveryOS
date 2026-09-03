import pytest
import uuid
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database.base import Base
from src.database.models import Merchant, Customer, Payment, PaymentFailure
from src.intelligence.taxonomy import get_taxonomy_info
from src.intelligence.extractor import FeatureExtractor
from src.intelligence.context import RecoveryContext

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

def test_taxonomy_mapping():
    tax = get_taxonomy_info("INSUFFICIENT_FUNDS")
    assert tax["category"] == "USER"
    assert tax["severity"] == "MEDIUM"
    assert tax["is_retryable"] is True

    # Unknown
    tax_unknown = get_taxonomy_info("SOME_RANDOM_CODE")
    assert tax_unknown["category"] == "UNKNOWN"
    assert tax_unknown["severity"] == "TERMINAL"
    assert tax_unknown["is_retryable"] is False

def test_data_leakage_safety(db_session):
    # Setup data
    merchant = Merchant(id=uuid.uuid4(), name="Leakage Test")
    db_session.add(merchant)
    customer = Customer(id=uuid.uuid4(), merchant_id=merchant.id, risk_score=0.2)
    db_session.add(customer)
    db_session.commit()

    base_time = datetime(2023, 1, 1, 12, 0, 0)

    # 1. Payment T-2: Success
    p1 = Payment(
        id=uuid.uuid4(), customer_id=customer.id, merchant_id=merchant.id,
        amount=10.0, status="SUCCESS", created_at=(base_time - timedelta(days=2)).isoformat()
    )
    db_session.add(p1)

    # 2. Payment T-1: Failed (The one we will extract features for)
    p2 = Payment(
        id=uuid.uuid4(), customer_id=customer.id, merchant_id=merchant.id,
        amount=20.0, status="FAILED", created_at=(base_time - timedelta(days=1)).isoformat()
    )
    db_session.add(p2)
    f2 = PaymentFailure(
        id=uuid.uuid4(), payment_id=p2.id, error_code="INSUFFICIENT_FUNDS"
    )
    db_session.add(f2)

    # 3. Payment T0: Failed (Should NOT be included in T-1's history)
    p3 = Payment(
        id=uuid.uuid4(), customer_id=customer.id, merchant_id=merchant.id,
        amount=30.0, status="FAILED", created_at=base_time.isoformat()
    )
    db_session.add(p3)
    f3 = PaymentFailure(
        id=uuid.uuid4(), payment_id=p3.id, error_code="CARD_DECLINED"
    )
    db_session.add(f3)

    db_session.commit()

    # Extract context for P2 (T-1)
    extractor = FeatureExtractor(db_session)
    context = extractor.extract_context(p2.id)

    # Assertions
    assert isinstance(context, RecoveryContext)
    
    # Only P1 should be in history for P2. P3 is in the future.
    assert context.customer.total_historical_payments == 1
    assert context.customer.historical_success_rate == 1.0  # P1 was success
    assert context.customer.historical_recovery_rate == 0.0 # No previous failures to recover
    assert context.customer.days_since_last_success == 1    # P1 was 2 days before base_time, P2 was 1 day before base_time. Delta = 1 day

    # Check failure context
    assert context.failure.error_code == "INSUFFICIENT_FUNDS"
    assert context.failure.category == "USER"

    # Check transaction context
    assert context.transaction.amount == 20.0
    assert context.transaction.hour_of_day == 12
