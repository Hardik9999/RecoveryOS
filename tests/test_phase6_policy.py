"""
Comprehensive tests for Phase 6: Policy & Guardrails Engine.

Test structure:
  TestRule1_MaxAttempts           — Rule 1 unit tests
  TestRule2_RetryCooldown         — Rule 2 unit tests
  TestRule3_FraudTerminalBlock    — Rule 3 (fraud/terminal restriction)
  TestRule4_ActionEligibility     — Rule 4 unit tests
  TestRule5_ContactFrequency      — Rule 5 unit tests
  TestRule6_MonetaryLimit         — Rule 6 unit tests
  TestRule7_EscalationRequired    — Rule 7 unit tests
  TestRule8_Idempotency           — Rule 8 unit tests
  TestRule9_MinimumAmount         — Rule 9 unit tests
  TestPolicyEngine_Integration    — Full engine evaluation
  TestAdversarial                 — Agent trying to bypass policy
  TestMultipleViolations          — All violations collected
  TestRuleOrdering                — First-failing rule is policy_rule
  TestBoundaryConditions          — Exact threshold values
  TestDeterminism                 — Same input → same output
"""
import pytest
from src.policy.context import PolicyRequest, PolicyResult
from src.policy.engine import PolicyEngine
from src.policy.rules import (
    evaluate_max_attempts, evaluate_retry_cooldown,
    evaluate_fraud_terminal_restriction, evaluate_action_eligibility,
    evaluate_contact_frequency, evaluate_monetary_limit,
    evaluate_escalation_required, evaluate_idempotency,
    evaluate_minimum_amount,
    POLICY_MAX_ATTEMPTS, POLICY_RETRY_COOLDOWN_SECONDS,
    POLICY_MAX_CONTACT_PER_24H, POLICY_MAX_ACTIONABLE_AMOUNT_INR,
    POLICY_ESCALATION_REQUIRED_ATTEMPTS, POLICY_IDEMPOTENCY_WINDOW_SECONDS,
    POLICY_MIN_ACTIONABLE_AMOUNT_INR
)
from src.decision.context import RecoveryActionType


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def make_request(**overrides) -> PolicyRequest:
    """Build a clean passing PolicyRequest and apply overrides."""
    defaults = {
        "payment_id": "pay-test-001",
        "proposed_action": RecoveryActionType.RETRY,
        "amount": 500.0,
        "failure_category": "BANK",
        "is_retryable": True,
        "failure_severity": "MEDIUM",
        "customer_risk_score": 0.3,
        "previous_attempt_count": 0,
        "seconds_since_last_attempt": None,
        "last_action_type": None,
        "seconds_since_last_action": None,
        "contact_attempts_last_24h": 0,
    }
    defaults.update(overrides)
    return PolicyRequest(**defaults)


engine = PolicyEngine()


# ─── Rule 1: Maximum Attempts ─────────────────────────────────────────────────

class TestRule1_MaxAttempts:
    def test_passes_at_zero_attempts(self):
        req = make_request(previous_attempt_count=0)
        assert evaluate_max_attempts(req) is None

    def test_passes_one_below_max(self):
        req = make_request(previous_attempt_count=POLICY_MAX_ATTEMPTS - 1)
        assert evaluate_max_attempts(req) is None

    def test_fails_at_exact_max(self):
        req = make_request(previous_attempt_count=POLICY_MAX_ATTEMPTS)
        v = evaluate_max_attempts(req)
        assert v is not None
        assert v.rule == "MAX_ATTEMPTS"

    def test_fails_above_max(self):
        req = make_request(previous_attempt_count=POLICY_MAX_ATTEMPTS + 5)
        v = evaluate_max_attempts(req)
        assert v is not None

    def test_engine_denies_max_attempts(self):
        req = make_request(previous_attempt_count=POLICY_MAX_ATTEMPTS)
        result = engine.evaluate(req)
        assert result.allowed is False
        assert result.policy_rule == "MAX_ATTEMPTS"


# ─── Rule 2: Retry Cooldown ───────────────────────────────────────────────────

