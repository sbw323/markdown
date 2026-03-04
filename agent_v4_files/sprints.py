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
    # Paths relative to reference/ (e.g. "codebase/main_sim.m", "docs/refactoring_plan_v4.md")
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
# Sprint catalogue — maps to the implementation order in refactoring plan v4
#
# v4 scope: Variable influent outer loop.  run_campaign.m gains a tranche
#           loop that slices DYNINFLUENT_ASM3.mat into fixed-length blocks,
#           writes each over dryinfluent.mat, and runs the full experiment
#           matrix per tranche.  A new dynamicInfluent_writer.m handles the
#           slice-renormalize-save operation.  main_sim.m gets a one-line
#           change to load sim_days from campaign_params.mat.
#
# Implementation order (from refactoring_plan_v4.md):
#   S01: dynamicInfluent_writer.m  — new function, standalone
#   S02: main_sim.m               — load sim_days from campaign_params.mat
#   S03: run_campaign.m            — outer tranche loop refactor
#   S04: End-to-end structural validation
# ---------------------------------------------------------------------------

SPRINTS: list[Sprint] = [
    # ── S01: dynamicInfluent_writer.m — new tranche extraction function ──
    Sprint(
        id="S01",
        title="dynamicInfluent_writer.m — tranche extraction function",
        objective="""\
Create a new function `dynamicInfluent_writer.m` that extracts a single
tranche from a long influent source file and writes it as the model's
influent input file.

FUNCTION SIGNATURE:
    function info = dynamicInfluent_writer(source_file, tranche_idx, ...
        tranche_len_rows, start_row, target_file)

DEFAULT ARGUMENTS (use nargin checks):
    source_file     = 'DYNINFLUENT_ASM3.mat'   (path to long influent)
    tranche_idx     — REQUIRED, 1-based
    tranche_len_rows = 1344                     (14 days × 96 steps/day)
    start_row       = 1                         (1-based, first tranche start)
    target_file     = 'dryinfluent.mat'         (model's expected influent)

ALGORITHM:
1. Load source_file.  The workspace variable is named ASM3_Influent
   (Mx21 matrix: col 1 = time in fractional days at 1/96 increments,
   cols 2–21 = state variables, flow, temperature, dummies).

2. Compute row range:
     row_start = start_row + (tranche_idx - 1) * tranche_len_rows
     row_end   = row_start + tranche_len_rows - 1

3. Validate row_end <= size(ASM3_Influent, 1).  If exceeded, error with
   a message reporting how many full tranches are available:
     max_tranches = floor((total_rows - start_row + 1) / tranche_len_rows)

4. Extract: tranche = ASM3_Influent(row_start:row_end, :)

5. Renormalize time column to start at 0:
     tranche(:,1) = tranche(:,1) - tranche(1,1)

6. Save as variable DRYINFLUENT (overwrites target_file):
     DRYINFLUENT = tranche;
     save(target_file, 'DRYINFLUENT');

7. Return info struct with fields:
     source_file, tranche_idx, row_start, row_end,
     time_start_original, time_end_original, source_start_day
   where time_start_original and source_start_day are both
   ASM3_Influent(row_start, 1) (the un-renormalized source time).

INPUT VALIDATION (error with descriptive IDs):
- source_file exists on disk
- source_file contains variable ASM3_Influent
- ASM3_Influent has exactly 21 columns
- tranche_idx >= 1, integer
- tranche_len_rows >= 1, integer
- start_row >= 1, integer
- Row range does not exceed source matrix bounds

DESIGN NOTE: The function overwrites target_file each time.  This is
intentional — benchmarkinit loads whatever is in dryinfluent.mat, so the
tranche must be written before main_sim is called.  The function runs
before benchmarkinit, so no workspace scoping issues apply.

Include a complete docstring with signature, parameter descriptions,
algorithm summary, examples, and author/date block.  Follow the style
conventions of the existing codebase (see ssInfluent_writer.m for a
similar file-writing function).""",
        acceptance_criteria=[
            "Function file dynamicInfluent_writer.m created with correct signature",
            "Default arguments: source_file='DYNINFLUENT_ASM3.mat', tranche_len_rows=1344, start_row=1, target_file='dryinfluent.mat'",
            "tranche_idx is required (no default)",
            "Loads ASM3_Influent variable from source file",
            "Validates source file has exactly 21 columns",
            "Row range: row_start = start_row + (tranche_idx-1)*tranche_len_rows, row_end = row_start + tranche_len_rows - 1",
            "Errors when row_end exceeds source matrix, reporting max available tranches",
            "Extracts correct submatrix of tranche_len_rows rows",
            "Renormalizes time column: tranche(:,1) = tranche(:,1) - tranche(1,1)",
            "Saves as variable DRYINFLUENT into target_file",
            "Output DRYINFLUENT has same dimensions as input tranche (tranche_len_rows x 21)",
            "Renormalized time starts at exactly 0",
            "Returns info struct with all 7 fields: source_file, tranche_idx, row_start, row_end, time_start_original, time_end_original, source_start_day",
            "info.source_start_day equals ASM3_Influent(row_start, 1) before renormalization",
            "Tranche 1 with start_row=1 extracts rows 1:1344",
            "Tranche 2 with start_row=1 extracts rows 1345:2688",
            "Tranche 1 with start_row=97 (day 1 offset) extracts rows 97:1440",
            "Consecutive tranches are non-overlapping with no gaps",
            "Overwrites target_file on each call (verified by calling twice with different tranche_idx)",
            "Input validation rejects: missing source file, wrong column count, tranche_idx < 1, non-integer tranche_idx",
            "Docstring documents all parameters, algorithm, and examples",
            "File parses without MATLAB syntax errors",
        ],
        files_to_create=["dynamicInfluent_writer.m"],
        reference_files=[
            "codebase/ssInfluent_writer.m",
            "docs/refactoring_plan_v4.md",
        ],
        matlab_test_cmd=(
            "results = runtests('tests/test_dynamicInfluent_writer.m'); "
            "disp(table(results)); "
            "exit(any([results.Failed]));"
        ),
    ),

    # ── S02: main_sim.m — load sim_days from campaign_params.mat ───────
    Sprint(
        id="S02",
        title="main_sim.m — load sim_days from campaign_params.mat",
        objective="""\
Modify main_sim.m to load sim_days from campaign_params.mat instead of
hardcoding it, enabling run_campaign.m to control simulation length
per tranche.

CHANGE 1 — Replace the sim_days assignment and campaign_params.mat
loading block in Section 1 (Configuration).

Current code (lines ~28–37):
    sim_days = 14;   % Simulation length in days
    ...
    if isfile('campaign_params.mat')
        load('campaign_params.mat', 'reduction_days');
        fprintf('  Loaded reduction_days from campaign_params.mat\\n');
    else
        reduction_days = 1:7;
        fprintf('  No campaign_params.mat found; using default ...\\n');
    end

Replace with:
    sim_days = 14;   % Default for standalone use (no campaign wrapper)
    if isfile('campaign_params.mat')
        load('campaign_params.mat', 'reduction_days', 'sim_days');
        fprintf('  Loaded reduction_days and sim_days from campaign_params.mat\\n');
    else
        reduction_days = 1:7;
        fprintf('  No campaign_params.mat found; using default reduction_days = [1:7], sim_days = %d\\n', sim_days);
    end

The key difference: sim_days is now loaded from campaign_params.mat when
present, overriding the default.  When campaign_params.mat is absent
(standalone use), sim_days retains the default value of 14.

CHANGE 2 — Verify sim_days is already in the sim_config.mat save call.
Current code already saves sim_days:
    save('sim_config.mat', ..., 'sim_days', ...);
No change needed here — just confirm it is present.

ACTION REQUIRED:
- Read the existing main_sim.m with the Read tool.
- Make the targeted edit to the campaign_params.mat loading block.
- Verify the sim_config.mat save call already includes sim_days.
- Do NOT modify any other sections of main_sim.m.

This is a minimal, surgical change.  The rest of main_sim.m (the
three-phase protocol, generate-persist-wipe-reload loop, effluent_data_writer
calls, error handling, cleanup) is UNCHANGED.""",
        acceptance_criteria=[
            "campaign_params.mat load call includes 'sim_days' alongside 'reduction_days'",
            "sim_days = 14 remains as default before the isfile check",
            "When campaign_params.mat is absent, sim_days defaults to 14",
            "When campaign_params.mat contains sim_days=7, main_sim uses sim_days=7",
            "fprintf message updated to mention sim_days",
            "sim_config.mat save call includes sim_days (confirm, no change needed)",
            "No other sections of main_sim.m are modified",
            "File parses without MATLAB syntax errors",
        ],
        files_to_modify=["main_sim.m"],
        reference_files=[
            "codebase/main_sim.m",
            "docs/refactoring_plan_v4.md",
        ],
        depends_on=[],
        skip_phases=[SprintPhase.UNIT_TEST],
    ),

    # ── S03: run_campaign.m — outer tranche loop ──────────────────────
    Sprint(
        id="S03",
        title="run_campaign.m — outer tranche loop",
        objective="""\
Refactor run_campaign.m to add an outer loop that iterates over
influent tranches from DYNINFLUENT_ASM3.mat.  Each tranche overwrites
dryinfluent.mat, forces a fresh steady-state calibration, resets the
experiment iterator, and runs the full experiment matrix via main_sim.

Read the existing run_campaign.m first.  The current structure is:
  Section 1: Configuration
  Section 2: Clean slate
  Section 3: Save wrapper state
  Section 4: Run main_sim
  Section 5: Restore wrapper state
  Section 6: Accumulate results
  Section 7: Cleanup & summary

STRUCTURAL CHANGE: Sections 2–6 are wrapped in:
    for tranche_idx = 1:num_tranches

NEW SECTION 1 PARAMETERS (add after existing config block):
    % --- Influent source configuration ---
    influent_source     = 'DYNINFLUENT_ASM3.mat';
    influent_target     = 'dryinfluent.mat';
    tranche_start_day   = 0;       % Start of first tranche (days)
    tranche_len_days    = 14;      % Length of each tranche = sim_days

    % Derived row-space parameters
    steps_per_day       = 96;
    tranche_len_rows    = tranche_len_days * steps_per_day;   % 1344
    start_row           = tranche_start_day * steps_per_day + 1;  % 1-based

NEW: TRANCHE COUNT DETERMINATION (after parameter block):
    % Validate source file exists
    if ~isfile(influent_source)
        error('run_campaign:SourceNotFound', ...
            'Influent source file not found: %s', influent_source);
    end
    tmp = load(influent_source, 'ASM3_Influent');
    total_source_rows = size(tmp.ASM3_Influent, 1);
    num_tranches = floor((total_source_rows - start_row + 1) / tranche_len_rows);
    clear tmp;
    if num_tranches < 1
        error('run_campaign:NoTranches', ...
            'Source file has %d rows from start_row %d; need at least %d for one tranche.', ...
            total_source_rows, start_row, tranche_len_rows);
    end
    fprintf('  Source: %s (%d rows, %d full tranches from row %d)\\n', ...
        influent_source, total_source_rows, num_tranches, start_row);

OUTER LOOP BODY — for each tranche_idx:
    (a) Set influent_condition = tranche_idx.
    (b) Call dynamicInfluent_writer:
        tranche_info = dynamicInfluent_writer(influent_source, tranche_idx, ...
            tranche_len_rows, start_row, influent_target);
        source_start_day = tranche_info.source_start_day;
    (c) Delete workspace_steady_state_initial.mat (force SS re-run):
        Each tranche has different influent composition → different SS baseline.
    (d) Delete sim_state.mat (reset main_sim iter to 1).
    (e) Existing Section 2 logic: delete stale cycle_file, campaign_params.mat.
        Do NOT delete campaign_state.mat here — it's used for resume.
    (f) Save wrapper state to campaign_state.mat (existing Section 3):
        Now also persists: tranche_idx, num_tranches, source_start_day,
        tranche_len_days, influent_source, influent_target, start_row,
        tranche_len_rows, tranche_start_day.
    (g) Save campaign_params.mat with reduction_days AND sim_days:
        sim_days = tranche_len_days;
        save('campaign_params.mat', 'reduction_days', 'sim_days');
    (h) Run main_sim (existing Section 4).
    (i) Restore wrapper state from campaign_state.mat (existing Section 5).
    (j) Accumulate results (existing Section 6):
        Add TWO new columns before existing data:
          InfluentCondition    = tranche_idx (integer)
          InfluentSourceStartDay = source_start_day (double, original time)
        Use addvars with 'Before', 1.

RESUME LOGIC FOR OUTER LOOP:
    Before the for loop, check if campaign_state.mat exists AND contains
    tranche_idx.  If so, load it and set the loop start:
        resume_tranche = 1;
        if isfile('campaign_state.mat')
            cs = load('campaign_state.mat');
            if isfield(cs, 'tranche_idx')
                resume_tranche = cs.tranche_idx;
                fprintf('  Resuming from tranche %d\\n', resume_tranche);
            end
            clear cs;
        end
        for tranche_idx = resume_tranche:num_tranches
    The inner main_sim resume (sim_state.mat) handles mid-experiment crashes.

CLEANUP (Section 7):
    Add to the cleanup list:
    - workspace_steady_state_initial.mat
    - sim_state.mat
    These are now created per-tranche and should be cleaned post-campaign.

BACKWARD COMPATIBILITY:
    When DYNINFLUENT_ASM3.mat is absent, error with a clear message.
    The old single-pass path is preserved in git history.

CONSOLE OUTPUT:
    Print tranche progress at the start of each iteration:
        fprintf('\\n=== Tranche %d/%d (source day %.2f) ===\\n', ...
            tranche_idx, num_tranches, source_start_day);
    Update the campaign summary at the end to show num_tranches.

ACTION REQUIRED:
- Read the existing run_campaign.m with the Read tool.
- Add the new parameters and tranche count logic to Section 1.
- Wrap Sections 2–6 in the outer tranche loop.
- Add resume logic before the loop.
- Update campaign_state.mat save/load with new variables.
- Update Section 6 to add InfluentCondition and InfluentSourceStartDay.
- Update Section 7 cleanup list.
- Update the summary fprintf at the end.""",
        acceptance_criteria=[
            "New parameters defined: influent_source, influent_target, tranche_start_day, tranche_len_days",
            "Derived parameters computed: steps_per_day, tranche_len_rows, start_row",
            "Source file validated: errors if DYNINFLUENT_ASM3.mat is absent",
            "Tranche count computed via floor((total_rows - start_row + 1) / tranche_len_rows)",
            "Errors if num_tranches < 1 with descriptive message",
            "Outer for loop: for tranche_idx = resume_tranche:num_tranches",
            "dynamicInfluent_writer called with correct 5 arguments per tranche",
            "workspace_steady_state_initial.mat deleted before each tranche",
            "sim_state.mat deleted before each tranche",
            "campaign_params.mat includes sim_days = tranche_len_days",
            "campaign_state.mat includes tranche_idx, num_tranches, source_start_day, and all new params",
            "Resume logic: loads tranche_idx from campaign_state.mat if present",
            "Master CSV has InfluentCondition column (= tranche_idx)",
            "Master CSV has InfluentSourceStartDay column (= source_start_day)",
            "Both new columns prepended before existing columns via addvars",
            "readtable used (not readmatrix) for CSV with string columns",
            "Cleanup list includes workspace_steady_state_initial.mat and sim_state.mat",
            "Console output shows tranche progress and source day",
            "Campaign summary shows num_tranches completed",
            "File parses without MATLAB syntax errors",
        ],
        files_to_modify=["run_campaign.m"],
        reference_files=[
            "codebase/run_campaign.m",
            "codebase/main_sim.m",
            "codebase/dynamicInfluent_writer.m",
            "docs/refactoring_plan_v4.md",
        ],
        depends_on=["S01", "S02"],
        skip_phases=[SprintPhase.UNIT_TEST, SprintPhase.INTEGRATE],
    ),

    # ── S04: End-to-end structural validation ──────────────────────────
    Sprint(
        id="S04",
        title="End-to-end structural validation",
        objective="""\
Perform structural validation of all created and modified files against
the refactoring plan v4 acceptance criteria.

1. Verify all .m files parse without MATLAB syntax errors:
   - dynamicInfluent_writer.m (new)
   - main_sim.m (modified)
   - run_campaign.m (modified)

2. Run mlint on all source files and resolve or justify all warnings.

3. Run dynamicInfluent_writer unit tests:
   - Nominal single-tranche extraction
   - Multi-tranche sequential extraction (verify non-overlapping)
   - Time renormalization (starts at 0, correct increments)
   - Boundary validation (source file too short → clear error)
   - Column count validation (wrong number of columns → error)
   - Output variable name is DRYINFLUENT
   - Info struct has all required fields
   - start_row offset (tranche_start_day > 0)

4. Verify main_sim.m backward compatibility:
   - Without campaign_params.mat: sim_days = 14
   - With campaign_params.mat containing sim_days=7: sim_days = 7
   - sim_config.mat save includes sim_days

5. Verify run_campaign.m structural integrity:
   - Tranche count formula correct
   - All required variables in campaign_state.mat save
   - campaign_params.mat includes sim_days
   - Master CSV addvars call prepends both new columns
   - Cleanup list includes all transient files
   - Resume logic present and structurally sound

6. Verify cross-file consistency:
   - campaign_params.mat written by run_campaign with 'sim_days'
     matches load call in main_sim
   - dynamicInfluent_writer output variable name (DRYINFLUENT)
     matches what benchmarkinit expects to load
   - run_campaign deletes workspace_steady_state_initial.mat,
     which triggers main_sim's existing SS guard

7. Produce verification_report.md with PASS/FAIL table.

This sprint does NOT run full Simulink simulations.""",
        acceptance_criteria=[
            "All .m files parse without syntax errors",
            "mlint produces no unresolved warnings",
            "test_dynamicInfluent_writer passes all cases",
            "main_sim.m backward compatibility confirmed (sim_days=14 without campaign_params.mat)",
            "main_sim.m loads sim_days from campaign_params.mat when present",
            "run_campaign.m tranche count formula verified",
            "run_campaign.m campaign_state.mat includes all required variables",
            "run_campaign.m campaign_params.mat includes sim_days",
            "run_campaign.m master CSV has InfluentCondition and InfluentSourceStartDay columns",
            "run_campaign.m cleanup list includes workspace_steady_state_initial.mat and sim_state.mat",
            "Cross-file consistency: campaign_params.mat variable names match between writer and reader",
            "Cross-file consistency: DRYINFLUENT variable name matches benchmarkinit expectation",
            "Cross-file consistency: SS workspace deletion triggers main_sim SS guard",
            "verification_report.md produced with PASS/FAIL table",
        ],
        files_to_create=["verification_report.md"],
        reference_files=[
            "codebase/dynamicInfluent_writer.m",
            "codebase/main_sim.m",
            "codebase/run_campaign.m",
            "docs/refactoring_plan_v4.md",
        ],
        depends_on=["S03"],
        skip_phases=[SprintPhase.GENERATE],
    ),
]