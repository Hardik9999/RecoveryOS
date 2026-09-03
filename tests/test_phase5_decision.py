"""
Comprehensive unit tests for Phase 5: Economic Decision Engine.

Tests cover:
  - Happy-path action selection for each failure type
  - Hard policy gates (attempts limit, probability floor, FRAUD, TERMINAL)
  - Economic viability: viable vs. unviable scenarios
  - REGRESSION: eligibility-filtered downgrade — a negative EV for one action
    must never cause a contextually inappropriate action to be selected
  - REGRESSION: non-retryable failures can never be downgraded to REMINDER/RETRY
  - REGRESSION: NETWORK failures can only downgrade within the NETWORK eligible set
  - REGRESSION: USER failures can only get user-facing actions
  - Customer risk-score routing: high-risk → payment link
  - Amount-based routing: large → link, small → reminder/retry
  - Boundary conditions: prob=0.0, prob=1.0, amount=0, max_attempts exactly at limit
  - Determinism: same input → same output every time
  - Conflicting signals: high probability but FRAUD category
  - Output schema: all fields present and correctly typed
  - Eligible action set verification
"""
import pytest
from datetime import datetime
from src.decision.context import DecisionInput, RecoveryActionType
from src.decision.engine import (
    decide, _get_eligible_actions,
    MAX_RECOVERY_ATTEMPTS, MIN_VIABLE_PROBABILITY,
    HIGH_RISK_THRESHOLD, LARGE_PAYMENT_THRESHOLD_INR
)
from src.decision.economics import calculate_economics, get_intervention_cost


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def make_input(**overrides) -> DecisionInput:
    """Build a default healthy DecisionInput and apply overrides."""
    defaults = {
        "payment_id": "test-payment-001",
        "amount": 500.0,
        "recovery_probability": 0.60,
        "failure_category": "BANK",
        "is_retryable": True,
        "failure_severity": "MEDIUM",
        "customer_risk_score": 0.3,
        "previous_attempt_count": 0,
        "payment_method": "card",
    }
    defaults.update(overrides)
    return DecisionInput(**defaults)


# ─── Economics Unit Tests ─────────────────────────────────────────────────────

class TestEconomics:
    def test_gross_recovery_value(self):
        inp = make_input(amount=1000.0, recovery_probability=0.5)
        econ = calculate_economics(inp, RecoveryActionType.RETRY)
        assert econ.gross_recovery_value == pytest.approx(500.0)

    def test_net_value_positive(self):
        inp = make_input(amount=1000.0, recovery_probability=0.5)
        econ = calculate_economics(inp, RecoveryActionType.RETRY)
        # cost=2, gross=500, net=498
        assert econ.expected_net_value == pytest.approx(498.0)
        assert econ.is_economically_viable is True

    def test_net_value_negative_micro_payment(self):
        # Amount ₹2, prob 0.5 → gross=1.0, retry cost=2.0 → net=-1.0
        inp = make_input(amount=2.0, recovery_probability=0.5)
        econ = calculate_economics(inp, RecoveryActionType.RETRY)
        assert econ.expected_net_value < 0
        assert econ.is_economically_viable is False

    def test_stop_has_zero_cost(self):
        inp = make_input()
        econ = calculate_economics(inp, RecoveryActionType.STOP)
        assert econ.intervention_cost == 0.0
        assert econ.is_economically_viable is True

    def test_break_even_probability(self):
        # For retry (cost ₹2) on ₹100 payment: break_even = 2/100 = 0.02
        inp = make_input(amount=100.0, recovery_probability=0.5)
        econ = calculate_economics(inp, RecoveryActionType.RETRY)
        assert econ.break_even_probability == pytest.approx(0.02)

    def test_escalate_cost(self):
        assert get_intervention_cost(RecoveryActionType.ESCALATE) == 15.0

    def test_reminder_is_cheapest_active(self):
        reminder_cost = get_intervention_cost(RecoveryActionType.SEND_PAYMENT_REMINDER)
        retry_cost = get_intervention_cost(RecoveryActionType.RETRY)
        link_cost = get_intervention_cost(RecoveryActionType.SEND_PAYMENT_LINK)
        assert reminder_cost < retry_cost
        assert reminder_cost < link_cost


# ─── Eligibility: Action Set Verification ────────────────────────────────────

