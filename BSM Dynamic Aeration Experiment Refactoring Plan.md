# BSM Dynamic Aeration Experiment — Refactoring Plan (v2)
## 1. Executive Summary

The current codebase runs aeration-reduction experiments by applying **constant KLa scalars** against a **constant influent**(`CONSTINFLUENT.mat`), with each iteration consisting of a perturbation phase followed by a nominal-recovery phase. The goal of this refactoring is to transition the workflow to:

- Replace scalar KLa overrides with **dynamic KLa timeseries** (96 steps/day, 15-min resolution).
- Replace the constant influent with the **diurnal dry-weather file** (`DRYINFLUENT.mat`), loaded natively by `benchmarkinit`. Note that `DRYINFLUENT.mat` has a time series length of 14 days (i.e. 1344 data points).
- Introduce a proper **pseudo-steady-state calibration phase** (Phase 2 per STR 23) between the initial steady-state convergence and the experimental data-collection run.
- Enumerate **all 60 experiment definitions** (5 reduction rates × 4 durations × 3 start times) instead of the current 9-row `test_cases` matrix.

### Simplifications for this phase

|Decision|Rationale|
|---|---|
|Pseudo-SS calibration and experiment use **identical duration and KLa pattern**|Get end-to-end workflow functional before tuning the 3×SRT calibration length.|
|`DRYINFLUENT.mat` is **static** across all experiments|Defer variable-influent looping to the next development phase.|
|`ssASM3_influent_sampler.m` and `ssInfluent_writer.m` are **not modified**|No longer needed in the inner loop; preserved for future variable-influent work.|
|`effluent_data_writer.m` call sites remain in the **same three positions**|Preserves the existing verification/debugging pattern.|

---

## 2. Combinatorics: Experiment Enumeration

Each experiment is fully defined by three scalar parameters applied uniformly to tanks 3, 4, and 5:

|Parameter|Values|Count|
|---|---|---|
|**Reduction fraction** (of nominal KLa)|0.90, 0.80, 0.70, 0.60, 0.50|5|
|**Reduction duration**|1 hr (4 steps), 2 hr (8), 3 hr (12), 4 hr (16)|4|
|**Start time** (daily, repeating)|08:00 (step 32), 12:00 (step 48), 16:00 (step 64)|3|

**Total experiments: 5 × 4 × 3 = 60**

These 60 parameter tuples replace the current `test_cases` matrix. Each tuple maps to one full iteration of the simulation loop (SS → pseudo-SS → experiment).

### Start-time indexing convention

The time column starts at 0 and increments by `1/96` (≈ 0.01042 days = 15 min). Within a single 24-hour diurnal cycle of 96 steps:

|Clock time|Fractional day|Step index within day|
|---|---|---|
|00:00|0.0000|0|
|08:00|1/3 ≈ 0.3333|32|
|12:00|1/2 = 0.5000|48|
|16:00|2/3 ≈ 0.6667|64|

---

## 3. New File: `generate_KLa_timeseries.m`

### Purpose

Given a nominal KLa value, a reduction fraction, a reduction duration (in hours), a daily start time, and a total simulation length (in days), produce a two-column `[time, KLa]` matrix suitable for the Simulink model's `From Workspace` block. Note that the KLa timeseries must be the same length as the influent timeseries. Since `DRYINFLUENT.mat` has 14 days of influent data, the KLa time series must be 14×96 = 1344 data points in length.

### Signature (proposed)

```matlab
function KLa_ts = generate_KLa_timeseries(nominal_KLa, reduction_frac, ...
    duration_hrs, start_hour, sim_days)
```

### Algorithm

1. Build the time column: `t = (0 : 1/96 : sim_days - 1/96)'` → length = `sim_days × 96`.
2. Initialize the KLa column to `nominal_KLa` everywhere.
3. Compute the reduced KLa: `KLa_reduced = nominal_KLa * reduction_frac`.
4. For each day `d = 0 .. sim_days-1`:
    - Compute the start step: `s = d*96 + round(start_hour * 96/24)`.
    - Compute the end step: `e = s + duration_hrs * 4 - 1`.
    - Set `KLa(s+1 : e+1) = KLa_reduced` (MATLAB 1-indexed).
