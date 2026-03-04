"""
config/sprints.py
Sprint phase definitions and the sprint catalogue for the BSM refactoring project.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Model defaults (importable by orchestrator for fallback/override logic)
# ---------------------------------------------------------------------------
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"


# ---------------------------------------------------------------------------
# Phase enum
# ---------------------------------------------------------------------------

class SprintPhase(Enum):
    """Phases within each sprint — executed sequentially."""
    PLAN       = "plan"
    GENERATE   = "generate"
    STATIC     = "static_analysis"
    UNIT_TEST  = "unit_test"
    INTEGRATE  = "integration_test"
    VERIFY     = "verify"
    PACKAGE    = "package"


# ---------------------------------------------------------------------------
# Sprint dataclass
# ---------------------------------------------------------------------------

@dataclass
class Sprint:
    """One unit of refactoring work, corresponding to a step in the plan."""
    id: str
    title: str
    objective: str
    acceptance_criteria: list[str]
    files_to_create: list[str] = field(default_factory=list)
    files_to_modify: list[str] = field(default_factory=list)
    # Paths relative to reference/ (e.g. "codebase/main_sim.m", "stubs/generate_KLa_timeseries.m")
    reference_files: list[str] = field(default_factory=list)
    matlab_test_cmd: Optional[str] = None
    depends_on: list[str] = field(default_factory=list)
    model: str = DEFAULT_MODEL
    max_turns_per_phase: dict = field(default_factory=lambda: {
        SprintPhase.PLAN: 8,
        SprintPhase.GENERATE: 30,
        SprintPhase.STATIC: 10,
        SprintPhase.UNIT_TEST: 20,
        SprintPhase.INTEGRATE: 10,
        SprintPhase.VERIFY: 10,
        SprintPhase.PACKAGE: 5,
    })
    retry_limit: int = 3
    skip_phases: list[SprintPhase] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Sprint catalogue — maps to the implementation order in the refactoring plan
# ---------------------------------------------------------------------------

SPRINTS: list[Sprint] = [
    # ── S01: generate_KLa_timeseries.m ─────────────────────────────────
    Sprint(
        id="S01",
        title="generate_KLa_timeseries.m",
        objective="""\
Write and unit-test `generate_KLa_timeseries.m` in isolation.

Signature:
    function KLa_ts = generate_KLa_timeseries(nominal_KLa, reduction_frac, ...
        duration_hrs, start_hour, sim_days)

Algorithm (from plan §3):
1. Build time column: t = (0 : 1/96 : sim_days - 1/96)' → length = sim_days × 96.
2. Initialize KLa column to nominal_KLa everywhere.
3. Compute reduced KLa: KLa_reduced = nominal_KLa * reduction_frac.
4. For each day d = 0 .. sim_days-1:
   - Start step: s = d*96 + round(start_hour * 96/24).
   - End step:   e = s + duration_hrs * 4 - 1.
   - Set KLa(s+1 : e+1) = KLa_reduced  (MATLAB 1-indexed).
5. Return KLa_ts = [t, KLa].
6. Length must equal sim_days × 96.

The function itself does NOT save to .mat — that is the caller's responsibility
(separation of concerns).

DRYINFLUENT.mat has 14 days of data → 14×96 = 1344 data points is the standard
length when sim_days=14.""",
        acceptance_criteria=[
            "Function file exists at src/generate_KLa_timeseries.m with correct signature",
            "Output is a two-column double matrix [time, KLa]",
            "Output has exactly sim_days * 96 rows (1344 for sim_days=14)",
            "Time column spans [0, sim_days - 1/96] with step 1/96",
            "KLa values outside reduction windows equal nominal_KLa exactly",
            "KLa values inside reduction windows equal nominal_KLa * reduction_frac exactly",
            "Reduction windows repeat on every simulated day at the correct clock time",
            "Edge case: reduction_frac=1.0 produces all-nominal timeseries",
            "Edge case: duration_hrs=0 produces all-nominal timeseries (or is rejected)",
            "Start hours 8, 12, 16 map to step indices 32, 48, 64 within each day",
        ],
        files_to_create=["src/generate_KLa_timeseries.m"],
        reference_files=[
            "stubs/generate_KLa_timeseries.m",
            "docs/BSM_Dynamic_Aeration_Experiment___Refactoring_Plan_v2.md",
        ],
        matlab_test_cmd=(
            "addpath('src'); "
            "results = runtests('tests/test_generate_KLa_timeseries.m'); "
            "disp(table(results)); "
            "exit(any([results.Failed]));"
        ),
    ),

    # ── S02: generate_test_cases.m ─────────────────────────────────────
    Sprint(
        id="S02",
        title="generate_test_cases.m",
        objective="""\
Write `generate_test_cases.m` — the combinatorics enumerator that replaces
the hardcoded 9-row test_cases matrix.

Signature:
    function T = generate_test_cases()

