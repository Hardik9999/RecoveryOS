import random
from faker import Faker
from sqlalchemy.orm import Session
from src.database.session import SessionLocal
from src.database.models import Merchant, Customer, Payment, PaymentFailure, RecoveryAction, RecoveryOutcome, AuditLog
import uuid
import sys
from datetime import datetime, timedelta
from src.simulation.rules import determine_failure_type, calculate_recovery_probability

fake = Faker()
Faker.seed(42)
random.seed(42)

def seed_data(db: Session, target_payments=1000):
    print(f"Starting to seed data. Target payments: {target_payments}")
    
    # Check if DB is already seeded
    if db.query(Payment).count() > 0:
        print("Database already contains payments. Aborting seed.")
        return

    # Seed Merchants
    merchants = []
    merchant_categories = ['E-commerce', 'SaaS', 'Retail', 'Gaming', 'EdTech']
    for _ in range(10):
        merchant = Merchant(
            id=uuid.uuid4(),
            name=fake.company(),
            category=random.choice(merchant_categories),
            is_active=True
        )
        db.add(merchant)
        merchants.append(merchant)
    db.commit()
    print(f"Seeded {len(merchants)} merchants.")

    # Seed Customers
    customers = []
    for _ in range(100):
        customer = Customer(
            id=uuid.uuid4(),
            merchant_id=random.choice(merchants).id,
            email=fake.email(),
            phone=fake.phone_number(),
            risk_score=round(random.uniform(0.0, 1.0), 2),
            total_payments=0,
            total_failures=0,
            total_recovered=0
        )
        db.add(customer)
        customers.append(customer)
    db.commit()
    print(f"Seeded {len(customers)} customers.")

    # Seed Payments with realistic temporal spacing
    payments = []
    payment_methods = ['card', 'upi', 'netbanking', 'wallet']
    statuses = ['SUCCESS', 'SUCCESS', 'SUCCESS', 'FAILED']  # 25% failure rate
    base_time = datetime(2024, 1, 1, 0, 0, 0)

    for i in range(target_payments):
        status = random.choice(statuses)
        created_at = base_time + timedelta(hours=i * 4 + random.randint(0, 3))
        payment = Payment(
            id=uuid.uuid4(),
            customer_id=random.choice(customers).id,
            merchant_id=random.choice(merchants).id,
            amount=round(random.uniform(50.0, 5000.0), 2),
            currency='INR',
            payment_method=random.choice(payment_methods),
            status=status,
            gateway_payment_id=f"pay_{fake.uuid4()[:16]}",
            created_at=created_at.isoformat()
        )
        db.add(payment)
        payments.append(payment)
        
        # Update customer counters
        cust = db.get(Customer, payment.customer_id)
        cust.total_payments += 1
        if status == 'FAILED':
            cust.total_failures += 1
            
        if (i + 1) % 100 == 0:
            db.commit()
            print(f"Seeded {i + 1} payments...")
            
    db.commit()
    print(f"Finished seeding {len(payments)} payments.")

    failed_payments = [p for p in payments if p.status == 'FAILED']
    recovered_count = 0

    for p in failed_payments:
        cust = db.get(Customer, p.customer_id)
        
        # Use the simulation rules engine to pick a method-aware failure type
        rule = determine_failure_type(random.random(), p.payment_method)
        is_retryable = rule.is_retryable

        failure = PaymentFailure(
            id=uuid.uuid4(),
            payment_id=p.id,
            error_code=rule.error_code,
            error_message=f"Payment failed due to {rule.error_code}",
            failure_category=rule.category,
            is_retryable=is_retryable
        )
        db.add(failure)

        # Only attempt recovery for retryable failures
        if not is_retryable and rule.base_recovery_prob_delayed == 0.0:
            p.status = 'FAILED_TERMINAL'
            continue

        # Choose action based on error type and amount
        if rule.error_code in ['NPCI:U69', 'VISA:51', 'MC:51', 'INSUFFICIENT_FUNDS']:
            action_type = 'SEND_PAYMENT_REMINDER'
        elif rule.category == 'NETWORK':
            action_type = 'RETRY'
        elif not rule.is_retryable:
            action_type = 'SEND_PAYMENT_LINK'
        elif float(p.amount) > 2000:
            action_type = 'SEND_PAYMENT_LINK'
        else:
            action_type = random.choice(['RETRY', 'SEND_PAYMENT_REMINDER'])
            
        is_delayed = action_type in ('SEND_PAYMENT_REMINDER', 'SEND_PAYMENT_LINK')
        
        # Compute signal-bearing recovery probability using the rule
        recovery_prob = calculate_recovery_probability(rule, cust.risk_score, is_delayed)
        
        # Amount penalty: log-scale, normalized to amounts 50–5000 INR
        import math
        amount_factor = max(0.6, 1.0 - (math.log(float(p.amount)) / math.log(5000)) * 0.3)
        recovery_prob = min(0.95, max(0.00, recovery_prob * amount_factor))
        
        if recovery_prob < 0.05:
            p.status = 'FAILED_TERMINAL'
            continue

        action = RecoveryAction(
            id=uuid.uuid4(),
            payment_id=p.id,
            action_type=action_type,
            action_status='EXECUTED',
            predicted_recovery_prob=round(recovery_prob, 4),
            expected_recovery_value=round(float(p.amount) * recovery_prob, 2),
            policy_decision='ALLOW',
            policy_reason='Within limits',
            attempt_number=1
        )
        db.add(action)

        # Recovery outcome driven by computed probability (with noise)
        is_success = random.random() < recovery_prob

        outcome = RecoveryOutcome(
            id=uuid.uuid4(),
            recovery_action_id=action.id,
            success=is_success,
            amount_recovered=float(p.amount) if is_success else 0.0,
            gateway_response={"status": "success" if is_success else "failed"}
        )
        db.add(outcome)

        if is_success:
            p.status = 'RECOVERED'
            cust.total_recovered += 1
            recovered_count += 1
        else:
            p.status = 'FAILED_TERMINAL'

        log = AuditLog(
            id=uuid.uuid4(),
            payment_id=p.id,
            event_type="RECOVERY_ATTEMPT",
            actor="System Agent",
            decision_context={"predicted_prob": round(recovery_prob, 4), "expected_val": float(action.expected_recovery_value)},
            proposed_action=action_type,
            policy_result="ALLOW",
            executed_action=action_type,
            explanation=f"Recovery attempted. Prob={recovery_prob:.3f}"
        )
        db.add(log)

    db.commit()
    print(f"Seeded failures, actions, outcomes, and audit logs.")
    print(f"Recovery rate: {recovered_count}/{len(failed_payments)} = {recovered_count/max(1,len(failed_payments)):.2%}")
    print("Seed complete!")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        target = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
        seed_data(db, target)
    finally:
        db.close()
