"""
Pydantic schemas for the analytics API.
"""
from pydantic import BaseModel
from typing import Optional


class AnalyticsSummaryResponse(BaseModel):
    total_payments: int = 0
    total_failed: int = 0
    total_recovered: int = 0
    total_terminal: int = 0
    revenue_at_risk: float = 0.0
    revenue_recovered: float = 0.0
    recovery_rate: Optional[float] = None
    interventions: int = 0
    interventions_avoided: int = 0
    escalations: int = 0
    stopped_payments: int = 0
    policy_denied_count: int = 0
    intervention_cost: float = 0.0
    net_recovered_value: float = 0.0
    average_attempts: Optional[float] = None