class TestRule2_RetryCooldown:
    def test_non_retry_action_not_subject_to_cooldown(self):
        req = make_request(
            proposed_action=RecoveryActionType.SEND_PAYMENT_REMINDER,
            seconds_since_last_attempt=10.0
        )
        assert evaluate_retry_cooldown(req) is None

    def test_retry_with_no_prior_attempt_passes(self):
        req = make_request(
            proposed_action=RecoveryActionType.RETRY,
            seconds_since_last_attempt=None
        )
        assert evaluate_retry_cooldown(req) is None

    def test_retry_within_cooldown_fails(self):
        req = make_request(
            proposed_action=RecoveryActionType.RETRY,
            seconds_since_last_attempt=POLICY_RETRY_COOLDOWN_SECONDS - 1
        )
        v = evaluate_retry_cooldown(req)
        assert v is not None
        assert v.rule == "RETRY_COOLDOWN"

    def test_retry_at_exact_cooldown_passes(self):
        req = make_request(
            proposed_action=RecoveryActionType.RETRY,
            seconds_since_last_attempt=float(POLICY_RETRY_COOLDOWN_SECONDS)
        )
        assert evaluate_retry_cooldown(req) is None

    def test_retry_after_cooldown_passes(self):
        req = make_request(
            proposed_action=RecoveryActionType.RETRY,
            seconds_since_last_attempt=POLICY_RETRY_COOLDOWN_SECONDS + 60.0
        )
        assert evaluate_retry_cooldown(req) is None

    def test_reminder_not_blocked_by_cooldown(self):
        """ADVERSARIAL: Agent tries REMINDER very soon after prior attempt — cooldown doesn't apply."""
        req = make_request(
            proposed_action=RecoveryActionType.SEND_PAYMENT_REMINDER,
            seconds_since_last_attempt=5.0
        )
        assert evaluate_retry_cooldown(req) is None


# ─── Rule 3: Fraud / Terminal Restriction ────────────────────────────────────

class TestRule3_FraudTerminalBlock:
    def test_fraud_blocks_retry(self):
        req = make_request(failure_category="FRAUD", is_retryable=False,
                           proposed_action=RecoveryActionType.RETRY)
        v = evaluate_fraud_terminal_restriction(req)
        assert v is not None
        assert v.rule == "FRAUD_TERMINAL_RESTRICTION"

    def test_fraud_blocks_reminder(self):
        req = make_request(failure_category="FRAUD", is_retryable=False,
                           proposed_action=RecoveryActionType.SEND_PAYMENT_REMINDER)
        v = evaluate_fraud_terminal_restriction(req)
        assert v is not None

    def test_fraud_blocks_link(self):
        req = make_request(failure_category="FRAUD", is_retryable=False,
                           proposed_action=RecoveryActionType.SEND_PAYMENT_LINK)
        v = evaluate_fraud_terminal_restriction(req)
        assert v is not None

    def test_fraud_blocks_escalate(self):
        """Even ESCALATE is blocked for FRAUD — agent should not review a FRAUD case."""
        req = make_request(failure_category="FRAUD", is_retryable=False,
                           proposed_action=RecoveryActionType.ESCALATE)
        v = evaluate_fraud_terminal_restriction(req)
        assert v is not None

    def test_fraud_allows_stop(self):
        req = make_request(failure_category="FRAUD", is_retryable=False,
                           proposed_action=RecoveryActionType.STOP)
        v = evaluate_fraud_terminal_restriction(req)
        assert v is None

    def test_terminal_severity_blocks_active_action(self):
        req = make_request(failure_severity="TERMINAL",
                           proposed_action=RecoveryActionType.RETRY)
        v = evaluate_fraud_terminal_restriction(req)
        assert v is not None

    def test_medium_severity_not_blocked(self):
        req = make_request(failure_severity="MEDIUM",
                           proposed_action=RecoveryActionType.RETRY)
        v = evaluate_fraud_terminal_restriction(req)
        assert v is None


# ─── Rule 4: Action Eligibility ───────────────────────────────────────────────

