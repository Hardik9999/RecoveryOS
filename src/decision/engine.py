"""
Recovery Decision Engine — deterministic, policy-enforced, economically grounded.

Decision flow (executed in strict order):
  1. Hard policy gates (block before any economics)
  2. Hard context gates (FRAUD, TERMINAL, non-retryable — not overrideable by economics)
  3. Compute eligible action set for this specific failure context
  4. For each eligible action (in cost-appropriateness order), check economic viability
  5. Select the highest-contextually-appropriate viable action, or STOP
  6. Return structured DecisionOutput

Key design principle: Economic optimization only ever operates WITHIN the eligible action
set for a given failure context. A negative EV for one action never causes an unrelated
or context-inappropriate action to be substituted.

No LLM. No randomness. Same inputs → same output, always.
"""
from datetime import datetime, timezone
from typing import List
from src.decision.context import (
    DecisionInput, DecisionOutput, Economics,
    RecoveryActionType
)
from src.decision.economics import calculate_economics, get_intervention_cost

# ─── Policy Constants ─────────────────────────────────────────────────────────

# Absolute ceiling on recovery attempts regardless of economics
MAX_RECOVERY_ATTEMPTS = 3

# Minimum recovery probability to even consider any action
MIN_VIABLE_PROBABILITY = 0.10

# Risk score above which we skip automated retry and go straight to reminder/link
HIGH_RISK_THRESHOLD = 0.70

# Amount thresholds for action selection
LARGE_PAYMENT_THRESHOLD_INR = 2000.0   # Above this → prefer payment link over retry
MICRO_PAYMENT_THRESHOLD_INR = 100.0    # Below this → cost may exceed recovery value

# Confidence bands
HIGH_CONFIDENCE_THRESHOLD   = 0.65
MEDIUM_CONFIDENCE_THRESHOLD = 0.35


# ─── Helper: Confidence Label ─────────────────────────────────────────────────

def _confidence_label(prob: float) -> str:
    if prob >= HIGH_CONFIDENCE_THRESHOLD:
        return "HIGH"
    elif prob >= MEDIUM_CONFIDENCE_THRESHOLD:
        return "MEDIUM"
    return "LOW"


# ─── Eligibility: Context-Aware Action Sets ───────────────────────────────────

