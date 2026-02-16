# Phase 2A: Refactor Planning

## 1. Codebase Inventory

| File | Purpose | Entry Points | Inputs | Hidden Side Effects | Architectural Violations |
| --- | --- | --- | --- | --- | --- |
| **`ASM3_Datagen_iterator.ipynb`** | Orchestrates the MATLAB simulation loop. | Cell Execution | Hardcoded parameters (offsets, fractions). | Calls `matlab.engine`; Writes `.mat` files to hardcoded absolute paths; Copies large directory trees (`shutil.copytree`). | Hardcoded paths; Mixes config, logic, and execution; Zero modularity; Depends on external MATLAB environment. |
| **`energy_use_utils.py`** | Utility for column naming. | Functions | Strings/Paths. | None. | None. Good candidate for `src/utils`. |
| **`pollu_vis.py`** | Visualization of pollutant percentiles. | `main()` | CSVs (Experiment & Nominal). | Displays plots (blocking) unless flag set. | Hardcoded paths in `parse_args` defaults. |
| **`pollu_norm_vis.py`** | Visualization of normalized differences. | `main()` | CSVs. | Displays plots. | Hardcoded paths; Duplicates logic from `pollu_vis`. |
| **`vessel_experiment_results.py`** | Aggregates windowed experiment data. | `main()` | CSVs. | Writes summary CSVs. | Hardcoded regex patterns for filenames; Hardcoded `INPUT_DIR`. |
| **`stacked_exp_influent_combiner.py`** | Joins influent data to experiment CSVs. | `main()` | CSVs. | Writes new CSVs. | Hardcoded paths. |
| **`naive_vstacker.py`** | Stacks CSVs from iteration folders. | `main()` | Directory structure. | Writes stacked CSVs. | Hardcoded paths; Assumes directory structure `Results_ExpLength_*`. |
| **`experiment_extractor.py`** | Extracts specific time windows based on energy triggers. | `main()` | CSVs. | Writes CSVs. | Hardcoded energy thresholds and column names. |
| **`SNH4_normalizer.py`** | Computes specific normalized features. | `main()` | Stacked CSVs. | Writes CSVs. | Hardcoded paths; Hardcoded nominal energy markdown path. |

---

## 2. Requirement Gap Matrix

| Plan Requirement | Current Behavior | Gap | Change Type |
| --- | --- | --- | --- |
| **Configurable Parameters** | Parameters buried in `ipynb` cells and `argparse` defaults. | Impossible to sweep params without editing code. | **Refactor** (Extract to YAML). |
| **Pseudo-Dynamic Step Response** | Runs full 273-day simulation loop via MATLAB. | Inefficient; Does not support "Snapshot" initialization logic described in plan. | **New Module** (Loop Orchestrator) + **Assumption** (MATLAB adapter). |
| **Structured Influent Sampling** | No sampling logic; uses full time-series. | Missing "Percentile" selection logic (10th, 50th, etc.). | **New Module** (`scenario_gen.py`). |
| **Surrogate Training Data** | Generates raw time-series CSVs. | Data is not flattened into `(Input Vector, Output Metric)` pairs for ML. | **New Module** (`feature_builder.py`). |
| **Probabilistic Risk Metric** | No risk calculation. | Missing  and  logic. | **New Module** (`risk_assessor.py`). |
| **Optimization Loop** | None. | Missing Surrogate + NSGA-II implementation. | **New Module** (`optimizer.py`). |
| **MATLAB Decoupling** | Direct `matlab.engine` calls in notebook. | Hard to mock/test; Fails if MATLAB missing. | **Wrap** (Create `MatlabAdapter` class). |

---

## 3. Dependency & Execution Graph

**Stage 1: Configuration & Setup**

* **Responsible:** `ConfigLoader`
* **Data:** `config.yaml` → `ConfigObject`
* **Boundary:** Validates paths and schema before any execution.

**Stage 2: Scenario Generation (Python)**

* **Responsible:** `ScenarioGenerator`
* **Data:** `influent.csv` → `influent_snapshots.json`
* **Action:** Samples the 10th, 25th, 50th... percentiles from raw influent data.

**Stage 3: Simulation Execution (Python wrapper -> MATLAB)**

* **Responsible:** `SimulationRunner` (replaces Notebook)
* **Data:** `ConfigObject` + `influent_snapshots.json` → `setpoints.mat`
* **Action:** Iterates scenarios → Calls `MatlabAdapter` → Captures CSV/MAT output.
* **Checkpoint:** Saves raw simulation outputs to `data/raw/{run_id}/`.

**Stage 4: Data Processing & Aggregation**

* **Responsible:** `DataProcessor` (Consolidates `vstacker`, `normalizer`, `extractor`)
* **Data:** `data/raw/` → `data/processed/simulation_database.parquet`
* **Action:** Computes , , and Risk metrics.

**Stage 5: Surrogate Modeling & Optimization**

* **Responsible:** `OptimizationEngine`
* **Data:** `simulation_database.parquet` → `policy.json`
* **Action:** Trains ML model → Runs NSGA-II → Extracts Policy.

---

## 4. Refactor Execution Map (CRITICAL CHECKPOINT ARTIFACT)

### Phase 2B-1: Foundation & Configuration

