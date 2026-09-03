# RecoveryOS Database Schema

This document outlines the Phase 1 database schema for RecoveryOS.

## Core Entities

### Merchants (`merchants`)
Represents businesses using the platform.
- **Fields**: `id` (UUID), `name`, `category`, `is_active`, `created_at`, `updated_at`

### Customers (`customers`)
Represents end-users who make payments. Includes ML-relevant aggregated features.
- **Fields**: `id` (UUID), `merchant_id` (FK), `email`, `phone`, `risk_score`, `total_payments`, `total_failures`, `total_recovered`, `created_at`, `updated_at`

### Payments (`payments`)
The core transactional entity.
- **Fields**: `id` (UUID), `customer_id` (FK), `merchant_id` (FK), `amount`, `currency`, `payment_method`, `status` (PENDING/SUCCESS/FAILED/RECOVERED), `gateway_payment_id`, `created_at`, `updated_at`

## Failure & Recovery Entities

### Payment Failures (`payment_failures`)
Detailed classification for a failed payment. 
- **Fields**: `id` (UUID), `payment_id` (FK), `error_code`, `error_message`, `failure_category`, `is_retryable`, `occurred_at`

### Recovery Actions (`recovery_actions`)
Interventions attempted by the AI agent.
- **Fields**: `id` (UUID), `payment_id` (FK), `action_type`, `action_status`, `predicted_recovery_prob`, `expected_recovery_value`, `policy_decision`, `policy_reason`, `attempt_number`, `attempted_at`

### Recovery Outcomes (`recovery_outcomes`)
The observed result of a recovery action.
- **Fields**: `id` (UUID), `recovery_action_id` (FK), `success`, `amount_recovered`, `gateway_response`, `recorded_at`

## Observability

### Audit Logs (`audit_logs`)
Immutable log of system and agent decisions.
- **Fields**: `id` (UUID), `payment_id` (FK), `event_type`, `actor`, `decision_context`, `proposed_action`, `policy_result`, `executed_action`, `explanation`, `created_at`