5. Return `KLa_ts = [t, KLa]`.
6. Length of time series is equal to length of influent time series (1344 in the case of `DRYINFLUENT.mat`).

### Output persistence — `.mat` file strategy

**This is a critical best-practice for surviving `benchmarkinit`'s `clear all`.**

Rather than attempting to hold the generated KLa timeseries in workspace variables across workspace wipes, the generator writes each tank's timeseries to a **named `.mat` file** in the MATLAB/ASM3 project folder. The files use fixed, predictable names so that any downstream code (including the Simulink model's `From Workspace` blocks) can reload them by name after a workspace wipe.

The recommended file naming convention:

|Tank|`.mat` filename|Variable inside file|
|---|---|---|
|Tank 3|`KLa3_timeseries.mat`|`KLa3_ts`|
|Tank 4|`KLa4_timeseries.mat`|`KLa4_ts`|
|Tank 5|`KLa5_timeseries.mat`|`KLa5_ts`|

Each file contains a single two-column `double` matrix (`[time, KLa]`).

**Key consequences of this approach:**

1. **The generator is called once per experiment, during the preparation phase** — before the loop enters the Phase 2 / Phase 3 simulation calls. It is _not_ called inside the simulation phases themselves.
2. **The `.mat` files are overwritten in-place** between experiments. Each iteration of the outer experiment loop calls `generate_KLa_timeseries` three times (once per tank), writes the three `.mat` files, and the subsequent `load(...)` calls within the loop body pick up the correct timeseries regardless of prior workspace wipes.
3. **After any `clear all` or workspace reload**, the KLa timeseries are recovered via `load('KLa3_timeseries.mat')` etc., identically to how `DRYINFLUENT.mat` is recovered. This is the same persistence pattern already proven by `sim_config.mat`, `sim_state.mat`, and `workspace_steady_state_initial.mat`.
4. **Cleanup:** The three KLa `.mat` files should be added to the cleanup list in Section 9 of `main_sim` (alongside `sim_state.mat`etc.) so they are removed after a successful campaign run.

### Caller pattern

At the top of each experiment iteration in `main_sim`, **before** reloading the nominal SS workspace:

```matlab
% --- Generate and persist KLa timeseries for this experiment ---
KLa3_ts = generate_KLa_timeseries(240, reduction_frac, duration_hrs, start_hour, sim_days);
KLa4_ts = generate_KLa_timeseries(240, reduction_frac, duration_hrs, start_hour, sim_days);
KLa5_ts = generate_KLa_timeseries(114, reduction_frac, duration_hrs, start_hour, sim_days);

save('KLa3_timeseries.mat', 'KLa3_ts');
save('KLa4_timeseries.mat', 'KLa4_ts');
save('KLa5_timeseries.mat', 'KLa5_ts');
```

Then, after the workspace reload:

```matlab
% --- Recover KLa timeseries after workspace wipe ---
load('KLa3_timeseries.mat', 'KLa3_ts');
load('KLa4_timeseries.mat', 'KLa4_ts');
load('KLa5_timeseries.mat', 'KLa5_ts');
```

This cleanly separates the _generation_ concern (called once per experiment) from the _persistence_ concern (handled by the filesystem, surviving any number of workspace wipes within the iteration).

---

## 4. New File: `generate_test_cases.m`

### Purpose

Replace the hardcoded `test_cases` matrix with a function that enumerates all 60 experiment definitions as a structured table.

### Signature

```matlab
function T = generate_test_cases()
```

### Output table columns

|Column|Type|Description|
|---|---|---|
|`ExperimentID`|int|1..60|
|`ReductionFrac`|double|0.90 .. 0.50|
|`DurationHrs`|int|1..4|
|`StartHour`|double|8, 12, 16|

### Implementation

Use `ndgrid` or nested loops over the three parameter vectors, then reshape into an N×3 matrix and wrap in a table. The ordering is deterministic, so crash-recovery by iteration index remains valid.

---

## 5. Refactored `main_sim.m` — Phase-by-Phase Walkthrough

The loop body changes from two phases (perturbation → recovery) to three phases (SS → pseudo-SS calibration → experiment). Below is the structural map showing what changes and what stays.

