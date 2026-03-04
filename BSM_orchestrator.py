#!/usr/bin/env python3
"""
BSM Dynamic Aeration Experiment — Refactoring Orchestrator
===========================================================
Uses the Claude Agent SDK to drive an agentic developer through the 6-step
implementation plan for transitioning the BSM/ASM3 simulation codebase from
constant-KLa / constant-influent to dynamic-KLa / diurnal-influent.

Requirements:
    pip install claude-agent-sdk anyio
    export ANTHROPIC_API_KEY=sk-ant-...
    MATLAB R2023b+ on PATH  (for verification phases)

Usage:
    python bsm_orchestrator.py                   # run all sprints
    python bsm_orchestrator.py --sprint S02      # run a single sprint
    python bsm_orchestrator.py --resume S03      # resume from sprint S03
    python bsm_orchestrator.py --dry-run         # validate config, no agent calls
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Claude Agent SDK imports
# ---------------------------------------------------------------------------
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    create_sdk_mcp_server,
    query,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FMT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FMT)
log = logging.getLogger("bsm_orchestrator")


# ═══════════════════════════════════════════════════════════════════════════
# §1  CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

# Root directory where the MATLAB/ASM3 project lives
MATLAB_PROJECT_DIR = Path("./matlab_project")

# Working root for all sprint artifacts (agent sandboxes, checkpoints)
WORK_ROOT = Path("./orchestrator_work")

# Where external checkpoints are archived
CHECKPOINT_ROOT = WORK_ROOT / "checkpoints"

# Where final verified outputs are promoted
OUTPUT_ROOT = WORK_ROOT / "verified_outputs"

# Agent model configuration
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
FALLBACK_MODEL = "claude-sonnet-4-5-20250929"
HIGH_REASONING_MODEL = "claude-sonnet-4-5-20250929"  # or upgrade to opus for complex sprints

# Budget guardrails
MAX_BUDGET_PER_SPRINT = 5.0   # USD
MAX_BUDGET_PER_PHASE = 2.0    # USD


# ═══════════════════════════════════════════════════════════════════════════
# §2  PHASE & SPRINT DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════

class SprintPhase(Enum):
    """Phases within each sprint — executed sequentially."""
    PLAN       = "plan"
    GENERATE   = "generate"
    STATIC     = "static_analysis"
    UNIT_TEST  = "unit_test"
    INTEGRATE  = "integration_test"
    VERIFY     = "verify"
    PACKAGE    = "package"


@dataclass
class Sprint:
    """One unit of refactoring work, corresponding to a step in §9 of the plan."""
    id: str
    title: str
    objective: str
    acceptance_criteria: list[str]
    files_to_create: list[str] = field(default_factory=list)
    files_to_modify: list[str] = field(default_factory=list)
    files_read_only: list[str] = field(default_factory=list)
    matlab_test_cmd: Optional[str] = None          # MATLAB command for unit/integration tests
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
# Sprint catalogue — maps 1:1 to §9 Implementation Order of the plan
# ---------------------------------------------------------------------------

SPRINTS: list[Sprint] = [
    # ── Step 1 ──────────────────────────────────────────────────────────
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
        files_read_only=[],
        matlab_test_cmd="addpath('src'); results = runtests('tests/test_generate_KLa_timeseries.m'); disp(table(results)); exit(any([results.Failed]));",
    ),

    # ── Step 2 ──────────────────────────────────────────────────────────
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
        files_read_only=[],
        depends_on=["S01"],
        matlab_test_cmd="addpath('src'); results = runtests('tests/test_generate_test_cases.m'); disp(table(results)); exit(any([results.Failed]));",
    ),

    # ── Step 3 ──────────────────────────────────────────────────────────
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
        files_read_only=["src/generate_test_cases.m", "src/generate_KLa_timeseries.m"],
        depends_on=["S01", "S02"],
        skip_phases=[SprintPhase.UNIT_TEST],  # tested at integration level in S04
    ),

    # ── Step 4 ──────────────────────────────────────────────────────────
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
        files_read_only=[
            "src/generate_KLa_timeseries.m",
            "src/generate_test_cases.m",
            "effluent_data_writer.m",
        ],
        depends_on=["S03"],
        matlab_test_cmd=None,  # integration test requires full Simulink — deferred to S06
    ),

    # ── Step 5 ──────────────────────────────────────────────────────────
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
        files_read_only=["main_sim.m"],
        depends_on=["S04"],
        skip_phases=[SprintPhase.UNIT_TEST, SprintPhase.INTEGRATE],
    ),

    # ── Step 6 ──────────────────────────────────────────────────────────
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
        files_read_only=[
            "src/generate_KLa_timeseries.m",
            "src/generate_test_cases.m",
            "main_sim.m",
            "run_campaign.m",
        ],
        depends_on=["S05"],
        skip_phases=[SprintPhase.GENERATE],  # no new code — validation only
    ),
]


# ═══════════════════════════════════════════════════════════════════════════
# §3  SYSTEM PROMPTS
# ═══════════════════════════════════════════════════════════════════════════

# Base context injected into every phase prompt
BASE_CONTEXT = """\
You are a senior MATLAB/Simulink developer working on the BSM (Benchmark
Simulation Model) codebase for wastewater treatment plant modeling.  The
project uses ASM3 (Activated Sludge Model No. 3) kinetics.

