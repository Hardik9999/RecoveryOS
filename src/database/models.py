import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, Float, Integer, ForeignKey, Text, Enum, Numeric, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator, CHAR
from sqlalchemy.dialects.postgresql import UUID

from src.database.base import Base

class GUID(TypeDecorator):
    """Platform-independent GUID type.
    Uses PostgreSQL's UUID type, otherwise uses CHAR(32), storing as stringified hex values.
    """
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(CHAR(32))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return str(value)
        else:
            if not isinstance(value, uuid.UUID):
                return "%.32x" % uuid.UUID(value).int
            else:
                return "%.32x" % value.int

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            if not isinstance(value, uuid.UUID):
                value = uuid.UUID(value)
            return value

def utcnow():
    return datetime.now(timezone.utc)

class Merchant(Base):
    __tablename__ = "merchants"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(Text, default=lambda: utcnow().isoformat())
    updated_at = Column(Text, default=lambda: utcnow().isoformat(), onupdate=lambda: utcnow().isoformat())

    customers = relationship("Customer", back_populates="merchant")
    payments = relationship("Payment", back_populates="merchant")

class Customer(Base):
    __tablename__ = "customers"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(GUID(), ForeignKey("merchants.id"), nullable=False)
    email = Column(String(255), nullable=True)
    phone = Column(String(30), nullable=True)
    risk_score = Column(Float, default=0.0)
    total_payments = Column(Integer, default=0)
    total_failures = Column(Integer, default=0)
    total_recovered = Column(Integer, default=0)
    created_at = Column(Text, default=lambda: utcnow().isoformat())
    updated_at = Column(Text, default=lambda: utcnow().isoformat(), onupdate=lambda: utcnow().isoformat())

    merchant = relationship("Merchant", back_populates="customers")
    payments = relationship("Payment", back_populates="customer")

class Payment(Base):
    __tablename__ = "payments"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    customer_id = Column(GUID(), ForeignKey("customers.id"), nullable=False)
    merchant_id = Column(GUID(), ForeignKey("merchants.id"), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), default="INR")
    payment_method = Column(String(50), nullable=True)
    status = Column(String(50), nullable=False, default="PENDING")
    gateway_payment_id = Column(String(255), nullable=True)
    created_at = Column(Text, default=lambda: utcnow().isoformat())
    updated_at = Column(Text, default=lambda: utcnow().isoformat(), onupdate=lambda: utcnow().isoformat())

    customer = relationship("Customer", back_populates="payments")
    merchant = relationship("Merchant", back_populates="payments")
    failures = relationship("PaymentFailure", back_populates="payment")
    recovery_actions = relationship("RecoveryAction", back_populates="payment")
    audit_logs = relationship("AuditLog", back_populates="payment")

class PaymentFailure(Base):
    __tablename__ = "payment_failures"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    payment_id = Column(GUID(), ForeignKey("payments.id"), nullable=False, unique=True)
    error_code = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    failure_category = Column(String(50), nullable=True)
    is_retryable = Column(Boolean, default=False)
    occurred_at = Column(Text, default=lambda: utcnow().isoformat())

    payment = relationship("Payment", back_populates="failures")

class RecoveryAction(Base):
    __tablename__ = "recovery_actions"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    payment_id = Column(GUID(), ForeignKey("payments.id"), nullable=False)
    action_type = Column(String(50), nullable=False)
    action_status = Column(String(50), nullable=False, default="PENDING")
    predicted_recovery_prob = Column(Float, nullable=True)
    expected_recovery_value = Column(Numeric(12, 2), nullable=True)
    policy_decision = Column(String(20), nullable=True)
    policy_reason = Column(Text, nullable=True)
    attempt_number = Column(Integer, default=1)
    attempted_at = Column(Text, default=lambda: utcnow().isoformat())

    payment = relationship("Payment", back_populates="recovery_actions")
    outcome = relationship("RecoveryOutcome", back_populates="recovery_action", uselist=False)

class RecoveryOutcome(Base):
    __tablename__ = "recovery_outcomes"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    recovery_action_id = Column(GUID(), ForeignKey("recovery_actions.id"), nullable=False, unique=True)
    success = Column(Boolean, nullable=False, default=False)
    amount_recovered = Column(Numeric(12, 2), default=0.0)
    gateway_response = Column(JSON, nullable=True)
    recorded_at = Column(Text, default=lambda: utcnow().isoformat())

    recovery_action = relationship("RecoveryAction", back_populates="outcome")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    payment_id = Column(GUID(), ForeignKey("payments.id"), nullable=True)
    event_type = Column(String(100), nullable=False)
    actor = Column(String(100), nullable=False)
    decision_context = Column(JSON, nullable=True)
    proposed_action = Column(String(50), nullable=True)
    policy_result = Column(String(20), nullable=True)
    executed_action = Column(String(50), nullable=True)
    explanation = Column(Text, nullable=True)
    created_at = Column(Text, default=lambda: utcnow().isoformat())

    payment = relationship("Payment", back_populates="audit_logs")
