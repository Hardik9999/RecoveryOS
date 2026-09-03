"""
LangGraph state definition for the Recovery Agent.

The state is passed between nodes in the graph and contains only the
structured data required for orchestration. It does not store unconstrained
chain-of-thought or raw LLM completions.
"""
from typing import TypedDict, Optional, List, Dict, Any


class AuditRecord(TypedDict):
    """Structured audit trail item for a single graph transition."""
    step: str
    timestamp: str
    details: Dict[str, Any]


class RecoveryState(TypedDict):
    """
    The state of the recovery orchestration graph.
    All fields should be JSON-serializable structured data.
    """
    payment_id: str
    
    # Context injected by deterministic systems
    recovery_context: Optional[Dict[str, Any]]
    recovery_probability: Optional[float]
    economic_decision: Optional[Dict[str, Any]]
    
    # Proposed by LLM Agent
    proposed_action: Optional[str]
    rationale: Optional[str]
    confidence: Optional[float]
    
    # Validated by Policy Engine
    policy_result: Optional[Dict[str, Any]]
    
    # Executed by Execution Layer
    execution_result: Optional[Dict[str, Any]]
    recovery_outcome: Optional[str]
    
    # Graph execution tracking
    attempt_number: int
    status: str          # PENDING, IN_PROGRESS, SUCCESS, FAILED_TERMINAL, STOPPED, ERROR
    error: Optional[str]
    audit_metadata: List[AuditRecord]
