"""
Script to run the Business Impact Benchmark for RecoveryOS.
"""
import os
import sys
import json
import argparse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database.models import Base
from src.evaluation.benchmark import setup_deterministic_population, run_baseline, run_recoveryos
from src.simulation.simulator import PaymentSimulator

def print_report(baseline, recoveryos):
    print("\nRECOVERYOS EVALUATION")
    print("=" * 60)
    print(f"Population: {baseline.population_size} failed payments\n")
    
    print(f"{'':<25} {'Baseline':<15} {'RecoveryOS':<15}")
    print("-" * 60)
    print(f"{'Recovery Rate':<25} {baseline.recovery_rate*100:6.1f}%          {recoveryos.recovery_rate*100:6.1f}%")
    print(f"{'Recovered Value':<25} ₹{baseline.recovered_value:,.2f}      ₹{recoveryos.recovered_value:,.2f}")
    print(f"{'Intervention Cost':<25} ₹{baseline.intervention_cost:,.2f}      ₹{recoveryos.intervention_cost:,.2f}")
    print(f"{'Net Recovered Value':<25} ₹{baseline.net_recovered_value:,.2f}      ₹{recoveryos.net_recovered_value:,.2f}")
    print(f"{'Avg Attempts':<25} {baseline.average_attempts:<15.2f} {recoveryos.average_attempts:<15.2f}")
    print(f"{'Escalations':<25} {baseline.escalations:<15} {recoveryos.escalations:<15}")
    
    # Impact
    abs_improvement = recoveryos.net_recovered_value - baseline.net_recovered_value
    pct_improvement = (abs_improvement / baseline.net_recovered_value * 100) if baseline.net_recovered_value > 0 else 0.0
    print("\nBUSINESS IMPACT")
    print("-" * 60)
    print(f"Incremental Net Value:   +₹{abs_improvement:,.2f} ({pct_improvement:+.1f}%)")
    print("=" * 60)

def main():
    parser = argparse.ArgumentParser(description="Run RecoveryOS business benchmark.")
    parser.add_argument("--population", type=int, default=1000, help="Number of failed payments")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for determinism")
    args = parser.parse_args()
    
    print(f"Setting up benchmark with {args.population} payments (Seed: {args.seed})...")
    
    # Ensure fresh DB for baseline
    engine_baseline = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine_baseline)
    SessionBaseline = sessionmaker(bind=engine_baseline)
    db_baseline = SessionBaseline()
    
    pop_baseline = setup_deterministic_population(db_baseline, args.seed, args.population)
    
    # Ensure fresh DB for recoveryOS
    engine_recoveryos = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine_recoveryos)
    SessionRecoveryOS = sessionmaker(bind=engine_recoveryos)
    db_recoveryos = SessionRecoveryOS()
    
    pop_recoveryos = setup_deterministic_population(db_recoveryos, args.seed, args.population)
    
    print("Running Baseline strategy (Blind Retry)...")
    simulator = PaymentSimulator(global_seed=args.seed)
    baseline_report = run_baseline(db_baseline, pop_baseline, simulator)
    
    print("Running RecoveryOS Intelligent Orchestration...")
    recoveryos_report = run_recoveryos(db_recoveryos, pop_recoveryos)
    
    print_report(baseline_report, recoveryos_report)
    
    os.makedirs("src/evaluation", exist_ok=True)
    with open("src/evaluation/benchmark_results.json", "w") as f:
        json.dump({
            "baseline": baseline_report.to_dict(),
            "recoveryos": recoveryos_report.to_dict()
        }, f, indent=2)
        
    print(f"\nReport saved to src/evaluation/benchmark_results.json")

if __name__ == "__main__":
    main()
