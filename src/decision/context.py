"""
Decision Engine schemas — input and output Pydantic models.
All fields are documented so the decision object is self-explanatory.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
from datetime import datetime


class RecoveryActionType(str, Enum):
    RETRY = "RETRY"
    SEND_PAYMENT_REMINDER = "SEND_PAYMENT_REMINDER"
    SEND_PAYMENT_LINK = "SEND_PAYMENT_LINK"
    ESCALATE = "ESCALATE"
    STOP = "STOP"


class DecisionInput(BaseModel):
    """All inputs required by the decision engine."""
    payment_id: str
    amount: float = Field(..., description="Payment amount in INR")
    error_code: Optional[str] = Field(None, description="The raw network error code")
    network: Optional[str] = Field(None, description="The network that generated the error")
    recovery_probability: float = Field(..., ge=0.0, le=1.0, description="Calibrated probability from Phase 4 model")
    failure_category: str = Field(..., description="USER, BANK, NETWORK, FRAUD, UNKNOWN")
    is_retryable: bool = Field(..., description="Whether the failure is technically retryable")
    failure_severity: str = Field(..., description="LOW, MEDIUM, HIGH, TERMINAL")
    customer_risk_score: float = Field(..., ge=0.0, le=1.0)
    previous_attempt_count: int = Field(0, ge=0, description="Number of prior recovery attempts on this payment")
    payment_method: str = Field(..., description="card, upi, netbanking, wallet, unknown")


class Economics(BaseModel):
    """All calculated economic values — fully auditable."""
    gross_recovery_value: float = Field(..., description="amount × recovery_probability")
    intervention_cost: float = Field(..., description="Cost of the intervention (INR equivalent)")
    expected_net_value: float = Field(..., description="gross_recovery_value − intervention_cost")
    break_even_probability: float = Field(..., description="Minimum recovery_prob to cover cost")
    is_economically_viable: bool = Field(..., description="expected_net_value > 0")


class DecisionOutput(BaseModel):
    """The fully resolved decision object from the engine."""
    payment_id: str
    timestamp: datetime

    # Inputs (echoed for auditability)
    inputs: DecisionInput

    # Calculated economics
    economics: Economics

    # Final decision
    recommended_action: RecoveryActionType
    decision_reason: str
    confidence: str = Field(..., description="HIGH, MEDIUM, LOW based on prob spread")
    max_attempts_reached: bool

    # Internal flags (for transparency)
    blocked_by_policy: bool = Field(False, description="True if a hard policy rule stopped the action")
    policy_block_reason: Optional[str] = None
