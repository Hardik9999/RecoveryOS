from dataclasses import dataclass
from typing import Optional

@dataclass
class FailureRule:
    error_code: str
    category: str
    is_retryable: bool
    base_recovery_prob_immediate: float
    base_recovery_prob_delayed: float

# Define the failure rules map
FAILURE_RULES = {
    "INSUFFICIENT_FUNDS": FailureRule(
        error_code="INSUFFICIENT_FUNDS",
        category="USER",
        is_retryable=True,
        base_recovery_prob_immediate=0.05,
        base_recovery_prob_delayed=0.80
    ),
    "NETWORK_TIMEOUT": FailureRule(
        error_code="NETWORK_TIMEOUT",
        category="NETWORK",
        is_retryable=True,
        base_recovery_prob_immediate=0.95,
        base_recovery_prob_delayed=0.95
    ),
    "CARD_DECLINED": FailureRule(
        error_code="CARD_DECLINED",
        category="BANK",
        is_retryable=True,
        base_recovery_prob_immediate=0.30,
        base_recovery_prob_delayed=0.40
    ),
    "FRAUD_SUSPECTED": FailureRule(
        error_code="FRAUD_SUSPECTED",
        category="FRAUD",
        is_retryable=False,
        base_recovery_prob_immediate=0.0,
        base_recovery_prob_delayed=0.0
    ),
    "LIMIT_EXCEEDED": FailureRule(
        error_code="LIMIT_EXCEEDED",
        category="BANK",
        is_retryable=True,
        base_recovery_prob_immediate=0.05,
        base_recovery_prob_delayed=0.60
    )
}

def determine_failure_type(random_val: float) -> FailureRule:
    """
    Deterministically choose a failure type based on a random float [0.0, 1.0).
    Distribution:
    - 50% INSUFFICIENT_FUNDS
    - 20% CARD_DECLINED
    - 15% NETWORK_TIMEOUT
    - 10% LIMIT_EXCEEDED
    - 5% FRAUD_SUSPECTED
    """
    if random_val < 0.50:
        return FAILURE_RULES["INSUFFICIENT_FUNDS"]
    elif random_val < 0.70:
        return FAILURE_RULES["CARD_DECLINED"]
    elif random_val < 0.85:
        return FAILURE_RULES["NETWORK_TIMEOUT"]
    elif random_val < 0.95:
        return FAILURE_RULES["LIMIT_EXCEEDED"]
    else:
        return FAILURE_RULES["FRAUD_SUSPECTED"]

def calculate_recovery_probability(
    rule: FailureRule,
    risk_score: float,
    is_delayed: bool = False
) -> float:
    """
    Calculate the exact probability of recovery based on the failure rule and customer risk.
    Higher risk score (1.0 = max risk) lowers the probability.
    """
    if not rule.is_retryable:
        return 0.0

    base_prob = rule.base_recovery_prob_delayed if is_delayed else rule.base_recovery_prob_immediate
    
    # Adjust probability based on risk score. High risk (e.g., 0.9) reduces prob significantly.
    # We penalize by up to 50% of the base prob if risk is 1.0
    risk_penalty = base_prob * 0.5 * risk_score
    
    adjusted_prob = base_prob - risk_penalty
    return max(0.0, min(1.0, adjusted_prob))