KEY DOMAIN FACTS:
- benchmarkinit runs 'clear all' which wipes the workspace.  Any data that
  must survive across phases is persisted to .mat files on disk.
- The Simulink model reads KLa timeseries from workspace variables via
  'From Workspace' blocks configured for zero-order hold interpolation.
- DRYINFLUENT.mat contains 14 days of diurnal influent data at 15-min
  resolution (96 steps/day → 1344 data points).
- Nominal KLa values: Tank 3 = 240, Tank 4 = 240, Tank 5 = 114.
- The .mat persistence pattern (generate → save → workspace_wipe → load)
  is a proven pattern already used by sim_config.mat and sim_state.mat.

CODING STANDARDS:
- Every function file starts with a header block: function name, purpose,
  inputs (with types/units), outputs, author, date.
- Use meaningful variable names; no single-letter vars except loop indices.
- Preallocate arrays; avoid grow-in-loop patterns.
- All simulation parameters go in a params struct or named variables, not
  hardcoded magic numbers.
- Comment non-obvious logic inline.
"""

PHASE_PROMPTS: dict[SprintPhase, str] = {
    SprintPhase.PLAN: """\
You are in the PLANNING phase.  Read the sprint objective, acceptance
criteria, and any referenced files.  Produce a plan.md with:
- Approach summary
- File manifest (every file you will create or modify)
- Key variable names and their types
- Expected outputs and how they will be verified
- Potential risks or gotchas

Do NOT write any MATLAB code yet.  Plan only.""",

    SprintPhase.GENERATE: """\
You are in the CODE GENERATION phase.  Write production-quality MATLAB
code per the plan.  Follow the coding standards.  Write files ONLY
into the src/ or tests/ directories as appropriate.

For function files: include the standard header block.
For test files: use matlab.unittest framework with setup/teardown,
  nominal cases, edge cases, and error cases.

If modifying an existing file, read it first, understand the full
structure, then make targeted edits.  Do not rewrite sections you
are not changing.""",

    SprintPhase.STATIC: """\
You are in the STATIC ANALYSIS phase.  mlint results are provided below.
For each warning:
- If it is a real issue → fix it in the source file.
- If it is a false positive → add %#ok<RULE> suppression with a brief
  comment explaining why.
Iterate until all warnings are resolved or justified.""",

    SprintPhase.UNIT_TEST: """\
You are in the UNIT TEST phase.  Write comprehensive test classes using
MATLAB's matlab.unittest framework in the tests/ directory.

Each test class should:
- Test one source function
- Include setup/teardown for temp files and path management
- Have at minimum: a nominal case, edge cases, and an error case
- Use verifyEqual, verifyTrue, verifyError, verifySize as appropriate
- Print clear diagnostic messages on failure

After writing tests, they will be executed automatically.  If any fail,
you will see the results and should fix either the tests or the source.""",

    SprintPhase.INTEGRATE: """\
You are in the INTEGRATION TEST phase.  Review the test execution results
below.  If tests passed, confirm the results look correct.  If tests
failed, diagnose the root cause and fix the source code or test code.
Do not introduce new features — only fix what is broken.""",

    SprintPhase.VERIFY: """\
