# LHS WIGM Wrapper — Development Plan v2

**Project:** BSM ASM3 Influent Scenario Sampling via Latin Hypercube Design **Methodology basis:** Borobio-Castillo et al. (2024), Water Research 255, 121436 **Date:** March 2026 **Version:** 2 (incorporates reconnaissance feedback)

---

## 1. Objective

Build a set of MATLAB scripts/functions that use Latin Hypercube Sampling to generate a library of dynamic influent timeseries from the ASM3 WIGM. Each profile represents a distinct combination of demographic, climatic, and pollutant loading conditions. The influent library provides the operational-condition dimension for the downstream aeration curtailment experiment design.

---

## 2. Confirmed Technical Facts

The following were confirmed during reconnaissance and are treated as fixed constraints:

|Item|Value|
|---|---|
|Simulink model|`ASM3_Influentmodel.mdl`|
|Model type|Standalone (not embedded in BSM)|
|Init script|`ASM3_Influent_init.m` (no `clear all` or `clearvars`)|
|Workspace strategy|**Option B** — wrapper is a function; init runs in base workspace via `evalin`; overrides via `assignin`|
|Simulation time unit|Days|
|Output resolution|15-minute intervals (96 steps/day)|
|Default stop time|**728 days** (use as-is)|
|Output variable|`ASM3_Influent` (appears in base workspace after `sim`)|
|Output columns|16 columns — see Section 2.1|
|Stabilization handling|**Do not trim or renormalize.** Save the full 728-day output as-is. Stabilization trimming is handled downstream by the aeration experiment protocol.|
|PE scaling|`PE` is set as raw value in init (e.g., 80); the ×1000 multiplier is applied inside a Simulink block. LHS samples should use raw values matching the init convention (e.g., sample around 80, not 80,000).|
|Noise seeds|**Fixed** across all LHS samples. Only the 10 LHS parameters vary between profiles.|
|Industry contribution|Keep at defaults. Not included in LHS.|
|Temperature model|Keep at defaults. Not included in LHS.|
|Run time per sample|~1–2 minutes. A 200-sample library takes ~4–7 hours.|

### 2.1 Output Column Map

The `ASM3_Influent` workspace variable is an M×16 matrix (M = 728 × 96 = 69,888 rows at 15-min resolution). Column 1 is time.

|Column|Variable|Units|
|---|---|---|
|1|Time|days (fractional)|
|2|SO|g O₂/m³|
|3|SI|g COD/m³|
|4|SS|g COD/m³|
|5|SNH|g N/m³|
|6|SN2|g N/m³|
|7|SNO|g N/m³|
|8|SALK|mol/m³|
|9|XI|g COD/m³|
|10|XS|g COD/m³|
|11|XBH|g COD/m³|
|12|XSTO|g COD/m³|
|13|XBA|g COD/m³|
|14|TSS|g SS/m³|
|15|Q|m³/d|
|16|Temp|°C|

**Note:** This is a 16-column format (includes Temp). The existing `DYNINFLUENT_ASM3.mat` used by `dynamicInfluent_writer.m`uses a 21-column format. Column mapping between the WIGM output and the BSM input format will need to be addressed at the integration layer (outside the scope of this wrapper). The wrapper saves the WIGM output in its native 16-column format.

---

## 3. Input Space Definition

### 3.1 LHS Variables (10 total)

#### Flow factors (5 variables, Normal distributions)

|#|Paper Symbol|MATLAB Variable|Default|Units|Mean|Std Dev|
|---|---|---|---|---|---|---|
|1|PE|`PE`|80|×1000 (in Simulink)|80|10% = 8|
|2|QperPE|`QperPE`|150|L/d per PE|150|10% = 15|
|3|αH|`aHpercent`|75|%|75|10% = 7.5|
|4|Qpermm|`Qpermm`|1500|m³/mm rain|1500|25% = 375|
|5|LLrain|`LLrain`|3.5|mm rain/d|3.5|25% = 0.875|

#### Pollutant factors (5 variables, Uniform distributions)

