"""
config/sprints.py
Sprint phase definitions and the sprint catalogue for an agentic development
project.

USAGE:
    1. Set DEFAULT_MODEL to your preferred LLM.
    2. Customise SprintPhase if your workflow has different stages.
    3. Populate the SPRINTS list with Sprint dataclasses describing each
       unit of work, its acceptance criteria, file manifest, and phase
       configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Model defaults (importable by orchestrator for fallback/override logic)
# ---------------------------------------------------------------------------
DEFAULT_MODEL = "claude-sonnet-4-20250514"


# ---------------------------------------------------------------------------
# Phase enum
# ---------------------------------------------------------------------------

class SprintPhase(Enum):
    """
    Phases within each sprint — executed sequentially by the orchestrator.

    Customise this enum to match your development workflow.  Common
    additions: DESIGN, REVIEW, DEPLOY, DOCS.
    """
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
    """
    One unit of development work, corresponding to a step in the project plan.

    Fields
    ------
    id : str
        Short unique identifier (e.g. "S01", "S02").
    title : str
        Human-readable name for the sprint.
    objective : str
        Detailed description of what the sprint must accomplish.  Include
        function signatures, algorithms, design notes, and any constraints.
    acceptance_criteria : list[str]
        Concrete, verifiable criteria.  Each item should be testable with
        a clear PASS/FAIL outcome.
    files_to_create : list[str]
        Paths (relative to project root) of new files this sprint produces.
    files_to_modify : list[str]
        Paths of existing files this sprint will edit.
    reference_files : list[str]
        Paths to files the agent should read for context before starting
        (e.g. existing source code, design docs, specs).
    test_cmd : Optional[str]
        Shell command to run the sprint's tests.  If None, the orchestrator
        uses a default test runner.
    depends_on : list[str]
        Sprint IDs that must complete before this one starts.
    model : str
        LLM model identifier to use for this sprint.
    max_turns_per_phase : dict[SprintPhase, int]
        Upper bound on agent turns for each phase.  Prevents runaway loops.
    retry_limit : int
        How many times a failed phase may be retried before aborting.
    skip_phases : list[SprintPhase]
        Phases to skip for this sprint (e.g. skip UNIT_TEST for a
        documentation-only sprint).
    """
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
#
# Populate this list with your project's sprints.  Each Sprint should have:
#   - A clear, self-contained objective with enough detail for an LLM agent
#     to implement it without further clarification.
#   - Acceptance criteria that are concrete and verifiable.
#   - A complete file manifest (files_to_create + files_to_modify).
#   - Reference files the agent needs for context.
#   - Dependency declarations so the orchestrator can sequence correctly.
#
# TIPS FOR WRITING GOOD SPRINT OBJECTIVES:
#   - Specify function/class signatures explicitly.
#   - State algorithms step-by-step, not just desired outcomes.
#   - Call out edge cases and error handling expectations.
#   - Reference existing code patterns the agent should follow.
#   - Note any backward-compatibility constraints.
#
# TIPS FOR WRITING GOOD ACCEPTANCE CRITERIA:
#   - Each criterion should be independently testable.
#   - Include positive cases (expected behavior) AND negative cases
#     (expected errors / rejections).
#   - Specify exact values, types, and formats where possible.
#   - Include backward-compatibility checks when modifying existing code.
#
# Example sprint structure (replace with your project's actual sprints):
# ---------------------------------------------------------------------------

SPRINTS: list[Sprint] = [
    # ── Example S01: New utility function ──────────────────────────────
    Sprint(
        id="S01",
        title="Example — data extraction utility",
        objective="""\
Create a new utility function that extracts and transforms data from
a source file.

FUNCTION SIGNATURE:
    def extract_records(source_path, batch_index, batch_size, start_offset=0,
                        target_path=None) -> dict:

ALGORITHM:
1. Load the source data file.
2. Compute the row range for the requested batch.
3. Validate the range does not exceed available data.
4. Extract the subset and normalize timestamps to start at 0.
5. Write the result to target_path (or return in-memory).
6. Return a metadata dict with source info, row range, and counts.

INPUT VALIDATION:
- Source file must exist and contain expected schema.
- batch_index >= 0, integer.
- batch_size >= 1, integer.
- Row range must not exceed source data bounds.

