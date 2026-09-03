"""
Pydantic request/response schemas for recovery and batch recovery endpoints.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class PolicyResponse(BaseModel):
    allowed: bool
    rule: Optional[str] = None
    reason: Optional[str] = None


class ExecutionResponse(BaseModel):
    status: str
    amount_recovered: float = 0.0
    error_message: Optional[str] = None


class RecoveryResponse(BaseModel):
    """Structured response from the /payments/{id}/recover endpoint."""
    payment_id: str
    recovery_probability: Optional[float] = None
    recommended_action: Optional[str] = None
    expected_recovery_value: Optional[float] = None
    intervention_cost: Optional[float] = None
    expected_net_value: Optional[float] = None
    policy: Optional[PolicyResponse] = None
    execution: Optional[ExecutionResponse] = None
    final_status: str
    attempt_count: int = 0
    audit_trail: List[Dict[str, Any]] = Field(default_factory=list)


class BatchRecoveryRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500, description="Number of eligible failed payments to process (max 500)")


class BatchRecoveryItem(BaseModel):
    payment_id: str
    status: str
    action: Optional[str] = None
    recovered: bool = False
    amount_recovered: float = 0.0


class BatchRecoveryResponse(BaseModel):
    payments_processed: int = 0
    payments_recovered: int = 0
    payments_failed: int = 0
    payments_stopped: int = 0
    payments_policy_denied: int = 0
    revenue_at_risk: float = 0.0
    revenue_recovered: float = 0.0
    intervention_count: int = 0
    intervention_cost: float = 0.0
    net_recovered_value: float = 0.0
    details: List[BatchRecoveryItem] = Field(default_factory=list)
