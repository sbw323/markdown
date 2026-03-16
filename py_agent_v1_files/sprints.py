"""
config/sprints.py
Sprint phase definitions and the sprint catalogue for the LEYP-Water
CIP Optimizer refactoring project.

SPRINT MAP:
    Phase 1 — Strip and Simplify
        S01: Config + test infrastructure + checkpoint config
        S02: ReplacementManager + delete InvestmentManager + import shim
        S03: Optimizer 5→2 genes + OptimizationCheckpoint integration
    Phase 2 — Rework Initialization Physics
        S04: VirtualSegment point-break refactor
        S05: Pipe.__init__ age interpolation + degrade()
    Phase 3 — Runner and Outputs
        S06: Runner 3-cost-stream + safe_write_file for outputs
        S07: Validation curve
    Phase 4 — Polish and Calibrate
        S08: End-to-end integration + preemption resume test

CHECKPOINT INTEGRATION:
    config/checkpoint.py provides three layers of crash safety:
      Layer 1: CheckpointManager — phase-granularity state persistence
      Layer 2: install_preemption_handler — SIGTERM/SIGINT → save + exit(3)
      Layer 3: OptimizationCheckpoint — pymoo callback for NSGA-II resume

    The orchestrator uses Layers 1–2 (transparent to sprint code).
    Sprint S03 wires Layer 3 into leyp_optimizer.py so the NSGA-II
    evolution resumes from the last completed generation after preemption.
    Sprint S06 uses safe_write_file for all output file creation.

AUDIT FIXES APPLIED:
    F01 — ACTION_CIP_REPLACEMENT / ACTION_EMERGENCY_REPLACEMENT in S01
    F02 — S02 import shim + S03 depends on S02
    F03 — S05 skips INTEGRATE
    F06 — S02 grep audit for leyp_investment
    F07 — S01 creates tests/conftest.py
    F10 — S06 uses specific budget values for monotonicity test
    F11 — HAZARD_LENGTH_SCALE in S01/S04
    C01 — S03 cleanup() moved AFTER all output writes (was before)
    C02 — S01 creates config/__init__.py for package imports
    C03 — S02 idempotent deletion guard (os.path.exists before remove)
    C04 — S08 uses NSGA2_CHECKPOINT_PATH config ref, not hardcoded filename
    C05 — S03 removes unused check_gcp_preemption from import example
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Model defaults
# ---------------------------------------------------------------------------
DEFAULT_MODEL = "claude-sonnet-4-20250514"


# ---------------------------------------------------------------------------
# Phase enum
# ---------------------------------------------------------------------------

class SprintPhase(Enum):
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
    id: str
    title: str
    objective: str
    acceptance_criteria: list[str]
    files_to_create: list[str] = field(default_factory=list)
    files_to_modify: list[str] = field(default_factory=list)
    files_to_delete: list[str] = field(default_factory=list)
    reference_files: list[str] = field(default_factory=list)
    test_cmd: Optional[str] = None
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


# ═══════════════════════════════════════════════════════════════════════════
# SPRINT CATALOGUE
# ═══════════════════════════════════════════════════════════════════════════

SPRINTS: list[Sprint] = [

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 1 — STRIP AND SIMPLIFY
    # ══════════════════════════════════════════════════════════════════════

    Sprint(
        id="S01",
        title="Config — water material tables + test infrastructure",
        objective="""\
Refactor leyp_config.py to replace sewer-specific parameters with water
main parameters, add new configuration sections, and create the test
infrastructure.

DELETIONS — remove entirely:
  - COST_MODELS dict (all entries)
  - TRIGGERS['PM_Start'], TRIGGERS['PM_Stop']
  - PM_CONDITION_BOOST, DEFAULT_BUDGET_SPLIT

MODIFICATIONS:
  - MATERIAL_PROPS: replace sewer materials with water:
      CI, DIP, AC, PVC, PCCP, CU, HDPE, Steel, Default
  - DEGRADATION_PARAMS: water-appropriate TTF distributions
  - TRIGGERS: keep only 'Rehab' key (default 2.0)

