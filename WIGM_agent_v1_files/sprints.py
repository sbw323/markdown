"""
config/sprints.py
Sprint phase definitions and sprint catalogue for the LHS WIGM influent
library generation project.

Project: BSM ASM3 Influent Scenario Sampling via Latin Hypercube Design
Based on: Borobio-Castillo et al. (2024), Water Research 255, 121436
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


# ---------------------------------------------------------------------------
# Sprint catalogue
# ---------------------------------------------------------------------------

SPRINTS: list[Sprint] = [

    # ── S01: LHS Design Matrix Generation ──────────────────────────────
    Sprint(
        id="S01",
        title="LHS design matrix generation function",
        objective="""\
Create generate_influent_lhs.m — a pure MATLAB function that produces
an n x 10 Latin Hypercube Sampling design matrix in physical units for
the 10 WIGM influent variables.

FUNCTION SIGNATURE:
    function [X_physical, var_info] = generate_influent_lhs(n_samples, seed)

INPUTS:
    n_samples — (positive integer) Number of LHS samples. No default;
                required argument.
    seed      — (non-negative integer) RNG seed for reproducibility.
                No default; required argument.

OUTPUTS:
    X_physical — (n_samples x 10 double) Design matrix in physical units.
                 Column order matches the var_info.names ordering below.
    var_info   — (1x1 struct) Metadata with fields:
        .names         — 1x10 cell of MATLAB variable names:
                         {'PE', 'QperPE', 'aHpercent', 'Qpermm', 'LLrain',
                          'CODsol_gperPEperd', 'CODpart_gperPEperd',
                          'SNH_gperPEperd', 'TKN_gperPEperd', 'SI_cst'}
        .distributions — 1x10 cell: {'normal','normal','normal','normal',
                         'normal','uniform','uniform','uniform','uniform',
                         'uniform'}
        .params        — 1x10 cell of parameter vectors:
                         Normal: [mean, std]
                         Uniform: [lower_bound, upper_bound]
        .units         — 1x10 cell of unit strings:
                         {'x1000 PE', 'L/d per PE', '%',
                          'm3/mm rain', 'mm rain/d',
                          'g COD/(d PE)', 'g COD/(d PE)',
                          'g N/(d PE)', 'g N/(d PE)', 'g COD/m3'}

ALGORITHM:
1. Validate inputs:
   - n_samples must be a positive integer scalar.
   - seed must be a non-negative integer scalar.
2. Build the var_info struct with all 10 variable definitions hardcoded
   as named constants within the function.
3. Set RNG state: rng(seed, 'twister').
4. Generate unit hypercube:
   X_unit = lhsdesign(n_samples, 10, 'criterion', 'maximin', 'iterations', 100)
5. Transform columns 1-5 (Normal) via norminv:
   X_physical(:,j) = norminv(X_unit(:,j), mu(j), sigma(j))
   Parameters:
     Col 1 (PE):         mu=80,   sigma=8
     Col 2 (QperPE):     mu=150,  sigma=15
     Col 3 (aHpercent):  mu=75,   sigma=7.5
     Col 4 (Qpermm):     mu=1500, sigma=375
     Col 5 (LLrain):     mu=3.5,  sigma=0.875
6. Transform columns 6-10 (Uniform) via linear scaling:
   X_physical(:,j) = X_unit(:,j) * (UB(j) - LB(j)) + LB(j)
   Parameters:
     Col 6  (CODsol):  LB=19.31,  UB=21.241
     Col 7  (CODpart): LB=115.08, UB=126.588
     Col 8  (SNH):     LB=5.8565, UB=6.44215
     Col 9  (TKN):     LB=12.104, UB=13.3144
     Col 10 (SI_cst):  LB=30,     UB=50
7. Clip Normal columns to physical bounds:
   Col 1 (PE):         max(X, eps)    — must be positive
   Col 2 (QperPE):     max(X, eps)    — must be positive
   Col 3 (aHpercent):  clip to [0, 100]
   Col 4 (Qpermm):     max(X, eps)    — must be positive
   Col 5 (LLrain):     max(X, eps)    — must be positive