Output: a MATLAB table with columns:
    ExperimentID  (int, 1..60)
    ReductionFrac (double: 0.90, 0.80, 0.70, 0.60, 0.50)
    DurationHrs   (int: 1, 2, 3, 4)
    StartHour     (double: 8, 12, 16)

Total rows: 5 × 4 × 3 = 60.

Use ndgrid or nested loops. Ordering must be deterministic so crash-recovery
by iteration index is valid.  Row ordering convention: reduction_frac varies
slowest, start_hour varies fastest.""",
        acceptance_criteria=[
            "Function file exists at src/generate_test_cases.m with correct signature",
            "Output is a MATLAB table with exactly 60 rows",
            "Table has columns: ExperimentID, ReductionFrac, DurationHrs, StartHour",
            "ExperimentID runs 1..60 contiguously",
            "ReductionFrac values are exactly {0.90, 0.80, 0.70, 0.60, 0.50}",
            "DurationHrs values are exactly {1, 2, 3, 4}",
            "StartHour values are exactly {8, 12, 16}",
            "All 60 unique combinations are present (no duplicates, no omissions)",
            "Ordering is deterministic across repeated calls",
        ],
        files_to_create=["src/generate_test_cases.m"],
        reference_files=[
            "docs/BSM_Dynamic_Aeration_Experiment___Refactoring_Plan_v2.md",
        ],
        depends_on=[],  # FIX: S02 is independent of S01
        matlab_test_cmd=(
            "addpath('src'); "
            "results = runtests('tests/test_generate_test_cases.m'); "
            "disp(table(results)); "
            "exit(any([results.Failed]));"
        ),
    ),

    # ── S03: Refactor main_sim.m — Configuration section ───────────────
    Sprint(
        id="S03",
        title="Refactor main_sim.m — Configuration section",
        objective="""\
Refactor the configuration section of main_sim.m (Section 1 in the plan):

1. Replace the hardcoded test_cases matrix with a call to generate_test_cases().
2. Add sim_days = 14 as a configurable parameter.
3. Remove any references to CONSTINFLUENT.mat — DRYINFLUENT.mat is loaded
   natively by benchmarkinit.
4. Update save('sim_config.mat', ...) to include all variables that need to
   survive workspace wipes (sim_config needs: iter, num_experiments, sim_days,
   exp_cal flag, test_cases table, and any new loop control vars).
5. Do NOT modify the loop body yet — that is Sprint S04.
6. Preserve the state-resume logic (Section 2) unchanged.

Read the existing main_sim.m from the project directory for context.  Only
modify the configuration section and sim_config save/load blocks.""",
        acceptance_criteria=[
            "main_sim.m calls generate_test_cases() instead of using hardcoded matrix",
            "sim_days variable is defined and set to 14",
            "No references to CONSTINFLUENT.mat remain in main_sim.m",
            "sim_config.mat save includes: iter, num_experiments, sim_days, exp_cal, test_cases",
            "sim_config.mat load correctly restores all saved variables",
            "State-resume logic (Section 2) is structurally unchanged",
            "File parses without MATLAB syntax errors",
        ],
        files_to_modify=["main_sim.m"],
        reference_files=[
            "codebase/main_sim.m",
            "docs/BSM_Dynamic_Aeration_Experiment___Refactoring_Plan_v2.md",
        ],
        depends_on=["S01", "S02"],
        skip_phases=[SprintPhase.UNIT_TEST],
    ),

    # ── S04: Refactor main_sim.m — Loop body (3-phase pattern) ─────────
    Sprint(
        id="S04",
        title="Refactor main_sim.m — Loop body (3-phase pattern)",
        objective="""\
Rewrite the main experiment loop body in main_sim.m to the three-phase
pattern described in plan §5, Section 4.

The loop body must implement steps A–G from the plan:

A. Load experiment parameters from test_cases(iter,:)
   → reduction_frac, duration_hrs, start_hour

B. GENERATE & PERSIST KLa timeseries (called ONCE here, BEFORE workspace reload)
   → generate_KLa_timeseries() × 3 tanks (nominal KLa: 240, 240, 114)
   → save('KLa3_timeseries.mat', 'KLa3_ts')  etc.

C. Reload nominal SS workspace
   → load('workspace_steady_state_initial.mat')
   ⚠ This wipes ALL workspace variables

D. Restore loop control vars + RELOAD KLa .mat files
   → load('sim_config.mat')
   → load('sim_state.mat')
   → load('KLa3_timeseries.mat') etc.
   → Assign to workspace vars the Simulink model reads from

E. PHASE 2 — PSEUDO-SS CALIBRATION
   → set_param(ts_model, 'StopTime', num2str(sim_days))
   → sim(ts_model)
   → stateset
   → effluent_data_writer(... 'IterationLabel', iter ...)

F. PHASE 3 — EXPERIMENT (workspace carries forward — no reset, no KLa reload)
   → set_param(ts_model, 'StopTime', num2str(sim_days))
   → sim(ts_model)
   → stateset
   → effluent_data_writer(... 'IterationLabel', iter+0.5 ...)