ADDITIONS to leyp_config.py (follow existing section numbering):

  STANDARD_LIFE dict — base_life/min_life/max_life per material
  N_SEGMENTS_PER_PIPE = 4
  SEGMENT_BREAK_THRESHOLD = 3
  HAZARD_LENGTH_SCALE = 1000.0
  CIP_REPLACEMENT_COST_PER_INCH_FT = 120.00
  EMERGENCY_REPAIR_COST_PER_BREAK = 5000.00
  EMERGENCY_REPLACEMENT_COST_PER_FT = 800.00
  DEFAULT_REPLACEMENT_MATERIAL = 'HDPE'

  Cross-module string constants:
    ACTION_CIP_REPLACEMENT = 'CIP_Replacement'
    ACTION_EMERGENCY_REPLACEMENT = 'Emergency_Replacement'

  Checkpoint configuration (used by config/checkpoint.py):
    NSGA2_CHECKPOINT_PATH = 'nsga2_checkpoint.pkl'
    NSGA2_CHECKPOINT_EVERY_N_GEN = 1

CREATE tests/conftest.py:
  import pytest
  import numpy as np

  @pytest.fixture(autouse=True)
  def seed_rng():
      np.random.seed(42)
      yield

CREATE config/__init__.py:
  Empty file (or single-line docstring).  Required so that
  'from config.checkpoint import ...' works as a package import.
  config/checkpoint.py, config/sprints.py, and config/tools.py
  already live in this directory — this just makes it a package.

PRESERVE UNCHANGED:
  ALPHA, COEFF_DIAMETER, COLUMN_MAP, GLOBAL_COST_PER_FT,
  ANNUAL_BUDGET, SIMULATION_START_YEAR, map_condition_to_n_start()""",

        acceptance_criteria=[
            "MATERIAL_PROPS contains exactly 9 keys: CI, DIP, AC, PVC, PCCP, CU, HDPE, Steel, Default",
            "DEGRADATION_PARAMS contains the same 9 keys",
            "STANDARD_LIFE contains the same 9 keys",
            "Every key in MATERIAL_PROPS also exists in DEGRADATION_PARAMS and STANDARD_LIFE",
            "PM_CONDITION_BOOST is not defined anywhere in the file",
            "DEFAULT_BUDGET_SPLIT is not defined anywhere in the file",
            "TRIGGERS dict contains only 'Rehab' key",
            "No COST_MODELS dict exists",
            "N_SEGMENTS_PER_PIPE and SEGMENT_BREAK_THRESHOLD are positive integers",
            "HAZARD_LENGTH_SCALE is a positive float",
            "CIP/emergency cost constants are positive floats",
            "DEFAULT_REPLACEMENT_MATERIAL exists as a key in MATERIAL_PROPS",
            "ACTION_CIP_REPLACEMENT and ACTION_EMERGENCY_REPLACEMENT are defined",
            "NSGA2_CHECKPOINT_PATH and NSGA2_CHECKPOINT_EVERY_N_GEN are defined",
            "ALPHA, COEFF_DIAMETER, COLUMN_MAP, GLOBAL_COST_PER_FT unchanged",
            "map_condition_to_n_start() function present and unchanged",
            "tests/conftest.py exists with autouse seed_rng fixture",
            "config/__init__.py exists (enables 'from config.checkpoint import ...')",
            "python -c 'import leyp_config' succeeds",
        ],
        files_to_create=["tests/conftest.py", "config/__init__.py"],
        files_to_modify=["leyp_config.py"],
        reference_files=["leyp_config.py"],
        test_cmd="pytest tests/test_leyp_config.py -v",
    ),

    # ── S02 ────────────────────────────────────────────────────────────
    Sprint(
        id="S02",
        title="ReplacementManager — replace InvestmentManager",
        objective="""\
Create water_replacement.py with ReplacementManager, delete
leyp_investment.py, and plant an import compatibility shim in
leyp_runner.py to keep the codebase importable during transition.

