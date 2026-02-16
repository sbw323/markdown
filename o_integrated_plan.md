# Integrated Aeration Curtailment Optimization Framework

## (Complete Methodology + Implementation Architecture)

This document unifies:

* Conceptual risk-energy optimization framework
* Experimental procedure definition
* Software implementation plan

The result is a reproducible pipeline that converts ASM3 physics into an operational control policy.

---

## 1. System Purpose

Design a decision framework that determines:

> *How much aeration can be reduced, and for how long, under a given influent condition — while maintaining required compliance reliability.*

The system produces:

[
\text{Influent State} \rightarrow \text{Allowed Aeration Curtailment Policy}
]

This policy becomes the training target for future predictive control.

---

## 2. Architecture Overview

The framework operates as a sequential multi-environment pipeline:

| Stage              | Environment | Role                               |
| ------------------ | ----------- | ---------------------------------- |
| Physics simulation | MATLAB      | ASM3 pseudo-dynamic experiments    |
| Data engineering   | Python      | Metric computation & risk modeling |
| Learning layer     | Python      | Surrogate model                    |
| Decision layer     | Python      | Optimization & policy extraction   |

The workflow is strictly sequential .

---

## 3. Operating Envelope Definition

### 3.1 Nominal Baseline

Compute steady state using nominal influent and aeration.
Save full biological state vector as universal initial condition .

Validation requirements:

* Converges from multiple initial conditions
* Physically realistic effluent values 

---

### 3.2 Structured Influent States

Extract representative loading regimes from historical data:

| Percentile | Regime   |
| ---------- | -------- |
| 10         | Low      |
| 25         | Off-peak |
| 50         | Normal   |
| 75         | Elevated |
| 90         | Peak     |

These form the plant operating envelope .

---

## 4. Pseudo-Dynamic Experiment Engine

### 4.1 Step-Response Simulation

For each experiment:

1. Initialize at nominal state
2. Apply influent snapshot
3. Reduce aeration
4. Run dynamic solver only for duration *t*
5. Record effluent at end time

This captures storage buffering and HRT effects .

---

### 4.2 Experiment Grid

| Variable            | Range           |
| ------------------- | --------------- |
| Influent conditions | 5               |
| Aeration reduction  | multiple levels |
| Duration            | minutes → hours |

Produces full parameter space mapping:

[
(Influent, Reduction, Duration) \rightarrow Effluent
]

Database generation described in batch runner design .

---

## 5. Performance Metrics

### 5.1 Degradation Index

[
\delta = \frac{C_{eff} - C_{nom}}{C_{limit}}
]

Interpretation:

| δ   | Meaning               |
| --- | --------------------- |
| < 0 | Improved              |
| 0–1 | Compliant degradation |
| ≥ 1 | Permit violation      |

Bounded metric avoids numerical instability .

---

### 5.2 Energy Savings

[
E_{saved} = (kLa_{nom} - kLa_{red}) \cdot t
]

Computed for each scenario .

---

## 6. Probabilistic Risk Model

Define:

* Event probability from MTBF distribution
* Consequence from degradation index

[
Risk = P(t) \times C(\delta)
]

Generates expected violation severity .

Reliability constraint:

[
R = P(\delta \le 1) \ge R_{target}
]

---

## 7. Data Processing Pipeline

Raw simulation results are transformed into a structured dataset containing:

* Effluent degradation
* Energy savings
* Expected risk

Processing scripts compute indices and normalized energy fractions .

---

## 8. Surrogate Model Layer

### Purpose

Replace expensive ODE simulation with fast approximation.

### Model Mapping

[
(Influent,\ kLa_{red},\ t) \rightarrow (\delta,\ Risk)
]

Random Forest or XGBoost recommended .

Validation:

* High predictive accuracy
* Reliable near violation boundary 

---

## 9. Optimization Engine

### Formulation

Maximize energy savings subject to reliability:

[
\max E_{saved}
]
[
\text{s.t. } Risk \le Risk_{target}
]

Implemented using NSGA-II .

The surrogate model acts as the fitness function .

---

## 10. Policy Extraction

From the Pareto front, extract operational rule:

[
\text{Influent State} \rightarrow \text{Maximum Allowed Curtailment}
]

Outputs lookup table for operators or ML control .

---

## 11. Assumptions and Validation

### Known Modeling Assumption

Instantaneous recovery after curtailment (optimistic bound).

Future validation: long dynamic simulations .

---

## 12. Complete End-to-End Workflow

1. Compute nominal steady state
2. Extract representative influent states
3. Run pseudo-dynamic aeration step tests
4. Build simulation database
5. Compute degradation & energy metrics
6. Construct probabilistic risk model
7. Train surrogate ML model
8. Run constrained NSGA-II optimization
9. Extract operational control policy
10. Validate with dynamic simulations

---

# Final Result

The framework now forms a coherent hierarchy:

| Layer        | Purpose                    |
| ------------ | -------------------------- |
| Physics      | Biological realism         |
| Data         | Quantified performance     |
| Risk         | Regulatory meaning         |
| ML           | Computational acceleration |
| Optimization | Decision making            |
| Policy       | Operational deployment     |