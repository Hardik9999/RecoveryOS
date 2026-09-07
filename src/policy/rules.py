"""
Individual policy rule evaluators.

Each rule is a pure function:
    evaluate_<rule_name>(request: PolicyRequest) -> Optional[PolicyViolation]

Returns a PolicyViolation if the rule is violated, None if the rule passes.

Rules are stateless — all state (counts, timestamps) is passed in via PolicyRequest.
This makes every rule trivially unit-testable without a database.

Rule constants are module-level so they can be imported in tests for boundary assertions.
"""
from typing import Optional
from src.policy.context import PolicyRequest, PolicyViolation, PolicyResult
from src.decision.context import RecoveryActionType
from src.decision.engine import _get_eligible_actions, MAX_RECOVERY_ATTEMPTS

# ─── Rule Constants ───────────────────────────────────────────────────────────

# Rule 1: Maximum recovery attempts
POLICY_MAX_ATTEMPTS = MAX_RECOVERY_ATTEMPTS  # 3 — shared with Decision Engine

# Rule 2: Retry cooldown — minimum seconds between consecutive RETRY actions
POLICY_RETRY_COOLDOWN_SECONDS = 300  # 5 minutes

# Rule 5: Maximum customer-facing contact actions per 24h window
POLICY_MAX_CONTACT_PER_24H = 3

# Rule 6: Maximum amount for any automated action (above this: ESCALATE only)
POLICY_MAX_ACTIONABLE_AMOUNT_INR = 50_000.0

# Rule 7: After this many prior attempts, HIGH severity must ESCALATE
POLICY_ESCALATION_REQUIRED_ATTEMPTS = 2

# Rule 8: Idempotency window — same action type blocked within this window
POLICY_IDEMPOTENCY_WINDOW_SECONDS = 60

# Rule 9: Minimum amount — below this, no action cost can be justified
POLICY_MIN_ACTIONABLE_AMOUNT_INR = 10.0

# Customer-facing actions (for contact frequency rule)
CUSTOMER_FACING_ACTIONS = {
    RecoveryActionType.SEND_PAYMENT_REMINDER,
    RecoveryActionType.SEND_PAYMENT_LINK,
}


# ─── Rule 1: Maximum Attempts ─────────────────────────────────────────────────

def evaluate_max_attempts(request: PolicyRequest) -> Optional[PolicyViolation]:
    """
    Block any action if the payment has already been attempted the maximum
    allowed number of times. This is a hard ceiling — no exceptions.
    STOP is always exempt: agents must be able to stop recovery regardless.
    """
    if request.proposed_action == RecoveryActionType.STOP:
        return None
    if request.previous_attempt_count >= POLICY_MAX_ATTEMPTS:
        return PolicyViolation(
            rule="MAX_ATTEMPTS",
            reason=(
                f"Payment has already been attempted {request.previous_attempt_count} times "
                f"(maximum allowed: {POLICY_MAX_ATTEMPTS}). No further actions permitted."
            )
        )
    return None


# ─── Rule 2: Retry Cooldown ───────────────────────────────────────────────────

def evaluate_retry_cooldown(request: PolicyRequest) -> Optional[PolicyViolation]:
    """
    RETRY actions must be separated by a minimum cooldown period to avoid
    hammering the gateway and triggering rate-limit bans.
    Only applies to RETRY actions that follow a prior attempt.
    """
    if request.proposed_action != RecoveryActionType.RETRY:
        return None
    if request.seconds_since_last_attempt is None:
        return None  # No prior attempt — cooldown does not apply
    if request.seconds_since_last_attempt < POLICY_RETRY_COOLDOWN_SECONDS:
        elapsed = int(request.seconds_since_last_attempt)
        remaining = int(POLICY_RETRY_COOLDOWN_SECONDS - elapsed)
        return PolicyViolation(
            rule="RETRY_COOLDOWN",
            reason=(
                f"RETRY requested only {elapsed}s after the last attempt. "
                f"Cooldown requires {POLICY_RETRY_COOLDOWN_SECONDS}s. "
                f"Try again in {remaining}s."
            )
        )
    return None


# ─── Rule 3: Action Eligibility ───────────────────────────────────────────────