CREATE water_replacement.py:
  class ReplacementManager — single-pool budget, replacement-only,
  risk-priority ranked.  See prompts.py DOMAIN_PREAMBLE for full
  class specification.

  CRITICAL: Use ACTION_CIP_REPLACEMENT from leyp_config for the Action
  field in action_log entries.  Do NOT hardcode the string literal.

DELETE leyp_investment.py (idempotent — guard for preemption re-run):
  import os
  if os.path.exists('leyp_investment.py'):
      os.remove('leyp_investment.py')
  This ensures re-running the sprint after a preemption that interrupted
  between deletion and checkpoint does not error on a missing file.

PLANT IMPORT SHIM in leyp_runner.py:
  Replace:  from leyp_investment import InvestmentManager
  With:     from water_replacement import ReplacementManager as InvestmentManager
            # SHIM: S06 will replace InvestmentManager with ReplacementManager

GREP AUDIT:
  After deletion, grep for 'leyp_investment' across all .py files.
  The ONLY match should be the shim in leyp_runner.py.""",

        acceptance_criteria=[
            "water_replacement.py exists and imports successfully",
            "ReplacementManager.__init__ accepts budget, rehab_trigger, cip_cost_rate, replacement_material, risk_cost_per_ft",
            "calculate_cost returns cip_cost_rate * diameter * length",
            "get_annualized_risk handles current_ttf near zero",
            "run_year returns dict with keys Year, Spend, Count",
            "run_year respects budget constraint",
            "execute_replacement resets condition to 6.0, material, age, segments",
            "action_log uses ACTION_CIP_REPLACEMENT constant (not string literal)",
            "No raw string 'CIP_Replacement' in water_replacement.py",
            "leyp_investment.py is deleted",
            "leyp_runner.py imports ReplacementManager via shim",
            "python -c 'import leyp_runner' succeeds without ImportError",
            "grep 'leyp_investment' returns matches ONLY in leyp_runner.py shim",
            "No PM, cleaning, repair, split_ratio references in water_replacement.py",
        ],
        files_to_create=["water_replacement.py"],
        files_to_modify=["leyp_runner.py"],
        files_to_delete=["leyp_investment.py"],
        reference_files=["leyp_investment.py", "leyp_config.py", "leyp_core.py", "leyp_runner.py"],
        depends_on=["S01"],
        test_cmd="pytest tests/test_water_replacement.py -v",
    ),

    # ── S03 ────────────────────────────────────────────────────────────
    Sprint(
        id="S03",
        title="Optimizer — 2 genes + NSGA-II checkpoint resume",
        objective="""\
Refactor leyp_optimizer.py: rename LEYP_Problem to Water_LEYP_Problem,
reduce from 5 genes to 2, drop constraint, update results processing,
and integrate OptimizationCheckpoint for preemption-safe NSGA-II.

PROBLEM DEFINITION CHANGES:
  Water_LEYP_Problem: n_var=2, n_obj=2, n_ieq_constr=0
  Genes: budget, rehab_trigger
  _evaluate: unpacks 2 values, no out["G"]

RESULTS PROCESSING:
  Columns: Investment_Cost, Risk_Cost, Budget, Rehab_Trigger, Total_Cost