8. Return X_physical and var_info.

NO FILE I/O — this function returns data only. The caller saves it.

IMPORTANT: The var_info struct is consumed by apply_influent_sample.m
(Sprint S02). The .names field defines the column-to-variable mapping
that both functions must agree on.""",
        acceptance_criteria=[
            "Function file generate_influent_lhs.m created with correct signature",
            "MATLAB arguments block validates n_samples (positive integer) and seed (non-negative integer)",
            "var_info struct contains all 5 fields: names, distributions, params, units",
            "var_info.names has exactly 10 entries matching the specified MATLAB variable names",
            "var_info.params Normal entries are [mean, std] pairs matching specification",
            "var_info.params Uniform entries are [LB, UB] pairs matching specification",
            "lhsdesign called with criterion='maximin' and iterations=100",
            "RNG seeded with rng(seed, 'twister') before lhsdesign call",
            "Normal columns transformed via norminv with correct mu and sigma per column",
            "Uniform columns transformed via linear scaling with correct LB and UB per column",
            "Normal columns clipped: PE>0, QperPE>0, aHpercent in [0,100], Qpermm>0, LLrain>0",
            "Output X_physical has dimensions n_samples x 10",
            "Same seed produces identical output (reproducibility)",
            "Function performs no file I/O",
        ],
        files_to_create=["src/generate_influent_lhs.m"],
        reference_files=["influent_lhs_development_plan_v2.md"],
    ),

    # ── S02: Parameter Override Function ───────────────────────────────
    Sprint(
        id="S02",
        title="WIGM parameter override function",
        objective="""\
Create apply_influent_sample.m — a MATLAB function that overrides the
10 LHS-sampled WIGM variables and their dependents in the MATLAB base
workspace. This function is called AFTER ASM3_Influent_init.m has
populated the base workspace with defaults, and BEFORE sim() runs the
WIGM Simulink model.

FUNCTION SIGNATURE:
    function apply_influent_sample(sample_row, var_info)

INPUTS:
    sample_row — (1x10 double) One row of X_physical from
                 generate_influent_lhs. Column order matches
                 var_info.names.
    var_info   — (1x1 struct) The metadata struct returned by
                 generate_influent_lhs. Used to map column indices
                 to MATLAB variable names via var_info.names.

ALGORITHM:
1. Validate inputs:
   - sample_row must be a 1x10 double vector.
   - var_info must be a struct with field 'names' containing 10 entries.
2. Assign the 10 primary variables to the base workspace:
   For j = 1:10
       assignin('base', var_info.names{j}, sample_row(j))
3. Read factor1 and factor3 from the base workspace:
   factor1 = evalin('base', 'factor1')   — expected value 2.0
   factor3 = evalin('base', 'factor3')   — expected value 2.0
   These are set by ASM3_Influent_init.m. Read them rather than
   hardcoding to stay robust if the init file changes.
4. Read the sampled values into local variables for clarity:
   PE_val      = sample_row(1)
   QperPE_val  = sample_row(2)
   CODsol_val  = sample_row(6)
   CODpart_val = sample_row(7)
   SNH_val     = sample_row(8)
   TKN_val     = sample_row(9)
   SI_val      = sample_row(10)
5. Compute and assign all dependent variables to base workspace:

   % From PE and QperPE
   assignin('base', 'QHHsatmax', QperPE_val * 50)

   % From CODsol_gperPEperd and PE
   assignin('base', 'CODsol_HH_max', 20 * CODsol_val * PE_val)
   assignin('base', 'CODsol_HH_nv',  factor1 * 2 * CODsol_val * PE_val)

   % From CODpart_gperPEperd and PE
   assignin('base', 'CODpart_HH_max', 20 * CODpart_val * PE_val)
   assignin('base', 'CODpart_HH_nv',  factor1 * CODpart_val * PE_val)

   % From SNH_gperPEperd and PE
   assignin('base', 'SNH_HH_max', 20 * SNH_val * PE_val)
   assignin('base', 'SNH_HH_nv',  factor1 * 2 * SNH_val * PE_val)

   % From TKN_gperPEperd and PE
   assignin('base', 'TKN_HH_max', 20 * TKN_val * PE_val)
   assignin('base', 'TKN_HH_nv',  factor1 * 1.5 * TKN_val * PE_val)

   % From SI_cst
   assignin('base', 'SI_nv',  factor3 * SI_val)
   assignin('base', 'Si_in',  SI_val)
   assignin('base', 'SI_max', 100 * SI_val)

