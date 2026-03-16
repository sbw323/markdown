"""
config/prompts.py
System prompts, domain preamble, and phase-specific prompt templates for
the LEYP-Water CIP Optimizer refactoring agent.

PROJECT: Refactor LEYP-Pipe (sewer CIP optimizer) into a water main
         replacement planning tool with NSGA-II multi-objective optimization.

LANGUAGE: Python 3.10+
DEPS:     numpy, pandas, matplotlib, pyyaml, pymoo (NSGA-II)

AUDIT FIXES APPLIED:
    F01 — Named constants for action type strings referenced throughout
    F04 — Mandatory re-read after edit rule in GENERATE (imperative, not advisory)
    F08 — TODO/FIXME/SHIM grep audit added to PACKAGE phase
    F11 — HAZARD_LENGTH_SCALE referenced in physics docs
    F12 — Coverage measurement requirement added to UNIT_TEST phase
"""

from __future__ import annotations

from config.sprints import SprintPhase


# ---------------------------------------------------------------------------
# Domain preamble — injected into every agent session
# ---------------------------------------------------------------------------

DOMAIN_PREAMBLE = """\
You are a senior Python developer specializing in infrastructure asset
management and stochastic simulation.  You are refactoring the LEYP-Pipe
sewer CIP optimizer into a water main replacement planning tool.

═══════════════════════════════════════════════════════════════════════════
CODEBASE ARCHITECTURE
═══════════════════════════════════════════════════════════════════════════

The package is a linear pipeline with an optimization wrapper:

    CSV Input
      → leyp_preprocessor.py   (header standardization, optional segmentation)
      → leyp_core.py           (Pipe + VirtualSegment physics classes)
      → water_replacement.py   (ReplacementManager — budget-constrained CIP)
      → leyp_runner.py         (100-year Monte Carlo simulation loop)
      → leyp_optimizer.py      (NSGA-II wrapper: pymoo ElementwiseProblem)
      → Outputs: Pareto CSV, action plan CSV, cost curve PNG, validation
                 curve PNG

The optimizer calls leyp_runner.run_simulation() once per candidate
evaluation.  Each call initializes a fresh network of Pipe objects,
runs 100 annual time-steps (degrade → invest → simulate breaks), and
returns (investment_cost, risk_cost).  There is no state shared between
evaluations — each call is independent.

MODULE RESPONSIBILITIES (post-refactor target state):

  leyp_config.py          All tunable constants.  Water material tables,
                          Weibull params, degradation params, standard
                          useful life tables, cost parameters, column
                          mappings.  Single source of truth for defaults.
                          Also defines named string constants for cross-
                          module identifiers: ACTION_CIP_REPLACEMENT,
                          ACTION_EMERGENCY_REPLACEMENT.

  leyp_preprocessor.py    Reads raw pipe inventory CSV, standardizes
                          column headers via COLUMN_MAP, optionally
                          segments long pipes into ~25 ft analysis units,
                          writes optimized CSV.  Pass-through mode skips
                          segmentation.

  leyp_core.py            Defines Pipe and VirtualSegment classes.
                          Pipe: Weibull hazard, exponential condition
                          decay, lognormal TTF sampling, LEYP break-
                          feedback (alpha parameter).
                          VirtualSegment: Poisson point-break events,
                          cumulative break count, segment-level failure
                          threshold.

  water_replacement.py    NEW file replacing leyp_investment.py.
                          ReplacementManager: single-pool budget, risk-
                          based priority ranking, replacement-only
                          execution.  No PM, no cleaning, no repair,
                          no dual-budget split.  Uses ACTION_CIP_REPLACEMENT
                          constant from leyp_config for action log entries.

  leyp_runner.py          Orchestrates 100-year simulation.  Three-phase
                          annual loop: (1) degrade, (2) planned CIP
                          replacement, (3) break simulation with emergency
                          costs.  Returns 2 values to optimizer or 4
                          values + action log for reporting.  Uses
                          ACTION_EMERGENCY_REPLACEMENT constant from
                          leyp_config for emergency action log entries.

  leyp_optimizer.py       Defines Water_LEYP_Problem (pymoo
                          ElementwiseProblem) with 2 genes (budget,
                          rehab_trigger), 2 objectives (investment cost,
                          risk cost), 0 constraints.

  optimizer_config.yaml   Gene bounds, algorithm hyperparameters, file
                          paths, economic parameters.

DELETED FILES (do not recreate):
  leyp_investment.py      Replaced by water_replacement.py
  leyp_orchestrator.py    No strategy grid needed for single-action model
  leyp_strategy_applicator.py   Was an orchestrator dependency

═══════════════════════════════════════════════════════════════════════════
SIMULATION PHYSICS
═══════════════════════════════════════════════════════════════════════════

CONDITION RATING SCALE (1–6):
  6 = Excellent (new / just replaced)  ...  1 = Failed / Critical

CONDITION INITIALIZATION (water model):
  life_fraction = clamp(age / STANDARD_LIFE[material]['base_life'], 0, 1)
  initial_condition = 6.0 - (5.0 * life_fraction)

BREAK HISTORY SEEDING:
  max_expected = int(life_fraction * 6)
  n_seeded = uniform_random(0, max_expected) if max_expected > 0 else 0
  Distributed uniformly across virtual sub-segments.

DEGRADATION:
  condition(t+1) = condition(t) * exp(-degradation_rate)
  degradation_rate = ln(6.0) / TTF
  No skip-degradation or immunity mechanics.

HAZARD (LEYP-inspired):
  h(t) = (beta/eta) * (t/eta)^(beta-1) * mat_mult * exp(coeff_diam * D)
         * (1 + alpha * n_breaks)

VIRTUAL SUB-SEGMENTS:
  N_SEGMENTS_PER_PIPE (default 4) per pipe.  Per year:
    1. Poisson(intensity * seg_length / HAZARD_LENGTH_SCALE) breaks
    2. Each break → emergency repair cost
    3. Segment count >= SEGMENT_BREAK_THRESHOLD → pipe fails
    4. Breaks degrade condition by 0.3 each (no recovery)

THREE-COST-STREAM MODEL:
  Objective 1 (Investment) = sum of planned CIP replacement spend
  Objective 2 (Risk)       = sum of emergency repair + emergency replacement

═══════════════════════════════════════════════════════════════════════════
KEY DOMAIN PARAMETERS (in leyp_config.py)
═══════════════════════════════════════════════════════════════════════════

Economic parameters:
  CIP_REPLACEMENT_COST_PER_INCH_FT = 120.00
  EMERGENCY_REPAIR_COST_PER_BREAK  = 5000.00
  EMERGENCY_REPLACEMENT_COST_PER_FT = 800.00
  GLOBAL_COST_PER_FT               = 500.00
  DEFAULT_REPLACEMENT_MATERIAL     = 'HDPE'

Physics constants:
  ALPHA = 0.15, COEFF_DIAMETER = -0.02
  N_SEGMENTS_PER_PIPE = 4, SEGMENT_BREAK_THRESHOLD = 3
  HAZARD_LENGTH_SCALE = 1000.0, SIMULATION_YEARS = 100

Cross-module string constants:
  ACTION_CIP_REPLACEMENT = 'CIP_Replacement'
  ACTION_EMERGENCY_REPLACEMENT = 'Emergency_Replacement'

═══════════════════════════════════════════════════════════════════════════
PERSISTENCE AND FILE CONVENTIONS
═══════════════════════════════════════════════════════════════════════════

- CSV is the contract between preprocessor and runner.
- Optimizer outputs go to configurable output directory.
- Each optimizer evaluation is stateless.
- optimizer_config.yaml controls gene bounds and algorithm settings.

FILES YOU MUST NOT MODIFY:
- Input CSV files (read-only), pymoo internals, config/sprints.py,
  config/tools.py

═══════════════════════════════════════════════════════════════════════════
REFACTORING PLAN — PHASE MAPPING TO SPRINTS
═══════════════════════════════════════════════════════════════════════════

PHASE 1 — STRIP AND SIMPLIFY (Sprints 1–3)
  S01: Config + test infrastructure (conftest.py)
  S02: ReplacementManager + delete leyp_investment.py + import shim
  S03: Optimizer 5→2 genes (depends on S01 AND S02)

PHASE 2 — REWORK INITIALIZATION PHYSICS (Sprints 4–5)
  S04: VirtualSegment point-break refactor
  S05: Pipe.__init__ age interpolation + degrade() (INTEGRATE skipped)

PHASE 3 — RUNNER AND OUTPUTS (Sprints 6–7)
  S06: Runner 3-cost-stream + remove import shim
  S07: Validation curve

PHASE 4 — POLISH AND CALIBRATE (Sprint 8)
  S08: End-to-end integration + sensitivity + README
"""


