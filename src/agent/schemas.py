"""
Pydantic schemas for structured LLM I/O in the Agent layer.
The LLM must return these structured outputs.
"""
from pydantic import BaseModel, Field
from src.decision.context import RecoveryActionType

class AgentActionProposal(BaseModel):
    """Structured proposal from the LLM agent regarding the next recovery action."""
    action: RecoveryActionType = Field(
        ..., 
        description="The proposed recovery action. Must be one of the enum values."
    )
    rationale: str = Field(
        ..., 
        description="Concise, high-level reasoning for this action. Suitable for audit logs."
    )
    confidence: float = Field(
        ..., 
        description="Agent's confidence in this action (0.0 to 1.0)",
        ge=0.0, 
        le=1.0
    )
