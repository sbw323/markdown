# Integrated Experimental Framework for Aeration Curtailment Risk-Energy Optimization

This document defines a consistent methodology for evaluating energy-saving aeration reductions in an ASM3 wastewater treatment model while preserving regulatory reliability.
The goal is to transform the existing experimental concept into a defensible **risk-constrained operational optimization framework** suitable for both steady-state interpretation and dynamic control development.

---

## 1. Conceptual Foundation

The original experimental logic is valid:

> nominal steady state → perturb influent → reduce aeration → compute normalized degradation → associate with energy savings → optimize 

This provides methodological continuity with prior dynamic experiments and preserves interpretability.

However, the system must be reformulated because:

* Steady-state cannot represent duration-dependent biological buffering 
* Reliability cannot be defined as duration/24 
* A GA cannot operate meaningfully on a fixed lookup table 

The corrected framework therefore becomes:

> Generate a dynamic step-response database → train surrogate → perform probabilistic risk optimization → derive operational policy

---

## 2. Simulation Structure

### 2.1 Nominal Operating Condition

1. Solve steady-state using nominal aeration and influent.
2. Save the full biological state vector.

This ensures every perturbation originates from a realistic operating point .

---

### 2.2 Structured Influent Sampling

Steady-state “snapshots” must represent the dynamic operating envelope.

Instead of arbitrary diurnal points, sample characteristic influent states:

| Percentile | Meaning          |
| ---------- | ---------------- |
| 10th       | Low load         |
| 25th       | Typical off-peak |
| 50th       | Normal           |
| 75th       | Elevated         |
| 90th       | Peak loading     |

This produces defensible coverage of plant operation .

---

### 2.3 Aeration Reduction Evaluation (Corrected Method)

A pure steady-state solver assumes infinite time at reduced aeration and ignores storage biology .

Instead use a **Pseudo-Dynamic Step-Response Simulation**:

1. Initialize at nominal aeration parameters
2. Apply influent snapshot
3. Reduce aeration
4. Run steady state ODE solver for the new aeration levels
5. Record effluent at end of event

This captures buffering via ASM3 storage compounds and HRT effects.

---

## 3. Effluent Degradation Index

### 3.1 Problem

Nominal-normalized metrics can explode when nominal effluent ≈ 0 .

### 3.2 Final Definition

Define degradation relative to regulatory compliance:

[
\delta = \frac{C_{eff} - C_{nom}}{C_{limit}}
]

Properties:

| Value | Interpretation            |
| ----- | ------------------------- |
| < 0   | Improvement               |
| 0–1   | Degradation but compliant |
| ≥ 1   | Permit violation          |

This gives a physically bounded reliability metric .

---

## 4. Energy Savings Calculation

Energy reduction for an event:

[
E_{saved} = (kLa_{nom} - kLa_{red}) \cdot t
]

This directly links operational action to benefit.

---

## 5. Reliability and Risk Formulation

### 5.1 Why the Original Formulation Fails

Reliability is **not proportional to duration** .

Wastewater reliability depends on:

* Frequency of curtailments
* Severity of effluent degradation
* Recovery behavior

---

### 5.2 Probabilistic Risk Assessment (Final Form)

Define:

* **P(t)** = probability of event duration from MTBF distribution
* **C(δ)** = consequence from degradation index

Expected risk:

[
Risk = P(t) \times C(\delta)
]

This converts compliance into a probabilistic quantity .

---

### 5.3 Plant Reliability

[
R = P(C_{effluent} \le C_{limit})
]

The optimization constraint becomes:

[
R \ge R_{target}
]

This matches regulatory practice .

---

## 6. Recovery Dynamics Assumption

The steady database cannot capture recovery time.

For proof-of-concept:

* Assume instantaneous recovery (optimistic bound)
* Validate later using full dynamic simulations

This limitation must be documented .

---

## 7. Optimization Strategy

### 7.1 Why Not Run GA on Database

A GA over a discrete table is just inefficient sorting .

---

### 7.2 Correct Approach — Surrogate-Assisted NSGA-II

1. Generate simulation database
2. Train ML surrogate (RF / XGBoost)
3. Run NSGA-II on surrogate
4. Obtain Pareto front

This produces the maximum energy savings for any allowed degradation .

---

## 8. Optimization Objective

Final decision formulation:

[
\max EnergySavings
]

subject to

[
Risk \le Risk_{target}
]

This converts the problem into an operationally meaningful constraint optimization .

---

## 9. End Product: Operational Policy

Instead of optimizing a single operating point, optimize a **mapping**:

[
Influent\ State \rightarrow Allowed\ Aeration\ Reduction
]

This policy directly supports future LSTM-based control .

---

# Final Unified Workflow

1. Compute nominal steady state
2. Sample structured influent conditions
3. Perform pseudo-dynamic aeration step tests
4. Compute normalized degradation index
5. Associate with energy savings
6. Build probabilistic risk model
7. Train surrogate model
8. Run NSGA-II optimization
9. Extract operational control policy

---

This unified framework resolves all inconsistencies:

| Issue                         | Resolution                 |
| ----------------------------- | -------------------------- |
| Steady-state duration paradox | Step-response simulation   |
| Normalization instability     | Limit-based index          |
| Invalid reliability metric    | PRA formulation            |
| GA misuse                     | Surrogate-assisted NSGA-II |
| Static result                 | Control policy output      |