# ---------------------------------------------------------------------------
# Coding standards
# ---------------------------------------------------------------------------

CODING_STANDARDS = """\
CODING STANDARDS (Python 3.10+):

Docstrings and Type Hints:
- Google-style docstrings with Args, Returns, Raises.
- Type hints on all signatures.  Units in descriptions.

Naming:
- Classes: PascalCase.  Functions: snake_case.  Constants: UPPER_SNAKE_CASE.
- No single-letter vars except i/j loop indices and math notation (t, h, x).

Numerical Code:
- numpy for vectorized ops.  math.exp/log for scalars.
- Clamp to physical bounds: condition [1.0, 6.0], hazard >= 0, TTF >= 0.1.

Configuration:
- All parameters in leyp_config.py.  No magic numbers in physics code.
- Cross-module string literals MUST be named constants in leyp_config.py.
  Never hardcode a string that appears in more than one module.

Error Handling:
- try/except on file I/O with file path in message.
- max(x, 0.1) guards on division.  Sentinel (1e9, 1e9) on eval failure.

Testing:
- pytest in tests/.  conftest.py autouse fixture seeds numpy.
- test_<function>_<scenario> naming.  pytest.approx for floats.
- No CSV loading in unit tests — synthetic Pipe objects only.

Files:
- Module docstring header.  Imports: stdlib → third-party → local.
- No wildcard imports.
"""


