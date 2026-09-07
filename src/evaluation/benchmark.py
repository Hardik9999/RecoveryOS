"""
Business Impact Benchmark
Compares a baseline "Blind Retry" strategy against RecoveryOS intelligent orchestration.
"""
import uuid
import random
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from src.database.models import Payment, PaymentFailure, Customer, Merchant, RecoveryAction, RecoveryOutcome
from src.simulation.simulator import PaymentSimulator
from src.simulation.adapter import SimulationAdapter
from src.simulation.rules import FAILURE_RULES
from src.decision.economics import get_intervention_cost
from src.decision.context import RecoveryActionType
from src.services.recovery_service import RecoveryService

class BenchmarkReport:
    def __init__(self, name: str, population_size: int):
        self.name = name
        self.population_size = population_size
        self.recovery_rate = 0.0
        self.recovered_value = 0.0
        self.intervention_cost = 0.0
        self.net_recovered_value = 0.0
        self.average_attempts = 0.0
        self.escalations = 0
        self.total_attempts = 0
        self.recovered_count = 0
        self.stopped_count = 0

    def to_dict(self):
        return {
            "name": self.name,
            "population_size": self.population_size,
            "recovery_rate": round(self.recovery_rate, 4),
            "recovered_value": round(self.recovered_value, 2),
            "intervention_cost": round(self.intervention_cost, 2),
            "net_recovered_value": round(self.net_recovered_value, 2),
            "average_attempts": round(self.average_attempts, 2),
            "escalations": self.escalations,
            "recovered_count": self.recovered_count,
            "stopped_count": self.stopped_count,
            "total_attempts": self.total_attempts
        }

def setup_deterministic_population(db: Session, seed: int, num_payments: int) -> List[str]:
    """Generates a deterministic population of failed payments for benchmarking."""
    rng = random.Random(seed)
    simulator = PaymentSimulator(global_seed=seed)
    adapter = SimulationAdapter(db, simulator)
    
    merchant_id = uuid.uuid4()
    merchant = Merchant(id=merchant_id, name="Benchmark Merchant")
    db.add(merchant)
    
    failed_payment_ids = []
    
    for i in range(num_payments):
        customer_id = uuid.uuid4()
        risk_score = rng.uniform(0.0, 1.0)
        customer = Customer(
            id=customer_id, 
            merchant_id=merchant_id, 
            risk_score=risk_score
        )
        db.add(customer)
        
        payment_id = uuid.uuid4()
        amount = round(rng.uniform(50.0, 5000.0), 2)
        payment_method = rng.choice(["upi", "card", "netbanking", "wallet"])
        
        payment = Payment(
            id=payment_id,
            customer_id=customer_id,
            merchant_id=merchant_id,
            amount=amount,
            payment_method=payment_method,
            status="PENDING"
        )
        db.add(payment)
        db.commit()
        
        # Force a failure for the benchmark by re-rolling until we get a failed one
        is_failed = False
        while not is_failed:
            failure_val = rng.random()
            from src.simulation.rules import determine_failure_type
            rule = determine_failure_type(failure_val, payment_method, rng)
            
            payment.status = "FAILED"
            failure = PaymentFailure(
                payment_id=payment.id,
                error_code=rule.error_code,
                error_message=f"Benchmark forced failure: {rule.error_code}",
                failure_category=rule.category,
                is_retryable=rule.is_retryable
            )
            db.add(failure)
            
            if not rule.is_retryable:
                payment.status = "FAILED_TERMINAL"
                
            db.commit()
            is_failed = True
            
        failed_payment_ids.append(str(payment_id))
        
    return failed_payment_ids

def run_baseline(db: Session, payment_ids: List[str], simulator: PaymentSimulator) -> BenchmarkReport:
    """Runs a blind-retry strategy (max 3 retries) on the population."""
    report = BenchmarkReport("Baseline", len(payment_ids))
    adapter = SimulationAdapter(db, simulator)
    
    for pid in payment_ids:
        payment = db.get(Payment, uuid.UUID(pid))
        if payment.status == "FAILED_TERMINAL":
            report.stopped_count += 1
            continue
            
        is_recovered = False
        attempts = 0
        
        for attempt in range(1, 4):
            attempts += 1
            report.total_attempts += 1
            report.intervention_cost += get_intervention_cost(RecoveryActionType.RETRY)
            
            action = RecoveryAction(
                payment_id=payment.id,
                action_type="RETRY",
                attempt_number=attempt,
                action_status="PENDING"
            )
            db.add(action)
            db.commit()
            
            outcome = adapter.execute_recovery_action(action.id)
            if outcome.success:
                is_recovered = True
                report.recovered_count += 1
                report.recovered_value += float(payment.amount)
                break
                
        if is_recovered:
            report.average_attempts += attempts
        if not is_recovered:
            report.stopped_count += 1
            
    if report.recovered_count > 0:
        report.average_attempts /= report.recovered_count
    else:
        report.average_attempts = 0.0
        
    report.recovery_rate = report.recovered_count / report.population_size
    report.net_recovered_value = report.recovered_value - report.intervention_cost
    return report

def run_recoveryos(db: Session, payment_ids: List[str]) -> BenchmarkReport:
    """Runs the full RecoveryOS intelligent pipeline on the population."""
    report = BenchmarkReport("RecoveryOS", len(payment_ids))
    service = RecoveryService(db)
    
    for pid in payment_ids:
        payment = db.get(Payment, uuid.UUID(pid))
        if payment.status == "FAILED_TERMINAL":
            report.stopped_count += 1
            continue
            
        attempts = 0
        while payment.status == "FAILED":
            if attempts > 10:
                break
            
            attempts += 1
            result = service.recover(pid)
            db.refresh(payment)
            
            action = result.get("recommended_action")
            exec_status = (result.get("execution") or {}).get("status")
            
            if action and action != "STOP":
                try:
                    report.intervention_cost += get_intervention_cost(RecoveryActionType(action))
                    report.total_attempts += 1
                    if action == "ESCALATE":
                        report.escalations += 1
                except ValueError:
                    pass
            else:
                break
                
            if exec_status == "SUCCESS":
                report.recovered_count += 1
                report.recovered_value += float(payment.amount)
                break
                
        if payment.status == "RECOVERED":
            report.average_attempts += attempts
        else:
            report.stopped_count += 1

    if report.recovered_count > 0:
        report.average_attempts /= report.recovered_count
    else:
        report.average_attempts = 0.0
        
    report.recovery_rate = report.recovered_count / report.population_size
    report.net_recovered_value = report.recovered_value - report.intervention_cost
    return report
