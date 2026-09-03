"""
Economic calculation layer for the Decision Engine.
All math is explicit, auditable, and has no hidden state.

Intervention cost model (INR equivalent):
  RETRY                → ₹2.00   (gateway retry fee + infra)
  SEND_PAYMENT_REMINDER → ₹1.00  (SMS/email delivery cost)
  SEND_PAYMENT_LINK    → ₹3.00   (link generation + notification + tracking)
  ESCALATE             → ₹15.00  (human agent time)
  STOP                 → ₹0.00   (no action taken)
"""
from src.decision.context import DecisionInput, Economics, RecoveryActionType

# Fixed intervention costs in INR
INTERVENTION_COSTS: dict[RecoveryActionType, float] = {
    RecoveryActionType.RETRY:                  2.0,
    RecoveryActionType.SEND_PAYMENT_REMINDER:  1.0,
    RecoveryActionType.SEND_PAYMENT_LINK:      3.0,
    RecoveryActionType.ESCALATE:              15.0,
    RecoveryActionType.STOP:                   0.0,
}


def get_intervention_cost(action: RecoveryActionType) -> float:
    return INTERVENTION_COSTS[action]


def calculate_economics(inputs: DecisionInput, action: RecoveryActionType) -> Economics:
    """
    Calculate expected economic value for a proposed recovery action.

    gross_recovery_value  = amount × recovery_probability
    intervention_cost     = fixed cost of the action type
    expected_net_value    = gross_recovery_value − intervention_cost
    break_even_probability = intervention_cost / amount
    is_economically_viable = expected_net_value > 0
    """
    gross = inputs.amount * inputs.recovery_probability
    cost = get_intervention_cost(action)
    net = gross - cost

    # Break-even: what probability is needed for this action to just pay for itself?
    break_even = cost / inputs.amount if inputs.amount > 0 else float("inf")

    return Economics(
        gross_recovery_value=round(gross, 4),
        intervention_cost=round(cost, 4),
        expected_net_value=round(net, 4),
        break_even_probability=round(break_even, 6),
        is_economically_viable=(net > 0)
    )
