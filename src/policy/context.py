"""
Policy Engine schemas — input and output Pydantic models.

PolicyRequest:  Everything the engine needs to evaluate all 9 rules.
PolicyResult:   Structured verdict — allowed/denied, which rule fired, all violations.

Design principle: All time-based and count-based state is injected as scalars
(seconds, counts) rather than raw DB objects, making the engine trivially testable
without a database.
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List, Optional
from src.decision.context import RecoveryActionType


class PolicyRequest(BaseModel):
    """Input to the Policy Engine. Caller is responsible for populating from DB state."""

    payment_id: str
    error_code: str = ""
    proposed_action: RecoveryActionType

    # Payment context
    amount: float = Field(..., description="Payment amount in INR")
    failure_category: str = Field(..., description="USER, BANK, NETWORK, FRAUD, UNKNOWN")
    is_retryable: bool
    failure_severity: str = Field(..., description="LOW, MEDIUM, HIGH, TERMINAL")
    customer_risk_score: float = Field(..., ge=0.0, le=1.0)

    # Attempt tracking
    previous_attempt_count: int = Field(0, ge=0)
    seconds_since_last_attempt: Optional[float] = Field(
        None, description="Seconds since the last recovery attempt on this payment. None if no prior attempts."
    )

    # Idempotency
    last_action_type: Optional[str] = Field(
        None, description="The action type of the most recent attempt. None if no prior attempts."
    )
    seconds_since_last_action: Optional[float] = Field(
        None, description="Seconds since the last action was taken. None if no prior attempts."
    )

    # Contact frequency (customer-facing actions: REMINDER, LINK)
    contact_attempts_last_24h: int = Field(
        0, ge=0, description="Number of customer-facing contact attempts in the past 24 hours."
    )


class PolicyViolation(BaseModel):
    """A single rule that was violated."""
    rule: str = Field(..., description="Machine-readable rule identifier, e.g. MAX_ATTEMPTS")
    reason: str = Field(..., description="Human-readable explanation of the violation")


class PolicyResult(BaseModel):
    """
    The structured verdict returned by the Policy Engine.

    If allowed=False, at least one PolicyViolation will be present.
    policy_rule is the FIRST rule that fired (rules are evaluated in priority order).
    """
    allowed: bool
    action: RecoveryActionType
    reason: str
    policy_rule: Optional[str] = Field(
        None, description="The first violated rule identifier, None if allowed."
    )
    violations: List[PolicyViolation] = Field(default_factory=list)