|#|Paper Symbol|MATLAB Variable|Default|Units|Lower Bound|Upper Bound|
|---|---|---|---|---|---|---|
|6|COD_SOL,PE|`CODsol_gperPEperd`|19.31|g COD/(d·PE)|19.31|21.241 (110% LB)|
|7|COD_PART,PE|`CODpart_gperPEperd`|115.08|g COD/(d·PE)|115.08|126.588 (110% LB)|
|8|S_NH4,PE|`SNH_gperPEperd`|5.8565|g N/(d·PE)|5.8565|6.44215 (110% LB)|
|9|TKN_PE|`TKN_gperPEperd`|12.104|g N/(d·PE)|12.104|13.3144 (110% LB)|
|10|S_I|`SI_cst`|30.0|g COD/m³|30|50|

**SNH/TKN note:** The init file computes `SNH_gperPEperd = 6.89 * 0.85 = 5.8565` and `TKN_gperPEperd = 14.24 * 0.85 = 12.104`. The LHS samples the **post-correction** value directly and sets the variable to the sampled value (bypassing the `* 0.85`calculation).

### 3.2 Dependent Variable Recomputation

When the wrapper overrides a primary variable, it must also recompute these dependents using the same formulas from `ASM3_Influent_init.m`:

```
From PE and QperPE:
  QHHsatmax        = QperPE * 50

From PE and CODsol_gperPEperd:
  CODsol_HH_max    = 20 * CODsol_gperPEperd * PE
  CODsol_HH_nv     = factor1 * 2 * CODsol_gperPEperd * PE    (factor1 = 2.0)

From PE and CODpart_gperPEperd:
  CODpart_HH_max   = 20 * CODpart_gperPEperd * PE
  CODpart_HH_nv    = factor1 * CODpart_gperPEperd * PE

From PE and SNH_gperPEperd:
  SNH_HH_max       = 20 * SNH_gperPEperd * PE
  SNH_HH_nv        = factor1 * 2 * SNH_gperPEperd * PE

From PE and TKN_gperPEperd:
  TKN_HH_max       = 20 * TKN_gperPEperd * PE
  TKN_HH_nv        = factor1 * 1.5 * TKN_gperPEperd * PE

From SI_cst:
  SI_nv             = factor3 * SI_cst                         (factor3 = 2.0)
  Si_in             = SI_cst      (initial concentration mirrors SI_cst)
  SI_max            = 100 * SI_cst
```

All other parameters (noise seeds, switch functions, ASM3 kinetics, fractionation parameters, industry loads, temperature model, sewer model) remain at their init-file defaults.

---

## 4. File Deliverables

The wrapper consists of three MATLAB files:

### 4.1 `generate_influent_lhs.m` (function)

**Purpose:** Generate the n × 10 LHS design matrix in physical units.

**Signature:**

```matlab
function [X_physical, var_info] = generate_influent_lhs(n_samples, seed)
```

**Inputs:**

- `n_samples` — number of LHS samples (e.g., 200)
- `seed` — RNG seed for reproducibility

**Outputs:**

- `X_physical` — n × 10 matrix in physical units (matching init-file conventions)
- `var_info` — struct containing variable names, units, distribution types, and bounds for metadata/logging

**Algorithm:**

1. Set RNG state from `seed`.
2. Call `lhsdesign(n_samples, 10, 'criterion', 'maximin', 'iterations', 100)` → `X_unit` (n × 10 in [0,1]).
3. Transform columns 1–5 (Normal): `X_physical(:,j) = norminv(X_unit(:,j), mu(j), sigma(j))`.
4. Transform columns 6–10 (Uniform): `X_physical(:,j) = X_unit(:,j) * (UB(j) - LB(j)) + LB(j)`.
5. Clip Normal columns to physical bounds: PE > 0, QperPE > 0, aHpercent ∈ [0, 100], Qpermm > 0, LLrain > 0.
6. Return.

**No file I/O.** Saving the config is the caller's responsibility.

### 4.2 `apply_influent_sample.m` (function)

**Purpose:** Override the 10 LHS-sampled variables and their dependents in the base workspace.

**Signature:**

```matlab
function apply_influent_sample(sample_row, var_info)
```

**Inputs:**