class TestRule4_ActionEligibility:
    def test_retry_eligible_for_network(self):
        req = make_request(failure_category="NETWORK", is_retryable=True,
                           failure_severity="LOW", proposed_action=RecoveryActionType.RETRY)
        assert evaluate_action_eligibility(req) is None

    def test_retry_not_eligible_for_non_retryable(self):
        req = make_request(failure_category="BANK", is_retryable=False,
                           failure_severity="MEDIUM", proposed_action=RecoveryActionType.RETRY)
        v = evaluate_action_eligibility(req)
        assert v is not None
        assert v.rule == "ACTION_ELIGIBILITY"

    def test_reminder_not_eligible_for_network(self):
        """
        ADVERSARIAL: Agent proposes SEND_PAYMENT_REMINDER for a NETWORK failure.
        Reminders are for user-action-required failures, not transient network errors.
        """
        req = make_request(failure_category="NETWORK", is_retryable=True,
                           failure_severity="LOW",
                           proposed_action=RecoveryActionType.SEND_PAYMENT_REMINDER)
        v = evaluate_action_eligibility(req)
        assert v is not None
        assert v.rule == "ACTION_ELIGIBILITY"

    def test_retry_not_eligible_for_user_failure(self):
        """
        ADVERSARIAL: Agent proposes RETRY for a USER/insufficient_funds failure.
        A silent retry will just fail again — user needs to take action.
        """
        req = make_request(failure_category="USER", is_retryable=True,
                           failure_severity="MEDIUM", amount=500.0,
                           proposed_action=RecoveryActionType.RETRY)
        v = evaluate_action_eligibility(req)
        assert v is not None

    def test_stop_always_eligible(self):
        req = make_request(failure_category="FRAUD", is_retryable=False,
                           failure_severity="TERMINAL", proposed_action=RecoveryActionType.STOP)
        assert evaluate_action_eligibility(req) is None

    def test_escalate_eligible_for_non_retryable(self):
        req = make_request(failure_category="BANK", is_retryable=False,
                           failure_severity="MEDIUM",
                           proposed_action=RecoveryActionType.ESCALATE)
        assert evaluate_action_eligibility(req) is None

    def test_reminder_eligible_for_user_failure(self):
        req = make_request(failure_category="USER", is_retryable=True,
                           failure_severity="MEDIUM", amount=500.0,
                           proposed_action=RecoveryActionType.SEND_PAYMENT_REMINDER)
        assert evaluate_action_eligibility(req) is None


# ─── Rule 5: Contact Frequency ────────────────────────────────────────────────

class TestRule5_ContactFrequency:
    def test_passes_below_limit(self):
        req = make_request(
            proposed_action=RecoveryActionType.SEND_PAYMENT_REMINDER,
            contact_attempts_last_24h=POLICY_MAX_CONTACT_PER_24H - 1
        )
        assert evaluate_contact_frequency(req) is None

    def test_fails_at_exact_limit(self):
        req = make_request(
            proposed_action=RecoveryActionType.SEND_PAYMENT_REMINDER,
            contact_attempts_last_24h=POLICY_MAX_CONTACT_PER_24H
        )
        v = evaluate_contact_frequency(req)
        assert v is not None
        assert v.rule == "CONTACT_FREQUENCY"

    def test_fails_above_limit_for_link(self):
        req = make_request(
            proposed_action=RecoveryActionType.SEND_PAYMENT_LINK,
            contact_attempts_last_24h=POLICY_MAX_CONTACT_PER_24H + 2
        )
        v = evaluate_contact_frequency(req)
        assert v is not None

    def test_retry_not_subject_to_contact_limit(self):
        """RETRY is automated — does not count as customer contact."""
        req = make_request(
            proposed_action=RecoveryActionType.RETRY,
            contact_attempts_last_24h=POLICY_MAX_CONTACT_PER_24H + 10
        )
        assert evaluate_contact_frequency(req) is None

    def test_escalate_not_subject_to_contact_limit(self):
        req = make_request(
            proposed_action=RecoveryActionType.ESCALATE,
            contact_attempts_last_24h=POLICY_MAX_CONTACT_PER_24H + 10
        )
        assert evaluate_contact_frequency(req) is None


# ─── Rule 6: Monetary Limit ───────────────────────────────────────────────────

class TestRule6_MonetaryLimit:
    def test_passes_below_limit(self):
        req = make_request(amount=POLICY_MAX_ACTIONABLE_AMOUNT_INR - 1.0,
                           proposed_action=RecoveryActionType.RETRY)
        assert evaluate_monetary_limit(req) is None

    def test_fails_above_limit_for_retry(self):
        req = make_request(amount=POLICY_MAX_ACTIONABLE_AMOUNT_INR + 1.0,
                           proposed_action=RecoveryActionType.RETRY)
        v = evaluate_monetary_limit(req)
        assert v is not None
        assert v.rule == "MONETARY_LIMIT"

    def test_fails_above_limit_for_reminder(self):
        req = make_request(amount=POLICY_MAX_ACTIONABLE_AMOUNT_INR + 1.0,
                           proposed_action=RecoveryActionType.SEND_PAYMENT_REMINDER)
        v = evaluate_monetary_limit(req)
        assert v is not None

    def test_escalate_always_allowed_above_limit(self):
        req = make_request(amount=POLICY_MAX_ACTIONABLE_AMOUNT_INR + 100_000.0,
                           proposed_action=RecoveryActionType.ESCALATE)
        assert evaluate_monetary_limit(req) is None

    def test_stop_always_allowed_above_limit(self):
        req = make_request(amount=POLICY_MAX_ACTIONABLE_AMOUNT_INR + 100_000.0,
                           proposed_action=RecoveryActionType.STOP)
        assert evaluate_monetary_limit(req) is None