def evaluate_action_eligibility(request: PolicyRequest) -> Optional[PolicyViolation]:
    """
    The proposed action must be in the eligible action set for this failure context.
    This prevents agents from forcing an inappropriate action (e.g. RETRY on a
    non-retryable failure, or REMINDER on a FRAUD failure).

    STOP is always permitted (agents can always stop).
    """
    if request.proposed_action == RecoveryActionType.STOP:
        return None

    # Reuse the Decision Engine's eligibility function — single source of truth
    from src.decision.context import DecisionInput
    # Build a minimal DecisionInput to call _get_eligible_actions
    mock_input = DecisionInput(
        payment_id=request.payment_id,
        amount=request.amount,
        recovery_probability=0.5,  # Not used by eligibility logic
        failure_category=request.failure_category,
        is_retryable=request.is_retryable,
        failure_severity=request.failure_severity,
        customer_risk_score=request.customer_risk_score,
        previous_attempt_count=request.previous_attempt_count,
        payment_method="unknown",
        error_code=request.error_code
    )
    eligible = _get_eligible_actions(mock_input)

    if request.proposed_action not in eligible:
        eligible_names = [a.value for a in eligible] if eligible else ["STOP (no recovery possible)"]
        return PolicyViolation(
            rule="ACTION_ELIGIBILITY",
            reason=(
                f"Action {request.proposed_action.value} is not eligible for failure context "
                f"{request.failure_category}/{request.failure_severity} "
                f"(retryable={request.is_retryable}). "
                f"Eligible actions: {eligible_names}."
            )
        )
    return None


# ─── Rule 4: Fraud / Terminal Restriction ────────────────────────────────────

def evaluate_fraud_terminal_restriction(request: PolicyRequest) -> Optional[PolicyViolation]:
    """
    Hard block: FRAUD and TERMINAL failures may never receive any active recovery
    action. This rule is redundant with action eligibility but is kept as an
    independent explicit check so that even if the eligibility logic changes,
    FRAUD and TERMINAL will always be blocked here.
    """
    if request.proposed_action == RecoveryActionType.STOP:
        return None

    if request.failure_category == "FRAUD":
        return PolicyViolation(
            rule="FRAUD_TERMINAL_RESTRICTION",
            reason=(
                f"Active recovery actions are prohibited for FRAUD failures. "
                f"Proposed action: {request.proposed_action.value}."
            )
        )
    if request.failure_severity == "TERMINAL":
        return PolicyViolation(
            rule="FRAUD_TERMINAL_RESTRICTION",
            reason=(
                f"Active recovery actions are prohibited for TERMINAL severity failures. "
                f"Proposed action: {request.proposed_action.value}."
            )
        )
    return None


# ─── Rule 5: Customer Contact Frequency ──────────────────────────────────────

def evaluate_contact_frequency(request: PolicyRequest) -> Optional[PolicyViolation]:
    """
    Customer-facing actions (REMINDER, LINK) are limited to prevent customer
    harassment and avoid spam/abuse flags from telecom providers.
    Max allowed: POLICY_MAX_CONTACT_PER_24H per 24-hour window per customer.
    """
    if request.proposed_action not in CUSTOMER_FACING_ACTIONS:
        return None
    if request.contact_attempts_last_24h >= POLICY_MAX_CONTACT_PER_24H:
        return PolicyViolation(
            rule="CONTACT_FREQUENCY",
            reason=(
                f"Customer has already been contacted {request.contact_attempts_last_24h} times "
                f"in the past 24 hours (maximum: {POLICY_MAX_CONTACT_PER_24H}). "
                f"Cannot send {request.proposed_action.value}."
            )
        )
    return None


# ─── Rule 6: Monetary / Action Limit ─────────────────────────────────────────

def evaluate_monetary_limit(request: PolicyRequest) -> Optional[PolicyViolation]:
    """
    Payments above POLICY_MAX_ACTIONABLE_AMOUNT_INR must be escalated to a human
    agent — they cannot be handled by automated RETRY, REMINDER, or LINK actions
    due to fraud risk and regulatory considerations at high values.
    """
    if request.proposed_action in (RecoveryActionType.ESCALATE, RecoveryActionType.STOP):
        return None  # Escalate and stop are always allowed regardless of amount
    if request.amount > POLICY_MAX_ACTIONABLE_AMOUNT_INR:
        return PolicyViolation(
            rule="MONETARY_LIMIT",
            reason=(
                f"Payment amount ₹{request.amount:.2f} exceeds the automated action limit "
                f"₹{POLICY_MAX_ACTIONABLE_AMOUNT_INR:,.0f}. "
                f"Only ESCALATE or STOP are permitted for high-value payments."
            )
        )
    return None


