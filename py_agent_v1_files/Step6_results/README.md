# LEYP-Pipe: Sewer Capital Improvement Plan Optimizer

## Overview

**LEYP-Pipe** is a Monte Carlo simulation and multi-objective optimization framework for generating optimized Capital Improvement Plans (CIPs) for sewer collection systems. It models pipe degradation physics, simulates break events over a 100-year planning horizon, applies investment strategies (rehabilitation and preventive maintenance), and uses the NSGA-II genetic algorithm to discover Pareto-optimal trade-offs between investment cost and failure risk cost.

The package is inspired by the **LEYP (Linear Extension of the Yule Process)** statistical model originally developed by Cemagref/IRSTEA for water main break prediction (see *Casses* software documentation). While the original LEYP model uses maximum-likelihood calibration on observed break histories, this implementation adapts the core concepts — Weibull baseline hazard, material covariates, and the "previous breaks increase future break rate" feedback loop — into a forward-looking simulation engine suitable for planning-level CIP optimization of sewer networks.

---

## What It Does

Given a pipe inventory CSV with attributes (ID, age, condition score, material, diameter, length, and consequence-of-failure), the package:

1. **Preprocesses** the network into analysis-ready segments (optional covariate-based grouping and segmentation).
2. **Simulates** 100 years of pipe life, including stochastic degradation, Poisson-distributed break events on virtual sub-segments, and condition-driven failure.
3. **Applies investment logic** each year: budget-constrained rehabilitation (replacement or CIPP lining) and preventive maintenance (spot repair or cleaning), prioritized by risk-reduction benefit-cost ratio.
4. **Optimizes** five decision variables simultaneously via NSGA-II to minimize both total investment spend and total risk cost across the planning horizon.
5. **Outputs** a Pareto front of strategies and a detailed year-by-year action plan for the best-found solution.

---

## Package Architecture

The package consists of seven Python modules and one YAML configuration file, organized in a linear pipeline with an optimization wrapper.

### Module Summary

| Module | Role | Key Responsibility |
|---|---|---|
| `leyp_config.py` | Configuration & Constants | All tunable parameters: file paths, column mappings, Weibull material properties, degradation physics, cost models, intervention triggers, and budget defaults. |
| `leyp_preprocessor.py` | Data Preparation | Reads raw pipe inventory CSV, standardizes column headers, optionally segments long pipes into uniform-length analysis units (~25 ft each), and writes an optimized input file. |
| `leyp_core.py` | Physics Engine | Defines the `Pipe` and `VirtualSegment` classes. Implements Weibull hazard calculation, lognormal time-to-failure sampling, exponential condition degradation, and Poisson break simulation on four virtual sub-segments per pipe. |
| `leyp_investment.py` | Investment Decision Engine | The `InvestmentManager` class implements budget-constrained, priority-ranked capital and O&M spending. Assesses rehabilitation vs. PM needs, computes annualized risk reduction, and executes interventions that modify pipe state. |
| `leyp_runner.py` | Simulation Executor | Orchestrates a single 100-year simulation run: loads data → initializes `Pipe` objects → loops (degrade → invest → simulate breaks) → accumulates investment and risk costs → returns summary or detailed action log. |
| `leyp_optimizer.py` | NSGA-II Optimization Wrapper | Defines a `pymoo` `ElementwiseProblem` with 5 genes (budget, PM start/stop thresholds, rehab trigger, capital/PM split ratio), 2 objectives (investment cost, risk cost), and 1 constraint. Runs evolutionary optimization and saves Pareto results plus the optimal action plan. |
| `leyp_orchestrator.py` | Batch Scenario Runner | Runs multiple strategy combinations (maintenance × rehabilitation) across the simulation pipeline. Used for comparative scenario analysis rather than optimization. |
| `optimizer_config.yaml` | Optimization Settings | Gene bounds, algorithm hyperparameters (population size, generations, seed), file paths, and economic parameters. |

---

## Core Concepts

### Condition Rating Scale

Pipes use a **1–6 condition score** (following NASSCO-style CCTV assessment conventions for sewer):

- **6** = Excellent (new or recently rehabilitated)
- **5** = Good (minor defects)
- **4** = Fair
- **3** = Moderate (observable deterioration)
- **2** = Poor (significant defects)
- **1** = Failed / Critical

