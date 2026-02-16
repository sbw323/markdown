You are operating in Phase 2B: Incremental Implementation.

Inputs you must treat as authoritative:
1) Attachment A: Experiment Plan (source of truth)
2) Phase 2A Refactor Plan (the checkpoint execution map)
3) Uploaded Python scripts (legacy code to refactor/extend)

You MUST implement strictly according to the Phase 2A Refactor Execution Map:
- Task 1.1: Create Directory Skeleton
- Task 1.2: Centralize Configuration
- Task 2.1: Abstract MATLAB Interface (MatlabAdapter w/ Mock mode)
- Task 2.2: Implement Influent Sampler (scenario_gen.py)
- Task 2.3: Build Simulation Runner (runner.py)
- Task 3.1: Unify Data Extractors (etl.py consolidating vstacker/normalizer/results)
- Task 3.2: Implement Risk Metrics (metrics.py)
- Task 4.1: Surrogate Trainer (surrogate.py, sklearn RF)
- Task 4.2: NSGA-II Optimizer (optimizer.py)
(Do not add or reorder tasks unless the plan explicitly indicates.)

Key pipeline stages to preserve:
Stage 1 config → Stage 2 scenarios → Stage 3 MATLAB-run checkpoint to data/raw/{run_id}/ →
Stage 4 ETL to data/processed/simulation_database.parquet → Stage 5 surrogate + NSGA-II → policy.json

STOP & CHECK GATE:
Before running the MATLAB engine for real, you must produce the KLa_Setpoints artifact and ask for a user verification checkpoint (mock mode is allowed). This gate is mandatory.

-------------------------------------------------------------------
HARD CONSTRAINTS (to prevent timeouts)
-------------------------------------------------------------------
- Execute at most 3 Task IDs per response.
- Output at most ~200 lines of code per response.
- Prefer unified diffs; do NOT paste whole files unless a file is ≤200 lines and new.
- Always end with a progress ledger so the session is resumable.

If you are approaching the output limit, stop early and checkpoint cleanly.

-------------------------------------------------------------------
WORKING STYLE
-------------------------------------------------------------------
- Treat scripts as legacy code: refactor, wrap, and parameterize. Avoid rewriting.
- Remove hardcoded paths by routing through config YAML (Task 1.2).
- Keep original scripts as “deprecated/reference” unless the plan explicitly says otherwise.
- When behavior is unclear, create a TODO contract stub; do not invent physics/logic.

-------------------------------------------------------------------
MANDATORY EXECUTION LOOP (every response)
-------------------------------------------------------------------
1) Select Tasks: pick up to 3 tasks from the Execution Map (next in order unless blocked).
2) Implement: provide patch(es) for those tasks.
3) Validate: describe what should now work + how to test it quickly (mock tests OK).
4) Checkpoint: update the Progress Ledger (completed / remaining / next).

-------------------------------------------------------------------
RESPONSE FORMAT (STRICT)
-------------------------------------------------------------------
### Selected Tasks
- Task X.Y — <short name>
- Task ...

### Patches
For each patch:

[PATCH]
File: <path>
Change Type: create | modify | move | delete
Diff:
<unified diff here>

Rationale:
- Why this change is required (tie to Task ID)

Verification:
- A minimal command or snippet that would validate success

### Local Validation Notes
- Expected behavior now:
- Known limitations / TODO contracts:

### Progress Ledger
Completed:
- Task ...

In Progress:
- Task ...

Remaining:
- Task ...

Next Recommended (max 3):
- Task ...

Manager Decision:
CONTINUE | WAIT_FOR_MORE_FILES | BLOCKED | COMPLETE

-------------------------------------------------------------------
TASK-SPECIFIC REQUIREMENTS FROM THE PHASE 2A PLAN
-------------------------------------------------------------------
Task 1.2 (Centralize Configuration):
- Create config/experiment_config.yaml
- Create src/utils/config_loader.py
- Extract hardcoded paths/params from the notebook and vessel_experiment_results into YAML.
- Config loader must validate schema (basic required keys) and return a typed dict.

Task 2.1 (MatlabAdapter):
- Encapsulate matlab.engine usage.
- Use try/except/finally to ensure engine closes.
- Include a Mock mode that simulates successful runs without MATLAB.
- Must have at least one unit test covering Mock mode success.

Task 2.2 (scenario_gen.py):
- Read influent.csv
- Produce percentile-based influent vectors (at minimum 10th, 50th, 90th; plan mentions multiple percentiles)
- Output JSON with 5 distinct influent vectors (per the plan’s verification target).

Task 2.3 (runner.py):
- Consume scenario JSON → generate KLa_Setpoints.mat (reuse create_experiment_kla_sequence logic from notebook)
- Call MatlabAdapter for each scenario
- Save raw outputs into data/raw/{run_id}/
- Must run in Mock mode end-to-end for a single scenario.

Task 3.1 (etl.py):
- Consolidate naive_vstacker.py, SNH4_normalizer.py, vessel_experiment_results.py behavior into one ETL pipeline.
- Remove hardcoded regex/paths; use config.
- Output a single Parquet file at data/processed/simulation_database.parquet.

Task 3.2 (metrics.py):
- Implement risk metric math from the experiment plan section referenced in Phase 2A.
- Include unit tests with known values (hand-calculable).

Task 4.1 (surrogate.py):
- Implement train_surrogate(parquet_path) using sklearn RandomForest.
- Return a pickleable model object + R2.

Task 4.2 (optimizer.py):
- Implement an NSGA-II optimizer to find a Pareto front from surrogate predictions.
- Return a list of candidate tuples (inputs, objective outputs) and write policy.json.

Environment risk mitigation:
- Generate requirements.txt or pyproject dependency notes if libraries may be missing.

-------------------------------------------------------------------
BEGIN
-------------------------------------------------------------------
Start with Task 1.1 and Task 1.2, unless the directory skeleton already exists.
If you need more scripts or file contents to proceed, return WAIT_FOR_MORE_FILES and specify exactly which file(s) are needed next.
