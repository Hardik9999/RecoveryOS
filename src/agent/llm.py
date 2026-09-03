"""
Model provider abstraction for the Agent.
Supports mocking for deterministic tests, and Groq (Llama-3-70B) for production.
"""
from typing import Optional, Dict, Any, Type, TypeVar
from pydantic import BaseModel
import os
import json

T = TypeVar('T', bound=BaseModel)

class AgentLLMProvider:
    """Abstract provider interface."""
    def propose_action(self, context_summary: str, schema: Type[T]) -> T:
        raise NotImplementedError()


class MockLLM(AgentLLMProvider):
    """Deterministic mock LLM for testing. Returns predefined structured outputs."""
    def __init__(self, predefined_responses: Dict[str, dict] = None):
        # Maps a substring in the context_summary to a predefined dict output
        self.predefined_responses = predefined_responses or {}
        self.default_response = {
            "action": "RETRY",
            "rationale": "Default mock rationale.",
            "confidence": 0.9
        }

    def propose_action(self, context_summary: str, schema: Type[T]) -> T:
        for key, resp in self.predefined_responses.items():
            if key in context_summary:
                return schema(**resp)
        return schema(**self.default_response)


class GroqLLM(AgentLLMProvider):
    """Groq Llama 3 provider utilizing LangChain's structured output."""
    def __init__(self, model_name: str = "llama3-70b-8192", temperature: float = 0.0):
        try:
            from langchain_groq import ChatGroq
        except ImportError:
            raise ImportError("Please install langchain-groq to use GroqLLM.")
            
        api_key = os.environ.get("GROQ_API_KEY", "dummy")
        self.llm = ChatGroq(
            temperature=temperature,
            model_name=model_name,
            api_key=api_key
        )

    def propose_action(self, context_summary: str, schema: Type[T]) -> T:
        structured_llm = self.llm.with_structured_output(schema)
        prompt = (
            "You are an advisory AI agent orchestrating a payment recovery process.\n"
            "Review the deterministic context and economic decision below.\n"
            "Propose the next recovery action. Ensure your rationale is concise.\n\n"
            f"Context Summary:\n{context_summary}\n"
        )
        return structured_llm.invoke(prompt)

def get_llm_provider() -> AgentLLMProvider:
    """Factory to get the configured LLM provider."""
    # Use mock by default in test environments unless real Groq is explicitly requested
    if os.environ.get("USE_REAL_LLM") == "true":
        return GroqLLM()
    return MockLLM()