NSGA-II CHECKPOINT INTEGRATION:
  Import from config.checkpoint:
    from config.checkpoint import (
        OptimizationCheckpoint,
        safe_write_file,
    )
    # NOTE: Do NOT import check_gcp_preemption here — it is called
    # internally by OptimizationCheckpoint.get_callback(), not by
    # optimizer code directly.
  Import checkpoint config:
    from leyp_config import NSGA2_CHECKPOINT_PATH, NSGA2_CHECKPOINT_EVERY_N_GEN

  In run_optimization(), replace direct algorithm creation with:

    opt_ckpt = OptimizationCheckpoint(
        checkpoint_path=NSGA2_CHECKPOINT_PATH,
        save_every_n_gen=NSGA2_CHECKPOINT_EVERY_N_GEN,
    )

    algorithm = opt_ckpt.restore_or_create(
        lambda: NSGA2(
            pop_size=alg['pop_size'],
            n_offsprings=alg['n_offsprings'],
            sampling=FloatRandomSampling(),
            crossover=SBX(prob=0.9, eta=15),
            mutation=PM(prob=0.2, eta=20),
            eliminate_duplicates=True,
        )
    )

    if opt_ckpt.resumed_from_gen > 0:
        print(f"Resuming from generation {opt_ckpt.resumed_from_gen}")

    res = minimize(
        Water_LEYP_Problem(config, optimized_input_path),
        algorithm,
        termination,
        callback=opt_ckpt.get_callback(),
        seed=alg['seed'],
        verbose=True,
    )

  The callback after each generation:
    1. Pickles algorithm state to NSGA2_CHECKPOINT_PATH (atomic write)
    2. Polls GCP metadata for preemption → exit(3) if detected

USE safe_write_file FOR ALL OUTPUT FILES:
  Replace open()/write() for CSV outputs with safe_write_file:
    safe_write_file(results_path, df.to_csv(index=False))
  Write action plan CSV, plots, etc. — ALL output files must be saved
  before cleanup.

CLEANUP — MUST BE LAST (after all output files are written):
    opt_ckpt.cleanup()
    print("NSGA-II checkpoint cleaned up.")

  CRITICAL ORDERING: cleanup() deletes the checkpoint pickle.  If it
  runs BEFORE output files are written and the VM is preempted during
  a write, the pickle is gone and the outputs don't exist.  On restart,
  restore_or_create() finds no pickle and reruns the entire evolution
  from generation 0.  This loses up to 80 minutes of compute.

  The correct sequence is always:
    1. minimize() — evolution runs, checkpoint saves per generation
    2. Write all output files (CSVs, plots, action plan)
    3. cleanup() — only after everything is safely on disk

UPDATE optimizer_config.yaml:
  Remove: pm_start, pm_stop, budget_split genes
  Keep: budget (10000–2000000), rehab_trigger (1.0–3.5)""",

        acceptance_criteria=[
            "Water_LEYP_Problem exists with n_var=2, n_obj=2, n_ieq_constr=0",
            "LEYP_Problem class no longer exists",
            "_evaluate unpacks exactly 2 values from x",
            "_evaluate does not set out['G']",
            "Results DataFrame has: Investment_Cost, Risk_Cost, Budget, Rehab_Trigger, Total_Cost",
            "Results DataFrame has NO: PM_Start, PM_Stop, Split_Ratio",
            "OptimizationCheckpoint is imported from config.checkpoint",
            "restore_or_create() called with lambda creating NSGA2",
            "opt_ckpt.get_callback() passed to minimize() as callback",
            "opt_ckpt.cleanup() called AFTER all output files are written (results CSV, action plan CSV, plots) — never before",
            "resumed_from_gen logged when resuming from checkpoint",
            "safe_write_file used for nsga2_results.csv output",
            "NSGA2_CHECKPOINT_PATH imported from leyp_config",
            "optimizer_config.yaml has exactly 2 gene definitions",
            "No imports from leyp_investment",
            "python -c 'from leyp_optimizer import Water_LEYP_Problem' succeeds",
        ],
        files_to_modify=["leyp_optimizer.py", "optimizer_config.yaml"],
        reference_files=[
            "leyp_optimizer.py", "optimizer_config.yaml",
            "leyp_runner.py", "config/checkpoint.py",
        ],
        depends_on=["S01", "S02"],
        test_cmd="python -c 'from leyp_optimizer import Water_LEYP_Problem; print(\"OK\")'",
    ),


    # ══════════════════════════════════════════════════════════════════════
    # PHASE 2 — REWORK INITIALIZATION PHYSICS
    # ══════════════════════════════════════════════════════════════════════

    Sprint(
        id="S04",
        title="VirtualSegment — point-break counts and segment failure",
        objective="""\
Refactor VirtualSegment in leyp_core.py: replace break-length tracking
with point-break counting, add segment failure threshold check.

