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
DEFAULT_MODEL = "claude-opus-4-6"


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
    # Paths relative to reference/ (e.g. "codebase/main_sim.m", "docs/refactoring_plan_v3.md")
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
# Sprint catalogue — maps to the implementation order in refactoring plan v3
#
# v3 scope: Add reduction-day patterns, midnight-wrapping support, and
#           active-day-only aeration energy averaging.
# All sprints modify existing files (no greenfield creates except tests).
# ---------------------------------------------------------------------------

SPRINTS: list[Sprint] = [
    # ── S01: generate_KLa_timeseries.m — reduction_days + midnight wrap ──
    Sprint(
        id="S01",
        title="generate_KLa_timeseries.m — reduction_days + midnight wrap",
        objective="""\
Modify the existing `generate_KLa_timeseries.m` to add two capabilities:

1. NEW PARAMETER: reduction_days (6th positional argument)
   - Vector of integers 1–7 specifying active days in a 7-day week pattern.
   - Default: [1 2 3 4 5 6 7] (daily — backward compatible).
   - Day mapping: week_day = mod(day_idx, 7) + 1 where day_idx is 0-based.
   - Only active days receive the reduction window; inactive days stay nominal.
   - Input validation: non-empty, integers in [1,7], no duplicates.

2. MIDNIGHT WRAPPING: Remove the error on midnight wrap.
   - Replace the error('KLa:windowWrapsMidnight', ...) block.
   - Use mod(step_index, STEPS_PER_DAY) to wrap overflow indices back to
     the beginning of the SAME day slot (no spill into next calendar day).
   - Example: start_hour=22, duration=4 → steps [88..95, 0..7] within one day.

3. Integrate both features in the day loop:
   - Skip inactive days via ismember(week_day, reduction_days).
   - Compute within-day indices with mod-based wrapping.

4. Update the docstring with the new parameter, wrapping behavior, and examples.

Read the existing file first.  Preserve the input validation structure,
named constants, and time-column construction.  Only modify the day loop
and add the new parameter handling.""",
        acceptance_criteria=[
            "Function signature has 6th argument: reduction_days with default [1 2 3 4 5 6 7]",
            "Calling with 5 args (old signature) produces identical output to the original code",
            "reduction_days=[1] on 14-day sim applies reduction only on days 1 and 8",
            "reduction_days=[1 3 5] on 14-day sim applies reduction on days 1,3,5,8,10,12",
            "Midnight wrap: start_hour=22, duration_hrs=4 produces reduced KLa at steps 88-95 and 0-7",
            "Midnight wrap does NOT spill into the next calendar day's step block",
            "Input validation rejects reduction_days values outside [1,7]",
            "Input validation rejects empty reduction_days",
            "Edge case: reduction_frac=1.0 still produces all-nominal timeseries",
            "Edge case: duration_hrs=0 still produces all-nominal timeseries",
            "Output dimensions unchanged: sim_days*96 rows × 2 columns",
            "Docstring documents reduction_days parameter and midnight wrap behavior",
        ],
        files_to_modify=["generate_KLa_timeseries.m"],
        reference_files=[
            "codebase/generate_KLa_timeseries.m",
            "docs/refactoring_plan_v3.md",
        ],
        matlab_test_cmd=(
            "results = runtests('tests/test_generate_KLa_timeseries.m'); "
            "disp(table(results)); "
            "exit(any([results.Failed]));"
        ),
    ),

    # ── S02: generate_test_cases.m — reduction_days pass-through ───────
    Sprint(
        id="S02",
        title="generate_test_cases.m — reduction_days pass-through",
        objective="""\
Modify the existing `generate_test_cases.m` to accept and propagate
the campaign-level reduction_days pattern.

1. Add reduction_days as an optional input argument (default [1 2 3 4 5 6 7]).
   Use nargin < 1 check for backward compatibility.

2. Add reduction_days_label() as a local helper function:
   label = "d" + strjoin(string(sort(days_vec)), "_")

3. Add two new columns to the output table — uniform across all 60 rows
   since reduction_days is a campaign-level setting, not an experimental factor:
   - ReductionDays (cell array column): repmat({reduction_days}, 60, 1)
   - ReductionDaysLabel (string column): repmat(label, 60, 1)

The 60-experiment grid (5×4×3) and ndgrid enumeration are UNCHANGED.
Read the existing file first.  Only add the new argument handling and columns.""",
        acceptance_criteria=[
            "Function accepts optional reduction_days argument",
            "Calling with no args produces 60-row table (backward compatible)",
            "Table has new columns: ReductionDays (cell) and ReductionDaysLabel (string)",
            "All 60 rows have identical ReductionDays value (campaign-level)",
            "reduction_days_label([1 2 3 4 5 6 7]) returns 'd1_2_3_4_5_6_7'",
            "reduction_days_label([1]) returns 'd1'",
            "reduction_days_label([1 3 5]) returns 'd1_3_5'",
            "Original 4 columns (ExperimentID, ReductionFrac, DurationHrs, StartHour) unchanged",
            "Row count still exactly 60",
        ],
        files_to_modify=["generate_test_cases.m"],
        reference_files=[
            "codebase/generate_test_cases.m",
            "docs/refactoring_plan_v3.md",
        ],
        depends_on=[],
        matlab_test_cmd=(
            "results = runtests('tests/test_generate_test_cases.m'); "
            "disp(table(results)); "
            "exit(any([results.Failed]));"
        ),
    ),

    # ── S03: effluent_data_writer.m — labeling + active-day AE filtering
    Sprint(
        id="S03",
        title="effluent_data_writer.m — labeling + active-day AE filtering",
        objective="""\
Modify `effluent_data_writer.m` to:

1. NEW ARGUMENTS (add to arguments block):
   - ReductionDaysLabel (1,1) string = "d1_2_3_4_5_6_7"
   - ReductionDays (:,1) double = (1:7)'

2. SUMMARY ROW: Insert ReductionDaysPattern column after 'Start Time'.

3. FILENAME: Update settler CSV filename to include the pattern label:
   settler_data_iter_%.1f_%s.csv (e.g., settler_data_iter_1.0_d1_3_5.csv)

4. ACTIVE-DAY-ONLY AE AVERAGING (critical new logic):
   The current code integrates aeration energy over the full evaluation window
   and divides by totalt.  When reduction_days is not daily, this dilutes the
   measured effect with nominal-only days.

   Implementation:
   a. Build a logical mask from the partition timestamps:
      day_indices = floor(partition_time)    % 0-based day number
      week_days = mod(day_indices, 7) + 1    % 1-based day-of-week
      active_mask = ismember(week_days, options.ReductionDays)
   b. Filter KLa vectors and dt weights to active_mask timesteps only.
   c. Compute both BSM energy methods on the filtered data.
   d. Normalize by totalt_active = sum(dt(active_mask)), not totalt.
   e. If no active days in window → return NaN for both AE columns.

   CRITICAL ALIGNMENT: The day mapping (mod(floor(t), 7) + 1) must match
   generate_KLa_timeseries's mapping (mod(day_idx, 7) + 1).  Both use
   the same formula; verify in tests.

   Effluent concentrations (flow-weighted averages) remain computed over
   the FULL evaluation window — only AE is filtered.

5. Steady-state mode: no changes needed (AE already returns NaN).

Read the existing file carefully.  The function is complex.  Only modify:
- The arguments block (add 2 new options)
- The summary_row table construction (add 1 column)
- The filename sprintf (add pattern label)
- The aeration energy section (replace with masked version)
Do NOT touch the column map, effluent concentration logic, or flow-weighted
averaging.""",
        acceptance_criteria=[
            "New arguments ReductionDaysLabel and ReductionDays in arguments block",
            "Summary row has ReductionDaysPattern column",
            "Settler CSV filename includes pattern label",
            "With ReductionDays=[1:7], AE output is identical to original code",
            "With ReductionDays=[1] on 7-day window, only ~1/7 timesteps contribute to AE",
            "With no active days in evaluation window, AE returns NaN",
            "Effluent concentrations still computed over full window (not filtered)",
            "Steady-state mode unaffected (AE still NaN)",
            "Day index alignment: mod(floor(t), 7)+1 matches generate_KLa_timeseries convention",
            "expand_scalar_kla helper function unchanged",
            "File parses without MATLAB syntax errors",
        ],
        files_to_modify=["effluent_data_writer.m"],
        reference_files=[
            "codebase/effluent_data_writer.m",
            "codebase/generate_KLa_timeseries.m",
            "docs/refactoring_plan_v3.md",
        ],
        depends_on=["S01"],
        matlab_test_cmd=(
            "results = runtests('tests/test_effluent_data_writer.m'); "
            "disp(table(results)); "
            "exit(any([results.Failed]));"
        ),
    ),

    # ── S04: main_sim.m — wire reduction_days through orchestration ────
    Sprint(
        id="S04",
        title="main_sim.m — wire reduction_days through orchestration",
        objective="""\
Modify main_sim.m to propagate the reduction_days pattern through
the entire simulation pipeline.

Changes to Section 1 (Configuration):
1. Load campaign_params.mat if present to get reduction_days.
   Fallback: reduction_days = 1:7 if file absent.
2. Pass reduction_days to generate_test_cases(reduction_days).
3. Add reduction_days to sim_config.mat save.

Changes to the loop body (Steps A–G):
A. Extract reduction_days and rd_label from test_cases:
   reduction_days = test_cases.ReductionDays{iter};
   rd_label = test_cases.ReductionDaysLabel(iter);

B. Pass reduction_days as 6th arg to all three generate_KLa_timeseries calls.

C. (unchanged — workspace reload)

D. Persist and reload reduction_days + rd_label:
   - Save to experiment_params.mat in Step B (before workspace wipe).
   - Load in Step D (after workspace wipe).

E. Pass ReductionDaysLabel=rd_label and ReductionDays=reduction_days(:)
   to the Phase 2 effluent_data_writer call.

F. Same for the Phase 3 effluent_data_writer call.

G. (unchanged — iter increment)

Also update:
- fprintf diagnostics to show reduction_days pattern.
- Cleanup list: add experiment_params.mat.
- Error handling: add experiment_params.mat reload in catch block.

Read the existing main_sim.m first.  Make targeted edits to each section.""",
        acceptance_criteria=[
            "Loads campaign_params.mat for reduction_days with fallback to 1:7",
            "generate_test_cases called with reduction_days argument",
            "reduction_days extracted from test_cases table per iteration",
            "generate_KLa_timeseries calls have 6th argument: reduction_days",
            "experiment_params.mat saved before workspace wipe (Step B)",
            "experiment_params.mat loaded after workspace wipe (Step D)",
            "Both effluent_data_writer calls pass ReductionDaysLabel and ReductionDays",
            "fprintf shows reduction_days pattern label",
            "Cleanup list includes experiment_params.mat",
            "File parses without MATLAB syntax errors",
        ],
        files_to_modify=["main_sim.m"],
        reference_files=[
            "codebase/main_sim.m",
            "codebase/effluent_data_writer.m",
            "docs/refactoring_plan_v3.md",
        ],
        depends_on=["S01", "S02", "S03"],
        skip_phases=[SprintPhase.UNIT_TEST],
    ),

    # ── S05: run_campaign.m — campaign-level reduction_days ────────────
    Sprint(
        id="S05",
        title="run_campaign.m — campaign-level reduction_days",
        objective="""\
Modify run_campaign.m to accept and propagate the reduction_days
campaign-level parameter.

1. Add reduction_days configuration variable in Section 1:
   reduction_days = [1 2 3 4 5 6 7];  % default
   Include commented examples for [1], [1 3 5], [6 7].

2. Save campaign_params.mat before main_sim:
   save('campaign_params.mat', 'reduction_days');

3. Add reduction_days to campaign_state.mat save/reload (Section 3/5).

4. Add campaign_params.mat to cleanup in Section 7.

5. Update console output:
   rd_label = "d" + strjoin(string(sort(reduction_days)), "_");
   fprintf('  Reduction-day pattern: %s\\n', rd_label);

6. Note in run_campaign.m header: the readmatrix call in Section 6 may
   need to switch to readtable since the summary CSV now contains a
   string column (ReductionDaysPattern).  Verify and fix if needed.

7. Update documentation header with usage examples.

Read the existing run_campaign.m first.  Make targeted edits.""",
        acceptance_criteria=[
            "reduction_days variable defined in configuration section with default [1:7]",
            "campaign_params.mat saved before run('main_sim')",
            "campaign_state.mat includes reduction_days",
            "campaign_params.mat cleaned up in Section 7",
            "Console output shows reduction-day pattern label",
            "readmatrix replaced with readtable if needed for string column compatibility",
            "Documentation header updated with reduction_days usage examples",
            "File parses without MATLAB syntax errors",
        ],
        files_to_modify=["run_campaign.m"],
        reference_files=[
            "codebase/run_campaign.m",
            "docs/refactoring_plan_v3.md",
        ],
        depends_on=["S04"],
        skip_phases=[SprintPhase.UNIT_TEST, SprintPhase.INTEGRATE],
    ),

    # ── S06: End-to-end validation (structural dry-run) ────────────────
    Sprint(
        id="S06",
        title="End-to-end validation (structural dry-run)",
        objective="""\
Perform structural validation of all modified files against the
refactoring plan v3 acceptance criteria.

1. Verify all modified .m files parse without MATLAB syntax errors.
2. Run mlint on all source files and resolve or justify all warnings.
3. Run generate_KLa_timeseries unit tests (including new reduction_days
   and midnight wrap tests).
4. Run generate_test_cases unit tests (including new column tests).
5. Run effluent_data_writer unit tests (including active-day AE filtering).
6. Verify day-index alignment: generate_KLa_timeseries and
   effluent_data_writer use the same mod(idx, 7)+1 mapping.
7. Verify backward compatibility: all functions called with old signatures
   produce identical output to pre-v3 code.
8. Produce verification_report.md with PASS/FAIL table.

This sprint does NOT run full Simulink simulations.""",
        acceptance_criteria=[
            "All .m files parse without syntax errors",
            "mlint produces no unresolved warnings",
            "test_generate_KLa_timeseries passes all cases including reduction_days and midnight wrap",
            "test_generate_test_cases passes all cases including new columns",
            "test_effluent_data_writer passes all cases including active-day AE filtering",
            "Day-index alignment verified between generate_KLa_timeseries and effluent_data_writer",
            "Backward compatibility confirmed for all modified functions",
            "verification_report.md produced with PASS/FAIL table",
        ],
        files_to_create=["verification_report.md"],
        reference_files=[
            "codebase/generate_KLa_timeseries.m",
            "codebase/generate_test_cases.m",
            "codebase/effluent_data_writer.m",
            "codebase/main_sim.m",
            "codebase/run_campaign.m",
            "docs/refactoring_plan_v3.md",
        ],
        depends_on=["S05"],
        skip_phases=[SprintPhase.GENERATE],
    ),
]