- `sample_row` — 1 × 10 vector of physical-unit values (one row of `X_physical`)
- `var_info` — metadata struct (used to map column indices to variable names)

**Behavior:**

1. Assign the 10 primary variables to the base workspace via `assignin('base', name, value)`.
2. Read `factor1` and `factor3` from base workspace via `evalin('base', 'factor1')` (these are set by the init script and remain at defaults).
3. Compute all dependent variables listed in Section 3.2 using the sampled values and the factors.
4. Assign all dependents to the base workspace.

**No Simulink interaction.** This function only manipulates workspace variables.

### 4.3 `generate_influent_library.m` (function)

**Purpose:** Main wrapper — generates the full library of influent profiles.

**Signature:**

```matlab
function generate_influent_library(n_samples, seed, output_dir)
```

**Inputs:**

- `n_samples` — number of LHS samples (default 200)
- `seed` — RNG seed (default 42)
- `output_dir` — library output directory (default `'influent_library'`)

**Behavior:**

```
1. CONFIGURATION
   - wigm_model = 'ASM3_Influentmodel'
   - sim_days   = 728
   - init_script = 'ASM3_Influent_init'

2. LHS GENERATION
   - [X_physical, var_info] = generate_influent_lhs(n_samples, seed)
   - mkdir(output_dir) if needed
   - Save config: X_physical, var_info, n_samples, seed, sim_days
     → <output_dir>/influent_library_config.mat

3. RESUME LOGIC
   - state_file = <output_dir>/influent_gen_state.mat
   - If exists → load start_idx; else start_idx = 1

4. PER-SAMPLE LOOP (i = start_idx : n_samples)

   4a. Populate base workspace with defaults
       evalin('base', 'run(''ASM3_Influent_init'')')

   4b. Override LHS-sampled variables + dependents
       apply_influent_sample(X_physical(i, :), var_info)

   4c. Load and configure Simulink model
       load_system(wigm_model)  [in base workspace context]
       set_param(wigm_model, 'StopTime', num2str(sim_days))

   4d. Run simulation
       evalin('base', 'sim(''ASM3_Influentmodel'')')

   4e. Extract output
       ASM3_Influent = evalin('base', 'ASM3_Influent')
       Validate: expect M×16 matrix, M ≈ sim_days × 96

   4f. Save output
       save(<output_dir>/influent_NNN.mat, 'ASM3_Influent')
       Filename: zero-padded 3-digit index (influent_001.mat, etc.)

   4g. Log to CSV
       Append row to <output_dir>/influent_library_log.csv
       Columns: SampleIndex, PE, QperPE, aHpercent, Qpermm, LLrain,
                CODsol, CODpart, SNH, TKN, SI_cst,
                OutputRows, OutputCols, Timestamp

   4h. Checkpoint
       save(state_file, 'start_idx')  where start_idx = i + 1

   4i. Close model to free memory
       bdclose(wigm_model)

5. CLEANUP
   - Delete state_file
   - Print summary: n completed, output_dir, total elapsed time
```

**Error handling:** Wrap the per-sample body in `try/catch`. On error: log the failure (sample index + error message) to a separate error log, increment `start_idx`, continue. Do not halt the library generation for a single failed sample.

---

## 5. Development Sprints

### Sprint 1: `generate_influent_lhs.m`

**Goal:** Deliver a tested LHS generation function.

**Tasks:**

1. Implement the function per Section 4.1 specification.
2. Hardcode the 10 variable definitions (names, distributions, parameters) as a struct within the function.
3. Unit tests:
    - Verify output dimensions: n_samples × 10.
    - Verify reproducibility: same seed → identical output.
    - Verify Normal columns: marginal statistics (mean, std) approximate prescribed values for large n.
    - Verify Uniform columns: all values within [LB, UB].
    - Verify clipping: no negative PE, QperPE, Qpermm, LLrain; aHpercent in [0, 100].
    - Verify column order matches var_info metadata.

**Deliverables:** `generate_influent_lhs.m`, unit test script.

### Sprint 2: `apply_influent_sample.m`

**Goal:** Deliver a tested parameter override function.

**Tasks:**