### Degradation Model

Each pipe is assigned a **lognormal time-to-failure (TTF)** sampled from material-specific distributions (e.g., PVC mean ~85 years, CP mean ~50 years). The condition decays exponentially:

```
condition(t+dt) = condition(t) × exp(-degradation_rate × dt)
```

where `degradation_rate = ln(6.0) / TTF`. This ensures a pipe starting at condition 6 reaches condition 1 at its sampled TTF.

### Hazard & Break Simulation (LEYP-Inspired)

The annual hazard rate for each pipe follows a **Weibull baseline** with covariate adjustment:

```
h(t) = (β/η) × (t/η)^(β-1) × material_multiplier × exp(coeff_diameter × diameter) × (1 + α × n_breaks)
```

Key parameters:
- **β (shape)** and **η (scale)**: Material-specific Weibull parameters controlling how quickly hazard rises with age.
- **α**: The LEYP feedback parameter — each prior break multiplicatively increases future hazard (default 0.15).
- **n_breaks**: Cumulative break count, initially mapped from condition score.

Each pipe is divided into **4 virtual sub-segments**. Breaks are drawn from a Poisson process at each segment, and break lengths are sampled uniformly. If cumulative break length exceeds 50% of pipe length, the pipe is declared failed (condition forced to 1.0).

### Investment Logic

The `InvestmentManager` splits annual budget between capital (rehab) and O&M (PM) using a configurable ratio, then:

1. **Rehab candidates** (condition ≤ rehab trigger, default 2.0): Ranked by `(risk_reduction) / cost`. If break damage exceeds 67% of length or pipe is already lined → full **Replacement** (to PVC, condition reset to 6.0). Otherwise → **CIPP Lining** (condition set to 4.0).

2. **PM candidates** (condition between PM stop and PM start, defaults 2.5–4.0): If prior breaks > 1 → **Spot Repair** (condition boosted by 0.5). Otherwise → **Cleaning** (grants 1 year of degradation immunity, no condition boost in current config).

3. Actions are executed in priority order until the respective budget pool is exhausted.

### Annualized Risk

Risk for each pipe is computed as:

```
Annualized_Risk = (CoF × Length × Cost_per_ft) / TTF_remaining
```

This captures both the consequence severity and the urgency (shorter remaining life = higher annualized risk). The optimizer minimizes the sum of all failure costs realized over 100 years.

### NSGA-II Optimization

The optimizer searches a 5-dimensional decision space:

| Gene | Description | Default Range |
|---|---|---|
| `budget` | Annual total budget ($) | $5,000 – $1,000,000 |
| `pm_start` | Condition threshold to begin PM | 2.0 – 4.0 |
| `pm_stop` | Condition threshold to stop PM | 2.0 – 4.0 |
| `rehab_trigger` | Condition at which rehab is triggered | 1.0 – 2.0 |
| `budget_split` | Fraction of budget allocated to capital | 10% – 90% |

A feasibility constraint enforces `pm_stop < pm_start`. The two objectives — total investment cost and total risk cost over 100 years — form a Pareto front. The solution with the lowest combined total cost is selected as the recommended strategy, and a detailed action plan is generated for it.

---

## Input Data Format

The input CSV must contain the following columns (mapped via `COLUMN_MAP` in config):

| CSV Header | Internal Name | Description |
|---|---|---|
| `id` | `PipeID` | Unique pipe segment identifier (e.g., `MH-1-014_MH-1-013`) |
| `age` | `Age` | Current age in years |
| `condition` | `Condition` | Condition score (1–6) |
| `material` | `Material` | Pipe material code: PVC, DIP, CP, CIPP, VCP |
| `diameter` | `Diameter` | Diameter in inches |
| `length` | `Length` | Length in feet |
| `cof` | `CoF_Value` | Consequence of Failure multiplier (defaults to 1.0) |

Additional columns in the sample data (`needs_clea`, `needs_cipp`, `needs_poin`, `no_action`, `Risk`) are present from upstream assessment but are not consumed by the simulation engine directly.

---

## Output Files

When optimization completes, the following are written to `Optimization_Results_NSGA2/`:

