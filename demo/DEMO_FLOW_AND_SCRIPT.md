# RecoveryOS — Complete Flow & Video Demo Guide

Welcome to the comprehensive walkthrough of **RecoveryOS**. This document explains both the **technical architecture under the hood** and provides a **step-by-step video demo script** so you can deliver a compelling and authoritative demonstration of the product.

---

## 1. Executive Summary: What is RecoveryOS?

In modern digital payments (UPI, Cards, Netbanking), payment failures are inevitable. Failures happen due to network drops, bank downtimes, insufficient funds, OTP timeouts, or suspected fraud.

Most payment gateways handle failures naively:
- **Blind Retries:** Hammering the bank repeatedly, costing gateway fees, increasing churn, and risking bank blocks.
- **Generic Payment Links:** Spamming customer notifications for transactions that will never succeed.
- **Ignoring Economics:** Spending ₹10 in operational intervention costs to recover a ₹5 transaction.
- **Zero Risk Awareness:** Retrying transactions that were flagged for high fraud risk.

**RecoveryOS** solves this. It is an **AI-powered revenue recovery intelligence and orchestration platform**.

### Core Philosophy
> **"AI proposes. Deterministic Economics and Policy Guardrails decide and authorize. Safe execution occurs. Outcomes are observed."**

The reasoning agent proposes actions based on failure context and economics, but **it never has unrestricted authority over financial decisions**. Every action must pass strict deterministic financial policies before execution.

---

## 2. End-to-End Architectural Flow

The entire lifecycle of a failed transaction flows through 6 distinct stages:

```mermaid
flowchart TD
    A[Failed Payment] --> B[1. Failure Intelligence & Taxonomy]
    B --> C[2. ML Recovery Prediction Model]
    C --> D[3. Economic Decision Engine]
    D --> E[4. AI Agent Proposal (LangGraph)]
    E --> F{5. Deterministic Policy Guardrails}
    F -- DENY --> G[Abort / Stop Execution]
    F -- ALLOW --> H[6. Execution Engine]
    H --> I[Outcome Recorded & Audited]
    I -- If Failed & Retries Left --> E
    I -- If Recovered --> J[Status: RECOVERED]
    G --> K[Status: FAILED_TERMINAL]
```

### Stage-by-Stage Breakdown

| Stage | Component | What Happens |
| :--- | :--- | :--- |
| **1. Failure Intelligence** | `src/intelligence/` | Normalizes raw gateway errors into a clean taxonomy: `NETWORK` (transient), `BANK` (issuer downtime/funds), `USER` (wrong OTP/dropped link), or `FRAUD`/`TERMINAL` (stolen card). |
| **2. Recovery Prediction** | `src/prediction/` | An XGBoost/probability calibration model predicts the likelihood that this payment can be recovered: $P(\text{recovery}) \in [0, 1]$. It uses strictly point-in-time features without data leakage. |
| **3. Economic Decision Engine** | `src/decision/` | Calculates **Expected Net Value (ENV)**:<br>$$\text{ENV} = (\text{Amount} \times P(\text{recovery})) - \text{Intervention Cost}$$<br>Filters actions by eligibility and ensures the business never loses money attempting a recovery. |
| **4. AI Agent (LangGraph)** | `src/agent/` | A stateful reasoning agent analyzes the transaction context, error taxonomy, and economic recommendation to propose the optimal operational action and rationale. |
| **5. Policy Engine Guardrails** | `src/policy/` | An independent, deterministic safety boundary evaluating 9 strict rules (Max 3 attempts, cooldown times, fraud blocks, cost thresholds). **The agent cannot bypass this layer.** |
| **6. Execution & Audit** | `src/execution/` | Executes the action (e.g. smart retry, payment reminder, or payment link), logs the outcome in the DB, and updates system analytics. |

---

## 3. Video Demo Script & Walkthrough Guide

Use this section as your exact speaking points and visual path while recording your demo video.