CRITICAL CONSTRAINTS:
- All workspace interaction via assignin('base',...) and evalin('base',...).
- Do NOT create variables in the function workspace that could shadow
  base workspace variables (e.g., do not name a local variable 'PE').
  Use suffixed names like PE_val, QperPE_val, etc.
- Do NOT modify any variables other than the 10 primaries and the
  listed dependents. Noise seeds, switch functions, ASM3 kinetics,
  fractionation parameters, industry loads, and temperature model
  parameters must remain at their init-file defaults.
- The function performs no file I/O and no Simulink interaction.""",
        acceptance_criteria=[
            "Function file apply_influent_sample.m created with correct signature",
            "Input validation: sample_row must be 1x10 double",
            "Input validation: var_info must be struct with 'names' field of length 10",
            "All 10 primary variables assigned to base workspace via assignin",
            "factor1 and factor3 read from base workspace via evalin (not hardcoded)",
            "QHHsatmax computed as QperPE * 50 and assigned to base",
            "CODsol_HH_max and CODsol_HH_nv computed with correct formulas and assigned",
            "CODpart_HH_max and CODpart_HH_nv computed with correct formulas and assigned",
            "SNH_HH_max and SNH_HH_nv computed with correct formulas and assigned",
            "TKN_HH_max and TKN_HH_nv computed with correct formulas and assigned",
            "SI_nv, Si_in, and SI_max computed from SI_cst and assigned to base",
            "No local variables shadow base workspace WIGM variable names",
            "Unrelated base workspace variables (noise seeds, switches, ASM3 kinetics) unchanged",
            "Function performs no file I/O and no Simulink interaction",
        ],
        files_to_create=["src/apply_influent_sample.m"],
        reference_files=[
            "src/generate_influent_lhs.m",
            "ASM3_Influent_init.m",
            "influent_lhs_development_plan_v2.md",
        ],
        depends_on=["S01"],
    ),

    # ── S03: Main Library Generation Wrapper ───────────────────────────
    Sprint(
        id="S03",
        title="Influent library generation wrapper",
        objective="""\
Create generate_influent_library.m — the main MATLAB function that
generates a complete library of LHS-sampled WIGM influent profiles.

FUNCTION SIGNATURE:
    function generate_influent_library(n_samples, seed, output_dir)

INPUTS:
    n_samples  — (positive integer) Number of LHS samples. Default: 200.
    seed       — (non-negative integer) RNG seed. Default: 42.
    output_dir — (char or string) Output directory path.
                 Default: 'influent_library'.

ALGORITHM:

1. CONFIGURATION
   wigm_model  = 'ASM3_Influentmodel';
   sim_days    = 728;
   init_script = 'ASM3_Influent_init';

   Apply defaults for missing/empty arguments:
     if nargin < 1 || isempty(n_samples), n_samples = 200; end
     if nargin < 2 || isempty(seed),      seed = 42;       end
     if nargin < 3 || isempty(output_dir), output_dir = 'influent_library'; end

   Validate inputs:
     n_samples: positive integer scalar
     seed: non-negative integer scalar
     output_dir: char or string, non-empty

2. LHS GENERATION
   [X_physical, var_info] = generate_influent_lhs(n_samples, seed);
   Create output_dir if it does not exist.
   Save config file:
     config_file = fullfile(output_dir, 'influent_library_config.mat');
     save(config_file, 'X_physical', 'var_info', 'n_samples', 'seed',
          'sim_days', 'wigm_model', 'init_script');
   fprintf: report n_samples, seed, output_dir.