You are in the VERIFICATION phase.  Review all outputs from this sprint
against the acceptance criteria.  Produce verification_report.md with:

| # | Criterion | Expected | Actual | Status |
|---|-----------|----------|--------|--------|
| 1 | ...       | ...      | ...    | PASS/FAIL |

At the bottom, provide an overall verdict: ACCEPT / REVISE / REJECT.
Be rigorous — a FAIL on any criterion means REVISE.""",

    SprintPhase.PACKAGE: """\
You are in the PACKAGING phase.  Write a brief sprint_summary.md
documenting:
- What was implemented
- Files created or modified
- Any deviations from the plan
- Known limitations or future work items

Keep it concise — 1 page maximum.""",
}


# ═══════════════════════════════════════════════════════════════════════════
# §4  CUSTOM MATLAB TOOLS (in-process MCP)
# ═══════════════════════════════════════════════════════════════════════════

def _run_matlab_cmd(cmd: str, timeout: int = 120) -> dict[str, str]:
    """Helper: execute a MATLAB -batch command and return stdout/stderr/rc."""
    try:
        result = subprocess.run(
            ["matlab", "-batch", cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(MATLAB_PROJECT_DIR),
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": str(result.returncode),
        }
    except FileNotFoundError:
        return {
            "stdout": "",
            "stderr": "ERROR: 'matlab' not found on PATH. MATLAB is required for verification phases.",
            "returncode": "-1",
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"ERROR: MATLAB command timed out after {timeout}s",
            "returncode": "-2",
        }


def build_matlab_mcp_server():
    """Create an in-process MCP server with MATLAB-specific tools."""

    from claude_agent_sdk.tools import tool as sdk_tool

    @sdk_tool("run_mlint", "Run MATLAB mlint/checkcode static analysis on a .m file and return warnings")
    async def run_mlint(file_path: str) -> str:
        cmd = f"msgs = checkcode('{file_path}', '-string'); if isempty(msgs), disp('CLEAN: No warnings.'); else, disp(msgs); end"
        result = _run_matlab_cmd(cmd)
        return f"STDOUT:\n{result['stdout']}\nSTDERR:\n{result['stderr']}\nReturn code: {result['returncode']}"

    @sdk_tool("run_matlab_tests", "Execute MATLAB unit tests in a directory and return results")
    async def run_matlab_tests(test_path: str, source_path: str = "src") -> str:
        cmd = (
            f"addpath('{source_path}'); "
            f"results = runtests('{test_path}'); "
            f"disp(table(results)); "
            f"if any([results.Failed]), exit(1); end"
        )
        result = _run_matlab_cmd(cmd, timeout=300)
        return f"STDOUT:\n{result['stdout']}\nSTDERR:\n{result['stderr']}\nReturn code: {result['returncode']}"

    @sdk_tool("matlab_syntax_check", "Check if a .m file parses without syntax errors")
    async def matlab_syntax_check(file_path: str) -> str:
        cmd = (
            f"try, "
            f"  pcode('{file_path}', '-inplace'); "
            f"  delete(strrep('{file_path}', '.m', '.p')); "
            f"  disp('SYNTAX OK'); "
            f"catch e, "
            f"  fprintf('SYNTAX ERROR: %s\\n', e.message); "
            f"  exit(1); "
            f"end"
        )
        result = _run_matlab_cmd(cmd, timeout=60)
        return f"STDOUT:\n{result['stdout']}\nSTDERR:\n{result['stderr']}\nReturn code: {result['returncode']}"

    @sdk_tool("read_mat_summary", "Read a .mat file and return variable names, sizes, and types")
    async def read_mat_summary(mat_path: str) -> str:
        cmd = (
            f"s = whos('-file', '{mat_path}'); "
            f"for i = 1:numel(s), "
            f"  fprintf('%s: size=%s class=%s\\n', s(i).name, mat2str(s(i).size), s(i).class); "
            f"end"
        )
        result = _run_matlab_cmd(cmd, timeout=60)
        return f"STDOUT:\n{result['stdout']}\nSTDERR:\n{result['stderr']}"

    server = create_sdk_mcp_server(
        name="matlab-tools",
        tools=[run_mlint, run_matlab_tests, matlab_syntax_check, read_mat_summary],
    )
    return server


# ═══════════════════════════════════════════════════════════════════════════
# §5  HOOKS — SANDBOXING & OBSERVABILITY
# ═══════════════════════════════════════════════════════════════════════════

class SprintMetrics:
    """Accumulates tool-use metrics and timing for a sprint."""

    def __init__(self, sprint_id: str):
        self.sprint_id = sprint_id
        self.tool_calls: list[dict] = []
        self.phase_timings: dict[str, float] = {}
        self.start_time = time.time()

    def record_tool_call(self, tool_name: str, tool_use_id: str | None):
        self.tool_calls.append({
            "tool": tool_name,
            "tool_use_id": tool_use_id,
            "elapsed_s": time.time() - self.start_time,
        })

    def to_dict(self) -> dict:
        return {
            "sprint_id": self.sprint_id,
            "total_elapsed_s": time.time() - self.start_time,
            "total_tool_calls": len(self.tool_calls),
            "phase_timings": self.phase_timings,
            "tool_calls": self.tool_calls,
        }


def build_hooks(sprint_dir: Path, metrics: SprintMetrics) -> dict:
    """Build hook configuration for sandbox enforcement and observability."""

    allowed_root = str(sprint_dir.resolve())

    async def enforce_sandbox(input_data, tool_use_id, context):
        tool = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})

        # Block writes outside sprint directory
        if tool in ("Write", "Edit", "MultiEdit"):
            file_path = tool_input.get("file_path", "")
            resolved = str(Path(file_path).resolve()) if file_path else ""
            if resolved and not resolved.startswith(allowed_root):
                log.warning(f"SANDBOX DENY: Write to {file_path} outside {allowed_root}")
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason":
                            f"Write blocked: {file_path} is outside sprint sandbox {allowed_root}",
                    }
                }

        # Block dangerous bash patterns
        if tool == "Bash":
            cmd = tool_input.get("command", "")
            blocked_patterns = [
                "rm -rf /", "rm -rf ~", "sudo ", "chmod 777",
                "pip install", "npm install",
                "curl ", "wget ", "ssh ",
                "> /dev/sd",  # disk writes
            ]
            for pattern in blocked_patterns:
                if pattern in cmd:
                    log.warning(f"SANDBOX DENY: Bash command contains '{pattern}'")
                    return {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason":
                                f"Bash blocked: contains forbidden pattern '{pattern}'",
                        }
                    }
        return {}

    async def log_tool_use(input_data, tool_use_id, context):
        tool_name = input_data.get("tool_name", "unknown")
        metrics.record_tool_call(tool_name, tool_use_id)
        return {}

    return {
        "PreToolUse": [
            HookMatcher(matcher="Write|Edit|MultiEdit", hooks=[enforce_sandbox]),
            HookMatcher(matcher="Bash", hooks=[enforce_sandbox]),
        ],
        "PostToolUse": [
            HookMatcher(matcher=None, hooks=[log_tool_use]),
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# §6  CHECKPOINTING
# ═══════════════════════════════════════════════════════════════════════════

def save_external_checkpoint(sprint: Sprint, phase: SprintPhase, sprint_dir: Path) -> Path:
    """Archive the sprint working directory as an external checkpoint."""
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    ckpt_dir = CHECKPOINT_ROOT / sprint.id / f"{phase.value}_{ts}"
    ckpt_dir.parent.mkdir(parents=True, exist_ok=True)

    if sprint_dir.exists():
        shutil.copytree(sprint_dir, ckpt_dir, dirs_exist_ok=True)

    meta = {
        "sprint_id": sprint.id,
        "sprint_title": sprint.title,
        "phase": phase.value,
        "timestamp": ts,
        "acceptance_criteria": sprint.acceptance_criteria,
    }
    (ckpt_dir / "checkpoint_meta.json").write_text(json.dumps(meta, indent=2))
    log.info(f"  Checkpoint saved: {ckpt_dir}")
    return ckpt_dir


def promote_to_output(sprint: Sprint, sprint_dir: Path):
    """Copy verified sprint outputs to the final output directory."""
    dest = OUTPUT_ROOT / sprint.id
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(sprint_dir, dest)
    log.info(f"  Promoted outputs: {dest}")


# ═══════════════════════════════════════════════════════════════════════════
# §7  PROMPT COMPOSITION
# ═══════════════════════════════════════════════════════════════════════════

def compose_prompt(
    sprint: Sprint,
    phase: SprintPhase,
    attempt: int,
    error_context: str = "",
    prior_output: str = "",
) -> str:
    """Assemble the full user prompt for a given sprint + phase + attempt."""

    parts = [
        f"# Sprint {sprint.id}: {sprint.title}",
        f"## Objective\n{sprint.objective}",
        "## Acceptance Criteria",
        *[f"- {c}" for c in sprint.acceptance_criteria],
        f"\n## Current Phase: {phase.value} (attempt {attempt}/{sprint.retry_limit})",
    ]

    if sprint.files_to_create:
        parts.append(f"\n## Files to Create\n" + "\n".join(f"- `{f}`" for f in sprint.files_to_create))
    if sprint.files_to_modify:
        parts.append(f"\n## Files to Modify\n" + "\n".join(f"- `{f}`" for f in sprint.files_to_modify))
    if sprint.files_read_only:
        parts.append(f"\n## Reference Files (read-only)\n" + "\n".join(f"- `{f}`" for f in sprint.files_read_only))

    if attempt > 1 and error_context:
        parts.append(f"\n## ⚠ Previous Attempt Failed\nError details:\n```\n{error_context}\n```")
        parts.append("Fix the issues identified above.  Do not repeat the same mistakes.")

    if prior_output and phase in (SprintPhase.VERIFY, SprintPhase.INTEGRATE):
        parts.append(f"\n## Prior Phase Output\n```\n{prior_output[:4000]}\n```")

    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# §8  VERIFICATION ROUTINES
# ═══════════════════════════════════════════════════════════════════════════

async def run_static_analysis(sprint_dir: Path) -> tuple[bool, str]:
    """Run mlint on all .m files in the sprint directory."""
    m_files = list(sprint_dir.rglob("*.m"))
    if not m_files:
        return False, "No .m files found for static analysis"

    all_output = []
    all_clean = True

    for mf in m_files:
        rel = mf.relative_to(sprint_dir)
        result = _run_matlab_cmd(
            f"msgs = checkcode('{mf}', '-string'); if isempty(msgs), disp('CLEAN'); else, disp(msgs); end"
        )
        stdout = result["stdout"].strip()
        if stdout and "CLEAN" not in stdout:
            all_clean = False
            all_output.append(f"--- {rel} ---\n{stdout}")
        else:
            all_output.append(f"--- {rel} --- CLEAN")

    return all_clean, "\n".join(all_output)


async def run_matlab_tests(sprint: Sprint, sprint_dir: Path) -> tuple[bool, str]:
    """Execute the sprint's MATLAB test command."""
    if not sprint.matlab_test_cmd:
        log.info("  No MATLAB test command defined — skipping")
        return True, "No tests defined"

    result = _run_matlab_cmd(
        f"cd('{sprint_dir}'); {sprint.matlab_test_cmd}",
        timeout=300,
    )
    passed = result["returncode"] == "0"
    output = f"STDOUT:\n{result['stdout']}\nSTDERR:\n{result['stderr']}\nReturn code: {result['returncode']}"
    return passed, output


