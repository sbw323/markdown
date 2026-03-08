# Metamodeling-Based Reliability Analysis Framework for ASM3 BSM Aeration Curtailment Strategies

## Adapted from Borobio-Castillo et al. (2024), Water Research 255, 121436

---

## 1. Problem Restatement and Scope

You have an ASM3-based Benchmark Simulation Model (BSM) capable of generating converged ODE solutions for arbitrary aeration curtailment profiles. The goal is to train a surrogate model (metamodel) that replaces the computationally expensive BSM for Monte Carlo Simulation (MCS)-based reliability analysis, enabling rapid evaluation of how different demand response aeration strategies affect WWTP compliance with effluent quality standards.

**Key simplification relative to the reference paper:** The influent conditions are held constant (or drawn from a fixed baseline dynamic profile). The stochastic input space is defined entirely by **aeration curtailment parameters** rather than wastewater production and pollutant loading factors.

---

## 2. Input Space Definition: Parameterizing the Aeration Curtailment Profile

### 2.1 The Parameterization Challenge

A naive representation of aeration profiles (e.g., a binary on/off vector at every 15-minute timestep across 365 days) yields ~35,000 dimensions — far too many for any surrogate to learn from feasible sample sizes. The critical first step is reducing the aeration curtailment space to a compact set of **continuous or discrete random variables** suitable for Latin Hypercube Sampling (LHS).

### 2.2 Recommended Parameterization

Define each aeration curtailment event using the following variables:

| Variable | Symbol | Description | Suggested Range | Distribution |
|----------|--------|-------------|-----------------|--------------|
| Curtailment frequency | f_curt | Number of curtailment events per year | 0–365 | Uniform or Discrete Uniform |
| Event duration | t_dur | Duration of each curtailment event (hours) | 0.5–8.0 | Uniform |
| Start time of day | t_start | Hour of day curtailment begins | 0–23 | Uniform |
| Aeration reduction factor | α_red | Fraction of KLa reduction during curtailment (0 = off, 1 = no change) | 0.0–1.0 | Uniform |
| Day-of-week pattern | d_pattern | Which days of the week curtailment is applied (encoded) | Categorical or binary vector | Uniform over categories |
| Seasonal clustering | s_cluster | Season or month when curtailment events concentrate | 1–12 or 1–4 | Uniform |
| Tank selection | tank_sel | Which aeration tank(s) are curtailed (if multi-tank) | Categorical | Uniform |
| DO setpoint during curtailment | DO_curt | Reduced DO setpoint during curtailment (if not full shutoff) | 0.0–2.0 g O₂/m³ | Uniform |

**Notes:**
- If your demand response scenarios are driven by electricity price signals or grid operator dispatch, you might replace several of the above with a **price threshold** variable (curtail whenever price exceeds threshold) or a **grid signal intensity** variable, which implicitly determines frequency, timing, and duration.
- The paper used 10 input variables for their influent space. Keeping your aeration space to **6–10 variables** is a practical target for GPR metamodeling with 200–500 training samples.
- All variables should be continuous where possible to leverage LHS stratification. Encode categorical variables as integers for LHS, then map back.

### 2.3 Alternative: Direct Profile Encoding via Dimensionality Reduction

If you want to preserve richer aeration profile shapes (e.g., time-varying KLa trajectories), consider:

1. Generate a library of N candidate aeration profiles (e.g., 1,000 distinct curtailment schedules).
2. Apply **Principal Component Analysis (PCA)** or **Functional PCA** to the KLa time series.
3. Retain the first p principal components explaining ≥95% of variance.
4. Use the PC scores as input variables to the GPR (typically p = 5–15).

This approach is more flexible but requires more upfront data generation and adds interpretive complexity.

---

## 3. Design of Experiments (DoE)

### 3.1 Latin Hypercube Sampling

Following the reference paper, use LHS to sample the aeration curtailment input space. LHS ensures each variable's marginal distribution is uniformly covered by dividing each variable's range into n equally probable strata and sampling exactly once from each stratum.

**Recommended sample sizes:**

