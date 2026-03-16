"""
config/sprints.py
Sprint phase definitions and the sprint catalogue for the LEYP-Water
CIP Optimizer refactoring project.

AUDIT FIXES APPLIED:
    F01 — ACTION_CIP_REPLACEMENT / ACTION_EMERGENCY_REPLACEMENT constants
           added to S01 config sprint; S02 and S06 reference them
    F02 — S02 plants import compatibility shim in leyp_runner.py;
           S03 now depends on S01 AND S02
    F03 — S05 skips INTEGRATE phase (simulate_year return type changes
           but runner isn't updated until S06)
    F06 — S02 includes grep audit for leyp_investment references
    F07 — S01 creates tests/conftest.py with autouse RNG seed fixture
    F10 — S06 acceptance criterion uses specific budget values (10000
           vs 500000) for monotonicity test
    F11 — HAZARD_LENGTH_SCALE added to S01 config; S04 references it
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

  Cross-module string constants (CRITICAL — prevents §6.2 mismatch):
    ACTION_CIP_REPLACEMENT = 'CIP_Replacement'
    ACTION_EMERGENCY_REPLACEMENT = 'Emergency_Replacement'

CREATE tests/conftest.py:
  import pytest
  import numpy as np

  @pytest.fixture(autouse=True)
  def seed_rng():
      np.random.seed(42)
      yield

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
            "ACTION_CIP_REPLACEMENT == 'CIP_Replacement' is defined",
            "ACTION_EMERGENCY_REPLACEMENT == 'Emergency_Replacement' is defined",
            "ALPHA, COEFF_DIAMETER, COLUMN_MAP, GLOBAL_COST_PER_FT unchanged",
            "map_condition_to_n_start() function present and unchanged",
            "tests/conftest.py exists with autouse seed_rng fixture",
            "python -c 'import leyp_config' succeeds",
        ],
        files_to_create=["tests/conftest.py"],
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

  from leyp_config import ACTION_CIP_REPLACEMENT
  ...
  log_entry = { ..., 'Action': ACTION_CIP_REPLACEMENT, ... }

DELETE leyp_investment.py.

PLANT IMPORT SHIM in leyp_runner.py (Fix F02):
  Replace the import line:
    from leyp_investment import InvestmentManager
  With:
    from water_replacement import ReplacementManager as InvestmentManager
    # SHIM: S06 will replace InvestmentManager with ReplacementManager
  This keeps leyp_runner.py importable during the transition period
  (S03–S05) before S06 does the full runner refactor.

GREP AUDIT (Fix F06):
  After deletion, run grep_codebase for 'leyp_investment' across all
  .py files.  The ONLY match should be the shim in leyp_runner.py.
  Any other match must be updated.""",

        acceptance_criteria=[
            "water_replacement.py exists and imports successfully",
            "ReplacementManager.__init__ accepts budget, rehab_trigger, cip_cost_rate, replacement_material, risk_cost_per_ft",
            "calculate_cost returns cip_cost_rate * diameter * length",
            "get_annualized_risk handles current_ttf near zero",
            "run_year returns dict with keys Year, Spend, Count",
            "run_year respects budget constraint",
            "execute_replacement resets condition to 6.0, material, age, segments",
            "action_log uses ACTION_CIP_REPLACEMENT constant (not string literal)",
            "No raw string 'CIP_Replacement' in water_replacement.py (grep check)",
            "leyp_investment.py is deleted",
            "leyp_runner.py imports ReplacementManager via shim",
            "python -c 'import leyp_runner' succeeds without ImportError",
            "grep 'leyp_investment' returns matches ONLY in leyp_runner.py shim line",
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
        title="Optimizer — reduce to 2 genes, smoke test",
        # Fix F02: depends on S02 so the import shim is in place
        objective="""\
Refactor leyp_optimizer.py: rename LEYP_Problem to Water_LEYP_Problem,
reduce from 5 genes to 2 (budget, rehab_trigger), drop constraint,
update results processing and visualization.

Also update optimizer_config.yaml to match.

See prompts.py for full specification of changes.

NOTE: This sprint depends on S02 because leyp_optimizer.py imports
leyp_runner, which now imports from water_replacement via the S02 shim.
Without S02 completing first, the import chain is broken.""",

        acceptance_criteria=[
            "Water_LEYP_Problem exists with n_var=2, n_obj=2, n_ieq_constr=0",
            "LEYP_Problem class no longer exists",
            "_evaluate unpacks exactly 2 values from x",
            "_evaluate does not set out['G']",
            "Results DataFrame has: Investment_Cost, Risk_Cost, Budget, Rehab_Trigger, Total_Cost",
            "Results DataFrame has NO: PM_Start, PM_Stop, Split_Ratio",
            "optimizer_config.yaml has exactly 2 gene definitions",
            "No imports from leyp_investment in the file",
            "python -c 'from leyp_optimizer import Water_LEYP_Problem' succeeds",
        ],
        files_to_modify=["leyp_optimizer.py", "optimizer_config.yaml"],
        reference_files=["leyp_optimizer.py", "optimizer_config.yaml", "leyp_runner.py"],
        # Fix F02: added S02 dependency
        depends_on=["S01", "S02"],
        test_cmd="python -c 'from leyp_optimizer import Water_LEYP_Problem; print(\"OK\")'",
    ),

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 2 — REWORK INITIALIZATION PHYSICS
    # ══════════════════════════════════════════════════════════════════════

    Sprint(
        id="S04",
        title="VirtualSegment — point-break counts and segment failure",
        # Fix F11: references HAZARD_LENGTH_SCALE constant
        objective="""\
Refactor VirtualSegment in leyp_core.py: replace break-length tracking
with point-break counting, add segment failure threshold check.

NEW VirtualSegment:
  __init__: self.length, self.n_point_breaks = 0
  simulate_breaks(intensity): Poisson(intensity * self.length / HAZARD_LENGTH_SCALE)
    Import HAZARD_LENGTH_SCALE from leyp_config — do NOT hardcode 1000.0.
  has_failed(threshold): n_point_breaks >= threshold
  reset(): n_point_breaks = 0

DELETE: self.break_length, self.n_breaks (renamed to n_point_breaks),
  break-length loop with np.random.uniform.

Also update Pipe.reset_breaks() to call seg.reset() for each segment.""",

        acceptance_criteria=[
            "VirtualSegment has n_point_breaks and length, no other state",
            "No break_length attribute",
            "simulate_breaks returns int (not tuple)",
            "simulate_breaks uses HAZARD_LENGTH_SCALE from leyp_config (not hardcoded 1000.0)",
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
        # Fix F03: skips INTEGRATE to avoid false failures from runner
        # incompatibility (simulate_year return type changes to dict but
        # runner isn't updated until S06)
        objective="""\
Refactor Pipe.__init__, degrade(), and simulate_year() in leyp_core.py
for the water model.

Pipe.__init__: condition interpolated from age/STANDARD_LIFE, break
  seeding from uniform distribution, distributed across sub-segments.
  DELETE: is_lined, cleaning_count, skip_degradation_years.

degrade(): remove skip logic entirely.  Pure exponential decay.

simulate_year(): new return type dict {breaks, repair_cost, failed}
  instead of bool.  Segment failure threshold check.

NOTE: After this sprint, leyp_runner.py will be temporarily incompatible
with the new simulate_year() return type.  This is expected and resolved
in S06.  Do NOT modify leyp_runner.py in this sprint.  Unit tests must
call Pipe.simulate_year() directly, NOT via run_simulation().""",

        acceptance_criteria=[
            "Condition at age=0 is 6.0, at age=base_life is 1.0",
            "Condition clamped to [1.0, 6.0] for age > base_life",
            "Seeded breaks >= 0, distributed across segments",
            "Pipe has no is_lined, cleaning_count, or skip_degradation_years attributes",
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
        # Fix F03: skip INTEGRATE — runner can't handle new return type yet
        skip_phases=[SprintPhase.INTEGRATE],
    ),

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 3 — RUNNER AND OUTPUTS
    # ══════════════════════════════════════════════════════════════════════

    Sprint(
        id="S06",
        title="Runner — 3-cost-stream simulation loop",
        objective="""\
Refactor leyp_runner.py: replace InvestmentManager with
ReplacementManager (remove S02 import shim), implement three-cost-stream
accounting, handle emergency replacements.

IMPORT CHANGES:
  Remove the S02 shim line.  Replace with:
    from water_replacement import ReplacementManager
    from leyp_config import (ACTION_CIP_REPLACEMENT,
                             ACTION_EMERGENCY_REPLACEMENT, ...)

REMOVE from signature: pm_start, pm_stop, budget_split

THREE COST ACCUMULATORS: cip, repair, emergency.
ANNUAL LOOP: degrade → CIP replace → simulate breaks + emergency.

CRITICAL: Use ACTION_EMERGENCY_REPLACEMENT from leyp_config for
emergency action_log entries.  Do NOT hardcode string literals.

Return 2 values to optimizer: (cip_cost, repair + emergency).
Return 4 values in report mode: (cip, repair, emergency, DataFrame).""",

        acceptance_criteria=[
            "Imports ReplacementManager directly (no shim, no InvestmentManager alias)",
            "No pm_start, pm_stop, budget_split in signature",
            "run_simulation returns exactly 2 floats in normal mode",
            "run_simulation returns exactly 4 values in report mode",
            "cip_cost >= 0, risk_cost >= 0",
            # Fix F10: specific budget values for monotonicity test
            "budget=10000 risk_cost >= budget=500000 risk_cost (seed=42, rel=0.1)",
            "Zero budget → cip_cost == 0",
            "Emergency actions use ACTION_EMERGENCY_REPLACEMENT constant",
            "CIP actions use ACTION_CIP_REPLACEMENT constant",
            "No raw 'CIP_Replacement' or 'Emergency_Replacement' string literals in file",
            "action_log has columns: Year, PipeID, Action, Cost, Priority, Condition_Before",
            "100-year loop completes without exception",
            "No references to InvestmentManager, pm_start, pm_stop, budget_split",
            "grep 'leyp_investment' in leyp_runner.py returns zero matches (shim removed)",
        ],
        files_to_modify=["leyp_runner.py"],
        reference_files=["leyp_runner.py", "water_replacement.py", "leyp_core.py", "leyp_config.py"],
        depends_on=["S02", "S05"],
        test_cmd="pytest tests/test_leyp_runner.py -v",
    ),

    Sprint(
        id="S07",
        title="Validation curve — % breaks avoided output",
        objective="""\
Implement generate_validation_curve() and plot_validation_curve(),
integrate into optimizer output pipeline.

See prompts.py for algorithm specification.

Create water_validation.py with both functions.
Modify leyp_optimizer.py to call them after victory lap.""",

        acceptance_criteria=[
            "generate_validation_curve() exists and is importable",
            "Returns 4 lists of equal length, all values in [0, 100]",
            "pct_replaced_by_number monotonically increasing, ends at 100.0",
            "pct_avoided_by_number monotonically increasing, ends at 100.0",
            "Curve above diagonal for first 50% (model better than random)",
            "plot_validation_curve produces PNG at specified path",
            "Plot has two subplots with red model curve and green diagonal",
            "leyp_optimizer.py calls generate_validation_curve after victory lap",
            "validation_curve.png saved to output directory",
        ],
        files_to_create=["water_validation.py"],
        files_to_modify=["leyp_optimizer.py"],
        reference_files=["leyp_runner.py", "leyp_core.py", "leyp_optimizer.py", "leyp_config.py"],
        depends_on=["S06"],
        test_cmd="pytest tests/test_water_validation.py -v",
    ),

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 4 — POLISH AND CALIBRATE
    # ══════════════════════════════════════════════════════════════════════

    Sprint(
        id="S08",
        title="End-to-end integration, sensitivity, documentation",
        objective="""\
Full pipeline validation, sensitivity checks, dead code audit, docs.

1. Run python leyp_optimizer.py — verify all outputs produced.
2. Pareto front shape: Investment up, Risk down, Total U-shaped.
3. Validation curve above diagonal for first 50%.
4. Sensitivity: SEGMENT_BREAK_THRESHOLD 2/3/5, emergency cost 400/800/1600.
5. Dead code audit: grep for ALL sewer terms (see VERIFY prompt).
6. String constant audit: grep for raw 'CIP_Replacement' and
   'Emergency_Replacement' outside leyp_config.py → zero matches.
7. TODO audit: grep for TODO/FIXME/HACK/SHIM → all resolved or documented.
8. Update README.md.""",

        acceptance_criteria=[
            "python leyp_optimizer.py completes without exception",
            "nsga2_results.csv exists with correct columns and > 0 rows",
            "Optimal_Action_Plan.csv exists with correct columns",
            "optimization_curve.png and validation_curve.png exist",
            "Risk_Cost decreases as Investment_Cost increases",
            "Total_Cost minimum at interior point",
            "Validation curve above diagonal for first 50%",
            "threshold=2 → more emergencies than threshold=5",
            "Higher emergency cost ratio → higher optimal budget",
            "grep sewer terms in production code → zero matches",
            "grep raw action type strings outside leyp_config → zero matches",
            "grep TODO/FIXME/HACK/SHIM in production code → zero or documented",
            "leyp_investment.py and leyp_orchestrator.py do not exist",
            "README describes water model, 3 cost streams, 2-gene optimizer",
        ],
        files_to_modify=["README.md", "optimizer_config.yaml"],
        reference_files=[
            "leyp_config.py", "leyp_core.py", "water_replacement.py",
            "leyp_runner.py", "leyp_optimizer.py", "water_validation.py",
        ],
        depends_on=["S06", "S07"],
        test_cmd="python leyp_optimizer.py && pytest tests/ -v",
        skip_phases=[SprintPhase.UNIT_TEST],
        max_turns_per_phase={
            SprintPhase.PLAN: 8, SprintPhase.GENERATE: 40,
            SprintPhase.STATIC: 10, SprintPhase.UNIT_TEST: 0,
            SprintPhase.INTEGRATE: 15, SprintPhase.VERIFY: 15,
            SprintPhase.PACKAGE: 5,
        },
    ),
]