# ─── Rule 7: Escalation Required ─────────────────────────────────────────────

class TestRule7_EscalationRequired:
    def test_high_severity_below_threshold_passes_retry(self):
        req = make_request(
            failure_severity="HIGH",
            previous_attempt_count=POLICY_ESCALATION_REQUIRED_ATTEMPTS - 1,
            proposed_action=RecoveryActionType.RETRY
        )
        assert evaluate_escalation_required(req) is None

    def test_high_severity_at_threshold_blocks_retry(self):
        req = make_request(
            failure_severity="HIGH",
            previous_attempt_count=POLICY_ESCALATION_REQUIRED_ATTEMPTS,
            proposed_action=RecoveryActionType.RETRY
        )
        v = evaluate_escalation_required(req)
        assert v is not None
        assert v.rule == "ESCALATION_REQUIRED"

    def test_high_severity_at_threshold_allows_escalate(self):
        req = make_request(
            failure_severity="HIGH",
            previous_attempt_count=POLICY_ESCALATION_REQUIRED_ATTEMPTS,
            proposed_action=RecoveryActionType.ESCALATE
        )
        assert evaluate_escalation_required(req) is None

    def test_medium_severity_never_forces_escalation(self):
        req = make_request(
            failure_severity="MEDIUM",
            previous_attempt_count=10,
            proposed_action=RecoveryActionType.RETRY
        )
        assert evaluate_escalation_required(req) is None

    def test_high_severity_at_threshold_blocks_reminder(self):
        req = make_request(
            failure_severity="HIGH",
            previous_attempt_count=POLICY_ESCALATION_REQUIRED_ATTEMPTS,
            failure_category="USER",
            is_retryable=True,
            proposed_action=RecoveryActionType.SEND_PAYMENT_REMINDER
        )
        v = evaluate_escalation_required(req)
        assert v is not None


# ─── Rule 8: Idempotency ──────────────────────────────────────────────────────

class TestRule8_Idempotency:
    def test_no_prior_action_passes(self):
        req = make_request(last_action_type=None, seconds_since_last_action=None)
        assert evaluate_idempotency(req) is None

    def test_different_action_type_passes(self):
        req = make_request(
            proposed_action=RecoveryActionType.SEND_PAYMENT_REMINDER,
            last_action_type=RecoveryActionType.RETRY.value,
            seconds_since_last_action=10.0
        )
        assert evaluate_idempotency(req) is None

    def test_same_action_within_window_blocked(self):
        req = make_request(
            proposed_action=RecoveryActionType.RETRY,
            last_action_type=RecoveryActionType.RETRY.value,
            seconds_since_last_action=POLICY_IDEMPOTENCY_WINDOW_SECONDS - 1
        )
        v = evaluate_idempotency(req)
        assert v is not None
        assert v.rule == "IDEMPOTENCY"

    def test_same_action_at_exact_window_boundary_passes(self):
        req = make_request(
            proposed_action=RecoveryActionType.RETRY,
            last_action_type=RecoveryActionType.RETRY.value,
            seconds_since_last_action=float(POLICY_IDEMPOTENCY_WINDOW_SECONDS)
        )
        assert evaluate_idempotency(req) is None

    def test_same_action_outside_window_passes(self):
        req = make_request(
            proposed_action=RecoveryActionType.SEND_PAYMENT_REMINDER,
            last_action_type=RecoveryActionType.SEND_PAYMENT_REMINDER.value,
            seconds_since_last_action=POLICY_IDEMPOTENCY_WINDOW_SECONDS + 60.0
        )
        assert evaluate_idempotency(req) is None

    def test_stop_not_subject_to_idempotency(self):
        """Agents must always be able to STOP even if the last action was also STOP."""
        req = make_request(
            proposed_action=RecoveryActionType.STOP,
            last_action_type=RecoveryActionType.STOP.value,
            seconds_since_last_action=1.0
        )
        assert evaluate_idempotency(req) is None