Include docstring, type hints, and follow project coding standards.""",
        acceptance_criteria=[
            "Function created with correct signature and type hints",
            "Default arguments match specification",
            "Loads and validates source data schema",
            "Row range calculation is correct for batch 0, 1, 2, ...",
            "Errors on out-of-bounds batch with descriptive message",
            "Timestamp normalization starts at exactly 0",
            "Output file written when target_path is provided",
            "Metadata dict contains all specified fields",
            "Consecutive batches are non-overlapping with no gaps",
            "Input validation rejects: missing file, wrong schema, negative index",
        ],
        files_to_create=["src/extract_records.py"],
        reference_files=["docs/data_format_spec.md"],
    ),

    # ── Example S02: Modify existing module ────────────────────────────
    Sprint(
        id="S02",
        title="Example — update pipeline to accept dynamic config",
        objective="""\
Modify the existing pipeline runner to load configuration from an
external config file when present, falling back to hardcoded defaults
for backward compatibility.

CHANGES:
1. At the top of run(), check for config.json in the working directory.
2. If present, load and merge with defaults (config values take priority).
3. Persist the resolved config to run_metadata.json for reproducibility.
4. All downstream logic uses the resolved config dict.

BACKWARD COMPATIBILITY:
- Without config.json, behavior is identical to the current version.
- Existing tests must continue to pass without modification.""",
        acceptance_criteria=[
            "Config loaded from config.json when present",
            "Falls back to hardcoded defaults when config.json absent",
            "Merged config written to run_metadata.json",
            "Existing unit tests pass without modification",
            "New config values propagate to downstream processing",
        ],
        files_to_modify=["src/pipeline.py"],
        reference_files=["src/pipeline.py", "tests/test_pipeline.py"],
        depends_on=["S01"],
    ),

    # ── Example S03: Integration / orchestration changes ───────────────
    Sprint(
        id="S03",
        title="Example — orchestrator outer loop",
        objective="""\
Refactor the orchestrator to add an outer loop that iterates over data
batches, running the full pipeline per batch and accumulating results.

CHANGES:
1. Compute batch count from source data size and batch_size parameter.
2. For each batch: extract data, reset pipeline state, run pipeline,
   collect results with batch metadata.
3. Add resume logic: persist loop index to state file, resume from last
   completed batch on restart.
4. Clean up transient files after all batches complete.

CONSOLE OUTPUT:
    Print batch progress at the start of each iteration.""",
        acceptance_criteria=[
            "Batch count computed correctly from source data",
            "Pipeline runs once per batch with correct data",
            "State reset between batches (no cross-contamination)",
            "Results include batch index and source metadata columns",
            "Resume logic reloads from persisted state file",
            "Transient files cleaned up after completion",
            "Console output shows batch progress",
        ],
        files_to_modify=["src/orchestrator.py"],
        reference_files=[
            "src/orchestrator.py",
            "src/pipeline.py",
            "src/extract_records.py",
        ],
        depends_on=["S01", "S02"],
        skip_phases=[SprintPhase.UNIT_TEST, SprintPhase.INTEGRATE],
    ),

    # ── Example S04: End-to-end validation ─────────────────────────────
    Sprint(
        id="S04",
        title="End-to-end structural validation",
        objective="""\
Validate all created and modified files against the project plan.

1. Verify all source files parse without syntax errors.
2. Run the linter on all source files and resolve or justify warnings.
3. Run unit tests for the new utility function.
4. Verify backward compatibility of the modified pipeline.
5. Verify cross-file consistency (shared config keys, variable names,
   file paths referenced across modules).
6. Produce verification_report.md with a PASS/FAIL table.""",
        acceptance_criteria=[
            "All source files parse without syntax errors",
            "Linter produces no unresolved warnings",
            "Unit tests pass for new utility function",
            "Pipeline backward compatibility confirmed",
            "Cross-file consistency verified for shared names and paths",
            "verification_report.md produced with PASS/FAIL table",
        ],
        files_to_create=["verification_report.md"],
        reference_files=[
            "src/extract_records.py",
            "src/pipeline.py",
            "src/orchestrator.py",
        ],
        depends_on=["S03"],
        skip_phases=[SprintPhase.GENERATE],
    ),
]