### Section 1 — Configuration (modified)

```
Old: test_cases = [KLa3, KLa4, KLa5]  (9 rows)
New: test_cases = generate_test_cases()  (60 rows, table)
     sim_days   = 14                     (calibration & experiment length, equal for now)
```

The `DRYINFLUENT.mat` file is **not touched**—`benchmarkinit` loads it natively into the workspace.

> **FUTURE HOOK — Variable Influent:** When variable influent conditions are reintroduced, a new outer loop (analogous to the current `run_campaign.m`) will iterate over influent rows _before_ entering this experiment loop. A call to a new `dynamicInfluent_writer` function (replacing `ssInfluent_writer`) will go here, between Section 1 and Section 2.

### Section 2 — State Resume Logic (unchanged)

Identical to current implementation.

### Section 3 — Steady-State Initialization / Phase 1 (minor modification)

This block remains largely the same. The key difference:

- **Remove** any reference to `CONSTINFLUENT.mat`; the steady-state model `benchmarkss` uses whatever influent `benchmarkinit`configured (which is `DRYINFLUENT`-based by default, or the constant flow-weighted average depending on the BSM variant).
- The `effluent_data_writer` call at `IterationLabel=0` stays as-is for the nominal baseline snapshot.

### Section 4 — Main Experiment Loop (substantially rewritten)

```
while iter <= num_experiments
    ┌─────────────────────────────────────────────────────────────┐
    │  A. Load experiment parameters from test_cases(iter,:)      │
    │     → reduction_frac, duration_hrs, start_hour              │
    │                                                             │
    │  B. GENERATE & PERSIST KLa timeseries (called ONCE here)   │
    │     → generate_KLa_timeseries() × 3 tanks                  │
    │     → save('KLa3_timeseries.mat', ...) etc.                 │
    │     This is the ONLY place the generator is called.         │
    │                                                             │
    │  C. Reload nominal SS workspace                             │
    │     load('workspace_steady_state_initial.mat')              │
    │     ⚠ This wipes ALL workspace variables                    │
    │                                                             │
    │  D. Restore loop control vars + RELOAD KLa .mat files      │
    │     load('KLa3_timeseries.mat') etc.                        │
    │     Assign to workspace vars the Simulink model reads from  │
    │                                                             │
    │  E. PHASE 2 — PSEUDO-SS CALIBRATION                        │
    │     set_param(ts_model, 'StopTime', num2str(sim_days))      │
    │     sim(ts_model)                                           │
    │     stateset                                                │
    │     effluent_data_writer(... IterationLabel=iter ...)        │
    │                                                             │
    │  F. PHASE 3 — EXPERIMENT (replaces old recovery)            │
    │     [workspace carries forward from Phase 2 — no reset]     │
    │     KLa .mat files still in workspace — no reload needed    │
    │     set_param(ts_model, 'StopTime', num2str(sim_days))      │
    │     sim(ts_model)                                           │
    │     stateset                                                │
    │     effluent_data_writer(... IterationLabel=iter+0.5 ...)   │
    │                                                             │
    │  G. Increment iter, checkpoint                              │
    └─────────────────────────────────────────────────────────────┘
```

**Note on step ordering (B before C):** The KLa timeseries generation and `.mat` file save happens _before_ the workspace reload in step C. This is deliberate — after step C wipes the workspace, step D recovers the timeseries from the `.mat` files. If the generator were called after the reload, it would work too, but placing it before the reload ensures the `.mat` files exist on disk as a checkpoint even if the reload itself fails.

#### Critical workflow changes from the current code