# ─── Rule 9: Minimum Amount ───────────────────────────────────────────────────

class TestRule9_MinimumAmount:
    def test_passes_above_minimum(self):
        req = make_request(amount=POLICY_MIN_ACTIONABLE_AMOUNT_INR + 1.0,
                           proposed_action=RecoveryActionType.RETRY)
        assert evaluate_minimum_amount(req) is None

    def test_fails_below_minimum(self):
        req = make_request(amount=POLICY_MIN_ACTIONABLE_AMOUNT_INR - 0.01,
                           proposed_action=RecoveryActionType.RETRY)
        v = evaluate_minimum_amount(req)
        assert v is not None
        assert v.rule == "MINIMUM_AMOUNT"

    def test_fails_at_zero_amount(self):
        req = make_request(amount=0.0, proposed_action=RecoveryActionType.RETRY)
        v = evaluate_minimum_amount(req)
        assert v is not None

    def test_escalate_exempt_from_minimum(self):
        req = make_request(amount=0.01, proposed_action=RecoveryActionType.ESCALATE)
        assert evaluate_minimum_amount(req) is None

    def test_stop_exempt_from_minimum(self):
        req = make_request(amount=0.0, proposed_action=RecoveryActionType.STOP)
        assert evaluate_minimum_amount(req) is None


# ─── Integration: Full Engine Evaluation ─────────────────────────────────────

class TestPolicyEngine_Integration:
    def test_clean_request_allowed(self):
        req = make_request()
        result = engine.evaluate(req)
        assert result.allowed is True
        assert result.policy_rule is None
        assert result.violations == []

    def test_denied_result_has_violations(self):
        req = make_request(previous_attempt_count=POLICY_MAX_ATTEMPTS)
        result = engine.evaluate(req)
        assert result.allowed is False
        assert len(result.violations) >= 1

    def test_result_action_matches_request(self):
        req = make_request(proposed_action=RecoveryActionType.SEND_PAYMENT_REMINDER,
                           failure_category="USER", is_retryable=True)
        result = engine.evaluate(req)
        assert result.action == RecoveryActionType.SEND_PAYMENT_REMINDER

    def test_stop_always_allowed_through_engine(self):
        """STOP should pass all policy rules under any conditions."""
        req = make_request(
            proposed_action=RecoveryActionType.STOP,
            failure_category="FRAUD",
            is_retryable=False,
            failure_severity="TERMINAL",
            previous_attempt_count=100,
            amount=0.0,
            contact_attempts_last_24h=100,
            seconds_since_last_attempt=0.0,
            last_action_type=RecoveryActionType.STOP.value,
            seconds_since_last_action=0.0
        )
        result = engine.evaluate(req)
        assert result.allowed is True


# ─── Adversarial Tests ────────────────────────────────────────────────────────

