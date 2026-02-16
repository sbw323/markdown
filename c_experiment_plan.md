# Implementation Plan: Aeration Curtailment Risk-Energy Optimization

## Architecture Overview

The implementation spans three computational environments and four development phases:

| Environment     | Purpose                                             | Language       |
| --------------- | --------------------------------------------------- | -------------- |
| MATLAB/Simulink | ASM3 simulation, step-response database generation  | MATLAB         |
| Python          | Data processing, surrogate modeling, optimization   | Python 3.11+   |

The dependency chain is strictly sequential: simulation → processing → modeling → optimization. Each phase produces artifacts that become inputs to the next.

---

## Phase 1: Nominal Baseline and Simulation Infrastructure

**Goal:**Establish a working ASM3 steady-state solver, generate the nominal operating point, and validate that the simulation produces physically meaningful results.

### 1.1 ASM3 Model Setup (MATLAB)

**Deliverables:**

- `asm3_parameters.m`— Full ASM3 kinetic and stoichiometric parameter set. Source values from Gujer et al. (1999) or the BSM1/BSM2 benchmark defaults. Store as a struct for clean passing between functions.
- `asm3_ode_system.m`— The ASM3 ODE right-hand side function. This takes the state vector (14 ASM3 state variables), influent vector, and aeration rate (kLa) as inputs and returns dX/dt. Write this as a standalone function so it can be called by both steady-state and dynamic solvers.
- `nominal_influent.m`— Define the nominal influent composition. Use the BSM1 dry-weather average influent as the starting point. Store flow rate Q, and all ASM3 influent fractions (S_I, S_S, X_I, X_S, X_H, X_A, X_STO, S_O2, S_NOX, S_NH4, S_N2, S_ALK, X_SS).
- `reactor_geometry.m`— Define the five-reactor activated sludge configuration (anoxic-anoxic-aerobic-aerobic-aerobic) and settler model parameters. Include reactor volumes, recycle ratios, and wastage rates.

**Acceptance criteria:**The parameter set is complete, documented with units and source references, and the ODE function returns a vector of the correct dimension.

### 1.2 Steady-State Solver (MATLAB)

**Deliverables:**

- `solve_nominal_steady_state.m`— Wrapper that calls`fsolve`(or runs the ODE integrator to convergence) with the nominal influent and nominal kLa to produce the steady-state biological state vector for all five reactors and the settler.
- `validate_steady_state.m`— Convergence validation script. Checks that the solution satisfies mass balance residuals below a tolerance (1e-6), that all state variable concentrations are non-negative, and that effluent NH4 and COD fall within expected ranges for the BSM1 benchmark (NH4 < 4 mg/L, COD < 100 mg/L under nominal conditions).
- `nominal_state.mat`— Saved state vector from the nominal solution.

**Acceptance criteria:**Solver converges from at least three different initial conditions to the same solution (within tolerance). Effluent quality matches published BSM1 benchmark steady-state values.

### 1.3 Pseudo-Dynamic Step-Response Engine (MATLAB)

This is the critical simulation component. Rather than solving to a new steady state under reduced aeration, the engine runs the dynamic ODE for a specified duration and records the effluent at the end.

**Deliverables:**

- `run_step_response.m`— Core function with signature:
    
    ```
    function [effluent, state_trajectory] = run_step_response( ...
        initial_state, influent, kLa_reduced, duration_hours, params)
    ```
    
    Initializes from`initial_state`, applies the reduced kLa, integrates the ASM3 ODE system for`duration_hours`using`ode15s`(stiff solver appropriate for ASM systems), and returns the effluent concentrations at the final timestep plus the full state trajectory for diagnostics.
    
- `extract_effluent.m`— Applies the settler model to the final reactor state to compute settler effluent concentrations. This is where COD and NH4 are calculated from the ASM3 state variables using the same formulas as your existing pipeline (COD = sum of S_I, S_S, X_I, X_S, X_H, X_A, X_STO after settling).
    
- `validate_step_response.m`— Tests the engine by running a zero-reduction step (kLa_nominal for some duration) and confirming the effluent matches the steady-state nominal values. Also runs a sanity check that increasing duration with reduced aeration monotonically increases NH4 effluent.
    

**Acceptance criteria:**Zero-reduction step reproduces nominal effluent within solver tolerance. NH4 response to aeration reduction is monotonically increasing with duration. Solver completes 1000 runs without numerical failure.

---

## Phase 2: Database Generation

**Goal:**Produce a structured database of step-response results covering the influent-aeration-duration parameter space.

### 2.1 Influent Sampling Grid (MATLAB + Python)

**Deliverables:**

- `extract_influent_percentiles.py`— Python script that reads the dynamic influent timeseries from your existing WWDR database, computes the joint distribution of flow rate and key pollutant concentrations (S_NH4, COD components), and extracts the 10th/25th/50th/75th/90th percentile snapshots. Output is a CSV file with one row per influent condition.
- `influent_grid.csv`— The resulting grid. Columns:`condition_id`,`Q`,`S_I`,`S_S`,`X_I`,`X_S`,`X_H`,`X_A`,`X_STO`,`S_O2`,`S_NOX`,`S_NH4`,`S_N2`,`S_ALK`,`X_SS`.