# ═══════════════════════════════════════════════════════════════════════════
# §9  PHASE EXECUTOR
# ═══════════════════════════════════════════════════════════════════════════

async def execute_phase(
    sprint: Sprint,
    phase: SprintPhase,
    sprint_dir: Path,
    attempt: int,
    metrics: SprintMetrics,
    error_context: str = "",
    prior_output: str = "",
) -> tuple[bool, str]:
    """
    Execute a single phase of a sprint.
    Returns (success: bool, output_or_error: str).
    """
    log.info(f"  Phase {phase.value} — attempt {attempt}")
    phase_start = time.time()

    # ── Save checkpoint before the phase ──
    save_external_checkpoint(sprint, phase, sprint_dir)

    # ── Build agent options ──
    system_prompt = BASE_CONTEXT + "\n\n" + PHASE_PROMPTS.get(phase, "")

    matlab_server = build_matlab_mcp_server()

    options = ClaudeAgentOptions(
        model=sprint.model,
        fallback_model=FALLBACK_MODEL,
        system_prompt=system_prompt,
        max_turns=sprint.max_turns_per_phase.get(phase, 15),
        max_budget_usd=MAX_BUDGET_PER_PHASE,
        cwd=str(sprint_dir),
        allowed_tools=["Read", "Write", "Edit", "MultiEdit", "Bash", "Glob"],
        permission_mode="acceptEdits",
        enable_file_checkpointing=True,
        extra_args={"replay-user-messages": None},
        mcp_servers={"matlab-tools": matlab_server},
        hooks=build_hooks(sprint_dir, metrics),
        effort="high",
    )

    # ── Compose the prompt ──
    prompt = compose_prompt(sprint, phase, attempt, error_context, prior_output)

    # ── Run the agent session ──
    agent_text_output: list[str] = []
    checkpoint_uuids: list[str] = []

    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)
            async for msg in client.receive_response():
                if isinstance(msg, UserMessage) and msg.uuid:
                    checkpoint_uuids.append(msg.uuid)
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            agent_text_output.append(block.text)
                        elif isinstance(block, ToolUseBlock):
                            log.debug(f"    Tool call: {block.name}")
                        elif isinstance(block, ToolResultBlock):
                            log.debug(f"    Tool result received")
    except Exception as e:
        log.error(f"  Agent session error: {e}")
        metrics.phase_timings[phase.value] = time.time() - phase_start
        return False, f"Agent session error: {e}"

    full_output = "\n".join(agent_text_output)
    metrics.phase_timings[phase.value] = time.time() - phase_start

    # ── Phase-specific post-processing and verification ──
    if phase == SprintPhase.STATIC:
        success, analysis = await run_static_analysis(sprint_dir)
        if not success:
            return False, analysis
        return True, analysis

    elif phase == SprintPhase.UNIT_TEST:
        success, test_output = await run_matlab_tests(sprint, sprint_dir)
        if not success:
            return False, test_output
        return True, test_output

    elif phase == SprintPhase.INTEGRATE:
        success, test_output = await run_matlab_tests(sprint, sprint_dir)
        if not success:
            return False, test_output
        return True, test_output

    elif phase == SprintPhase.VERIFY:
        # Check the agent's verdict
        if "ACCEPT" in full_output:
            return True, full_output
        elif "REJECT" in full_output or "REVISE" in full_output:
            return False, full_output
        else:
            log.warning("  Verification phase did not produce a clear verdict")
            return True, full_output  # assume pass if no explicit rejection

    else:
        # PLAN, GENERATE, PACKAGE — succeed if agent completes without error
        return True, full_output