class TestAdversarial:
    def test_agent_forces_retry_on_fraud(self):
        """Agent proposes RETRY for a FRAUD failure."""
        req = make_request(failure_category="FRAUD", is_retryable=False,
                           proposed_action=RecoveryActionType.RETRY)
        result = engine.evaluate(req)
        assert result.allowed is False
        # Both FRAUD_TERMINAL_RESTRICTION and ACTION_ELIGIBILITY should fire
        rule_names = {v.rule for v in result.violations}
        assert "FRAUD_TERMINAL_RESTRICTION" in rule_names
        assert "ACTION_ELIGIBILITY" in rule_names

    def test_agent_forces_reminder_on_network_failure(self):
        """Agent bypasses eligibility and proposes REMINDER for a NETWORK failure."""
        req = make_request(failure_category="NETWORK", is_retryable=True,
                           failure_severity="LOW",
                           proposed_action=RecoveryActionType.SEND_PAYMENT_REMINDER)
        result = engine.evaluate(req)
        assert result.allowed is False
        rule_names = {v.rule for v in result.violations}
        assert "ACTION_ELIGIBILITY" in rule_names

    def test_agent_retries_non_retryable_payment(self):
        """Agent proposes RETRY for a gateway-rejected (is_retryable=False) payment."""
        req = make_request(failure_category="BANK", is_retryable=False,
                           failure_severity="MEDIUM",
                           proposed_action=RecoveryActionType.RETRY)
        result = engine.evaluate(req)
        assert result.allowed is False
        rule_names = {v.rule for v in result.violations}
        assert "ACTION_ELIGIBILITY" in rule_names

    def test_agent_spams_retry_within_cooldown(self):
        """Agent tries to bypass cooldown by submitting RETRY 1 second after last attempt."""
        req = make_request(
            proposed_action=RecoveryActionType.RETRY,
            seconds_since_last_attempt=1.0
        )
        result = engine.evaluate(req)
        assert result.allowed is False
        assert result.policy_rule == "RETRY_COOLDOWN"

    def test_agent_submits_duplicate_action(self):
        """Agent submits the exact same action 5 seconds after it was just executed."""
        req = make_request(
            proposed_action=RecoveryActionType.SEND_PAYMENT_REMINDER,
            failure_category="USER",
            is_retryable=True,
            last_action_type=RecoveryActionType.SEND_PAYMENT_REMINDER.value,
            seconds_since_last_action=5.0
        )
        result = engine.evaluate(req)
        assert result.allowed is False
        rule_names = {v.rule for v in result.violations}
        assert "IDEMPOTENCY" in rule_names

    def test_agent_sends_link_after_contact_limit_reached(self):
        """Agent tries to contact customer after they've already been contacted max times."""
        req = make_request(
            proposed_action=RecoveryActionType.SEND_PAYMENT_LINK,
            failure_category="USER",
            is_retryable=True,
            contact_attempts_last_24h=POLICY_MAX_CONTACT_PER_24H
        )
        result = engine.evaluate(req)
        assert result.allowed is False
        rule_names = {v.rule for v in result.violations}
        assert "CONTACT_FREQUENCY" in rule_names

    def test_agent_acts_on_exhausted_payment(self):
        """Agent proposes an action on a payment that has already hit the attempt limit."""
        req = make_request(previous_attempt_count=POLICY_MAX_ATTEMPTS)
        result = engine.evaluate(req)
        assert result.allowed is False
        assert result.policy_rule == "MAX_ATTEMPTS"

    def test_agent_acts_on_high_value_without_escalation(self):
        """Agent proposes REMINDER on a ₹75,000 payment (must ESCALATE for high value)."""
        req = make_request(
            proposed_action=RecoveryActionType.SEND_PAYMENT_REMINDER,
            failure_category="USER",
            is_retryable=True,
            amount=75_000.0
        )
        result = engine.evaluate(req)
        assert result.allowed is False
        rule_names = {v.rule for v in result.violations}
        assert "MONETARY_LIMIT" in rule_names

    def test_agent_bypasses_escalation_with_retry_after_2_high_severity_attempts(self):
        """After 2+ attempts on HIGH severity, agent tries RETRY instead of ESCALATE."""
        req = make_request(
            failure_severity="HIGH",
            previous_attempt_count=POLICY_ESCALATION_REQUIRED_ATTEMPTS,
            proposed_action=RecoveryActionType.RETRY
        )
        result = engine.evaluate(req)
        assert result.allowed is False
        rule_names = {v.rule for v in result.violations}
        assert "ESCALATION_REQUIRED" in rule_names


# ─── Multiple Violations ──────────────────────────────────────────────────────

class TestMultipleViolations:
    def test_all_violations_collected(self):
        """
        A single request can violate multiple rules simultaneously.
        All violations should be returned, not just the first.
        """
        # This request violates:
        # - MAX_ATTEMPTS (attempt_count = MAX)
        # - FRAUD_TERMINAL_RESTRICTION (FRAUD + active action)
        # - ACTION_ELIGIBILITY (RETRY on FRAUD)
        req = make_request(
            failure_category="FRAUD",
            is_retryable=False,
            previous_attempt_count=POLICY_MAX_ATTEMPTS,
            proposed_action=RecoveryActionType.RETRY
        )
        result = engine.evaluate(req)
        assert result.allowed is False
        assert len(result.violations) >= 2
        rule_names = {v.rule for v in result.violations}
        assert "MAX_ATTEMPTS" in rule_names
        assert "FRAUD_TERMINAL_RESTRICTION" in rule_names

    def test_violations_includes_all_failed_rules(self):
        """Request failing MAX_ATTEMPTS, RETRY_COOLDOWN, FRAUD, and ELIGIBILITY."""
        req = make_request(
            failure_category="FRAUD",
            is_retryable=False,
            previous_attempt_count=POLICY_MAX_ATTEMPTS,
            proposed_action=RecoveryActionType.RETRY,
            seconds_since_last_attempt=10.0
        )
        result = engine.evaluate(req)
        rule_names = {v.rule for v in result.violations}
        # MAX_ATTEMPTS fires first, RETRY_COOLDOWN also fires (RETRY action, within cooldown)
        assert "MAX_ATTEMPTS" in rule_names
        assert "RETRY_COOLDOWN" in rule_names


