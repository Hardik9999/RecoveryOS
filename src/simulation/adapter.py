import uuid
from sqlalchemy.orm import Session
from src.database.models import Payment, PaymentFailure, RecoveryAction, RecoveryOutcome, Customer
from src.simulation.simulator import PaymentSimulator
from src.simulation.rules import FAILURE_RULES

class SimulationAdapter:
    def __init__(self, db: Session, simulator: PaymentSimulator = None):
        self.db = db
        self.simulator = simulator or PaymentSimulator()

    def execute_initial_payment(self, payment_id: uuid.UUID) -> Payment:
        payment = self.db.get(Payment, payment_id)
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")
        if payment.status != "PENDING":
            raise ValueError(f"Payment {payment_id} is not PENDING")

        customer = self.db.get(Customer, payment.customer_id)
        
        is_success, rule, response = self.simulator.process_initial_payment(
            payment_id=payment.id,
            risk_score=customer.risk_score
        )

        if is_success:
            payment.status = "SUCCESS"
        else:
            payment.status = "FAILED"
            failure = PaymentFailure(
                payment_id=payment.id,
                error_code=rule.error_code,
                error_message=response["message"],
                failure_category=rule.category,
                is_retryable=rule.is_retryable
            )
            self.db.add(failure)
            
            # If not retryable, it's terminal
            if not rule.is_retryable:
                payment.status = "FAILED_TERMINAL"
                
        self.db.commit()
        self.db.refresh(payment)
        return payment

    def execute_recovery_action(self, recovery_action_id: uuid.UUID) -> RecoveryOutcome:
        action = self.db.get(RecoveryAction, recovery_action_id)
        if not action:
            raise ValueError(f"RecoveryAction {recovery_action_id} not found")
        if action.action_status != "PENDING":
            raise ValueError("RecoveryAction must be PENDING to execute")

        payment = self.db.get(Payment, action.payment_id)
        customer = self.db.get(Customer, payment.customer_id)
        
        # We need the failure rule that caused this payment to fail
        # In a real app we might fetch it from DB, but we map error_code to rule here
        failure = payment.failures[0]
        rule = FAILURE_RULES.get(failure.error_code)

        if not rule:
            raise ValueError(f"Unknown rule for error code {failure.error_code}")

        is_success, response = self.simulator.process_recovery_attempt(
            payment_id=payment.id,
            rule=rule,
            risk_score=customer.risk_score,
            action_type=action.action_type,
            attempt_number=action.attempt_number
        )

        action.action_status = "EXECUTED"
        
        outcome = RecoveryOutcome(
            recovery_action_id=action.id,
            success=is_success,
            amount_recovered=payment.amount if is_success else 0.0,
            gateway_response=response
        )
        self.db.add(outcome)

        if is_success:
            payment.status = "RECOVERED"
        elif not rule.is_retryable or action.attempt_number >= 3:
            # Hardcode max 3 attempts for simulation terminal state logic
            payment.status = "FAILED_TERMINAL"

        self.db.commit()
        self.db.refresh(outcome)
        return outcome