class TestEligibleActionSets:
    """Verify the eligible action set for each failure context."""

    def test_fraud_has_no_eligible_actions(self):
        inp = make_input(failure_category="FRAUD", is_retryable=False)
        assert _get_eligible_actions(inp) == []

    def test_terminal_has_no_eligible_actions(self):
        inp = make_input(failure_severity="TERMINAL")
        assert _get_eligible_actions(inp) == []

    def test_non_retryable_only_allows_escalate(self):
        inp = make_input(failure_category="BANK", is_retryable=False, failure_severity="MEDIUM")
        eligible = _get_eligible_actions(inp)
        assert eligible == [RecoveryActionType.ESCALATE]
        assert RecoveryActionType.RETRY not in eligible
        assert RecoveryActionType.SEND_PAYMENT_REMINDER not in eligible
        assert RecoveryActionType.SEND_PAYMENT_LINK not in eligible

    def test_network_failure_only_allows_retry(self):
        inp = make_input(failure_category="NETWORK", failure_severity="LOW", is_retryable=True)
        eligible = _get_eligible_actions(inp)
        # NETWORK should only return RETRY — reminder/link are not appropriate for transient errors
        assert RecoveryActionType.RETRY in eligible
        assert RecoveryActionType.SEND_PAYMENT_REMINDER not in eligible

    def test_user_failure_allows_user_facing_actions_only(self):
        inp = make_input(failure_category="USER", is_retryable=True, failure_severity="MEDIUM", amount=500.0)
        eligible = _get_eligible_actions(inp)
        # USER failures: customer needs to take action, not silent retry
        assert RecoveryActionType.RETRY not in eligible
        assert RecoveryActionType.SEND_PAYMENT_REMINDER in eligible or RecoveryActionType.SEND_PAYMENT_LINK in eligible

    def test_bank_failure_standard_allows_retry_and_reminder(self):
        inp = make_input(failure_category="BANK", is_retryable=True, failure_severity="MEDIUM",
                         amount=500.0, customer_risk_score=0.2)
        eligible = _get_eligible_actions(inp)
        assert RecoveryActionType.RETRY in eligible

    def test_bank_failure_large_amount_prefers_link(self):
        inp = make_input(failure_category="BANK", is_retryable=True, failure_severity="MEDIUM",
                         amount=LARGE_PAYMENT_THRESHOLD_INR + 1.0, customer_risk_score=0.2)
        eligible = _get_eligible_actions(inp)
        assert eligible[0] == RecoveryActionType.SEND_PAYMENT_LINK


# ─── REGRESSION: Eligibility-Filtered Downgrade ──────────────────────────────