| Input dimensions (k) | Minimum n (Loeppky's rule: n ≈ 10k) | Recommended n | Notes |
|-----------------------|---------------------------------------|---------------|-------|
| 6 | 60 | 150–200 | Sufficient for smooth GPR response surfaces |
| 8 | 80 | 200–300 | More variables → need more samples |
| 10 | 100 | 250–400 | Upper practical limit for mechanistic sims |

**Implementation (MATLAB):**
```matlab
k = 8;          % number of input variables
n = 200;        % number of samples
X_lhs = lhsdesign(n, k, 'criterion', 'maximin', 'iterations', 100);
% Scale to physical bounds:
X_physical = X_lhs .* (upper_bounds - lower_bounds) + lower_bounds;
```

**Implementation (Python):**
```python
from scipy.stats.qmc import LatinHypercube
sampler = LatinHypercube(d=8, seed=42)
X_lhs = sampler.random(n=200)
# Scale to physical bounds
X_physical = X_lhs * (upper_bounds - lower_bounds) + lower_bounds
```

### 3.2 Design Matrix Construction

The resulting design matrix **X** = [x₁, ..., xₙ]ᵀ has dimensions n × k. Each row xᵢ defines a unique aeration curtailment scenario. From each xᵢ, you construct the full aeration profile (KLa time series) that gets passed to your ASM3 BSM.

### 3.3 Progressive LHS for Iterative Refinement

If computational budget is uncertain, use **progressive LHS** (Sheikholeslami and Razavi, 2017): start with n₀ = 50 samples, train preliminary GPRs, evaluate accuracy, and add batches of 50 samples in regions of high prediction uncertainty until validation criteria are met.

---

## 4. Mechanistic Simulation and Response Matrix Generation

### 4.1 Simulation Protocol

For each of the n scenarios in X:

1. **Construct the aeration profile**: Map the sampled parameters (t_start, t_dur, α_red, f_curt, etc.) into a full KLa time series at 15-minute resolution for 365 days.
2. **Run the ASM3 BSM**: Simulate 244 days of stabilization + 365 days of evaluation (following BSM1_LT convention), recording effluent state variables at each 15-minute timestep.
3. **Verify ODE convergence**: Confirm that each simulation has reached mathematical convergence (you already have this capability).
4. **Extract response vectors**: From the 365-day evaluation period, compute:

### 4.2 Response Variables (What to Extract)

**Primary outputs for reliability analysis — failure event counts:**

For each EPI (COD, BOD₅, TN, NH₄-N, TSS) and each regulation's MAC:

```
failure_count(i, EPI, MAC) = Σ I[EPI_eff(t) · Q_eff(t) > MAC · Q_eff(t)]  over all timesteps t
```

Or equivalently, since Q_eff(t) > 0:

```
failure_count(i, EPI, MAC) = Σ I[PC_eff(t) > MAC]  for concentration-based limits
```

This gives you a scalar per (scenario, EPI, regulation) combination — these are the primary GPR training targets.

**Secondary outputs for performance characterization:**

| Output | Symbol | Description |
|--------|--------|-------------|
| Annual failure rate | λ_a | failure_count / T (where T = 1 year) |
| Average effluent concentrations | COD_eff, BOD₅_eff, TN_eff, NH₄-N_eff, TSS_eff | Time-averaged over evaluation period |
| Removal efficiencies | REM_COD, REM_TN, etc. | (C_inf - C_eff) / C_inf × 100 |
| Instantaneous EQI | EQI_INST | Weighted pollutant sum per BSM conventions |
| Peak effluent concentrations | max(PC_eff) | Worst-case during curtailment events |
| Recovery time | t_recovery | Time from curtailment end to return below MAC |
| HRT and SRT | HRT, SRT | Hydraulic and solids retention times |
| Aeration energy | E_aer | Integrated KLa·V over evaluation period |

**Critical note on ASM3 vs. ASM1:** ASM3 includes stored polymers (X_STO) and distinguishes between storage and growth processes. Your effluent TN computation must account for all nitrogen species in ASM3 (S_NH, S_NO, S_N2, X_I nitrogen content, etc.) — not just the ASM1 nitrogen state variables.

### 4.3 Parallel Computing

Run the n BSM simulations in parallel using MATLAB's Parallel Computing Toolbox:

```matlab
parfor i = 1:n
    aeration_profile = construct_profile(X_physical(i, :));
    [effluent_data] = run_ASM3_BSM(aeration_profile, baseline_influent);
    Y_failures(i, :) = count_failures(effluent_data, MAC_table);
    Y_performance(i, :) = compute_performance(effluent_data);
end
```

This step generates the response matrix **Y** = [y₁, ..., yₙ]ᵀ where each yᵢ contains all failure counts and performance metrics for scenario i.

---

## 5. Surrogate Model Training: Gaussian Process Regression

### 5.1 Architecture

Following the reference paper, use Gaussian Process Regression (GPR):

```
Y(x) = G(x) = β·f(x) + σ²·Z(x, ω)
```

Where:
- β·f(x) is the mean function (constant, linear, or quadratic basis)
- σ²·Z(x, ω) is the stochastic process defined by kernel function Z with hyperparameters ω
- The kernel encodes assumptions about smoothness and correlation structure

### 5.2 One GPR per (EPI × Regulation) Combination

Build separate GPR models for each output of interest. For a setup with 5 EPIs and 3 regulations:

```
Total GPR models = (5 EPIs × 3 regulations) + 5 avg_effluent + 2 retention_times + 1 energy = 23 models
```

Each model maps X (n × k) → y (n × 1) for one specific output.

### 5.3 Kernel Function Selection

Test the following ARD (Automatic Relevance Determination) kernels for each model and select the best:

| Kernel | MATLAB Name | Best for |
|--------|-------------|----------|
| ARD Exponential | 'ardexponential' | Non-smooth, noisy responses |
| ARD Squared Exponential | 'ardsquaredexponential' | Smooth, continuous responses |
| ARD Matérn 3/2 | 'ardmatern32' | Moderately rough responses |
| ARD Matérn 5/2 | 'ardmatern52' | Between Matérn 3/2 and SE |
| ARD Rational Quadratic | 'ardrationalquadratic' | Multi-scale variation |

**The paper found ARD Exponential performed best overall (47.2% of models).** However, for aeration curtailment responses — which may exhibit sharper transitions (e.g., sudden failure onset as curtailment duration crosses a threshold) — Matérn kernels may outperform.

### 5.4 Training Protocol (MATLAB)

```matlab
% Split data
cv = cvpartition(n, 'HoldOut', 0.15);  % 85/15 train/test split
X_train = X_physical(training(cv), :);
Y_train = Y_failures(training(cv), j);  % j-th output
X_test  = X_physical(test(cv), :);
Y_test  = Y_failures(test(cv), j);

% Test all kernels
kernels = {'ardexponential', 'ardsquaredexponential', ...
           'ardmatern32', 'ardmatern52', 'ardrationalquadratic'};

best_R2 = -Inf;
for k = 1:length(kernels)
    gpr_model = fitrgp(X_train, Y_train, ...
        'KernelFunction', kernels{k}, ...
        'BasisFunction', 'constant', ...
        'Standardize', true, ...
        'OptimizeHyperparameters', 'auto');
    
    Y_pred = predict(gpr_model, X_test);
    R2 = 1 - sum((Y_test - Y_pred).^2) / sum((Y_test - mean(Y_pred)).^2);
    
    if R2 > best_R2
        best_R2 = R2;
        best_model = gpr_model;
        best_kernel = kernels{k};
    end
end
```

### 5.5 Training Protocol (Python with scikit-learn)

```python
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import Matern, RBF, RationalQuadratic, ConstantKernel
from sklearn.model_selection import cross_val_score, LeaveOneOut

kernels = [
    ConstantKernel() * Matern(nu=1.5, length_scale=np.ones(k)),
    ConstantKernel() * Matern(nu=2.5, length_scale=np.ones(k)),
    ConstantKernel() * RBF(length_scale=np.ones(k)),
    ConstantKernel() * RationalQuadratic(length_scale=1.0, alpha=1.0),
]

for kernel in kernels:
    gpr = GaussianProcessRegressor(kernel=kernel, n_restarts_optimizer=10, normalize_y=True)
    gpr.fit(X_train, Y_train)
    Y_pred = gpr.predict(X_test)
    R2 = 1 - np.sum((Y_test - Y_pred)**2) / np.sum((Y_test - np.mean(Y_test))**2)
```

### 5.6 Handling Edge Cases in Your Aeration Context

**Near-zero failure counts:** When large bioreactor volumes or mild curtailment produce very few failures (e.g., 0–5 events per year), GPR prediction error becomes proportionally large. The paper encountered this in Scenarios 3–4. Mitigation strategies:

1. **Log-transform** the response: Train on log(failure_count + 1) and back-transform predictions.
2. **Classification + regression hybrid**: First train a classifier (failure vs. no-failure), then train GPR only on the non-zero subset.
3. **Increase training samples** in the low-failure region using adaptive sampling.

**Threshold effects:** Aeration curtailment may produce sharp transitions (e.g., nitrification collapses after curtailment exceeds a critical duration). GPRs with smooth kernels (SE) may struggle here. Use Matérn 3/2 or Exponential kernels, or consider:
- Piecewise GPR (separate models for above/below threshold)
- Neural network surrogates for highly nonlinear responses

---

## 6. Validation

### 6.1 Validation Criteria (from the reference paper)

| Metric | Criterion | Computation |
|--------|-----------|-------------|
| Coefficient of Determination R² | > 95% | R² = 1 − Σ(y_test − y_pred)² / Σ(y_test − ȳ_test)² |
| Leave-One-Out Cross-Validation Q² | > 90% | Same formula but over LOO predictions |

### 6.2 Validation Protocol

```
For each GPR model:
    1. Compute R² on the held-out 15% test set
    2. Compute Q² via leave-one-out cross-validation on the full dataset
    3. If R² < 95% or Q² < 90%:
        a. Try different kernel functions
        b. Try different random train/test splits
        c. Increase training samples (progressive LHS)
        d. Apply response transformation (log, Box-Cox)
    4. If still below threshold:
        a. Document the shortfall and its cause (e.g., near-zero counts)
        b. Assess whether model accuracy improves on the full dataset
        c. Consider alternative surrogate architectures
```

### 6.3 Additional Validation Checks Specific to Aeration Studies

Beyond R² and Q², verify that the metamodel preserves **physically meaningful behavior**:

1. **Monotonicity check**: Longer curtailment durations should generally increase failure rates (test with 1D sweeps holding other variables constant).
2. **Boundary consistency**: Zero curtailment (α_red = 1.0 or f_curt = 0) should predict baseline failure rates matching the uncurtailed BSM run.
3. **Prediction interval coverage**: GPR provides uncertainty estimates — verify that actual BSM outputs fall within the 95% prediction interval at least 90% of the time.

---

## 7. Reliability Analysis via Monte Carlo Simulation

### 7.1 Limit State Function

For each EPI and regulation:

```
Z = MAC − EPI
```

Where:
- MAC = maximum allowable concentration from the target regulation
- EPI = effluent pollutant indicator (concentration × flow, or just concentration for concentration-based standards)
- Z < 0 → failure event
- Z ≥ 0 → safe event

### 7.2 Annual Failure Rate

```
λ_a = Σ I[Z ≤ 0] / (N · T)
```

Where:
- I is the indicator function counting violations
- N is the number of MCS scenarios
- T = 1 year
- The metamodel predicts the failure count per scenario directly, so:

```
λ_a = (1/N) · Σᵢ failure_count_predicted(xᵢ)    for i = 1, ..., N_MCS
```

### 7.3 MCS Execution

```matlab
% Generate MCS samples
N_MCS = 100000;
X_mcs = lhsdesign(N_MCS, k) .* (upper_bounds - lower_bounds) + lower_bounds;

% Predict using trained GPR
[Y_pred, Y_std] = predict(best_gpr_model, X_mcs);

% Compute reliability metrics
lambda_a = mean(max(Y_pred, 0));  % avg annual failure rate across all scenarios
P_failure = sum(Y_pred > 0) / N_MCS;  % probability of any failure occurring

% Convergence check: plot running mean of lambda_a
running_mean = cumsum(max(Y_pred, 0)) ./ (1:N_MCS)';
```

### 7.4 Convergence Verification

Following the paper's approach:
1. Run 1,000 → 10,000 → 100,000 MCS evaluations.
2. Track the rate of change in λ_a between successive orders of magnitude.
3. Convergence is achieved when rate of change < ±1%.
4. The paper found convergence by ~1.5 million simulations for their input space; your convergence point depends on the breadth of your aeration parameter ranges.

---

## 8. Risk Matrix Construction

Since your broader research involves risk-energy optimization, the metamodel outputs feed directly into risk matrix construction:

### 8.1 Risk Quantification per Curtailment Strategy

For each MCS-sampled aeration strategy xᵢ:

```
Risk(xᵢ) = λ_a(xᵢ) × Consequence(EPI)
```

Where Consequence can be:
- Regulatory penalty magnitude
- EQI deviation from baseline (your existing framework)
- Environmental damage index

### 8.2 Pareto Front: Risk vs. Energy Savings

```
Energy_savings(xᵢ) = E_baseline − E_aer(xᵢ)    [predicted by energy GPR]
Risk(xᵢ) = λ_a(xᵢ)                               [predicted by failure GPR]
```

The 100,000 MCS points give you a dense sampling of the Risk–Energy tradeoff space, enabling identification of Pareto-optimal curtailment strategies.

---

## 9. Computational Budget Summary

| Stage | Computation | Estimated Time | One-time? |
|-------|-------------|----------------|-----------|
| LHS sampling | Generate n=200 aeration scenarios | Seconds | Yes |
| BSM simulations | 200 × ASM3 BSM runs (parallel) | 200 × 30 min = ~4 days on 1 core; ~12 hrs on 16 cores | Yes |
| GPR training | ~20–25 models, kernel search | 1–2 hours | Yes (per design scenario) |
| Validation | LOO-CV on all models | 2–4 hours | Yes |
| MCS (100k) | 100,000 GPR predictions | Minutes | Repeatable at will |
| MCS (10M for convergence check) | 10,000,000 GPR predictions | 10–30 minutes | Optional |

**Total one-time investment:** ~1–2 days with parallel computing.
**Per-analysis marginal cost:** Minutes (the entire point of metamodeling).
**Equivalent mechanistic cost for 100k simulations:** ~200 days on a single core.

---

## 10. Practical Implementation Checklist

```
Phase 1: Input Space Design
  □ Define 6-10 continuous aeration curtailment parameters
  □ Set physically meaningful bounds for each parameter
  □ Assign probability distributions (uniform if no prior knowledge)
  □ Generate LHS design matrix X (n=200, k=6-10)

Phase 2: Mechanistic Data Generation
  □ Map each LHS row to a full KLa aeration profile
  □ Run ASM3 BSM for all n scenarios (parallel)
  □ Verify ODE convergence for each run
  □ Extract failure counts for each (EPI, regulation) pair
  □ Extract average effluent concentrations, HRT, SRT, energy
  □ Store as response matrix Y

Phase 3: Surrogate Training
  □ 85/15 train/test split
  □ Train GPR for each output, testing 5 ARD kernels
  □ Select best kernel per output by R² on test set
  □ Validate R² > 95%, Q² (LOO) > 90%
  □ Retrain on full dataset for production use
  □ Verify physical monotonicity and boundary conditions

Phase 4: Reliability Analysis
  □ Generate 100,000 MCS samples via LHS
  □ Predict failure counts using trained GPRs
  □ Compute annual failure rates λ_a
  □ Verify convergence (rate of change < ±1%)
  □ Construct risk matrices and Pareto fronts

Phase 5: Decision Support
  □ Identify Pareto-optimal curtailment strategies
  □ Sensitivity analysis: which aeration parameters most influence λ_a
  □ Report confidence intervals using GPR prediction uncertainty
```

---

## 11. Extensions and Considerations

### 11.1 Sensitivity Analysis
The ARD kernel hyperparameters (length scales) directly encode variable importance — shorter length scales indicate variables to which the output is more sensitive. Extract these post-training for a built-in global sensitivity ranking of your aeration parameters.

### 11.2 Adaptive Sampling
If initial 200 samples yield poor resolution in critical regions (e.g., near the failure threshold), use the GPR's prediction variance to identify where additional BSM simulations would most improve the metamodel, then add targeted samples.

### 11.3 Multi-Fidelity Approaches
If you also have a simplified ASM3 model (e.g., steady-state or reduced-order), you can use multi-fidelity GPR: train on many cheap low-fidelity runs plus fewer expensive high-fidelity BSM runs for improved accuracy per computational dollar.

### 11.4 ASM3-Specific Considerations
- **Storage processes**: ASM3's X_STO dynamics may introduce additional lag in recovery after aeration curtailment compared to ASM1 growth-only kinetics. Ensure your recovery time metric captures this.
- **Endogenous respiration**: ASM3 separates endogenous respiration from decay, which affects oxygen demand calculations. Your energy savings predictions must use the ASM3-consistent OUR formulation.
- **Nitrogen pathway completeness**: Include S_N2 (dissolved N₂) in your nitrogen mass balance if your risk framework considers greenhouse gas (N₂O) emissions as a consequence metric.