NEW VirtualSegment:
  __init__: self.length, self.n_point_breaks = 0
  simulate_breaks(intensity): Poisson(intensity * self.length / HAZARD_LENGTH_SCALE)
    Import HAZARD_LENGTH_SCALE from leyp_config.
  has_failed(threshold): n_point_breaks >= threshold
  reset(): n_point_breaks = 0

DELETE: self.break_length, self.n_breaks (renamed to n_point_breaks),
  break-length loop with np.random.uniform.

Also update Pipe.reset_breaks() to call seg.reset() for each segment.""",

        acceptance_criteria=[
            "VirtualSegment has n_point_breaks and length, no other state",
            "No break_length attribute",
            "simulate_breaks returns int (not tuple)",
            "simulate_breaks uses HAZARD_LENGTH_SCALE from leyp_config",
            "No np.random.uniform in simulate_breaks",
            "has_failed returns correct bool at and below threshold",
            "reset() zeros n_point_breaks",
            "Pipe.reset_breaks() calls seg.reset() for each segment",
            "python -c 'from leyp_core import VirtualSegment, Pipe' succeeds",
        ],
        files_to_modify=["leyp_core.py"],
        reference_files=["leyp_core.py", "leyp_config.py"],
        depends_on=["S01"],
        test_cmd="pytest tests/test_leyp_core.py -v -k 'VirtualSegment or reset_breaks'",
    ),

    Sprint(
        id="S05",
        title="Pipe.__init__ — age interpolation, break seeding, degrade()",
        objective="""\
Refactor Pipe.__init__, degrade(), and simulate_year() in leyp_core.py.

Pipe.__init__: condition from age/STANDARD_LIFE, break seeding,
  distributed across sub-segments.
  DELETE: is_lined, cleaning_count, skip_degradation_years.

degrade(): remove skip logic.  Pure exponential decay.

simulate_year(): return dict {breaks, repair_cost, failed}.

NOTE: leyp_runner.py is temporarily incompatible after this sprint.
Do NOT modify it.  Unit tests call Pipe methods directly.""",

        acceptance_criteria=[
            "Condition at age=0 is 6.0, at age=base_life is 1.0",
            "Condition clamped to [1.0, 6.0] for age > base_life",
            "Seeded breaks >= 0, distributed across segments",
            "Pipe has no is_lined, cleaning_count, or skip_degradation_years",
            "degrade() has no conditional skip logic",
            "simulate_year() returns dict with keys: breaks, repair_cost, failed",
            "simulate_year() sets failed=True when segment exceeds threshold",
            "No break_length references as attribute in leyp_core.py",
            "Unit tests call Pipe methods directly, NOT via run_simulation",
        ],
        files_to_modify=["leyp_core.py"],
        reference_files=["leyp_core.py", "leyp_config.py"],
        depends_on=["S01", "S04"],
        test_cmd="pytest tests/test_leyp_core.py -v",
        skip_phases=[SprintPhase.INTEGRATE],
    ),


    # ══════════════════════════════════════════════════════════════════════
    # PHASE 3 — RUNNER AND OUTPUTS
    # ══════════════════════════════════════════════════════════════════════

    Sprint(
        id="S06",
        title="Runner — 3-cost-stream + atomic output writes",
        objective="""\
Refactor leyp_runner.py: replace InvestmentManager with
ReplacementManager (remove S02 shim), three-cost-stream accounting,
emergency replacements, and safe_write_file for all output.

IMPORT CHANGES:
  Remove shim.  Add:
    from water_replacement import ReplacementManager
    from leyp_config import (ACTION_CIP_REPLACEMENT,
                             ACTION_EMERGENCY_REPLACEMENT, ...)
    from config.checkpoint import safe_write_file

REMOVE from signature: pm_start, pm_stop, budget_split

THREE COST ACCUMULATORS: cip, repair, emergency.
ANNUAL LOOP: degrade → CIP replace → simulate breaks + emergency.