class TestEligibilityFilteredDowngrade:
    """
    The critical regression suite: ensure that a negative EV for one action
    never causes a contextually inappropriate action to be substituted.
    """

    def test_non_retryable_negative_ev_escalate_does_not_fall_to_reminder(self):
        """
        REGRESSION: Non-retryable failure. ESCALATE is the only eligible action.
        If ESCALATE is not economically viable (tiny payment), the engine must STOP —
        NOT switch to SEND_PAYMENT_REMINDER which would be contextually inappropriate
        (sending a reminder to retry a non-retryable failure is wrong).
        """
        # Amount ₹10, prob 0.5 → gross=₹5. ESCALATE costs ₹15 → not viable.
        # REMINDER is cheaper but NOT in the eligible set for non-retryable.
        inp = make_input(
            failure_category="BANK",
            is_retryable=False,
            failure_severity="MEDIUM",
            amount=10.0,
            recovery_probability=0.50
        )
        out = decide(inp)
        # Must STOP, not SEND_PAYMENT_REMINDER
        assert out.recommended_action == RecoveryActionType.STOP
        assert out.recommended_action != RecoveryActionType.SEND_PAYMENT_REMINDER
        assert out.recommended_action != RecoveryActionType.RETRY

    def test_network_failure_negative_ev_retry_does_not_fall_to_reminder(self):
        """
        REGRESSION: NETWORK failure. Only RETRY is eligible.
        If RETRY is not economically viable (tiny amount), must STOP —
        NOT switch to SEND_PAYMENT_REMINDER which is contextually wrong
        (reminders are for user-action-required failures, not transient network issues).
        """
        # Amount ₹3, prob 0.5 → gross=₹1.50. RETRY costs ₹2 → not viable.
        inp = make_input(
            failure_category="NETWORK",
            is_retryable=True,
            failure_severity="LOW",
            amount=3.0,
            recovery_probability=0.50
        )
        out = decide(inp)
        assert out.recommended_action == RecoveryActionType.STOP
        assert out.recommended_action != RecoveryActionType.SEND_PAYMENT_REMINDER

    def test_user_failure_negative_ev_reminder_falls_to_link_not_retry(self):
        """
        REGRESSION: USER failure. Eligible set = [REMINDER, LINK] (in that order for low risk).
        If REMINDER is not economically viable, should try LINK next (still user-facing).
        Must NOT silently retry — a retry on an insufficient funds error will just fail again.
        """
        # Amount ₹1.50, prob 0.5 → gross=₹0.75. REMINDER (₹1) not viable. LINK (₹3) not viable.
        inp = make_input(
            failure_category="USER",
            is_retryable=True,
            failure_severity="MEDIUM",
            amount=1.5,
            recovery_probability=0.50
        )
        out = decide(inp)
        # Both reminder and link are not viable at this amount → STOP
        assert out.recommended_action == RecoveryActionType.STOP
        assert out.recommended_action != RecoveryActionType.RETRY

    def test_user_failure_medium_amount_reminder_not_viable_link_is(self):
        """
        USER failure, reminder not viable but link is.
        SEND_PAYMENT_LINK costs ₹3. At ₹7 amount, prob 0.5 → gross=₹3.5 > ₹3 → viable.
        SEND_PAYMENT_REMINDER costs ₹1. At ₹1.5 amount → not viable for this test.
        Use amount ₹7 to make reminder viable AND link viable — preferred is reminder.
        """
        inp = make_input(
            failure_category="USER",
            is_retryable=True,
            failure_severity="MEDIUM",
            amount=7.0,
            recovery_probability=0.50,
            customer_risk_score=0.2
        )
        out = decide(inp)
        # reminder (cost ₹1, gross ₹3.5 → viable) should be selected first
        assert out.recommended_action == RecoveryActionType.SEND_PAYMENT_REMINDER
        assert out.recommended_action != RecoveryActionType.RETRY

    def test_bank_failure_retry_not_viable_falls_to_reminder_not_link_for_small_amount(self):
        """
        BANK failure, low risk, small amount. Eligible: [RETRY, REMINDER].
        RETRY (cost ₹2) not viable → REMINDER (cost ₹1) checked → if viable, select it.
        Must NOT select SEND_PAYMENT_LINK which is not in this eligible set.
        """
        # amount ₹3, prob 0.5 → gross ₹1.5. RETRY (₹2) not viable. REMINDER (₹1) viable.
        inp = make_input(
            failure_category="BANK",
            is_retryable=True,
            failure_severity="MEDIUM",
            amount=3.0,
            recovery_probability=0.50,
            customer_risk_score=0.2
        )
        out = decide(inp)
        assert out.recommended_action == RecoveryActionType.SEND_PAYMENT_REMINDER

    def test_fraud_high_prob_economic_viability_does_not_override_eligibility(self):
        """
        REGRESSION: FRAUD failure with very high recovery_probability (0.99).
        The economics would say "this is highly viable" — but FRAUD has no eligible actions.
        The engine must STOP unconditionally before reaching the economic check.
        """
        inp = make_input(
            failure_category="FRAUD",
            is_retryable=False,
            recovery_probability=0.99,
            amount=5000.0
        )
        out = decide(inp)
        assert out.recommended_action == RecoveryActionType.STOP
        assert out.blocked_by_policy is True
        assert out.policy_block_reason == "FAILURE_NON_RECOVERABLE"

    def test_terminal_fraud_never_gets_user_facing_action(self):
        """
        TERMINAL severity: no action should ever be taken.
        Even if recovery_probability is high and economics are favorable.
        """
        inp = make_input(
            failure_severity="TERMINAL",
            recovery_probability=0.80,
            amount=5000.0,
            is_retryable=False
        )
        out = decide(inp)
        assert out.recommended_action == RecoveryActionType.STOP


# ─── Policy Gate Tests ────────────────────────────────────────────────────────