# ─── Rule Ordering ────────────────────────────────────────────────────────────

class TestRuleOrdering:
    def test_max_attempts_is_highest_priority(self):
        """MAX_ATTEMPTS fires before RETRY_COOLDOWN even when both are violated."""
        req = make_request(
            previous_attempt_count=POLICY_MAX_ATTEMPTS,
            proposed_action=RecoveryActionType.RETRY,
            seconds_since_last_attempt=10.0  # Also would fail cooldown
        )
        result = engine.evaluate(req)
        assert result.policy_rule == "MAX_ATTEMPTS"

    def test_fraud_restriction_before_eligibility(self):
        """FRAUD_TERMINAL_RESTRICTION fires before ACTION_ELIGIBILITY."""
        req = make_request(
            failure_category="FRAUD",
            is_retryable=False,
            proposed_action=RecoveryActionType.RETRY
        )
        result = engine.evaluate(req)
        # fraud_terminal_restriction (Rule 3) comes before action_eligibility (Rule 4)
        assert result.policy_rule == "FRAUD_TERMINAL_RESTRICTION"


# ─── Boundary Conditions ─────────────────────────────────────────────────────

class TestBoundaryConditions:
    def test_attempt_count_one_below_max_passes(self):
        req = make_request(previous_attempt_count=POLICY_MAX_ATTEMPTS - 1)
        result = engine.evaluate(req)
        rule_names = {v.rule for v in result.violations}
        assert "MAX_ATTEMPTS" not in rule_names

    def test_cooldown_at_exact_boundary_passes(self):
        req = make_request(
            proposed_action=RecoveryActionType.RETRY,
            seconds_since_last_attempt=float(POLICY_RETRY_COOLDOWN_SECONDS)
        )
        result = engine.evaluate(req)
        rule_names = {v.rule for v in result.violations}
        assert "RETRY_COOLDOWN" not in rule_names

    def test_contact_frequency_one_below_limit_passes(self):
        req = make_request(
            proposed_action=RecoveryActionType.SEND_PAYMENT_REMINDER,
            failure_category="USER",
            is_retryable=True,
            contact_attempts_last_24h=POLICY_MAX_CONTACT_PER_24H - 1
        )
        result = engine.evaluate(req)
        rule_names = {v.rule for v in result.violations}
        assert "CONTACT_FREQUENCY" not in rule_names

    def test_monetary_limit_exactly_at_threshold_passes(self):
        req = make_request(amount=POLICY_MAX_ACTIONABLE_AMOUNT_INR,
                           proposed_action=RecoveryActionType.RETRY)
        result = engine.evaluate(req)
        rule_names = {v.rule for v in result.violations}
        assert "MONETARY_LIMIT" not in rule_names

    def test_minimum_amount_exactly_at_threshold_passes(self):
        req = make_request(amount=POLICY_MIN_ACTIONABLE_AMOUNT_INR,
                           proposed_action=RecoveryActionType.RETRY)
        result = engine.evaluate(req)
        rule_names = {v.rule for v in result.violations}
        assert "MINIMUM_AMOUNT" not in rule_names


# ─── Determinism ─────────────────────────────────────────────────────────────

class TestDeterminism:
    def test_same_input_same_output(self):
        req = make_request()
        results = [engine.evaluate(req) for _ in range(20)]
        first = results[0]
        for r in results[1:]:
            assert r.allowed == first.allowed
            assert r.policy_rule == first.policy_rule
            assert len(r.violations) == len(first.violations)

    def test_denied_deterministic(self):
        req = make_request(failure_category="FRAUD", is_retryable=False)
        results = [engine.evaluate(req) for _ in range(20)]
        for r in results:
            assert r.allowed is False
            assert r.policy_rule == "FRAUD_TERMINAL_RESTRICTION"