G. Increment iter, save checkpoint (sim_state.mat)

CRITICAL: Step B is BEFORE step C.  KLa .mat files are written to disk before
the workspace wipe so they survive as checkpoints.

CRITICAL: Workspace is NOT reset between Phase 2 (E) and Phase 3 (F).  Phase 3
continues from the conditioned biomass state.

Also update the cleanup list to include KLa .mat files:
    state_files = {'sim_state.mat', 'sim_config.mat', ...
                   'workspace_steady_state_initial.mat', ...
                   'KLa3_timeseries.mat', 'KLa4_timeseries.mat', ...
                   'KLa5_timeseries.mat'};""",
        acceptance_criteria=[
            "Loop reads experiment params from test_cases table (reduction_frac, duration_hrs, start_hour)",
            "generate_KLa_timeseries called 3 times per iteration with correct nominal KLa (240, 240, 114)",
            "KLa .mat files saved BEFORE workspace reload (step B before step C)",
            "KLa .mat files reloaded AFTER workspace reload (step D after step C)",
            "Phase 2 (calibration) runs sim(ts_model) with KLa timeseries applied",
            "Phase 3 (experiment) runs from Phase 2 terminal state — no workspace reset between them",
            "effluent_data_writer called after both Phase 2 and Phase 3 with distinct iteration labels",
            "Cleanup list includes KLa3/4/5_timeseries.mat",
            "Error handling catch block updated for new variable names",
            "File parses without MATLAB syntax errors",
        ],
        files_to_modify=["main_sim.m"],
        reference_files=[
            "codebase/effluent_data_writer.m",
            "docs/BSM_Dynamic_Aeration_Experiment___Refactoring_Plan_v2.md",
            "docs/BSM_Dynamic_Control_Modeling_Best_Practices.md",
        ],
        depends_on=["S03"],
        matlab_test_cmd=None,  # integration test requires full Simulink — deferred to S06
    ),

    # ── S05: Simplify run_campaign.m ───────────────────────────────────
    Sprint(
        id="S05",
        title="Simplify run_campaign.m",
        objective="""\
Reduce run_campaign.m to a thin single-pass wrapper that calls main_sim once
with a single DRYINFLUENT configuration.

Requirements:
1. Remove the outer influent-row loop.
2. Preserve the master-results CSV accumulation logic.
3. Add FUTURE HOOK comments where variable-influent reintegration will go.
4. Ensure run_campaign calls main_sim with no arguments (main_sim handles
   its own test_cases internally via generate_test_cases).

Read the existing run_campaign.m for context.""",
        acceptance_criteria=[
            "run_campaign.m exists and is syntactically valid",
            "No outer influent-row loop remains",
            "Single call to main_sim (no arguments or single config struct)",
            "Master-results CSV accumulation logic preserved",
            "FUTURE HOOK comments present for variable-influent reintegration",
            "No references to ssInfluent_writer or ssASM3_influent_sampler",
            "File parses without MATLAB syntax errors",
        ],
        files_to_modify=["run_campaign.m"],
        reference_files=[
            "codebase/run_campaign.m",
            "docs/BSM_Dynamic_Aeration_Experiment___Refactoring_Plan_v2.md",
        ],
        depends_on=["S04"],
        skip_phases=[SprintPhase.UNIT_TEST, SprintPhase.INTEGRATE],
    ),

    # ── S06: End-to-end validation (structural dry-run) ────────────────
    Sprint(
        id="S06",
        title="End-to-end validation (structural dry-run)",
        objective="""\
Perform a structural validation of the complete refactored codebase.
Since full Simulink execution requires the BSM model files, this sprint
focuses on verifiable structural checks:

1. Verify all new/modified files parse without MATLAB syntax errors.
2. Run mlint on all source files and resolve or justify all warnings.
3. Verify generate_KLa_timeseries unit tests pass.
4. Verify generate_test_cases unit tests pass.
5. Verify main_sim.m can be parsed and the configuration section
   executes without error (up to the point where Simulink models are needed).
6. Produce a final verification_report.md summarizing all checks.

This sprint does NOT run full Simulink simulations — that requires the
actual BSM model files on a MATLAB-licensed machine.""",
        acceptance_criteria=[
            "All .m files in src/ and project root parse without syntax errors",
            "mlint produces no unresolved warnings (all suppressed with justification or fixed)",
            "test_generate_KLa_timeseries passes all test cases",
            "test_generate_test_cases passes all test cases",
            "main_sim.m configuration section executes through generate_test_cases() call",
            "verification_report.md produced with PASS/FAIL table for all checks",
        ],
        files_to_create=["verification_report.md"],
        reference_files=[
            "codebase/effluent_data_writer.m",
            "docs/BSM_Dynamic_Aeration_Experiment___Refactoring_Plan_v2.md",
        ],
        depends_on=["S05"],
        skip_phases=[SprintPhase.GENERATE],
    ),
]