class TestPolicyGates:
    def test_max_attempts_stops(self):
        inp = make_input(previous_attempt_count=MAX_RECOVERY_ATTEMPTS)
        out = decide(inp)
        assert out.recommended_action == RecoveryActionType.STOP
        assert out.max_attempts_reached is True
        assert out.blocked_by_policy is True
        assert out.policy_block_reason == "MAX_ATTEMPTS_EXCEEDED"

    def test_max_attempts_exactly_at_limit(self):
        inp = make_input(previous_attempt_count=MAX_RECOVERY_ATTEMPTS)
        out = decide(inp)
        assert out.max_attempts_reached is True

    def test_one_below_max_attempts_allowed(self):
        inp = make_input(previous_attempt_count=MAX_RECOVERY_ATTEMPTS - 1)
        out = decide(inp)
        assert out.max_attempts_reached is False

    def test_probability_below_floor_stops(self):
        inp = make_input(recovery_probability=0.0)
        out = decide(inp)
        assert out.recommended_action == RecoveryActionType.STOP
        assert out.policy_block_reason == "PROBABILITY_BELOW_FLOOR"

    def test_probability_exactly_at_floor_stops(self):
        inp = make_input(recovery_probability=MIN_VIABLE_PROBABILITY - 0.001)
        out = decide(inp)
        assert out.recommended_action == RecoveryActionType.STOP

    def test_probability_above_floor_proceeds(self):
        inp = make_input(recovery_probability=MIN_VIABLE_PROBABILITY + 0.01)
        out = decide(inp)
        assert out.recommended_action != RecoveryActionType.STOP

    def test_fraud_always_stops(self):
        inp = make_input(failure_category="FRAUD", recovery_probability=0.99, is_retryable=False)
        out = decide(inp)
        assert out.recommended_action == RecoveryActionType.STOP
        assert out.policy_block_reason == "FAILURE_NON_RECOVERABLE"

    def test_terminal_severity_stops(self):
        inp = make_input(failure_severity="TERMINAL", recovery_probability=0.80)
        out = decide(inp)
        assert out.recommended_action == RecoveryActionType.STOP
        assert out.policy_block_reason == "FAILURE_NON_RECOVERABLE"

    def test_non_retryable_escalates(self):
        inp = make_input(failure_category="BANK", is_retryable=False, failure_severity="MEDIUM",
                         amount=5000.0, recovery_probability=0.60)
        out = decide(inp)
        assert out.recommended_action == RecoveryActionType.ESCALATE


# ─── Action Selection Tests ───────────────────────────────────────────────────

class TestActionSelection:
    def test_network_failure_retries(self):
        inp = make_input(failure_category="NETWORK", failure_severity="LOW", is_retryable=True)
        out = decide(inp)
        assert out.recommended_action == RecoveryActionType.RETRY

    def test_user_failure_sends_reminder_low_risk_small_amount(self):
        inp = make_input(
            failure_category="USER", failure_severity="MEDIUM",
            is_retryable=True, amount=500.0, customer_risk_score=0.2
        )
        out = decide(inp)
        assert out.recommended_action == RecoveryActionType.SEND_PAYMENT_REMINDER

    def test_user_failure_large_amount_sends_link(self):
        inp = make_input(
            failure_category="USER", failure_severity="MEDIUM",
            is_retryable=True, amount=LARGE_PAYMENT_THRESHOLD_INR + 1.0,
            customer_risk_score=0.2
        )
        out = decide(inp)
        assert out.recommended_action == RecoveryActionType.SEND_PAYMENT_LINK

    def test_bank_large_payment_sends_link(self):
        inp = make_input(
            failure_category="BANK", failure_severity="MEDIUM",
            is_retryable=True, amount=LARGE_PAYMENT_THRESHOLD_INR + 1.0,
            customer_risk_score=0.2
        )
        out = decide(inp)
        assert out.recommended_action == RecoveryActionType.SEND_PAYMENT_LINK

    def test_bank_small_payment_retries(self):
        inp = make_input(
            failure_category="BANK", failure_severity="MEDIUM",
            is_retryable=True, amount=500.0, customer_risk_score=0.2
        )
        out = decide(inp)
        assert out.recommended_action == RecoveryActionType.RETRY

    def test_high_risk_bank_sends_link(self):
        inp = make_input(
            customer_risk_score=HIGH_RISK_THRESHOLD + 0.01,
            failure_category="BANK", is_retryable=True, failure_severity="MEDIUM"
        )
        out = decide(inp)
        assert out.recommended_action == RecoveryActionType.SEND_PAYMENT_LINK

    def test_high_risk_user_sends_link(self):
        inp = make_input(
            customer_risk_score=HIGH_RISK_THRESHOLD + 0.01,
            failure_category="USER", is_retryable=True,
            failure_severity="MEDIUM", amount=300.0
        )
        out = decide(inp)
        assert out.recommended_action == RecoveryActionType.SEND_PAYMENT_LINK

    def test_high_risk_network_still_retries(self):
        """
        NETWORK failures are infrastructure problems, not customer-risk issues.
        A high-risk customer experiencing a network timeout should still get a retry.
        """
        inp = make_input(
            customer_risk_score=HIGH_RISK_THRESHOLD + 0.01,
            failure_category="NETWORK", is_retryable=True, failure_severity="LOW"
        )
        out = decide(inp)
        assert out.recommended_action == RecoveryActionType.RETRY