Use ACTION_EMERGENCY_REPLACEMENT from leyp_config.

ATOMIC WRITES: All output files via safe_write_file().

Return 2 values to optimizer, 4 in report mode.""",

        acceptance_criteria=[
            "Imports ReplacementManager directly (no shim)",
            "Imports safe_write_file from config.checkpoint",
            "No pm_start, pm_stop, budget_split in signature",
            "Returns exactly 2 floats normal, 4 values report mode",
            "cip_cost >= 0, risk_cost >= 0",
            "budget=10000 risk_cost >= budget=500000 risk_cost (seed=42, rel=0.1)",
            "Zero budget → cip_cost == 0",
            "Emergency actions use ACTION_EMERGENCY_REPLACEMENT constant",
            "CIP actions use ACTION_CIP_REPLACEMENT constant",
            "No raw action type string literals",
            "Output files written via safe_write_file",
            "action_log has correct columns",
            "100-year loop completes without exception",
            "No InvestmentManager, pm_start, pm_stop, budget_split references",
            "grep 'leyp_investment' returns zero matches",
        ],
        files_to_modify=["leyp_runner.py"],
        reference_files=[
            "leyp_runner.py", "water_replacement.py",
            "leyp_core.py", "leyp_config.py", "config/checkpoint.py",
        ],
        depends_on=["S02", "S05"],
        test_cmd="pytest tests/test_leyp_runner.py -v",
    ),

    Sprint(
        id="S07",
        title="Validation curve — % breaks avoided output",
        objective="""\
Implement generate_validation_curve() and plot_validation_curve().
Integrate into optimizer output pipeline.

Create water_validation.py.  Modify leyp_optimizer.py to call after
victory lap.  Use safe_write_file for any data file outputs.""",

        acceptance_criteria=[
            "generate_validation_curve() exists and is importable",
            "Returns 4 lists of equal length, all in [0, 100]",
            "pct_replaced_by_number monotonically increasing, ends at 100",
            "pct_avoided_by_number monotonically increasing, ends at 100",
            "Curve above diagonal for first 50%",
            "plot_validation_curve produces PNG",
            "Plot has two subplots with model curve and diagonal",
            "leyp_optimizer.py calls generate_validation_curve after victory lap",
            "validation_curve.png saved to output directory",
        ],
        files_to_create=["water_validation.py"],
        files_to_modify=["leyp_optimizer.py"],
        reference_files=[
            "leyp_runner.py", "leyp_core.py",
            "leyp_optimizer.py", "leyp_config.py",
            "config/checkpoint.py",
        ],
        depends_on=["S06"],
        test_cmd="pytest tests/test_water_validation.py -v",
    ),


    # ══════════════════════════════════════════════════════════════════════
    # PHASE 4 — POLISH AND CALIBRATE
    # ══════════════════════════════════════════════════════════════════════

    Sprint(
        id="S08",
        title="End-to-end integration, preemption test, sensitivity, docs",
        objective="""\
Full pipeline validation, preemption resume verification, sensitivity
checks, dead code audit, and documentation.

INTEGRATION VALIDATION:
1. Run python leyp_optimizer.py — verify all outputs.
2. Pareto front: Investment up, Risk down, Total U-shaped.
3. Validation curve above diagonal for first 50%.

PREEMPTION RESUME VERIFICATION:
4. Simulate mid-optimization preemption and verify resume:
   Use NSGA2_CHECKPOINT_PATH from leyp_config for all references to
   the checkpoint pickle — do NOT hardcode 'nsga2_checkpoint.pkl'.
   a. Run optimizer for ~5 generations (temporarily set n_gen=5 in
      optimizer_config.yaml, or use small pop_size for speed).
   b. Verify the NSGA2_CHECKPOINT_PATH file is created after gen 1.
   c. Kill the process (Ctrl-C / SIGINT to trigger handler).
   d. Verify the checkpoint file exists and is not corrupt — use the
      inspect_checkpoint tool in pickle mode:
        inspect_checkpoint(file_path=NSGA2_CHECKPOINT_PATH, mode="pickle")
      Confirm output says "PICKLE OK" and generation > 0.
   e. Re-run optimizer.  Verify console prints:
        "Resuming from generation N" where N > 0.
   f. Let it complete.  Verify NSGA2_CHECKPOINT_PATH file is DELETED
      after successful completion (opt_ckpt.cleanup() ran).
   g. Verify all output files are valid and structurally identical to
      a clean (non-resumed) run.  Use validate_simulation_output tool.
   h. Restore original n_gen in optimizer_config.yaml.