* **Task 1.1: Create Directory Skeleton**
* *Category:* Create Structure
* *Pre:* None.
* *Post:* `config/`, `src/`, `data/`, `outputs/` exist.
* *Verify:* `ls -R` shows structure.


* **Task 1.2: Centralize Configuration**
* *Category:* Create Module
* *Files:* `config/experiment_config.yaml`, `src/utils/config_loader.py`
* *Action:* Extract all hardcoded paths/params from `ASM3_Datagen_iterator.ipynb` and `vessel_experiment_results.py` into YAML.
* *Verify:* Loading config returns a typed dictionary.



### Phase 2B-2: Simulation Orchestration (Replacing the Notebook)

* **Task 2.1: Abstract MATLAB Interface**
* *Category:* Create Module / Wrap
* *Files:* `src/simulation/matlab_adapter.py`
* *Action:* Encapsulate `matlab.engine` calls. Add error handling (try/except/finally) to ensure engine closes. Add "Mock" mode for testing without MATLAB.
* *Verify:* Unit test calling the adapter in Mock mode returns success.


* **Task 2.2: Implement Influent Sampler**
* *Category:* New Module
* *Files:* `src/simulation/scenario_gen.py`
* *Action:* Implement logic to read `influent.csv` and return vectors for 10th, 50th, 90th percentiles (Plan Section 2.2).
* *Verify:* Output JSON contains 5 distinct influent vectors.


* **Task 2.3: Build Simulation Runner**
* *Category:* Create Module / Refactor
* *Files:* `src/simulation/runner.py` (Refactors logic from Notebook)
* *Action:* Create a loop that consumes Scenarios -> Generates `KLa_Setpoints.mat` (using logic from `create_experiment_kla_sequence`) -> Calls `MatlabAdapter`.
* *Verify:* Runner generates expected directory structure for a single mock run.



### Phase 2B-3: Data Pipeline Consolidation

* **Task 3.1: Unify Data Extractors**
* *Category:* Refactor / Merge
* *Files:* `src/data/etl.py` (Merges `naive_vstacker.py`, `SNH4_normalizer.py`, `vessel_experiment_results.py`)
* *Action:* Create a pipeline that accepts raw experiment folders and outputs a single generic DataFrame. Remove hardcoded "reactor" regexes if possible, use Config.
* *Verify:* Running ETL on dummy CSVs produces a clean Parquet file.


* **Task 3.2: Implement Risk Metrics**
* *Category:* New Module
* *Files:* `src/data/metrics.py`
* *Action:* Implement math from Plan Section 5.2 ().
* *Verify:* Unit tests with known values match manual calculation.



### Phase 2B-4: Surrogate & Optimization (New Capabilities)

* **Task 4.1: Surrogate Trainer**
* *Category:* New Module
* *Files:* `src/optimization/surrogate.py`
* *Action:* Implement `train_surrogate(parquet_path)` using sklearn (RandomForest).
* *Verify:* Returns a pickleable model object and R2 score.


* **Task 4.2: NSGA-II Optimizer**
* *Category:* New Module
* *Files:* `src/optimization/optimizer.py`
* *Action:* Implement `optimize(surrogate_model)` to find Pareto front.
* *Verify:* Returns a list of (Influent, Reduction) tuples.



---

## 5. Risk & Ambiguity Register

* **Risk:** **MATLAB Black Box.** We cannot see `ASM3_DR_datagen.m`.
* *Assumption:* The Python script only needs to provide inputs (`KLa` setpoints) and the MATLAB script will handle the physics.
* *Mitigation:* The `MatlabAdapter` will be designed to be agnostic to the specific `.m` file internals, only passing arguments and checking for output files.


* **Ambiguity:** **Initial State Management.** The plan requires "Initialize at nominal steady state". The notebook has a "Steady State Initialization" phase.
* *Assumption:* The existing MATLAB script `ASM3_DR_datagen.m` already saves/loads `workspace_steady_state_initial.mat`. We will rely on this existing mechanism rather than trying to inject state vectors manually from Python.


* **Risk:** **Environment.** The user might not have `pymoo` or `scikit-learn` installed.
* *Mitigation:* Add `requirements.txt` generation to Phase 2B tasks.



---

## 6. Phase-2B Execution Instructions

1. **Start with Task 1.1 & 1.2 (Config).** Do not proceed until the configuration structure is agreed upon. This anchors all future paths.
2. **Execute Task 2.1 (MatlabAdapter).** Ensure this is robust. This is the bridge to the user's legacy code.
3. **Execute Task 2.2 & 2.3 (Runner).** This replaces the Notebook.
* *Stop & Check:* Ask user to verify if the generated `KLa_Setpoints` look correct before connecting the MATLAB engine.


4. **Execute Task 3.1 & 3.2 (Data).** This consolidates the messy script collection into a clean library.
5. **Execute Task 4.1 & 4.2 (ML/Opt).** This is the "new value" promised in the plan.
6. **Final Verification:** Run the `Manager` agent to oversee a full "Mock" end-to-end run.

**Note to Implementer:** When modifying `naive_vstacker.py` or similar, do not rewrite them in place. Create new class-based modules in `src/` and mark the original scripts as deprecated/reference.