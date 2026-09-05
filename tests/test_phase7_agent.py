"""
Tests for Phase 7: Agent Orchestration using LangGraph.
"""
import pytest
from src.agent.graph import create_recovery_graph
from src.agent.llm import MockLLM
from src.execution.base import RecoveryExecutor, ExecutionResult
from src.decision.context import RecoveryActionType

# Mock the get_llm_provider function to use our configured MockLLM
import src.agent.nodes
from unittest.mock import patch

class MockExecutor(RecoveryExecutor):
    """A mock executor that allows us to script success/failure per attempt."""
    def __init__(self, predefined_outcomes=None):
        # predefined_outcomes: dict mapping attempt_number -> bool (success)
        self.predefined_outcomes = predefined_outcomes or {}
        self.execution_calls = []

    def execute(self, payment_id: str, action: RecoveryActionType, attempt_number: int) -> ExecutionResult:
        self.execution_calls.append((action.value, attempt_number))
        
        success = self.predefined_outcomes.get(attempt_number, True)
        return ExecutionResult(
            payment_id=payment_id,
            action_type=action,
            success=success,
            amount_recovered=500.0 if success else 0.0,
            gateway_response={"status": "mocked"},
            error_message=""
        )

# Base state for tests
BASE_STATE = {
    "payment_id": "test-pay-001",
    "recovery_context": {
        "amount": 500.0,
        "failure_category": "BANK",
        "is_retryable": True,
        "failure_severity": "MEDIUM",
        "customer_risk_score": 0.3
    },
    "attempt_number": 0,
    "audit_metadata": []
}

@pytest.fixture
def mock_llm_provider():
    # Provide predefined responses if needed, else defaults to RETRY
    mock_llm = MockLLM()
    with patch.object(src.agent.nodes, 'get_llm_provider', return_value=mock_llm):
        yield mock_llm

@pytest.fixture
def setup_graph(mock_llm_provider):
    def _setup(executor_outcomes=None, llm_responses=None):
        if llm_responses:
            mock_llm_provider.predefined_responses = llm_responses
        executor = MockExecutor(predefined_outcomes=executor_outcomes)
        graph = create_recovery_graph(executor, db_session=None)
        return graph, executor
    return _setup


class TestAgentOrchestration:

    def test_successful_recovery_on_first_action(self, setup_graph):
        """Graph should execute RETRY, get SUCCESS, and STOP."""
        graph, executor = setup_graph(executor_outcomes={1: True})
        
        result = graph.invoke(BASE_STATE)
        
        assert result["status"] == "SUCCESS"
        assert result["recovery_outcome"] == "SUCCESS"
        assert result["attempt_number"] == 1
        assert len(executor.execution_calls) == 1
        
        # Verify audit trail captures the flow
        steps = [audit["step"] for audit in result["audit_metadata"]]
        assert steps == ["load_context", "propose_action", "policy_check", "execute_action"]

    def test_failed_recovery_loops_and_retries(self, setup_graph):
        """First attempt fails, graph loops back, second attempt succeeds."""
        graph, executor = setup_graph(executor_outcomes={1: False, 2: True})
        
        # We need a recursion limit in LangGraph to prevent infinite loops, 
        # but 2 iterations will pass easily.
        result = graph.invoke(BASE_STATE, config={"recursion_limit": 15})
        
        assert result["status"] == "SUCCESS"
        assert result["attempt_number"] == 2
        assert len(executor.execution_calls) == 2
        
        steps = [audit["step"] for audit in result["audit_metadata"]]
        # Loop 1: load -> propose -> policy -> execute
        # Loop 2: load -> propose -> policy -> execute
        assert steps == [
            "load_context", "propose_action", "policy_check", "execute_action",
            "load_context", "propose_action", "policy_check", "execute_action"
        ]

    def test_agent_chooses_stop_immediately(self, setup_graph):
        """If the LLM proposes STOP, execution is skipped and graph ends."""
        graph, executor = setup_graph(llm_responses={"BANK": {"action": "STOP", "rationale": "Too risky", "confidence": 0.9}})
        
        result = graph.invoke(BASE_STATE)
        
        assert result["status"] == "STOPPED"
        assert len(executor.execution_calls) == 0
        
        steps = [audit["step"] for audit in result["audit_metadata"]]
        assert steps == ["load_context", "propose_action", "policy_check", "execute_action"]

    def test_policy_deny_prevents_execution(self, setup_graph):
        """If policy denies the action (e.g., FRAUD), execution must not occur."""
        graph, executor = setup_graph(llm_responses={"FRAUD": {"action": "RETRY", "rationale": "I want to retry", "confidence": 0.9}})
        
        state = dict(BASE_STATE)
        state["recovery_context"] = {
            "failure_category": "FRAUD",
            "is_retryable": False,
            "failure_severity": "TERMINAL"
        }
        
        # The MockLLM is forced to propose RETRY.
        # Policy should intercept this and DENY it because it's FRAUD.
        result = graph.invoke(state)
        
        # Action should be stopped, execution calls = 0
        assert len(executor.execution_calls) == 0
        assert result["policy_result"]["allowed"] is False
        
        # The graph routes to END after policy deny in our implementation
        steps = [audit["step"] for audit in result["audit_metadata"]]
        assert steps == ["load_context", "propose_action", "policy_check"]

    def test_max_attempts_exhausted(self, setup_graph):
        """If attempt count reaches max, policy denies and loops end."""
        # Force all attempts to fail, and force LLM to propose RETRY
        graph, executor = setup_graph(
            executor_outcomes={1: False, 2: False, 3: False, 4: False},
            llm_responses={"BANK": {"action": "RETRY", "rationale": "stubborn", "confidence": 0.9}}
        )
        
        # Start at attempt 2. 
        # Next attempt will be 3 (fails). Next is 4 -> Policy blocks.
        state = dict(BASE_STATE)
        state["attempt_number"] = 2
        
        result = graph.invoke(state, config={"recursion_limit": 20})
        
        # Attempt 3 was executed and failed.
        # Loop back -> load_context (attempt_number=3) -> propose -> policy_check (sees 3 >= MAX, DENY) -> END
        assert len(executor.execution_calls) == 1
        assert result["policy_result"]["allowed"] is False
        assert result["policy_result"]["policy_rule"] == "MAX_ATTEMPTS"