5. Verify safe_write_file usage:
   a. grep for patterns like "open(.*'w'" in leyp_optimizer.py and
      leyp_runner.py — should return zero matches for output writes.
      All file output should go through safe_write_file.
   b. Exception: matplotlib savefig() is acceptable (already atomic).

SENSITIVITY CHECKS:
6. SEGMENT_BREAK_THRESHOLD: 2/3/5.
7. Emergency cost ratio: 400/800/1600.

AUDITS:
8. Dead code: grep sewer terms → zero matches.
9. String constants: grep raw action types outside config → zero.
10. TODO/FIXME/HACK/SHIM: all resolved or documented.

DOCUMENTATION — Update README.md:
11. Water model, three cost streams, 2-gene optimizer.
12. Preemption handling section:
    - SIGTERM handler saves checkpoint + exits code 3.
    - Outer runner detects exit 3 and restarts.
    - NSGA-II resumes from last completed generation via pickle.
    - NSGA2_CHECKPOINT_PATH pickle is cleaned up after successful run.
    - All output files written atomically (safe_write_file).
13. Configuration: NSGA2_CHECKPOINT_PATH, NSGA2_CHECKPOINT_EVERY_N_GEN.
14. GCP spot VM deployment notes:
    - Recommended: systemd unit with Restart=on-failure,
      RestartPreventExitStatus=0 1 2, so exit code 3 triggers restart.
    - Alternative: GCP startup script that loops on exit code 3.""",

        acceptance_criteria=[
            "python leyp_optimizer.py completes without exception",
            "nsga2_results.csv exists with correct columns and > 0 rows",
            "Optimal_Action_Plan.csv exists with correct columns",
            "optimization_curve.png and validation_curve.png exist",
            "Risk_Cost decreases as Investment_Cost increases",
            "Total_Cost minimum at interior point",
            "Validation curve above diagonal for first 50%",
            "NSGA2_CHECKPOINT_PATH file created during optimization (verified via inspect_checkpoint tool)",
            "NSGA2_CHECKPOINT_PATH file deleted after successful completion (cleanup() ran)",
            "Interrupted run resumes from generation N > 0",
            "Resumed run produces valid output files",
            "No raw open()/write() for outputs in optimizer or runner",
            "threshold=2 → more emergencies than threshold=5",
            "Higher emergency cost ratio → higher optimal budget",
            "grep sewer terms → zero matches in production code",
            "grep raw action type strings outside config → zero",
            "grep TODO/FIXME/HACK/SHIM → zero or documented",
            "leyp_investment.py and leyp_orchestrator.py do not exist",
            "README describes checkpoint resume and GCP deployment",
        ],
        files_to_modify=["README.md", "optimizer_config.yaml"],
        reference_files=[
            "leyp_config.py", "leyp_core.py", "water_replacement.py",
            "leyp_runner.py", "leyp_optimizer.py", "water_validation.py",
            "config/checkpoint.py",
        ],
        depends_on=["S06", "S07"],
        test_cmd="python leyp_optimizer.py && pytest tests/ -v",
        skip_phases=[SprintPhase.UNIT_TEST],
        max_turns_per_phase={
            SprintPhase.PLAN: 8, SprintPhase.GENERATE: 40,
            SprintPhase.STATIC: 10, SprintPhase.UNIT_TEST: 0,
            SprintPhase.INTEGRATE: 20, SprintPhase.VERIFY: 15,
            SprintPhase.PACKAGE: 5,
        },
    ),
]