| File | Contents |
|---|---|
| `nsga2_results.csv` | Full Pareto front: investment cost, risk cost, total cost, and the 5 gene values for each solution |
| `Optimal_Action_Plan.csv` | Year-by-year action log for the best strategy: pipe ID, action type, cost, priority score, and condition before/after |
| `optimization_curve.png` | Visualization of investment vs. risk vs. total cost, with the optimum marked |

---

## How to Run

### Prerequisites

```
pip install numpy pandas matplotlib pyyaml pymoo
```

**Optional** (only required for the MCP server path):

```
pip install claude-agent-sdk
```

### Single Simulation

```python
from leyp_runner import run_simulation

inv_cost, risk_cost = run_simulation(
    use_mock_data=False,
    override_input_path="temp_optimization_input.csv",
    annual_budget=50000,
    pm_start=4.0,
    pm_stop=2.5,
    rehab_trigger=2.0,
    budget_split=0.80
)
print(f"Investment: ${inv_cost:,.0f}  |  Risk: ${risk_cost:,.0f}")
```

### Full Optimization

1. Edit `optimizer_config.yaml` to set your input file path and desired gene bounds.
2. Run:

```bash
python leyp_optimizer.py
```

3. Review results in `Optimization_Results_NSGA2/`.

### Batch Scenario Comparison (Orchestrator)

The orchestrator requires a separate `orchestrator_config.yaml` and a `leyp_strategy_applicator.py` module (not included in this package). It is designed for comparative analysis of pre-defined maintenance/rehabilitation strategy combinations.

---

## Relationship to the Original LEYP / Casses Software

The original **LEYP** model (Le Gat, 2008) is a parametric statistical model for water main break prediction, implemented in the **Casses** software by Cemagref. It uses maximum-likelihood estimation on historical break data to calibrate:

- A **Weibull baseline hazard** capturing age-related failure
- **Covariate coefficients** (material, diameter, length, soil, etc.)
- An **α parameter** quantifying how prior breaks accelerate future failure (the "Yule process" extension)
- **Selective survival bias** corrections (ζ₀, ζ₁)

This Python package borrows the conceptual framework but differs in several important ways:

| Aspect | Original LEYP/Casses | This Package |
|---|---|---|
| **Purpose** | Retrospective break prediction from observed data | Forward simulation for CIP planning |
| **Calibration** | Maximum-likelihood on break histories | Pre-set material parameters (no calibration) |
| **Condition** | Not modeled (break-count only) | Explicit 1–6 condition score with exponential decay |
| **Investment** | Not modeled | Full budget-constrained rehab/PM decision engine |
| **Optimization** | Not included | NSGA-II multi-objective optimization |
| **Target** | Water mains | Sewer collection systems |
| **Break model** | Exact LEYP likelihood | Simplified Poisson on virtual sub-segments |

---

## Configuration Quick Reference

All tunable parameters live in `leyp_config.py`:

- **`ALPHA`** (0.15): Break feedback intensity. Higher values mean prior breaks more aggressively increase future hazard.
- **`MATERIAL_PROPS`**: Weibull β/η and base multiplier per material.
- **`DEGRADATION_PARAMS`**: Mean and standard deviation of time-to-failure per material.
- **`COST_MODELS`**: Unit cost per inch-foot for each intervention type.
- **`TRIGGERS`**: Condition thresholds for PM start/stop and rehab initiation.
- **`ANNUAL_BUDGET`**: Default annual budget (overridden by optimizer).
- **`GLOBAL_COST_PER_FT`**: Failure consequence cost rate ($500/ft default).

---

## Limitations & Assumptions

- **No spatial correlation**: Pipes are treated as independent; no modeling of shared trench conditions, soil zones, or hydraulic interdependence.
- **Stochastic variability**: Results vary between runs due to Monte Carlo sampling. The optimizer uses a fixed seed for reproducibility, but individual simulation calls are not seeded.
- **Simplified cost model**: Intervention costs scale linearly with length only (diameter is in the cost model structure but not currently applied as a multiplier).
- **No inflation or discounting**: All costs are in present-value dollars.
- **100-year horizon**: Fixed; not configurable without code changes.
- **Single-period budget**: The same annual budget applies every year; no multi-year capital planning or debt financing.

---

## License

Internal / Proprietary. For authorized use only.