1. Implement the function per Section 4.2 specification.
2. Unit tests (run in a test harness that calls `ASM3_Influent_init` first):
    - Override all 10 variables with known test values.
    - Verify each primary variable is set correctly in base workspace.
    - Verify each dependent variable is recomputed correctly (compare against manual calculation).
    - Verify unrelated variables (e.g., `Q_HH_ns`, `ASM3_PARS`, `Indpopswitch`) are unchanged.
    - Edge case: verify behavior with extreme LHS values (min/max of each variable's range).

**Deliverables:** `apply_influent_sample.m`, unit test script.

### Sprint 3: `generate_influent_library.m`

**Goal:** Deliver the main wrapper function.

**Tasks:**

1. Implement the function per Section 4.3 specification.
2. Integration test with n_samples = 3:
    - Verify output directory structure: config file, 3 influent .mat files, log CSV.
    - Verify each .mat file contains variable `ASM3_Influent` with expected dimensions (≈69,888 × 16).
    - Verify log CSV has 3 rows with correct sample values.
    - Verify resume: interrupt after sample 2, restart, confirm sample 3 is generated without re-running 1 and 2.
3. Verify error handling: inject a deliberate failure (e.g., corrupt one variable), confirm the loop continues and logs the error.

**Deliverables:** `generate_influent_library.m`, integration test script.

### Sprint 4: Validation

**Goal:** Confirm end-to-end correctness and compatibility.

**Tasks:**

1. Generate a small library (n = 10) on the VM.
2. Verify influent diversity:
    - Plot mean Q across all 10 profiles — should show spread consistent with PE and QperPE variation.
    - Plot mean SNH across all 10 profiles — should show spread consistent with SNH_gperPEperd variation.
    - Compare the default (unperturbed) profile against extreme profiles.
3. Compatibility check:
    - Load one output file into the existing aeration pipeline (`dynamicInfluent_writer.m` or equivalent).
    - Note: the 16-column WIGM output may need column reordering/padding to match the 21-column `DYNINFLUENT_ASM3.mat` format. Document the required mapping but do not implement the adapter in this sprint — that belongs to the integration layer.
4. Timing: record actual per-sample wall-clock time. Extrapolate to full library generation time for n = 200.

**Deliverables:** Validation report, column mapping documentation.

---

## 6. Agent Orchestration Notes

The four sprints map to sequential agent phases. Key instructions for `sprints.py` and `prompts.py`:

**Sprint 1 (`generate_influent_lhs.m`):**

- Pure MATLAB function, no Simulink dependency.
- Can be developed and tested entirely without the VM.
- The function must not perform any file I/O.
- The `var_info` struct must contain: `names` (1×10 cell of MATLAB variable names), `distributions` (1×10 cell, 'normal' or 'uniform'), `params` (1×10 cell of distribution parameter vectors), and `units` (1×10 cell of strings).

**Sprint 2 (`apply_influent_sample.m`):**

- Depends on Sprint 1 for `var_info` struct format.
- Requires `ASM3_Influent_init.m` to be present (for loading defaults before override).
- All base-workspace interaction via `assignin`/`evalin` — the function itself must not create variables in its own workspace that shadow base workspace variables.
- The dependent variable formulas in Section 3.2 are the ground truth. The agent must use exactly these formulas.

**Sprint 3 (`generate_influent_library.m`):**

- Depends on Sprints 1 and 2.
- Requires `ASM3_Influent_init.m` and `ASM3_Influentmodel.mdl` to be present.
- The `sim()` call must happen in the base workspace context (via `evalin`) because the Simulink model reads parameters from the base workspace.
- Output filenames use zero-padded 3-digit indices: `influent_001.mat` through `influent_200.mat`.
- The variable saved in each .mat file must be named `ASM3_Influent` (matching the Simulink output variable name).
- Resume logic is mandatory — library generation may take hours and the VM may interrupt.

**Sprint 4 (Validation):**

- Manual/interactive — not a code-generation sprint.
- Produces a report, not a deliverable script.
- The column mapping documentation (16 variable cols + 5 dummy variable cols WIGM → 21-col DYNINFLUENT) is a critical output that informs downstream integration work.