|Aspect|Current|Refactored|
|---|---|---|
|KLa injection|Scalar workspace variable override (`KLa3 = value`)|Two-column timeseries matrix loaded from `.mat` file and assigned to workspace variable read by `From Workspace` block|
|KLa persistence|N/A (scalar, set inline)|`.mat` files on disk (`KLa3_timeseries.mat` etc.), overwritten per experiment, reloaded after any workspace wipe|
|Perturbation phase purpose|Generate perturbed effluent data|**Pseudo-SS calibration** — acclimate biomass to cyclic KLa pattern|
|Recovery phase purpose|Restore nominal, collect recovery data|**Experiment phase** — collect the benchmark dataset under the same KLa pattern|
|Recovery KLa|Resets to nominal (240/240/114)|Keeps the **same experimental KLa timeseries** (identical to calibration for now)|
|Influent|`CONSTINFLUENT.mat` rewritten per row|`DRYINFLUENT.mat`, static, loaded by `benchmarkinit`|
|Test case source|9-row hardcoded matrix of absolute KLa values|60-row generated table of (reduction_frac, duration_hrs, start_hour)|
|Sim stop time|Default 14 days (BSM benchmark window)|Configurable `sim_days` (14 days for now)|

#### Phase 2 → Phase 3 state continuity

A key methodological point: the **workspace is NOT reset** between Phase 2 (calibration) and Phase 3 (experiment). The entire purpose of Phase 2 is to bring the ODE state variables into pseudo-steady-state _under the experimental KLa pattern_. Phase 3 then simply continues from that conditioned state to collect the evaluation dataset. This is analogous to how the current code's recovery phase starts from the perturbed state—except now both phases share the same KLa pattern rather than reverting to nominal.

Because the workspace is not wiped between Phase 2 and Phase 3, the KLa timeseries variables loaded in step D are still present and do not need to be reloaded from `.mat` files for Phase 3.

### Sections 5-9 — Error handling, cleanup (minimal changes)

The error-handling `catch` block, the `exp_cal` flag, and the file cleanup logic remain structurally identical. The only changes:

- Update variable names to match the new `test_cases` table fields.
- **Add KLa `.mat` files to the cleanup list:**

```matlab
state_files = {'sim_state.mat', 'sim_config.mat', 'workspace_steady_state_initial.mat', ...
               'KLa3_timeseries.mat', 'KLa4_timeseries.mat', 'KLa5_timeseries.mat'};
```

---

## 6. `run_campaign.m` — Simplified for This Phase

Since the influent is now static (`DRYINFLUENT.mat`), the outer `run_campaign` loop over influent rows is **no longer needed in its current form**.

Therefore: Keep `run_campaign.m` as a thin wrapper that calls `main_sim` once (with a single influent configuration), preserving the master-results accumulation logic for forward compatibility.

> **FUTURE HOOK — Variable Influent:** When variable influent timeseries are reintroduced, `run_campaign.m`will be resurrected to loop over influent conditions in its outer loop, with `main_sim` handling the 60 KLa experiments in its inner loop. The `ssInfluent_writer` call site in `run_campaign` step 5a will be replaced with a `dynamicInfluent_writer(...)` call that writes the appropriate variant of `DRYINFLUENT.mat`.

---

## 7. `effluent_data_writer.m` — No Structural Changes

Per requirement 4, the function and its three call sites remain identical. The only consideration is ensuring the `KLa` name-value argument can meaningfully represent the experiment: since KLa is now time-varying, the summary row's `KLa3`/`KLa4`/`KLa5` columns will report the **reduced** values, `ExperimentID`, `ReductionFrac`, `DurationHrs`, and `StartHour` columns to the summary row so the CSV is self-documenting. This can be done by extending the `VariableNames` in `effluent_data_writer` or by post-processing in `main_sim`.

---

## 8. Files Not Modified

|File|Status|Notes|
|---|---|---|
|`ssASM3_influent_sampler.m`|**Frozen**|Will be refactored in the variable-influent phase.|
|`ssInfluent_writer.m`|**Frozen**|Will be replaced by `dynamicInfluent_writer.m` in the variable-influent phase.|
|`effluent_data_writer.m`|**Unchanged**(structurally)|Call sites preserved; minor metadata columns may be added.|

---

## 9. Implementation Order

The recommended implementation sequence, designed so each step is independently testable:

### Step 1: `generate_KLa_timeseries.m`

Write and unit-test the function in isolation. Verify:

- Output dimensions match `sim_days × 96` rows.
- Reduction windows fall at the correct clock times.
- Verify that KLa time series is same length as influent time series.
- Nominal values outside the reduction window are preserved.
- The function itself does NOT save to `.mat` — that is the caller's responsibility (separation of concerns).

