from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class FailureContext(BaseModel):
    error_code: str
    category: str
    is_retryable: bool
    severity: str

class CustomerContext(BaseModel):
    historical_success_rate: float = Field(..., description="Success rate of previous payments (0.0 to 1.0)")
    historical_recovery_rate: float = Field(..., description="Recovery rate of previously failed payments (0.0 to 1.0)")
    days_since_last_success: Optional[int] = Field(None, description="Days since the customer's last successful payment")
    risk_score: float = Field(..., description="Current risk score of the customer (0.0 to 1.0)")
    total_historical_payments: int = Field(..., description="Total payments attempted before this failure")

class TransactionContext(BaseModel):
    amount: float
    currency: str
    payment_method: str
    hour_of_day: int
    day_of_week: int

class RecoveryContext(BaseModel):
    payment_id: str
    timestamp: datetime
    transaction: TransactionContext
    failure: FailureContext
    customer: CustomerContext
