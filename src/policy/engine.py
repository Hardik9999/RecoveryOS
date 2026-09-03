"""
Policy Engine — deterministic safety boundary.

Evaluates all 9 policy rules against a proposed action and returns a
structured PolicyResult. The LLM/agent layer MUST NOT proceed if
result.allowed is False — this boundary is non-negotiable.

Usage:
    engine = PolicyEngine()
    result = engine.evaluate(request)
    if not result.allowed:
        # Reject the proposed action. Log violations.
        ...
"""
from src.policy.context import PolicyRequest, PolicyResult, PolicyViolation
from src.policy.rules import ORDERED_RULES
from src.decision.context import RecoveryActionType


class PolicyEngine:
    """
    Stateless policy evaluator. All state is injected via PolicyRequest.
    Thread-safe: no shared mutable state.
    """

    def evaluate(self, request: PolicyRequest) -> PolicyResult:
        """
        Evaluate all policy rules against the proposed action.

        - All rules are evaluated even if an early rule fails (collect all violations).
        - policy_rule is set to the FIRST failing rule (highest priority).
        - allowed=True only when zero violations are found.
        """
        violations: list[PolicyViolation] = []

        for rule_fn in ORDERED_RULES:
            violation = rule_fn(request)
            if violation is not None:
                violations.append(violation)

        if not violations:
            return PolicyResult(
                allowed=True,
                action=request.proposed_action,
                reason=(
                    f"Action {request.proposed_action.value} passed all policy checks "
                    f"for payment {request.payment_id}."
                ),
                policy_rule=None,
                violations=[]
            )

        # First violation sets the primary policy_rule (rule ordering is priority ordering)
        primary_rule = violations[0].rule
        all_rules = ", ".join(v.rule for v in violations)

        return PolicyResult(
            allowed=False,
            action=request.proposed_action,
            reason=(
                f"Action {request.proposed_action.value} denied for payment {request.payment_id}. "
                f"Violated rules: [{all_rules}]."
            ),
            policy_rule=primary_rule,
            violations=violations
        )
