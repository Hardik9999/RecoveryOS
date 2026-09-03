"""
Pydantic response/request schemas for the Payments API.
Maps SQLAlchemy models to clean API-facing representations.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class FailureResponse(BaseModel):
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    failure_category: Optional[str] = None
    is_retryable: Optional[bool] = None
    occurred_at: Optional[str] = None


class RecoveryActionResponse(BaseModel):
    id: str
    action_type: str
    action_status: str
    attempt_number: int
    predicted_recovery_prob: Optional[float] = None
    policy_decision: Optional[str] = None
    policy_reason: Optional[str] = None
    attempted_at: Optional[str] = None
    outcome_success: Optional[bool] = None
    amount_recovered: Optional[float] = None


class PaymentResponse(BaseModel):
    id: str
    customer_id: str
    merchant_id: str
    amount: float
    currency: str
    payment_method: Optional[str] = None
    status: str
    created_at: Optional[str] = None

    # Related data
    failure: Optional[FailureResponse] = None
    recovery_actions: List[RecoveryActionResponse] = Field(default_factory=list)
    attempt_count: int = 0


class PaymentListResponse(BaseModel):
    payments: List[PaymentResponse]
    total: int
    limit: int
    offset: int
