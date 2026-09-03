"""
LangGraph compilation for the Recovery Agent.
"""
from typing import Literal
from langgraph.graph import StateGraph, START, END
from src.agent.state import RecoveryState
from src.agent.nodes import (
    load_context_node,
    propose_action_node,
    policy_check_node,
    execute_action_node
)
from src.execution.base import RecoveryExecutor

def route_after_policy(state: RecoveryState) -> Literal["execute_action", "__end__"]:
    """
    Route based on Policy Engine verdict.
    If denied, we stop the orchestration cycle. 
    (In a more advanced version, we could loop back to propose_action to try a fallback).
    """
    if not state.get("policy_result", {}).get("allowed", False):
        return END
    return "execute_action"

def route_after_execution(state: RecoveryState) -> Literal["load_context", "__end__"]:
    """
    Route based on execution outcome.
    SUCCESS or STOPPED -> end graph.
    FAILURE -> loop back to load_context for the next recovery attempt.
    """
    status = state.get("status")
    if status in ("SUCCESS", "STOPPED", "ERROR"):
        return END
    # If IN_PROGRESS / FAILURE, loop back for another attempt
    return "load_context"

def create_recovery_graph(executor: RecoveryExecutor, db_session=None):
    """
    Builds and compiles the closed-loop recovery graph.
    """
    workflow = StateGraph(RecoveryState)
    
    # Wrap nodes that need dependencies
    def load_context_wrapper(state: RecoveryState):
        return load_context_node(state, db_session)
        
    def execute_action_wrapper(state: RecoveryState):
        return execute_action_node(state, executor)
    
    # Add nodes
    workflow.add_node("load_context", load_context_wrapper)
    workflow.add_node("propose_action", propose_action_node)
    workflow.add_node("policy_check", policy_check_node)
    workflow.add_node("execute_action", execute_action_wrapper)
    
    # Define edges
    workflow.add_edge(START, "load_context")
    workflow.add_edge("load_context", "propose_action")
    workflow.add_edge("propose_action", "policy_check")
    
    # Conditional edge after policy check
    workflow.add_conditional_edges(
        "policy_check",
        route_after_policy,
        {
            "execute_action": "execute_action",
            END: END
        }
    )
    
    # Conditional edge after execution (closed loop)
    workflow.add_conditional_edges(
        "execute_action",
        route_after_execution,
        {
            "load_context": "load_context",
            END: END
        }
    )
    
    return workflow.compile()
