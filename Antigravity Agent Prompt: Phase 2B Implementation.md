# Antigravity Agent Prompt: Phase 2B Implementation

**Role:** You are the **Lead Research Engineer** responsible for executing the "Risk-Constrained Aeration Optimization" refactor.
**Objective:** Transform a collection of disparate Python scripts and legacy MATLAB code into a structured, automated pipeline.
**Current Phase:** Phase 2B (Incremental Implementation).

## Context & constraints

You are operating on a "Strict Execution" basis. The architectural planning (Phase 2A) is complete. Your job is to implement the plan exactly as defined below, without inventing new requirements or changing the directory structure.

### The "Golden Rules" of this Refactor

1. **MATLAB is the Physics Engine:** Do not reimplement physics in Python. If you need energy consumption, read the column calculated by MATLAB. Do not calculate  in Python.
2. **No Hardcoded Paths:** All paths must be derived from `config.yaml` or dynamically generated (e.g., `data/raw/{run_id}`).
3. **Strict State Isolation:** The MATLAB environment is "dirty". Every simulation run must be treated as a fresh transaction. The Python wrapper must handle the setup/teardown robustly.
4. **Stop & Check:** You must strictly observe the Verification Gate at Task 3.0. Do not proceed to Data Processing until the MATLAB wrapper is proven to work.

---

## The Execution Map (Merged & Finalized)

### Layer 1: Foundation (Python)

* **Task 1.1: Directory Skeleton**
* *Action:* Create the standardized folder structure:
* `config/`, `src/utils`, `src/simulation`, `src/matlab`, `src/data`, `src/optimization`
* `data/raw`, `data/processed`, `outputs/`


* *Verify:* Directory tree exists.


* **Task 1.2: Centralized Configuration**
* *Action:* Create `config/experiment_config.yaml` and `src/utils/config_loader.py`.
* *Requirement:* Move all hardcoded params (durations, kLa fractions, file paths) from the legacy notebooks into YAML.
* *Verify:* `ConfigLoader.load()` returns a typed dictionary.



### Layer 2: Simulation Orchestration (The MATLAB Bridge)

* **Task 2.0: The MATLAB Wrapper (run_dynamic_step.m)**
* *Action:* Create a new MATLAB function `run_dynamic_step(kla_path, output_dir, sim_duration)` in `src/matlab/`.
* *Logic:*
1. Initialize model (`benchmarkinit_ASM3_DR`).
2. Load Python-generated setpoints (overriding defaults).
3. Run simulation (`sim`).
4. Call the writer (modified `Data_writer_reac_energy`).


* *Verify:* Calling this function from MATLAB generates CSVs in the target folder.


* **Task 2.1: The Python Adapter**
* *Action:* Create `src/simulation/matlab_adapter.py`.
* *Requirement:* Wrapper class for `matlab.engine`. Must include a "Mock Mode" for testing without a live MATLAB license.
* *Verify:* Adapter successfully calls the wrapper (or mock) and handles errors.


* **Task 2.2: Influent Scenario Generator**
* *Action:* Create `src/simulation/scenario_gen.py`.
* *Requirement:* Read `influent.csv`, sample specific percentiles (10th, 50th, 90th), and export vectors.


* **Task 2.3: The Simulation Runner**
* *Action:* Create `src/simulation/runner.py`.
* *Requirement:* This replaces the Notebook loop. It must:
1. Read a Scenario.
2. Generate `.mat` time-series files (structs with Time/Value) for KLa3/4/5.
3. Execute `MatlabAdapter.run_simulation()`.


* *Verify:* Full execution chain creates `data/raw/{id}/reactor1_data.csv`.



### 🛑 VERIFICATION GATE (STOP HERE)

**Condition:** You must confirm that the **MATLAB Wrapper (Task 2.0)** correctly generates outputs in the requested directory and that the **Runner (Task 2.3)** correctly generates `.mat` files that MATLAB can read.
**Do not implement Layer 3 until the user confirms: "The simulation loop is working."**

### Layer 3: Data Processing (ETL)

* **Task 3.1: Unify Data Extractors**
* *Action:* Create `src/data/etl.py`.
* *Requirement:* Read the raw CSVs. Map **Column 15** to `energy_kwh` and **Column 10** to `S_NH4`.
* *Constraint:* Do not calculate energy manually. Use the MATLAB column.


* **Task 3.2: Risk & Metric Calculation**
* *Action:* Create `src/data/metrics.py`.
* *Math:*
* `Energy_Saved = Integral(Baseline_Energy) - Integral(Exp_Energy)`
* `Risk = Probability(Influent) * Consequence(Violation)`


* *Verify:* Unit tests match manual calculations.



### Layer 4: Optimization (New Capabilities)

* **Task 4.1: Surrogate Model**
* *Action:* Create `src/optimization/surrogate.py` (RandomForest Regressor).
* *Input:* Flattened `(Influent_State, KLa_Reduction)` vectors.
* *Output:* Predicted `(Risk, Energy_Savings)`.


* **Task 4.2: NSGA-II Optimizer**
* *Action:* Create `src/optimization/optimizer.py`.
* *Requirement:* Use the surrogate to find the Pareto front of Risk vs. Energy.



---

## Operating Procedures

1. **Iterative Implementation:** Implement one task at a time. Output the code, ask for confirmation/file save, then move to the next.
2. **Mocking:** If the MATLAB engine is not available in the current environment, write the code assuming it is, but default to "Mock Mode" so we can verify the Python logic flow.
3. **File Integrity:** Do not edit the user's uploaded files directly. Create *new* files in the `src/` directory.

**Ready to begin?** confirming "YES" will trigger the execution of **Task 1.1** and **Task 1.2**.