**Design decision:**Whether to use marginal percentiles (5 flow rates × 5 NH4 levels = 25 conditions) or joint percentiles (5 conditions that preserve correlation structure). Joint percentiles are more defensible because plant load variables are correlated — high flow often coincides with diluted pollutant concentrations during storm events, while low flow with concentrated pollutants during dry weather. Start with 5 joint percentile conditions and expand later if the surrogate model indicates coverage gaps.

### 2.2 Aeration Reduction Sweep (MATLAB)

Define the parameter space for aeration curtailment:

|Parameter|Range|Resolution|Count|
|---|---|---|---|
|kLa reduction factor|0.0 (full shutoff) to 0.95 (5% reduction)|8 levels: 0.0, 0.10, 0.25, 0.40, 0.55, 0.70, 0.85, 0.95|8|
|Event duration|0.25 hr to 24 hr|12 levels: 0.25, 0.5, 1, 2, 3, 4, 6, 8, 10, 12, 18, 24|12|

Combined with 5 influent conditions: 5 × 8 × 12 =**480 simulation runs**.

Each run takes a few seconds of ODE integration, so the full sweep completes in under an hour on a standard machine.

### 2.3 Batch Runner (MATLAB)

**Deliverables:**

- `generate_experiment_grid.m`— Creates the full factorial combination of influent conditions, kLa reductions, and durations. Outputs a table where each row defines one simulation run.
    
- `run_batch_experiments.m`— Iterates over the grid, calls`run_step_response`for each combination, and collects results into a structured output table. Includes checkpoint saving every 50 runs so partial results are preserved if the batch is interrupted.
    
- `results_database.csv`— Final output with columns:
    
    ```
    run_id, condition_id, Q, S_NH4_influent, ..., kLa_reduction_factor,
    duration_hours, NH4_effluent, COD_effluent, NH4_nominal, COD_nominal,
    solver_converged, max_residual
    ```
    

**Acceptance criteria:**All 480 runs complete with solver convergence. No negative effluent concentrations. Results for zero-duration runs match nominal values. Results for full-shutoff long-duration runs show NH4 approaching influent concentration (physical upper bound).

---

## Phase 3: Data Processing, Index Computation, and Surrogate Modeling

**Goal:**Transform raw simulation results into the degradation index and energy savings metrics, then train a surrogate model suitable for optimization.

### 3.1 Degradation Index Calculation (Python)

**Deliverables:**

- `compute_degradation_index.py`— Reads`results_database.csv`and computes:
    
    ```
    delta_NH4 = (NH4_effluent - NH4_nominal) / NH4_limit
    delta_COD = (COD_effluent - COD_nominal) / COD_limit
    delta_combined = max(delta_NH4, delta_COD)
    ```
    
    where`NH4_limit`and`COD_limit`are regulatory permit values (configurable; typical values: NH4 = 4 mg/L, COD = 125 mg/L for EU standards or site-specific values).
    
- `compute_energy_savings.py`— Computes:
    
    ```
    E_saved = (kLa_nominal - kLa_reduced) * duration_hours
    E_saved_normalized = E_saved / (kLa_nominal * 24)  # fraction of daily energy
    ```
    
- `processed_database.csv`— Augmented database with degradation indices and energy savings columns appended.
    

**Integration note:**This step intentionally mirrors the normalization logic in your WWDR pipeline but uses the limit-based index from the reformulated framework rather than the influent-normalized or nominal-normalized metrics. The existing pipeline code in`normalizer_helper.py`can serve as a reference implementation, but the calculation is simpler here since the denominator is a fixed constant.

### 3.2 Exploratory Data Analysis (Python)

Before building the surrogate, characterize the response surface to inform model selection.

**Deliverables:**

- `eda_response_surfaces.py`— Generates diagnostic plots:
    - δ_NH4 vs. duration for each kLa reduction level (family of curves, one per influent condition)
    - δ_COD vs. duration (same structure)
    - Energy savings vs. δ_combined (the Pareto-relevant view)
    - Heatmap of δ_combined across the kLa × duration grid for each influent condition
- `eda_report.md`— Summary of key observations: linearity/nonlinearity of responses, presence of thresholds, sensitivity ranking of input variables.

**Purpose:**If the response surface is smooth and low-dimensional, a simple surrogate (RF, polynomial) suffices. If it contains sharp transitions (e.g., nitrification collapse thresholds), you may need a more flexible model or finer sampling near the transition.

### 3.3 Surrogate Model Training (Python)

**Deliverables:**