# ─── Rule 7: Escalation Required ─────────────────────────────────────────────

def evaluate_escalation_required(request: PolicyRequest) -> Optional[PolicyViolation]:
    """
    After POLICY_ESCALATION_REQUIRED_ATTEMPTS failed recovery attempts, any HIGH
    severity failure must be ESCALATED to a human agent — automated actions can no
    longer be justified since multiple automated attempts have already failed.
    """
    if request.proposed_action in (RecoveryActionType.ESCALATE, RecoveryActionType.STOP):
        return None
    if (
        request.failure_severity == "HIGH"
        and request.previous_attempt_count >= POLICY_ESCALATION_REQUIRED_ATTEMPTS
    ):
        return PolicyViolation(
            rule="ESCALATION_REQUIRED",
            reason=(
                f"Failure severity is HIGH and {request.previous_attempt_count} prior attempts "
                f"have been made (threshold: {POLICY_ESCALATION_REQUIRED_ATTEMPTS}). "
                f"Only ESCALATE or STOP are now permitted. "
                f"Proposed action {request.proposed_action.value} is not allowed."
            )
        )
    return None


# ─── Rule 8: Idempotency / Duplicate Action Prevention ───────────────────────

def evaluate_idempotency(request: PolicyRequest) -> Optional[PolicyViolation]:
    """
    Prevents the same action type from being executed twice within the idempotency
    window. This guards against double-submission bugs, retry storms, and agent loops.
    Applies to all active actions (not STOP).
    """
    if request.proposed_action == RecoveryActionType.STOP:
        return None
    if request.last_action_type is None or request.seconds_since_last_action is None:
        return None  # No prior action — idempotency does not apply

    if (
        request.last_action_type == request.proposed_action.value
        and request.seconds_since_last_action < POLICY_IDEMPOTENCY_WINDOW_SECONDS
    ):
        elapsed = int(request.seconds_since_last_action)
        remaining = int(POLICY_IDEMPOTENCY_WINDOW_SECONDS - elapsed)
        return PolicyViolation(
            rule="IDEMPOTENCY",
            reason=(
                f"Action {request.proposed_action.value} was already executed {elapsed}s ago. "
                f"Idempotency window is {POLICY_IDEMPOTENCY_WINDOW_SECONDS}s. "
                f"Duplicate blocked. Retry after {remaining}s."
            )
        )
    return None


# ─── Rule 9: Minimum Amount ───────────────────────────────────────────────────

def evaluate_minimum_amount(request: PolicyRequest) -> Optional[PolicyViolation]:
    """
    No active recovery action makes economic sense for payments below the minimum
    threshold — even the cheapest intervention costs more than the recoverable value.
    STOP is always permitted.
    """
    if request.proposed_action in (RecoveryActionType.ESCALATE, RecoveryActionType.STOP):
        return None
    if request.amount < POLICY_MIN_ACTIONABLE_AMOUNT_INR:
        return PolicyViolation(
            rule="MINIMUM_AMOUNT",
            reason=(
                f"Payment amount ₹{request.amount:.2f} is below the minimum actionable "
                f"threshold ₹{POLICY_MIN_ACTIONABLE_AMOUNT_INR:.2f}. "
                f"No active recovery action is economically justifiable."
            )
        )
    return None


# ─── Rule Registry (ordered) ──────────────────────────────────────────────────

# Rules are applied in this exact order. Earlier rules take priority.
# The first failing rule sets policy_rule in the PolicyResult.
ORDERED_RULES = [
    evaluate_max_attempts,            # 1 — Attempt ceiling
    evaluate_retry_cooldown,          # 2 — Rate limiting
    evaluate_fraud_terminal_restriction,  # 3 — Hard categorical block
    evaluate_action_eligibility,      # 4 — Context eligibility
    evaluate_contact_frequency,       # 5 — Customer harassment prevention
    evaluate_monetary_limit,          # 6 — High-value amount gate
    evaluate_escalation_required,     # 7 — Forced escalation
    evaluate_idempotency,             # 8 — Duplicate suppression
    evaluate_minimum_amount,          # 9 — Micro-payment floor
]