3. RESUME LOGIC
   state_file = fullfile(output_dir, 'influent_gen_state.mat');
   If state_file exists:
     Load start_idx from it.
     fprintf: 'Resuming from sample %d', start_idx.
   Else:
     start_idx = 1;

4. INITIALIZE LOG FILE
   log_file = fullfile(output_dir, 'influent_library_log.csv');
   If log_file does not exist (fresh run):
     Write CSV header row:
       SampleIndex, PE, QperPE, aHpercent, Qpermm, LLrain,
       CODsol_gperPEperd, CODpart_gperPEperd, SNH_gperPEperd,
       TKN_gperPEperd, SI_cst, OutputRows, OutputCols, Timestamp

5. PER-SAMPLE LOOP: for i = start_idx : n_samples

   Wrap the loop body in try/catch for error resilience.

   5a. Populate base workspace with defaults
       evalin('base', sprintf('run(''%s'')', init_script));

   5b. Override LHS-sampled variables and dependents
       apply_influent_sample(X_physical(i, :), var_info);

   5c. Load and configure Simulink model
       evalin('base', sprintf('load_system(''%s'')', wigm_model));
       evalin('base', sprintf('set_param(''%s'', ''StopTime'', ''%d'')', ...
              wigm_model, sim_days));

   5d. Run simulation
       evalin('base', sprintf('sim(''%s'')', wigm_model));

   5e. Extract output from base workspace
       ASM3_Influent = evalin('base', 'ASM3_Influent');
       Validate dimensions: expect ~69888 rows x 16 columns.
       If column count ~= 16, issue a warning (do not error).

   5f. Save output file
       out_filename = sprintf('influent_%03d.mat', i);
       out_filepath = fullfile(output_dir, out_filename);
       save(out_filepath, 'ASM3_Influent');
       fprintf: report file saved, dimensions.

   5g. Append to log CSV
       Open log_file in append mode ('a').
       Write one row: i, all 10 sample values, size(ASM3_Influent,1),
       size(ASM3_Influent,2), datestr(now,'yyyy-mm-dd HH:MM:SS').
       Close file.

   5h. Checkpoint
       start_idx_next = i + 1;
       save(state_file, 'start_idx_next');
       Note: On resume, load start_idx_next and assign to start_idx.

   5i. Close Simulink model to free memory
       evalin('base', sprintf('bdclose(''%s'')', wigm_model));

   CATCH block:
       fprintf(2, ...): log sample index and error message.
       Append error info to an error log file:
         fullfile(output_dir, 'influent_library_errors.csv')
       Continue to next sample (do NOT halt).

6. CLEANUP
   Delete state_file if all samples completed successfully.
   fprintf: summary — n completed, output_dir, elapsed time.
   Use tic/toc at the top/bottom of the function for timing.

CONSOLE OUTPUT:
  - Print a header banner at start with n_samples, seed, output_dir.
  - Print progress per sample: 'Sample %d/%d ...'.
  - Print elapsed time at completion.

CRITICAL CONSTRAINTS:
- This is a FUNCTION, not a script. Loop variables live in function scope.
- All Simulink interaction (load_system, set_param, sim, bdclose) must
  happen in the base workspace via evalin('base', ...) because the
  model reads its parameters from the base workspace.
