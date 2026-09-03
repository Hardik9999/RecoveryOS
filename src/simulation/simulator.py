import random
import uuid
from typing import Dict, Any, Tuple, Optional
from src.simulation.rules import determine_failure_type, calculate_recovery_probability, FailureRule

class PaymentSimulator:
    def __init__(self, global_seed: int = 42):
        self.global_seed = global_seed

    def _get_deterministic_random(self, payment_id: uuid.UUID, salt: str = "") -> random.Random:
        """
        Creates an isolated random number generator seeded deterministically
        by combining the global seed, the payment ID, and an optional salt.
        This ensures simulations are 100% reproducible.
        """
        seed_string = f"{self.global_seed}_{str(payment_id)}_{salt}"
        rng = random.Random()
        rng.seed(seed_string)
        return rng

    def process_initial_payment(
        self, 
        payment_id: uuid.UUID, 
        risk_score: float, 
        base_failure_rate: float = 0.25
    ) -> Tuple[bool, Optional[FailureRule], Dict[str, Any]]:
        """
        Simulate an initial payment attempt.
        Returns: (is_success, failure_rule, gateway_response)
        """
        rng = self._get_deterministic_random(payment_id, salt="initial")
        
        # Determine if the payment succeeds or fails on the first try
        # A higher risk score slightly increases the failure rate
        adjusted_failure_rate = base_failure_rate + (risk_score * 0.1)
        
        if rng.random() > adjusted_failure_rate:
            # Payment succeeds
            return True, None, {"status": "success", "message": "Payment successful"}
        
        # Payment fails. Determine the reason deterministically.
        failure_val = rng.random()
        rule = determine_failure_type(failure_val)
        
        return False, rule, {
            "status": "failed", 
            "error_code": rule.error_code, 
            "category": rule.category,
            "message": f"Payment failed due to {rule.error_code}"
        }

    def process_recovery_attempt(
        self, 
        payment_id: uuid.UUID, 
        rule: FailureRule,
        risk_score: float,
        action_type: str,
        attempt_number: int
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Simulate a recovery attempt (e.g., RETRY).
        Returns: (is_success, gateway_response)
        """
        if not rule.is_retryable:
            return False, {"status": "failed", "error_code": "NON_RETRYABLE", "message": "Failure is not retryable"}

        rng = self._get_deterministic_random(payment_id, salt=f"recovery_{attempt_number}")
        
        # If action is SEND_PAYMENT_LINK or similar, we consider it a 'delayed' recovery
        is_delayed = action_type in ("SEND_PAYMENT_REMINDER", "SEND_PAYMENT_LINK")
        
        recovery_prob = calculate_recovery_probability(rule, risk_score, is_delayed=is_delayed)
        
        # Additional penalty for multiple attempts
        recovery_prob = recovery_prob * (0.8 ** (attempt_number - 1))
        
        is_success = rng.random() < recovery_prob
        
        if is_success:
            return True, {"status": "success", "message": "Payment recovered successfully"}
        else:
            return False, {"status": "failed", "error_code": rule.error_code, "message": "Recovery attempt failed"}