# ═══════════════════════════════════════════════════════════════════════════
# §10  SPRINT EXECUTOR
# ═══════════════════════════════════════════════════════════════════════════

async def run_sprint(sprint: Sprint) -> bool:
    """Execute all phases of a sprint with retry logic."""
    log.info(f"{'='*60}")
    log.info(f"SPRINT {sprint.id}: {sprint.title}")
    log.info(f"{'='*60}")

    # ── Prepare sprint working directory ──
    sprint_dir = WORK_ROOT / "sprints" / sprint.id
    sprint_dir.mkdir(parents=True, exist_ok=True)
    (sprint_dir / "src").mkdir(exist_ok=True)
    (sprint_dir / "tests").mkdir(exist_ok=True)
    (sprint_dir / "data").mkdir(exist_ok=True)

    # ── Copy read-only reference files into sprint dir ──
    for ref_file in sprint.files_read_only:
        src = MATLAB_PROJECT_DIR / ref_file
        dst = sprint_dir / ref_file
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            log.info(f"  Copied reference: {ref_file}")

    # ── Copy files-to-modify into sprint dir (if they exist in project) ──
    for mod_file in sprint.files_to_modify:
        src = MATLAB_PROJECT_DIR / mod_file
        dst = sprint_dir / mod_file
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            log.info(f"  Copied for modification: {mod_file}")

    # ── Copy outputs from dependency sprints ──
    for dep_id in sprint.depends_on:
        dep_output = OUTPUT_ROOT / dep_id
        if dep_output.exists():
            # Copy src/ and tests/ from dependency
            for subdir in ["src", "tests"]:
                dep_sub = dep_output / subdir
                if dep_sub.exists():
                    for f in dep_sub.iterdir():
                        dst = sprint_dir / subdir / f.name
                        if not dst.exists():
                            shutil.copy2(f, dst)
                            log.info(f"  Inherited from {dep_id}: {subdir}/{f.name}")

    metrics = SprintMetrics(sprint.id)

    # ── Phase execution loop ──
    phase_order = [
        SprintPhase.PLAN,
        SprintPhase.GENERATE,
        SprintPhase.STATIC,
        SprintPhase.UNIT_TEST,
        SprintPhase.INTEGRATE,
        SprintPhase.VERIFY,
        SprintPhase.PACKAGE,
    ]

    last_output = ""

    for phase in phase_order:
        if phase in sprint.skip_phases:
            log.info(f"  Skipping phase: {phase.value}")
            continue

        success = False
        error_context = ""

        for attempt in range(1, sprint.retry_limit + 1):
            success, output = await execute_phase(
                sprint=sprint,
                phase=phase,
                sprint_dir=sprint_dir,
                attempt=attempt,
                metrics=metrics,
                error_context=error_context,
                prior_output=last_output,
            )

            if success:
                log.info(f"  ✓ Phase {phase.value} PASSED")
                last_output = output
                break
            else:
                log.warning(f"  ✗ Phase {phase.value} FAILED (attempt {attempt}/{sprint.retry_limit})")
                error_context = output
                if attempt < sprint.retry_limit:
                    log.info(f"  Retrying phase {phase.value}...")

        if not success:
            log.error(f"  SPRINT {sprint.id} FAILED at phase {phase.value} after {sprint.retry_limit} attempts")

            # Save failure metrics
            metrics_path = sprint_dir / "data" / "sprint_metrics.json"
            metrics_path.write_text(json.dumps(metrics.to_dict(), indent=2))

            return False

    # ── Sprint completed successfully ──
    metrics_path = sprint_dir / "data" / "sprint_metrics.json"
    metrics_path.write_text(json.dumps(metrics.to_dict(), indent=2))
    promote_to_output(sprint, sprint_dir)

    log.info(f"  ✓ SPRINT {sprint.id} COMPLETED")
    log.info(f"  Total tool calls: {len(metrics.tool_calls)}")
    log.info(f"  Total elapsed: {time.time() - metrics.start_time:.1f}s")

    return True