- The saved variable in each .mat file must be named ASM3_Influent.
- Output filenames use zero-padded 3-digit indices.
- Resume logic is mandatory — library generation may take hours.""",
        acceptance_criteria=[
            "Function file generate_influent_library.m created with correct signature",
            "Default arguments applied when inputs are missing or empty",
            "Input validation for n_samples, seed, and output_dir",
            "generate_influent_lhs called with correct arguments",
            "Config file saved to output_dir/influent_library_config.mat with all required variables",
            "Resume logic: state_file checked on startup, start_idx loaded if present",
            "Log CSV created with correct header on fresh run",
            "Per-sample loop: init script run in base workspace via evalin",
            "Per-sample loop: apply_influent_sample called with correct row and var_info",
            "Per-sample loop: Simulink model loaded, configured with StopTime=728, and simulated in base workspace",
            "Per-sample loop: ASM3_Influent extracted from base workspace and dimensions validated",
            "Per-sample loop: output saved as influent_NNN.mat with variable named ASM3_Influent",
            "Per-sample loop: log CSV appended with sample metadata per iteration",
            "Per-sample loop: checkpoint saved after each sample",
            "Per-sample loop: Simulink model closed after each sample",
            "Error handling: try/catch wraps loop body, errors logged, loop continues",
            "Cleanup: state_file deleted on successful completion",
            "Console output: header banner, per-sample progress, elapsed time summary",
        ],
        files_to_create=["src/generate_influent_library.m"],
        reference_files=[
            "src/generate_influent_lhs.m",
            "src/apply_influent_sample.m",
            "ASM3_Influent_init.m",
            "influent_lhs_development_plan_v2.md",
        ],
        depends_on=["S01", "S02"],
        # Skip unit test and integration test — this function requires
        # the Simulink model and full WIGM environment. Validation is
        # performed in Sprint S04 on the VM.
        skip_phases=[SprintPhase.UNIT_TEST, SprintPhase.INTEGRATE],
    ),

    # ── S04: Structural Validation ─────────────────────────────────────
    Sprint(
        id="S04",
        title="Structural validation of all deliverables",
        objective="""\
Validate all created files against the development plan specification.
This sprint does NOT run the Simulink model — it performs structural
and consistency checks on the code.

CHECKS:
1. Verify all three .m files parse without MATLAB syntax errors.
2. Verify function signatures match specification exactly:
   - generate_influent_lhs(n_samples, seed)
   - apply_influent_sample(sample_row, var_info)
   - generate_influent_library(n_samples, seed, output_dir)
3. Verify var_info struct definition in generate_influent_lhs.m:
   - .names has 10 entries matching specified MATLAB variable names
   - .distributions has 10 entries ('normal' or 'uniform')
   - .params has 10 entries with correct [mean,std] or [LB,UB] values
   - .units has 10 entries with correct unit strings
4. Verify LHS distribution parameters match the development plan:
   - Normal: PE(80,8), QperPE(150,15), aHpercent(75,7.5),
     Qpermm(1500,375), LLrain(3.5,0.875)
   - Uniform: CODsol(19.31,21.241), CODpart(115.08,126.588),
     SNH(5.8565,6.44215), TKN(12.104,13.3144), SI_cst(30,50)
5. Verify apply_influent_sample.m dependent variable formulas:
   - Cross-reference each formula against ASM3_Influent_init.m
   - Confirm factor1 and factor3 are read via evalin, not hardcoded
6. Verify generate_influent_library.m:
   - sim_days = 728
   - Output filename pattern: influent_%03d.mat
   - Saved variable named ASM3_Influent
   - Resume logic present (state_file load/save)
   - Error handling (try/catch in loop)
7. Verify cross-file consistency:
   - var_info.names used identically in generate_influent_lhs.m and
     apply_influent_sample.m
   - Column indices (1-10) referenced consistently
8. Produce verification_report.md with PASS/FAIL table.""",
        acceptance_criteria=[
            "All three .m files parse without syntax errors",
            "Function signatures match specification exactly",
            "var_info struct contains correct variable names, distributions, params, and units",
            "LHS distribution parameters match development plan values",
            "Dependent variable formulas in apply_influent_sample match ASM3_Influent_init.m",
            "factor1 and factor3 read from base workspace (not hardcoded)",
            "generate_influent_library uses sim_days=728, correct filename pattern, correct variable name",
            "Resume logic and error handling present in generate_influent_library",
            "Cross-file consistency: var_info.names used identically across files",
            "verification_report.md produced with PASS/FAIL table and overall verdict",
        ],
        files_to_create=["verification_report.md"],
        reference_files=[
            "src/generate_influent_lhs.m",
            "src/apply_influent_sample.m",
            "src/generate_influent_library.m",
            "ASM3_Influent_init.m",
            "influent_lhs_development_plan_v2.md",
        ],
        depends_on=["S03"],
        skip_phases=[SprintPhase.GENERATE],
    ),
]