def _get_eligible_actions(inputs: DecisionInput) -> List[RecoveryActionType]:
    """
    Returns the ordered list of candidate actions that are CONTEXTUALLY APPROPRIATE
    for this failure. Economic viability is checked afterward — the eligible set
    constrains what economics may ever choose from.

    Order within the list represents descending preference (most preferred first).
    Economic optimization only downgrades within this set — never substitutes
    an action from outside it.

    Returns empty list if no recovery action is contextually appropriate.
    """
    # FRAUD: no recovery action is appropriate. Period.
    if inputs.failure_category == "FRAUD":
        return []

    # TERMINAL severity: gateway has hard-rejected this. No action is appropriate.
    if inputs.failure_severity == "TERMINAL":
        return []

    # Non-retryable by the gateway: cannot send retry or reminder (they'd just fail again).
    # Only ESCALATE to a human who can fix the underlying account issue.
    if not inputs.is_retryable:
        return [RecoveryActionType.ESCALATE]

    # From here on: failure is retryable and not FRAUD/TERMINAL.
    # Build the ordered eligible set based on failure context.

    eligible: List[RecoveryActionType] = []

    if inputs.failure_category == "NETWORK":
        # Network errors are transient — retry is the primary and preferred action.
        # High-risk customers still get retried since the failure is infrastructure, not customer.
        eligible = [RecoveryActionType.RETRY]

    elif inputs.failure_category == "USER":
        # User-side failures (e.g. insufficient funds) require user action.
        # Sending a reminder or payment link is appropriate; a silent retry will just fail again.
        
        # Specific handling for MPIN exhaustion / Invalid MPIN (NPCI:U29)
        if inputs.error_code == "NPCI:U29":
            eligible = [RecoveryActionType.SEND_PAYMENT_LINK, RecoveryActionType.SEND_PAYMENT_REMINDER]
        elif inputs.error_code in ["VISA:54", "MC:54"]:
            # Expired card - link is the only way to get a new card
            eligible = [RecoveryActionType.SEND_PAYMENT_LINK]
        elif inputs.customer_risk_score >= HIGH_RISK_THRESHOLD or inputs.amount >= LARGE_PAYMENT_THRESHOLD_INR:
            eligible = [RecoveryActionType.SEND_PAYMENT_LINK, RecoveryActionType.SEND_PAYMENT_REMINDER]
        else:
            eligible = [RecoveryActionType.SEND_PAYMENT_REMINDER, RecoveryActionType.SEND_PAYMENT_LINK]

    elif inputs.failure_category == "BANK":
        # Bank-side failures may resolve with retry (e.g. card limit reset) or
        # require customer action (e.g. call bank). Order by context.
        
        # Limit exceeded or Do Not Honor often requires user intervention
        if inputs.error_code in ["NPCI:U30", "VISA:65", "MC:65", "VISA:05", "MC:05"]:
            if inputs.amount >= LARGE_PAYMENT_THRESHOLD_INR:
                eligible = [RecoveryActionType.SEND_PAYMENT_LINK, RecoveryActionType.RETRY]
            else:
                eligible = [RecoveryActionType.SEND_PAYMENT_LINK, RecoveryActionType.SEND_PAYMENT_REMINDER]
        elif inputs.customer_risk_score >= HIGH_RISK_THRESHOLD:
            # High-risk: don't auto-retry, send a link for customer to manage
            eligible = [RecoveryActionType.SEND_PAYMENT_LINK, RecoveryActionType.SEND_PAYMENT_REMINDER]
        elif inputs.amount >= LARGE_PAYMENT_THRESHOLD_INR:
            # Large payment: payment link preferred (customer can re-authenticate)
            eligible = [RecoveryActionType.SEND_PAYMENT_LINK, RecoveryActionType.RETRY]
        else:
            # Standard bank failure: retry first, fallback to reminder
            eligible = [RecoveryActionType.RETRY, RecoveryActionType.SEND_PAYMENT_REMINDER]

    else:
        # Unknown/other categories: conservative — retry if small, link if large
        if inputs.amount >= LARGE_PAYMENT_THRESHOLD_INR:
            eligible = [RecoveryActionType.SEND_PAYMENT_LINK, RecoveryActionType.RETRY]
        else:
            eligible = [RecoveryActionType.RETRY, RecoveryActionType.SEND_PAYMENT_REMINDER]

    return eligible


# ─── Core Engine ──────────────────────────────────────────────────────────────