# ═══════════════════════════════════════════════════════════════════════════
# §11  CAMPAIGN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════

async def run_campaign(
    sprints: list[Sprint],
    start_from: str | None = None,
    single_sprint: str | None = None,
    dry_run: bool = False,
):
    """Execute a sequence of sprints with dependency resolution."""

    # ── Ensure working directories exist ──
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    # ── Filter sprints if requested ──
    if single_sprint:
        sprints = [s for s in sprints if s.id == single_sprint]
        if not sprints:
            log.error(f"Sprint '{single_sprint}' not found")
            return

    if start_from:
        ids = [s.id for s in sprints]
        if start_from not in ids:
            log.error(f"Sprint '{start_from}' not found for resume")
            return
        idx = ids.index(start_from)
        sprints = sprints[idx:]
        log.info(f"Resuming from sprint {start_from}")

    # ── Validate dependencies ──
    completed_ids: set[str] = set()
    for s in SPRINTS:
        if (OUTPUT_ROOT / s.id).exists():
            completed_ids.add(s.id)

    log.info(f"Previously completed sprints: {completed_ids or 'none'}")

    # ── Dry run ──
    if dry_run:
        log.info("DRY RUN — validating sprint configuration:")
        for s in sprints:
            missing_deps = [d for d in s.depends_on if d not in completed_ids]
            status = "READY" if not missing_deps else f"BLOCKED (needs: {missing_deps})"
            log.info(f"  {s.id}: {s.title} — {status}")
            log.info(f"    Phases: {[p.value for p in SprintPhase if p not in s.skip_phases]}")
            log.info(f"    Create: {s.files_to_create}")
            log.info(f"    Modify: {s.files_to_modify}")
        return

    # ── Execute sprints ──
    campaign_start = time.time()
    results: dict[str, bool] = {}

    for sprint in sprints:
        # Check dependencies
        missing = [d for d in sprint.depends_on if d not in completed_ids]
        if missing:
            log.error(f"Sprint {sprint.id} blocked — missing dependencies: {missing}")
            results[sprint.id] = False
            break

        success = await run_sprint(sprint)
        results[sprint.id] = success

        if success:
            completed_ids.add(sprint.id)
        else:
            log.error(f"Campaign halted at sprint {sprint.id}")
            break

    # ── Summary ──
    elapsed = time.time() - campaign_start
    log.info(f"\n{'='*60}")
    log.info(f"CAMPAIGN SUMMARY")
    log.info(f"{'='*60}")
    for sid, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        log.info(f"  {sid}: {status}")
    log.info(f"Total elapsed: {elapsed:.1f}s")

    # Save campaign summary
    summary = {
        "timestamp": datetime.now().isoformat(),
        "results": {k: ("PASS" if v else "FAIL") for k, v in results.items()},
        "elapsed_seconds": elapsed,
    }
    summary_path = WORK_ROOT / "campaign_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    log.info(f"Campaign summary: {summary_path}")


