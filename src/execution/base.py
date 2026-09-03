"""
Execution Layer Base Abstraction.

Separates the agent/orchestration from the actual execution backend
(Simulator vs. Razorpay Test Mode).
"""
from abc import ABC, abstractmethod
from typing import Dict, Any
from pydantic import BaseModel
from src.decision.context import RecoveryActionType

class ExecutionResult(BaseModel):
    """Structured result of a recovery action execution."""
    payment_id: str
    action_type: RecoveryActionType
    success: bool
    amount_recovered: float
    gateway_response: Dict[str, Any]
    error_message: str = ""

class RecoveryExecutor(ABC):
    """Base interface for executing recovery actions."""
    
    @abstractmethod
    def execute(self, payment_id: str, action: RecoveryActionType, attempt_number: int) -> ExecutionResult:
        """
        Execute the given action against the payment.
        Must return an ExecutionResult. Must handle network/gateway exceptions gracefully.
        """
        pass