def decide(inputs: DecisionInput) -> DecisionOutput:
    """
    Main entry point. Returns a fully populated DecisionOutput.
    All logic is deterministic and independently testable.
    """
    now = datetime.now(timezone.utc)

    # ── Gate 1: Attempt limit ────────────────────────────────────────────────
    if inputs.previous_attempt_count >= MAX_RECOVERY_ATTEMPTS:
        econ = calculate_economics(inputs, RecoveryActionType.STOP)
        return DecisionOutput(
            payment_id=inputs.payment_id,
            timestamp=now,
            inputs=inputs,
            economics=econ,
            recommended_action=RecoveryActionType.STOP,
            decision_reason=(
                f"Maximum recovery attempts reached "
                f"({inputs.previous_attempt_count}/{MAX_RECOVERY_ATTEMPTS}). Stopping."
            ),
            confidence=_confidence_label(inputs.recovery_probability),
            max_attempts_reached=True,
            blocked_by_policy=True,
            policy_block_reason="MAX_ATTEMPTS_EXCEEDED"
        )

    # ── Gate 2: Probability floor ────────────────────────────────────────────
    if inputs.recovery_probability < MIN_VIABLE_PROBABILITY:
        econ = calculate_economics(inputs, RecoveryActionType.STOP)
        return DecisionOutput(
            payment_id=inputs.payment_id,
            timestamp=now,
            inputs=inputs,
            economics=econ,
            recommended_action=RecoveryActionType.STOP,
            decision_reason=(
                f"Recovery probability {inputs.recovery_probability:.2%} is below the "
                f"minimum viable threshold {MIN_VIABLE_PROBABILITY:.0%}. Stopping."
            ),
            confidence="LOW",
            max_attempts_reached=False,
            blocked_by_policy=True,
            policy_block_reason="PROBABILITY_BELOW_FLOOR"
        )

    # ── Gate 3: Context eligibility ──────────────────────────────────────────
    # This gate runs BEFORE any economic check. If no action is contextually
    # appropriate (FRAUD, TERMINAL), we stop here unconditionally.
    eligible_actions = _get_eligible_actions(inputs)

    if not eligible_actions:
        # FRAUD or TERMINAL — no action is ever appropriate
        econ = calculate_economics(inputs, RecoveryActionType.STOP)
        stop_reason = (
            "Failure category FRAUD — no recovery action is appropriate."
            if inputs.failure_category == "FRAUD"
            else f"Failure severity TERMINAL ({inputs.failure_severity}) — gateway has hard-rejected this payment."
        )
        return DecisionOutput(
            payment_id=inputs.payment_id,
            timestamp=now,
            inputs=inputs,
            economics=econ,
            recommended_action=RecoveryActionType.STOP,
            decision_reason=stop_reason,
            confidence=_confidence_label(inputs.recovery_probability),
            max_attempts_reached=False,
            blocked_by_policy=True,
            policy_block_reason="FAILURE_NON_RECOVERABLE"
        )

    # ── Gate 4: Economic viability within eligible set ───────────────────────
    # Try each eligible action (in preference order). Select the first one
    # whose expected net value is positive. This ensures:
    #   - We never select an ineligible action due to EV math
    #   - We gracefully downgrade WITHIN the context-appropriate set only
    selected_action = None
    selected_econ = None

    for action in eligible_actions:
        econ = calculate_economics(inputs, action)
        if econ.is_economically_viable:
            selected_action = action
            selected_econ = econ
            break

    # Nothing in the eligible set is economically viable — stop
    if selected_action is None:
        cheapest_eligible = min(eligible_actions, key=lambda a: get_intervention_cost(a))
        cheapest_cost = get_intervention_cost(cheapest_eligible)
        stop_econ = calculate_economics(inputs, RecoveryActionType.STOP)
        return DecisionOutput(
            payment_id=inputs.payment_id,
            timestamp=now,
            inputs=inputs,
            economics=stop_econ,
            recommended_action=RecoveryActionType.STOP,
            decision_reason=(
                f"No eligible action is economically viable for this failure context "
                f"({inputs.failure_category}/{inputs.failure_severity}). "
                f"Gross recovery value ₹{inputs.amount * inputs.recovery_probability:.2f} < "
                f"cheapest eligible intervention ₹{cheapest_cost:.2f} ({cheapest_eligible.value})."
            ),
            confidence=_confidence_label(inputs.recovery_probability),
            max_attempts_reached=False,
            blocked_by_policy=False
        )

    # ── Final decision ───────────────────────────────────────────────────────
    confidence = _confidence_label(inputs.recovery_probability)

    # Note whether a downgrade occurred (selected != first eligible)
    preferred = eligible_actions[0]
    was_downgraded = (selected_action != preferred)
    downgrade_note = (
        f" (downgraded from {preferred.value}: negative EV)"
        if was_downgraded else ""
    )

    reason_parts = [
        f"Action: {selected_action.value}{downgrade_note}.",
        f"Recovery probability: {inputs.recovery_probability:.2%}.",
        f"Expected net value: ₹{selected_econ.expected_net_value:.2f}",
        f"(gross ₹{selected_econ.gross_recovery_value:.2f} − cost ₹{selected_econ.intervention_cost:.2f}).",
        f"Failure: [{inputs.failure_category}/{inputs.failure_severity}].",
        f"Attempt #{inputs.previous_attempt_count + 1}/{MAX_RECOVERY_ATTEMPTS}.",
    ]

    return DecisionOutput(
        payment_id=inputs.payment_id,
        timestamp=now,
        inputs=inputs,
        economics=selected_econ,
        recommended_action=selected_action,
        decision_reason=" ".join(reason_parts),
        confidence=confidence,
        max_attempts_reached=False,
        blocked_by_policy=False
    )