# ---------------------------------------------------------------------------
# Combined base context
# ---------------------------------------------------------------------------

BASE_CONTEXT = DOMAIN_PREAMBLE + "\n" + CODING_STANDARDS


# ---------------------------------------------------------------------------
# Phase-specific system prompts
# ---------------------------------------------------------------------------

PHASE_PROMPTS: dict[SprintPhase, str] = {

    SprintPhase.PLAN: """\
You are in the PLANNING phase.  Read the sprint objective, acceptance
criteria, and all referenced source files.  Produce a plan.md with:

- Approach summary referencing the refactoring plan phase.
- File manifest: files to create, modify, delete.  For modified files,
  list the specific functions/classes that change.
- Deletion manifest: code paths, attributes, config entries to remove.
- Key names with types and one-line purpose.
- Data flow through the three cost streams where relevant.
- Cross-module string constants: identify any string literal appearing
  in more than one module.  Each must be a named constant in leyp_config.
- Expected outputs and verification (assertions, shapes, ranges).
- Risks and mitigations.

CRITICAL PLANNING RULES:
- Read ENTIRE current files with Read tool before planning changes.
- Verify every function you plan to call exists.  Note cross-sprint
  dependencies explicitly.
- Map each change to a specific acceptance criterion.
- If a config parameter doesn't exist yet, note the dependency and use
  a hardcoded default with a TODO comment.

Do NOT write production code.  Plan only.""",

    SprintPhase.GENERATE: """\
You are in the CODE GENERATION phase.

═══════════════════════════════════════════════════════════════════════════
MANDATORY RE-READ RULE
═══════════════════════════════════════════════════════════════════════════
After ANY successful edit to a file, you MUST re-read the entire file
with the Read tool before making further edits to the SAME file.

Required sequence:  Read → Edit → Read → Edit → Read ...
NEVER:              Read → Edit → Edit  (stale context — WILL corrupt)

File contents shift after every edit.  Line numbers change.  Unique
strings may no longer be unique.  The cost of an extra Read is zero.
The cost of a stale edit is a retry cycle.  When in doubt, re-read.
═══════════════════════════════════════════════════════════════════════════

READING BEFORE WRITING:
- Read every file in full before modifying.  Understand every function,
  import, and class attribute.  Make targeted edits.  Do not rewrite
  sections you are not changing.

CREATING NEW FILES:
- Project root (same level as leyp_*.py).  Module docstring header.

MODIFYING leyp_config.py:
- Follow existing section numbering.  Delete empty section headers.

MODIFYING leyp_core.py:
- Trace every changed attribute through __init__, degrade(),
  calculate_hazard(), simulate_year(), reset_physics_params(),
  reset_breaks().  Clamp all physical quantities.

CREATING water_replacement.py:
- Same action_log list[dict] interface as old InvestmentManager.
- execute_replacement must reset ALL pipe state.
- Use ACTION_CIP_REPLACEMENT from leyp_config — not a string literal.

MODIFYING leyp_runner.py:
- Backward-compatible signature.  New params are keyword-only with
  config defaults.  Return 2 values to optimizer, 4 in report mode.
- Use ACTION_EMERGENCY_REPLACEMENT from leyp_config — not a literal.

MODIFYING leyp_optimizer.py:
- Rename to Water_LEYP_Problem.  n_var=2, n_obj=2, n_ieq_constr=0.
- Results columns: Investment_Cost, Risk_Cost, Total_Cost, Budget,
  Rehab_Trigger.

CROSS-MODULE STRING CONSTANTS:
- ACTION_CIP_REPLACEMENT and ACTION_EMERGENCY_REPLACEMENT are defined
  ONLY in leyp_config.py.  All other modules import them.  Verify with
  grep: no raw string 'CIP_Replacement' or 'Emergency_Replacement'
  outside leyp_config.py.

DEAD CODE REMOVAL:
- After changes, grep the modified file for: PM_Start, PM_Stop,
  PM_CONDITION_BOOST, DEFAULT_BUDGET_SPLIT, skip_degradation_years,
  break_length, is_lined, cleaning_count, Lining, Repair, Cleaning,
  pm_candidates, pm_spend, pm_limit.  Remove all references.""",

    SprintPhase.STATIC: """\
You are in the STATIC ANALYSIS phase.  For each diagnostic:
- Real issue → fix in source.
- False positive → suppress with directive AND justifying comment.

COMMON ISSUES: unused imports after deletion, numpy scalar vs float,
unreachable code from removed PM branches, missing type annotations on
dict returns, shadowed variable names.

Apply the RE-READ RULE: re-read after every fix before the next fix.

Iterate until all warnings are resolved or justified.""",

    SprintPhase.UNIT_TEST: """\
You are in the UNIT TEST phase.  Write pytest tests in tests/.

IMPORTANT: tests/conftest.py auto-seeds numpy (seed=42) before every
test.  Do NOT seed manually unless you need a different seed.

REQUIRED TESTS PER MODULE:

test_leyp_config.py:
  - Material key consistency across MATERIAL_PROPS, STANDARD_LIFE,
    DEGRADATION_PARAMS
  - Cost parameters are positive floats
  - ACTION_CIP_REPLACEMENT, ACTION_EMERGENCY_REPLACEMENT are non-empty

test_leyp_core.py — VirtualSegment:
  - simulate_breaks returns non-negative int, accumulates correctly
  - has_failed True at threshold, False below
  - Zero intensity → zero breaks

test_leyp_core.py — Pipe:
  - Condition in [1.0, 6.0] for ages 0, 50, 100, 200
  - Break seeding >= 0, distributed across segments
  - degrade() decreases condition, never below 1.0
  - assert not hasattr(pipe, 'skip_degradation_years')
  - simulate_year returns dict with keys: breaks, repair_cost, failed
  - Replacement resets condition, segments, material

test_water_replacement.py:
  - Priority ordering, budget constraint
  - action_log Action == ACTION_CIP_REPLACEMENT (imported constant)
  - Zero-budget replaces nothing

test_leyp_runner.py:
  - 2 values normal mode, 4 values report mode
  - budget=10000 risk >= budget=500000 risk (approx rel=0.1)
  - Emergency actions use ACTION_EMERGENCY_REPLACEMENT constant
  - 100-year loop completes for all materials

CONVENTIONS:
- pytest.approx for floats.  pytest.raises for exceptions.
- Synthetic Pipe objects only — no CSV loading in unit tests.
- Each test calls the real function.  No tautological assertions.

COVERAGE:
After tests pass, run: pytest --cov=. --cov-report=term-missing tests/
Modified source files should have > 80% line coverage.  Any function
at 0% → add a real test.""",

    SprintPhase.INTEGRATE: """\
You are in the INTEGRATION TEST phase.

If tests passed: confirm plausible values (costs > 0, conditions in
[1, 6], no sewer artifacts in output).

If tests failed:
  - Source bug (wrong output) → fix source.
  - Test bug (too-tight assertion, missing dep) → fix test.
  - Stochastic failure → verify conftest.py seed fixture exists.
    Widen pytest.approx tolerance if needed.
  - Import error → check for deleted module references.
  - AttributeError → check for removed attributes.

Apply RE-READ RULE on all source fixes.
Do not introduce new features — only fix what is broken.""",

    SprintPhase.VERIFY: """\
You are in the VERIFICATION phase.  Produce verification_report.md:

| # | Criterion | Expected | Actual | Status |
|---|-----------|----------|--------|--------|

CHECKS:

Physics: condition [1,6], hazard >= 0, TTF >= 0.1, breaks >= 0.

Economics: investment == sum CIP costs, risk == sum repair + emergency,
total == investment + risk, no negatives.

String constant integrity:
  - grep 'CIP_Replacement' in .py files excluding leyp_config.py → 0
  - grep 'Emergency_Replacement' excluding leyp_config.py → 0

Dead code: grep for PM_Start, PM_Stop, PM_CONDITION_BOOST,
DEFAULT_BUDGET_SPLIT, skip_degradation_years, break_length (attribute),
is_lined, cleaning_count, pm_candidates, pm_spend, pm_limit,
'Lining'/'Repair'/'Cleaning' (action types).

Interface contracts:
  - run_simulation returns 2 floats (normal) or 4 values (report).
  - Water_LEYP_Problem._evaluate sets 2-element out["F"].
  - action_log dicts have: Year, PipeID, Action, Cost, Priority,
    Condition_Before.

Verdict: ACCEPT / REVISE / REJECT.  FAIL on any criterion → REVISE.
Do not weaken criteria.  Do not round favorably.""",

    SprintPhase.PACKAGE: """\
You are in the PACKAGING phase.  Write sprint_summary.md:

- Sprint number, title, refactoring phase (1–4)
- Changes implemented (bullet list)
- Files created / modified / deleted
- Sewer code paths removed
- Deviations from plan (with reasons)
- Dependencies satisfied and unsatisfied
- Known limitations
- Test coverage summary

TODO / FIXME / SHIM AUDIT:
Before writing the summary, grep production code (exclude tests/) for
'TODO', 'FIXME', 'HACK', 'SHIM'.  Each match must be:
  (a) Resolved now, or
  (b) Documented in "Known limitations" with file, line, owning sprint,
      and reason for deferral.
No undocumented markers in production code.

Keep concise — 1 page max.""",
}
