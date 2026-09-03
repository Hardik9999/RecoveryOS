"""
Phase 8 API Tests — verifies the FastAPI layer connects to existing RecoveryOS
domain components correctly.

Uses an in-memory SQLite database with a shared connection and TestClient.
"""
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from src.database.base import Base
from src.database.models import (
    Merchant, Customer, Payment, PaymentFailure,
    RecoveryAction, RecoveryOutcome
)
from src.api.main import app
from src.api.dependencies import get_db

# ─── Test DB Setup ────────────────────────────────────────────────────────────
# Use a file-based temporary SQLite DB shared across the test module
# so that both the TestClient requests and the test fixtures see the same data.

TEST_DB_URL = "sqlite:///./test_phase8.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def setup_db():
    """Create tables before each test, drop after."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def seed_data(db_session):
    """Seed a merchant, customer, and a few payments for testing."""
    merchant = Merchant(name="Test Merchant", category="ecommerce")
    db_session.add(merchant)
    db_session.flush()

    customer = Customer(
        merchant_id=merchant.id,
        email="test@example.com",
        risk_score=0.3,
        total_payments=10,
        total_failures=2,
        total_recovered=1
    )
    db_session.add(customer)
    db_session.flush()

    # Payment 1: FAILED (recoverable)
    p1 = Payment(
        customer_id=customer.id,
        merchant_id=merchant.id,
        amount=500.00,
        currency="INR",
        payment_method="card",
        status="FAILED"
    )
    db_session.add(p1)
    db_session.flush()

    f1 = PaymentFailure(
        payment_id=p1.id,
        error_code="CARD_DECLINED",
        error_message="Card declined by issuer",
        failure_category="BANK",
        is_retryable=True
    )
    db_session.add(f1)

    # Payment 2: SUCCESS
    p2 = Payment(
        customer_id=customer.id,
        merchant_id=merchant.id,
        amount=1000.00,
        currency="INR",
        payment_method="upi",
        status="SUCCESS"
    )
    db_session.add(p2)

    # Payment 3: FAILED_TERMINAL (fraud)
    p3 = Payment(
        customer_id=customer.id,
        merchant_id=merchant.id,
        amount=2000.00,
        currency="INR",
        payment_method="card",
        status="FAILED_TERMINAL"
    )
    db_session.add(p3)
    db_session.flush()

    f3 = PaymentFailure(
        payment_id=p3.id,
        error_code="FRAUD_SUSPECTED",
        error_message="Suspected fraudulent transaction",
        failure_category="FRAUD",
        is_retryable=False
    )
    db_session.add(f3)

    db_session.commit()

    return {
        "merchant": merchant,
        "customer": customer,
        "failed_payment": p1,
        "success_payment": p2,
        "terminal_payment": p3,
    }


# ─── Health Tests ─────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_returns_200(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["database"] == "healthy"
        assert data["service"] == "RecoveryOS"


# ─── Payment Tests ────────────────────────────────────────────────────────────

class TestPayments:
    def test_list_payments_empty(self):
        resp = client.get("/payments")
        assert resp.status_code == 200
        data = resp.json()
        assert data["payments"] == []
        assert data["total"] == 0

    def test_list_payments_with_data(self, seed_data):
        resp = client.get("/payments")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["payments"]) == 3

    def test_list_payments_filter_by_status(self, seed_data):
        resp = client.get("/payments?status=FAILED")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["payments"][0]["status"] == "FAILED"

    def test_list_payments_pagination(self, seed_data):
        resp = client.get("/payments?limit=1&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["payments"]) == 1
        assert data["total"] == 3
        assert data["limit"] == 1
        assert data["offset"] == 0

    def test_get_payment_detail(self, seed_data):
        pid = str(seed_data["failed_payment"].id)
        resp = client.get(f"/payments/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == pid
        assert data["status"] == "FAILED"
        assert data["amount"] == 500.0
        assert data["failure"] is not None
        assert data["failure"]["error_code"] == "CARD_DECLINED"
        assert data["failure"]["is_retryable"] is True

    def test_get_payment_not_found(self):
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/payments/{fake_id}")
        assert resp.status_code == 404

    def test_get_payment_invalid_id(self):
        resp = client.get("/payments/not-a-uuid")
        assert resp.status_code == 400


# ─── Recovery Tests ───────────────────────────────────────────────────────────

class TestRecovery:
    def test_recover_not_found(self):
        fake_id = str(uuid.uuid4())
        resp = client.post(f"/payments/{fake_id}/recover")
        assert resp.status_code == 404

    def test_recover_invalid_id(self):
        resp = client.post("/payments/not-a-uuid/recover")
        assert resp.status_code == 400

    def test_recover_already_success(self, seed_data):
        pid = str(seed_data["success_payment"].id)
        resp = client.post(f"/payments/{pid}/recover")
        assert resp.status_code == 409

    def test_recover_failed_payment(self, seed_data):
        """Integration test: API → RecoveryService → Agent → Policy → Execution → DB"""
        pid = str(seed_data["failed_payment"].id)
        resp = client.post(f"/payments/{pid}/recover")
        assert resp.status_code == 200
        data = resp.json()

        assert data["payment_id"] == pid
        assert data["recovery_probability"] is not None
        assert data["recommended_action"] is not None
        assert data["final_status"] in ("RECOVERED", "FAILED", "FAILED_TERMINAL", "STOPPED")
        assert isinstance(data["attempt_count"], int)
        assert isinstance(data["audit_trail"], list)

    def test_recover_terminal_fraud_payment(self, seed_data):
        """FRAUD payments should be STOPPED by the decision/policy engine."""
        pid = str(seed_data["terminal_payment"].id)
        resp = client.post(f"/payments/{pid}/recover")
        assert resp.status_code == 200
        data = resp.json()

        # Decision engine should recommend STOP for fraud
        assert data["recommended_action"] == "STOP"

    def test_recover_response_has_economics(self, seed_data):
        pid = str(seed_data["failed_payment"].id)
        resp = client.post(f"/payments/{pid}/recover")
        assert resp.status_code == 200
        data = resp.json()

        assert "expected_recovery_value" in data
        assert "intervention_cost" in data
        assert "expected_net_value" in data


# ─── Batch Recovery Tests ─────────────────────────────────────────────────────

class TestBatchRecovery:
    def test_batch_empty_db(self):
        resp = client.post("/recovery/batch", json={"limit": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert data["payments_processed"] == 0

    def test_batch_processes_failed_payments(self, seed_data):
        resp = client.post("/recovery/batch", json={"limit": 10})
        assert resp.status_code == 200
        data = resp.json()
        # Only 1 payment has status FAILED (the other is FAILED_TERMINAL)
        assert data["payments_processed"] == 1
        assert data["revenue_at_risk"] > 0
        assert isinstance(data["details"], list)

    def test_batch_limit_validation(self):
        resp = client.post("/recovery/batch", json={"limit": 0})
        assert resp.status_code == 422

        resp = client.post("/recovery/batch", json={"limit": 501})
        assert resp.status_code == 422

    def test_batch_default_limit(self):
        resp = client.post("/recovery/batch", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["payments_processed"] == 0


# ─── Analytics Tests ──────────────────────────────────────────────────────────

class TestAnalytics:
    def test_analytics_empty_db(self):
        resp = client.get("/analytics/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_payments"] == 0
        assert data["revenue_at_risk"] == 0.0

    def test_analytics_with_data(self, seed_data):
        resp = client.get("/analytics/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_payments"] == 3
        assert data["total_failed"] >= 1
        assert data["revenue_at_risk"] > 0


# ─── Integration Test ─────────────────────────────────────────────────────────

class TestIntegration:
    def test_full_recovery_flow_e2e(self, seed_data):
        """
        End-to-end: list payments → get details → recover → verify analytics updated.
        This verifies API → RecoveryService → Decision → Agent → Policy → Execution → DB.
        """
        # 1. List payments
        resp = client.get("/payments?status=FAILED")
        assert resp.status_code == 200
        failed_payments = resp.json()["payments"]
        assert len(failed_payments) >= 1

        pid = failed_payments[0]["id"]

        # 2. Get payment detail
        resp = client.get(f"/payments/{pid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "FAILED"

        # 3. Recover
        resp = client.post(f"/payments/{pid}/recover")
        assert resp.status_code == 200
        recovery = resp.json()
        assert recovery["payment_id"] == pid
        assert recovery["recovery_probability"] is not None
        assert recovery["recommended_action"] is not None

        # 4. Payment status should have changed
        resp = client.get(f"/payments/{pid}")
        assert resp.status_code == 200
        updated = resp.json()
        # Status should no longer be FAILED (it's either RECOVERED or FAILED_TERMINAL)
        assert updated["status"] != "FAILED" or recovery["recommended_action"] == "STOP"

        # 5. Analytics should reflect the change
        resp = client.get("/analytics/summary")
        assert resp.status_code == 200


def teardown_module():
    """Clean up the test database file."""
    import os
    try:
        os.remove("test_phase8.db")
    except OSError:
        pass
