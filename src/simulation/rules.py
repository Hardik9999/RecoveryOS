from dataclasses import dataclass
from typing import Optional, Dict
import random

@dataclass
class FailureRule:
    error_code: str
    category: str
    is_retryable: bool
    base_recovery_prob_immediate: float
    base_recovery_prob_delayed: float

# Define the failure rules map (legacy and new)
FAILURE_RULES: Dict[str, FailureRule] = {
    # ─── Legacy / Fallback Codes (for backward compatibility and tests) ───
    "INSUFFICIENT_FUNDS": FailureRule("INSUFFICIENT_FUNDS", "USER", True, 0.05, 0.80),
    "NETWORK_TIMEOUT": FailureRule("NETWORK_TIMEOUT", "NETWORK", True, 0.95, 0.95),
    "CARD_DECLINED": FailureRule("CARD_DECLINED", "BANK", True, 0.30, 0.40),
    "FRAUD_SUSPECTED": FailureRule("FRAUD_SUSPECTED", "FRAUD", False, 0.0, 0.0),
    "LIMIT_EXCEEDED": FailureRule("LIMIT_EXCEEDED", "BANK", True, 0.05, 0.60),

    # ─── NPCI (UPI) Error Codes ───
    "NPCI:U69": FailureRule("NPCI:U69", "USER", True, 0.05, 0.85),
    "NPCI:U90": FailureRule("NPCI:U90", "NETWORK", True, 0.95, 0.95),
    "NPCI:U30": FailureRule("NPCI:U30", "BANK", True, 0.0, 0.60),
    "NPCI:U29": FailureRule("NPCI:U29", "USER", True, 0.0, 0.50),
    "NPCI:U68": FailureRule("NPCI:U68", "FRAUD", False, 0.0, 0.0),
    "NPCI:U31": FailureRule("NPCI:U31", "BANK", False, 0.0, 0.05),
    "NPCI:ZA": FailureRule("NPCI:ZA", "USER", True, 0.0, 0.70),

    # ─── VISA / Mastercard Error Codes (ISO 8583) ───
    "VISA:51": FailureRule("VISA:51", "USER", True, 0.05, 0.80),
    "MC:51": FailureRule("MC:51", "USER", True, 0.05, 0.80),
    "VISA:05": FailureRule("VISA:05", "BANK", True, 0.20, 0.40),
    "MC:05": FailureRule("MC:05", "BANK", True, 0.20, 0.40),
    "VISA:91": FailureRule("VISA:91", "NETWORK", True, 0.90, 0.90),
    "MC:96": FailureRule("MC:96", "NETWORK", True, 0.90, 0.90),
    "VISA:65": FailureRule("VISA:65", "BANK", True, 0.0, 0.55),
    "MC:65": FailureRule("MC:65", "BANK", True, 0.0, 0.55),
    "VISA:54": FailureRule("VISA:54", "USER", False, 0.0, 0.40), # Cannot auto-retry, but can be updated via link
    "MC:54": FailureRule("MC:54", "USER", False, 0.0, 0.40),
    "VISA:07": FailureRule("VISA:07", "FRAUD", False, 0.0, 0.0),
    "MC:41": FailureRule("MC:41", "FRAUD", False, 0.0, 0.0),

    # ─── Netbanking / Wallet Error Codes ───
    "NB:NET_TIMEOUT": FailureRule("NB:NET_TIMEOUT", "NETWORK", True, 0.85, 0.85),
    "NB:AUTH_FAIL": FailureRule("NB:AUTH_FAIL", "USER", True, 0.0, 0.50),
    "WALLET:LOW_BALANCE": FailureRule("WALLET:LOW_BALANCE", "USER", True, 0.0, 0.75),
}

def determine_failure_type(random_val: float, payment_method: str = "unknown", rng: random.Random = random) -> FailureRule:
    """
    Deterministically choose a failure type based on a random float [0.0, 1.0) and payment method.
    """
    if payment_method == "upi":
        if random_val < 0.40: return FAILURE_RULES["NPCI:U69"] # Insufficient funds
        elif random_val < 0.60: return FAILURE_RULES["NPCI:U90"] # Network timeout
        elif random_val < 0.75: return FAILURE_RULES["NPCI:ZA"] # User cancelled
        elif random_val < 0.85: return FAILURE_RULES["NPCI:U29"] # MPIN error
        elif random_val < 0.92: return FAILURE_RULES["NPCI:U30"] # Limit exceeded
        elif random_val < 0.96: return FAILURE_RULES["NPCI:U68"] # Fraud
        else: return FAILURE_RULES["NPCI:U31"] # Account blocked
        
    elif payment_method == "card":
        # Randomly assign Visa or Mastercard prefix for realism
        prefix = "VISA:" if rng.random() < 0.6 else "MC:"
        if random_val < 0.45: return FAILURE_RULES[f"{prefix}51"] # Insufficient funds
        elif random_val < 0.65: return FAILURE_RULES[f"{prefix}05"] # Do not honor
        elif random_val < 0.80: return FAILURE_RULES[f"{prefix}91" if prefix == "VISA:" else f"{prefix}96"] # Timeout
        elif random_val < 0.90: return FAILURE_RULES[f"{prefix}65"] # Limit exceeded
        elif random_val < 0.95: return FAILURE_RULES[f"{prefix}54"] # Expired
        else: return FAILURE_RULES[f"{prefix}07" if prefix == "VISA:" else f"{prefix}41"] # Fraud
        
    elif payment_method == "netbanking":
        if random_val < 0.60: return FAILURE_RULES["NB:AUTH_FAIL"]
        else: return FAILURE_RULES["NB:NET_TIMEOUT"]
        
    elif payment_method == "wallet":
        return FAILURE_RULES["WALLET:LOW_BALANCE"]
        
    else:
        # Fallback to generic legacy codes (keeps older tests happy if they don't specify method)
        if random_val < 0.50: return FAILURE_RULES["INSUFFICIENT_FUNDS"]
        elif random_val < 0.70: return FAILURE_RULES["CARD_DECLINED"]
        elif random_val < 0.85: return FAILURE_RULES["NETWORK_TIMEOUT"]
        elif random_val < 0.95: return FAILURE_RULES["LIMIT_EXCEEDED"]
        else: return FAILURE_RULES["FRAUD_SUSPECTED"]

def calculate_recovery_probability(
    rule: FailureRule,
    risk_score: float,
    is_delayed: bool = False
) -> float:
    """
    Calculate the exact probability of recovery based on the failure rule and customer risk.
    Higher risk score (1.0 = max risk) lowers the probability.
    """
    if not rule.is_retryable and rule.base_recovery_prob_delayed == 0.0:
        return 0.0

    base_prob = rule.base_recovery_prob_delayed if is_delayed else rule.base_recovery_prob_immediate
    
    # Adjust probability based on risk score. High risk (e.g., 0.9) reduces prob significantly.
    # We penalize by up to 50% of the base prob if risk is 1.0
    risk_penalty = base_prob * 0.5 * risk_score
    
    adjusted_prob = base_prob - risk_penalty
    return max(0.0, min(1.0, adjusted_prob))