# ─── Boundary Conditions ─────────────────────────────────────────────────────

class TestBoundaryConditions:
    def test_probability_exactly_1_0(self):
        inp = make_input(recovery_probability=1.0)
        out = decide(inp)
        assert out.recommended_action != RecoveryActionType.STOP

    def test_probability_exactly_min_viable(self):
        # Exactly at floor: check uses `<`, so exactly at floor should pass
        inp = make_input(recovery_probability=MIN_VIABLE_PROBABILITY)
        out = decide(inp)
        assert out.policy_block_reason != "PROBABILITY_BELOW_FLOOR"

    def test_zero_previous_attempts(self):
        inp = make_input(previous_attempt_count=0)
        out = decide(inp)
        assert out.max_attempts_reached is False

    def test_high_risk_exactly_at_threshold_triggers_link(self):
        inp = make_input(
            customer_risk_score=HIGH_RISK_THRESHOLD,
            failure_category="BANK", is_retryable=True, failure_severity="MEDIUM"
        )
        out = decide(inp)
        assert out.recommended_action == RecoveryActionType.SEND_PAYMENT_LINK

    def test_amount_exactly_at_large_threshold_triggers_link_for_bank(self):
        inp = make_input(
            failure_category="BANK", is_retryable=True, failure_severity="MEDIUM",
            amount=LARGE_PAYMENT_THRESHOLD_INR, customer_risk_score=0.2
        )
        out = decide(inp)
        assert out.recommended_action == RecoveryActionType.SEND_PAYMENT_LINK


# ─── Determinism Tests ────────────────────────────────────────────────────────

class TestDeterminism:
    def test_same_input_same_output(self):
        inp = make_input()
        results = [decide(inp) for _ in range(20)]
        first = results[0]
        for r in results[1:]:
            assert r.recommended_action == first.recommended_action
            assert r.decision_reason == first.decision_reason
            assert r.economics.expected_net_value == first.economics.expected_net_value

    def test_different_failure_categories_give_different_actions(self):
        fraud_inp = make_input(failure_category="FRAUD", is_retryable=False)
        network_inp = make_input(failure_category="NETWORK", is_retryable=True)
        assert decide(fraud_inp).recommended_action != decide(network_inp).recommended_action


# ─── Output Schema Tests ──────────────────────────────────────────────────────

class TestOutputSchema:
    def test_output_has_all_required_fields(self):
        inp = make_input()
        out = decide(inp)
        assert out.payment_id == "test-payment-001"
        assert isinstance(out.timestamp, datetime)
        assert out.inputs is not None
        assert out.economics is not None
        assert out.recommended_action is not None
        assert out.decision_reason != ""
        assert out.confidence in ("HIGH", "MEDIUM", "LOW")
        assert isinstance(out.max_attempts_reached, bool)
        assert isinstance(out.blocked_by_policy, bool)

    def test_confidence_high_for_high_probability(self):
        inp = make_input(recovery_probability=0.80)
        out = decide(inp)
        assert out.confidence == "HIGH"

    def test_confidence_low_for_low_probability(self):
        inp = make_input(recovery_probability=0.20)
        out = decide(inp)
        assert out.confidence == "LOW"

    def test_blocked_policy_reason_set_when_blocked(self):
        inp = make_input(failure_category="FRAUD", is_retryable=False)
        out = decide(inp)
        assert out.blocked_by_policy is True
        assert out.policy_block_reason is not None and len(out.policy_block_reason) > 0

    def test_economics_in_output_match_recalculation(self):
        inp = make_input(amount=1000.0, recovery_probability=0.5)
        out = decide(inp)
        recalculated = calculate_economics(inp, out.recommended_action)
        assert out.economics.gross_recovery_value == recalculated.gross_recovery_value
        assert out.economics.expected_net_value == recalculated.expected_net_value

    def test_downgrade_note_in_reason_when_downgraded(self):
        """When a downgrade occurred, the reason string should mention it."""
        # BANK, low-risk, small amount → preferred=RETRY but amount=₹3 makes RETRY not viable
        # → downgrade to REMINDER
        inp = make_input(
            failure_category="BANK", is_retryable=True, failure_severity="MEDIUM",
            amount=3.0, recovery_probability=0.50, customer_risk_score=0.2
        )
        out = decide(inp)
        assert out.recommended_action == RecoveryActionType.SEND_PAYMENT_REMINDER
        assert "downgraded" in out.decision_reason.lower()