### Step 2: `generate_test_cases.m`

Write the combinatorics enumerator. Verify it produces exactly 60 rows with the expected parameter combinations.

### Step 3: Refactor `main_sim.m` — Configuration section

- Replace hardcoded `test_cases` matrix with `generate_test_cases()` call.
- Remove any `CONSTINFLUENT.mat` references.
- Update `save('sim_config.mat', ...)` to include new variables that need to be retained between workspace wipes.

### Step 4: Refactor `main_sim.m` — Loop body

- Restructure the loop into the three-phase pattern (SS → pseudo-SS → experiment).
- Wire `generate_KLa_timeseries` calls into the **preparation section** (step B in the loop diagram).
- Immediately save outputs to `KLa3_timeseries.mat`, `KLa4_timeseries.mat`, `KLa5_timeseries.mat`.
- After workspace reload (step C), recover via `load('KLa3_timeseries.mat')` etc.
- Remove nominal-KLa restoration between calibration and experiment (state continuity).
- Update `effluent_data_writer` call arguments to pass new self-documenting labels.
- Add KLa `.mat` files to the cleanup list.

### Step 5: Simplify `run_campaign.m`

- Reduce to a single-pass wrapper.
- Preserve the master-results CSV accumulation logic.
- Add `FUTURE HOOK` comments for variable influent reintegration.

### Step 6: End-to-end validation

- Run the full 60-experiment campaign on a single `DRYINFLUENT` condition.
- Confirm `sim_results.csv` contains 60 × 3 rows (baseline + calibration + experiment per iteration, or however the labeling shakes out).

---

## 10. Simulation Duration & Computational Budget

|Phase|Duration per experiment|Model|Notes|
|---|---|---|---|
|Phase 1 (SS)|Run once|`benchmarkss`|Same as current; ~seconds.|
|Phase 2 (Pseudo-SS)|`sim_days` = 14 days|`benchmark`|KLa reduction time series applied to attain pseudo steady-state|
|Phase 3 (Experiment)|`sim_days` = 14 days|`benchmark`|Evaluation dataset window.|

---

## 11. Risk Register

|Risk|Mitigation|
|---|---|
|`benchmarkinit`'s `clear all` destroys KLa timeseries variables|KLa timeseries are persisted to `.mat` files _before_ the workspace reload, then recovered via `load(...)` afterward. Same proven pattern as `sim_config.mat`.|
|Stale KLa `.mat` files from a crashed prior run could contaminate a new experiment|The KLa `.mat` files are unconditionally overwritten at the start of each iteration (step B), before the workspace reload. Additionally, they are included in the cleanup list on successful completion.|
|Simulink `From Workspace` block interpolation between KLa steps could smooth the step changes|Verify the block is configured for zero-order hold (ZOH) interpolation, not linear.|
|14-day pseudo-SS calibration may be insufficient for full biomass acclimatization|Acceptable for this phase; future refinement increases to 28+ days. Check Phase 2 terminal-cycle overlay as a convergence diagnostic.|
|`effluent_data_writer` `StartTime`/`StopTime`windows may need adjustment for longer sims|Phase 3 evaluation window should cover the last 14 days of the experiment phase; update the call arguments accordingly.|

---

## 12. Dependency Graph

```
run_campaign.m  (simplified / retired for now)
    │
    └──▶ main_sim.m  (refactored)
              │
              ├──▶ benchmarkinit            (external, unchanged)
              ├──▶ benchmarkss / benchmark  (Simulink models, unchanged)
              ├──▶ stateset                 (external, unchanged)
              ├──▶ generate_test_cases()           ◄── NEW
              ├──▶ generate_KLa_timeseries()       ◄── NEW
              │       │
              │       └──▶ KLa3_timeseries.mat ─┐
              │       └──▶ KLa4_timeseries.mat ──┼─ .mat persistence layer
              │       └──▶ KLa5_timeseries.mat ─┘
              │
              ├──▶ effluent_data_writer()          (unchanged)
              │
              └──  [FUTURE] dynamicInfluent_writer()
                             ▲
                   ssASM3_influent_sampler.m  ── FROZEN
                   ssInfluent_writer.m        ── FROZEN
```