### **Scene 1: Introduction (0:00 - 0:45)**
* **What to show on screen:** Open the browser to [http://localhost:8501](http://localhost:8501) on the **Welcome screen** or **Executive Dashboard**.
* **What to say:**
  > *"Hello everyone! Today I’m excited to show you **RecoveryOS**, an intelligent payment recovery platform designed to recover lost revenue from failed digital transactions.*
  > 
  > *In online commerce, failed payments cause billions in lost GMV. But traditional recovery systems either retry blindly—wasting fees and irritating customers—or spam payment links without understanding why the payment failed in the first place.*
  > 
  > *RecoveryOS brings together failure intelligence, calibrated machine learning, economic evaluation, and an autonomous reasoning agent governed by strict, deterministic financial guardrails. Let's walk through how it works."*

---

### **Scene 2: Executive Dashboard (0:45 - 1:45)**
* **What to show on screen:** Click on **`Executive Dashboard`** in the left sidebar. Let the KPI cards and chart load.
* **What to point out:**
  1. **Top Row KPI Cards:**
     - **Revenue at Risk:** Total value of payments that failed.
     - **Revenue Recovered:** Actual money saved and brought back into the merchant's account.
     - **Recovery Rate:** Percentage of failed transactions successfully recovered.
     - **Net Recovered Value:** The bottom-line financial impact (Revenue Recovered minus Intervention Costs).
  2. **Bottom Row & Charts:**
     - **Interventions Avoided:** Highlights intelligent restraint. RecoveryOS saved money by NOT retrying hopeless or fraudulent payments.
     - **Payment Outcomes Donut Chart:** Visual breakdown of Recovered vs. Stopped/Terminal vs. Pending.
* **What to say:**
  > *"We start here at the **Executive Dashboard**, built for finance and operations leaders. 
  > 
  > Notice that RecoveryOS doesn't just track recovered revenue—it tracks **Net Recovered Value**. Every retry or SMS payment link costs real money. By factoring in intervention costs and automatically avoiding unviable attempts, RecoveryOS ensures that every action taken is economically positive."*

---

### **Scene 3: Payment Explorer — Inspecting a Failure (1:45 - 3:00)**
* **What to show on screen:** Click on **`Payment Explorer`** in the sidebar.
* **What to do:**
  1. Show the **Recent Payments** table (Amount, Payment Method, Failure Type, Status).
  2. Select a payment with status `FAILED` from the dropdown list.
  3. Explore the 3 tabs on the right:
     - **Intelligence Tab:** Show the categorized failure (e.g. Category: `BANK`, Code: `INSUFFICIENT_FUNDS`, Retryable: `Yes`).
     - **Context Tab:** Show customer risk score, merchant info, and transaction metadata.
     - **Recovery History Tab:** Show previous attempt history.
* **What to say:**
  > *"Now let's look under the hood at an individual payment in the **Payment Explorer**.
  > 
  > Here we can see an unrecovered transaction. Rather than just seeing a raw error message, our **Failure Intelligence layer** has categorized the failure, identified whether it is technically retryable, and evaluated the customer's risk profile.
  > 
  > Now, watch what happens when I click **Run Recovery Workflow**."*

---

### **Scene 4: Executing Recovery & The Decision Trace (3:00 - 4:45) ⭐ (Most Important Screen)**
* **What to show on screen:**
  1. Click **`Run Recovery Workflow`** on the payment.
  2. Once complete, navigate to **`Decision Trace`** in the sidebar.
* **What to point out on the Decision Trace screen:**
  1. **Step 1: Intelligence & Economics**
     - Point out the **Recovery Probability** calculated by the ML model (e.g., 72%).
     - Point out the **Expected Net Value (ENV)** calculation (Gross Recovery vs. Cost).
  2. **Step 2: AI Decision (Agent Proposal)**
     - Show the proposed action (e.g., `RETRY` or `SEND_PAYMENT_REMINDER`).
     - Highlight the **Rationale** generated by the agent explaining why this action was chosen.
  3. **Step 3: Deterministic Policy Guardrail**
     - Show the **Guardrail Check: ALLOWED** banner (or DENIED if limits reached).
     - **Emphasize the core architectural message:** The AI is an advisor; the deterministic policy engine has final veto authority.
  4. **Step 4: Execution & Final Outcome**
     - Show the Execution Status (`SUCCESS`) and Final Status (`RECOVERED`).
* **What to say:**
  > *"This is the **Decision Trace**, the core showcase of RecoveryOS's architecture. It makes the decision pipeline completely transparent and auditable.
  > 
  > First, our machine learning model estimates the probability of recovery.
  > 
  > Second, the Economic Engine calculates the Expected Net Value to ensure the action is commercially viable.
  > 
  > Third, our LangGraph agent reasons over this context and proposes the optimal recovery action with an operational rationale.
  > 
  > Fourth—and most importantly—notice this section: **Deterministic Policy Guardrails**. In a regulated financial environment, you cannot let an autonomous agent make unconstrained financial choices. Our deterministic policy engine verifies that the action respects hard limits: cooldown periods, max retries, and fraud checks.
  > 
  > Because it was approved by policy, the execution succeeded, and the payment is now marked as **RECOVERED**."*

---

### **Scene 5: Recovery Operations — Batch Recovery (4:45 - 6:00)**
* **What to show on screen:** Navigate to **`Recovery Operations`** in the sidebar.
* **What to do:**
  1. Enter a batch size (e.g., `20` or `50`).
  2. Click **`Run Batch Recovery`**.
  3. Watch the progress spinner as the backend processes the transactions.
  4. Once complete, show the **Batch Results Summary** and the **Batch Details Table**.
* **What to point out:**
  - Metrics: Payments Processed, Payments Recovered, Revenue Recovered, Policy Denied, Stopped/Terminal.
  - In the table: Show different statuses (`RECOVERED`, `FAILED_TERMINAL`, `FAILED`).
  - Explain what `FAILED_TERMINAL` means: *"Notice these payments marked `FAILED_TERMINAL`—RecoveryOS correctly identified them as hard failures (such as fraud or exceeding max retries) and halted execution to prevent financial waste."*
* **What to say:**
  > *"Finally, let’s look at **Recovery Operations** for scaled automation.
  > 
  > In production, operations teams handle thousands of failed transactions daily. Here, we can run a controlled batch of payments through the complete pipeline.
  > 
  > When I trigger this batch, the FastAPI backend processes each payment sequentially through prediction, economics, agent proposal, and policy evaluation.
  > 
  > In just a few seconds, look at the aggregate results: we recovered revenue, tracked our intervention costs, and correctly halted terminal transactions without a single manual intervention."*

---

### **Scene 6: Conclusion (6:00 - 6:30)**
* **What to show on screen:** Switch back to the **Executive Dashboard** (showing the newly updated metrics from the batch run).
* **What to say:**
  > *"To summarize: RecoveryOS transforms payment recovery from a dumb retry loop into an intelligent, economically grounded, and safely governed revenue engine.
  > 
  > With calibrated ML, autonomous agent reasoning, and non-negotiable deterministic guardrails, RecoveryOS delivers maximum recovery with zero financial hallucination.
  > 
  > Thank you for watching!"*

---

## 4. Key Terminology Cheat Sheet for the Demo

Keep these handy in case questions arise:

| Term | Plain English Meaning |
| :--- | :--- |
| **`FAILED`** | A payment that failed, but is still eligible for recovery attempts. |
| **`RECOVERED`** | A payment that was successfully recovered via an intervention (retry, reminder, or link). |
| **`FAILED_TERMINAL`** | A payment that has permanently failed and will never be retried (e.g., suspected fraud, stolen card, or hit the 3-attempt maximum limit). |
| **`Expected Net Value (ENV)`** | $\text{Gross Recovery Value} - \text{Intervention Cost}$. RecoveryOS only acts if ENV is positive. |
| **`Policy Guardrail`** | Deterministic Python rules that act as an unbreachable firewall between the AI proposal and money movement. |
