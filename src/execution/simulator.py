"""
Execution layer implementation using the PaymentSimulator and database.
"""
from src.execution.base import RecoveryExecutor, ExecutionResult
from src.decision.context import RecoveryActionType
from src.simulation.adapter import SimulationAdapter
from src.database.models import RecoveryAction
from sqlalchemy.orm import Session
import uuid

class DBBackedSimulatorExecutor(RecoveryExecutor):
    """
    Executes a recovery action by persisting it to the DB and running
    the simulation adapter to get the deterministic outcome.
    """
    def __init__(self, db_session: Session):
        self.db = db_session
        self.adapter = SimulationAdapter(db=self.db)

    def execute(self, payment_id: str, action: RecoveryActionType, attempt_number: int) -> ExecutionResult:
        try:
            # Idempotency check: Ensure we haven't already executed this attempt
            existing_action = self.db.query(RecoveryAction).filter(
                RecoveryAction.payment_id == uuid.UUID(payment_id),
                RecoveryAction.attempt_number == attempt_number
            ).first()
            
            if existing_action:
                if existing_action.action_status == "EXECUTED":
                    from src.database.models import RecoveryOutcome
                    outcome = self.db.query(RecoveryOutcome).filter(RecoveryOutcome.recovery_action_id == existing_action.id).first()
                    return ExecutionResult(
                        payment_id=payment_id,
                        action_type=action,
                        success=outcome.success if outcome else True,
                        amount_recovered=float(outcome.amount_recovered) if outcome and outcome.amount_recovered else 0.0,
                        gateway_response=outcome.gateway_response if outcome else {"status": "already_executed"},
                        error_message="Idempotent return."
                    )
                else:
                    action_record = existing_action
            else:
                # Create PENDING RecoveryAction record
                action_record = RecoveryAction(
                    payment_id=uuid.UUID(payment_id),
                    action_type=action.value,
                    attempt_number=attempt_number,
                    action_status="PENDING"
                )
                self.db.add(action_record)
                self.db.commit()
            
            # Execute it via adapter
            outcome = self.adapter.execute_recovery_action(action_record.id)
            
            return ExecutionResult(
                payment_id=payment_id,
                action_type=action,
                success=outcome.success,
                amount_recovered=outcome.amount_recovered,
                gateway_response=outcome.gateway_response,
                error_message=""
            )
        except Exception as e:
            self.db.rollback()
            return ExecutionResult(
                payment_id=payment_id,
                action_type=action,
                success=False,
                amount_recovered=0.0,
                gateway_response={},
                error_message=str(e)
            )