- `train_surrogate.py`— Trains a surrogate model mapping:
    
    ```
    (influent_condition, kLa_reduction_factor, duration) → (delta_NH4, delta_COD)
    ```
    
    Implementation approach: Start with Random Forest (scikit-learn) as the baseline. If EDA reveals smooth responses, also fit XGBoost and compare. Use 5-fold cross-validation with the following metrics: RMSE, R², and max absolute error (important for constraint satisfaction — you need the surrogate to be accurate near the δ = 1 boundary).
    
- `surrogate_validation.py`— Hold out 20% of the database for validation. Produce:
    
    - Predicted vs. actual scatter plots for both δ_NH4 and δ_COD
    - Residual analysis by input region (check whether errors are uniform or concentrated near thresholds)
    - Confidence/prediction interval estimates (for RF: use quantile regression or out-of-bag predictions)
- `surrogate_model.pkl`— Serialized trained model for use in optimization.
    

**Acceptance criteria:**Cross-validation R² > 0.95 for both outputs. Max absolute error on holdout set < 0.1 (10% of the permit limit). If the surrogate fails these criteria, the database may need augmentation with additional runs in high-error regions.

---

## Phase 4: Optimization and Policy Extraction

**Goal:**Run constrained multi-objective optimization to find the Pareto front and extract an operational policy.

### 4.1 Probabilistic Risk Model (Python)

**Deliverables:**

- `risk_model.py`— Implements the risk calculation:
    
    ```python
    def compute_risk(delta, duration, mtbf_function):
        """
        P(event) = duration exposure from MTBF distribution
        C(delta) = consequence from degradation index
        Risk = P * C
        """
        p_event = mtbf_function(duration)
        consequence = max(0, delta)  # only degradation counts
        return p_event * consequence
    ```
    
    The MTBF function should be configurable. Start with an exponential model:`P(event of duration t) = exp(-t / MTBF(t))`where`MTBF(t)`is specified from facility records. Allow the user to supply a lookup table of (duration, MTBF) pairs or a parametric model.
    
- `reliability_calculator.py`— Computes:
    
    ```
    R = P(C_effluent ≤ C_limit) = P(delta ≤ 1.0)
    ```
    
    Using the surrogate model's prediction distribution (not just point estimate) to account for model uncertainty.
    

### 4.2 NSGA-II Optimization (Python)

**Deliverables:**

- `run_optimization.py`— Uses`pymoo`(NSGA-II implementation) to solve:
    
    ```
    maximize: E_saved(kLa_reduction, duration)
    subject to: Risk(delta, duration, MTBF) ≤ Risk_target
                0.0 ≤ kLa_reduction ≤ 0.95
                0.25 ≤ duration ≤ 24
                R ≥ R_target
    ```
    
    The optimization evaluates the surrogate model (not the MATLAB simulation) at each candidate point, making it fast enough for population-based search. Run the GA separately for each influent condition to produce condition-specific Pareto fronts.
    
    Configuration:
    
    - Population size: 100
    - Generations: 200
    - Crossover: SBX (η=15)
    - Mutation: polynomial (η=20)
- `pareto_analysis.py`— Post-processes NSGA-II results:
    
    - Plots the Pareto front (energy savings vs. max degradation index) for each influent condition
    - Identifies "knee point" solutions that represent the best trade-off
    - Overlays the risk constraint boundary to show feasible vs. infeasible regions

### 4.3 Operational Policy Extraction (Python)

**Deliverables:**

- `extract_policy.py`— Transforms the Pareto-optimal solutions into an operational policy table:
    
    ```
    influent_condition → (recommended_kLa_reduction, max_duration, expected_delta, expected_energy_savings)
    ```
    
    For each influent condition, select the Pareto-optimal point that maximizes energy savings while satisfying R ≥ R_target. This produces a lookup table that an operator (or future LSTM controller) can use.
    
- `policy_table.csv`— The operational policy, directly interpretable and ready for validation against the dynamic model.
    
- `policy_visualization.py`— Generates a summary figure showing the recommended aeration reduction as a function of influent load, with confidence bands from the surrogate model uncertainty.

## Risk Register

|Risk|Impact|Mitigation|
|---|---|---|
|ASM3 ODE solver fails to converge for extreme kLa reductions|Gaps in database at operationally relevant points|Implement adaptive initial condition selection; fall back to longer integration with tighter tolerances|
|Multiple steady states exist for some parameter combinations|Wrong physical solution selected|Validate all solutions against mass balance and known physical bounds; always initialize from nominal state|
|Surrogate model inaccurate near nitrification collapse threshold|Optimization finds solutions that violate constraints when run on full model|Adaptive sampling: add simulation runs where surrogate prediction uncertainty is highest; use conservative constraint margin|
|MTBF function poorly characterized|Risk estimates unreliable|Perform sensitivity analysis on MTBF parameters; present results for a range of assumptions|
|Instantaneous recovery assumption too optimistic|Operational policy recommends reductions that cause prolonged violations|Flag as known limitation; bound the error by running selected dynamic validations from your existing timeseries model|