# ═══════════════════════════════════════════════════════════════════════════
# §12  CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="BSM Dynamic Aeration Refactoring Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python bsm_orchestrator.py                     Run all 6 sprints
  python bsm_orchestrator.py --sprint S01        Run only sprint S01
  python bsm_orchestrator.py --resume S03        Resume from sprint S03
  python bsm_orchestrator.py --dry-run           Validate config
  python bsm_orchestrator.py --list              List all sprints
  python bsm_orchestrator.py --project-dir /path Set MATLAB project dir
""",
    )
    parser.add_argument("--sprint", type=str, help="Run a single sprint by ID")
    parser.add_argument("--resume", type=str, help="Resume from a specific sprint")
    parser.add_argument("--dry-run", action="store_true", help="Validate config without running")
    parser.add_argument("--list", action="store_true", help="List all sprints and exit")
    parser.add_argument("--project-dir", type=str, help="Path to MATLAB project directory")
    parser.add_argument("--work-dir", type=str, help="Path to orchestrator working directory")
    parser.add_argument("--model", type=str, help="Override model for all sprints")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Override globals if CLI args provided
    global MATLAB_PROJECT_DIR, WORK_ROOT, CHECKPOINT_ROOT, OUTPUT_ROOT
    if args.project_dir:
        MATLAB_PROJECT_DIR = Path(args.project_dir)
    if args.work_dir:
        WORK_ROOT = Path(args.work_dir)
        CHECKPOINT_ROOT = WORK_ROOT / "checkpoints"
        OUTPUT_ROOT = WORK_ROOT / "verified_outputs"

    if args.model:
        for s in SPRINTS:
            s.model = args.model

    # List mode
    if args.list:
        print(f"\n{'ID':<6} {'Title':<50} {'Deps':<12} {'Skip'}")
        print("-" * 90)
        for s in SPRINTS:
            deps = ", ".join(s.depends_on) if s.depends_on else "—"
            skips = ", ".join(p.value for p in s.skip_phases) if s.skip_phases else "—"
            print(f"{s.id:<6} {s.title:<50} {deps:<12} {skips}")
        return

    # Validate project directory
    if not MATLAB_PROJECT_DIR.exists():
        log.warning(
            f"MATLAB project directory not found: {MATLAB_PROJECT_DIR}\n"
            f"Use --project-dir to set the path, or create the directory.\n"
            f"The orchestrator will still run (agent writes to sandbox) but "
            f"reference file copying and MATLAB verification will be limited."
        )

    log.info(f"MATLAB project: {MATLAB_PROJECT_DIR.resolve()}")
    log.info(f"Working root:   {WORK_ROOT.resolve()}")
    log.info(f"Sprints:        {len(SPRINTS)}")

    # Run
    asyncio.run(
        run_campaign(
            sprints=SPRINTS,
            single_sprint=args.sprint,
            start_from=args.resume,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()