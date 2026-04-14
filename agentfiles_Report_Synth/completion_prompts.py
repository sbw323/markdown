"""
Programmer-agent prompt builders for Report Synthesizer completion sprints.

Source of truth:
  - Governing v4 design specification (report_synthesizer_v4.md)
  - Completion sprint registry in completion_sprints.py
  - Report_Synth_Completion_Plan.md (integration gap analysis)

These prompts operate on an EXISTING, COMPONENT-TESTED codebase. Every
prompt opens with a codebase awareness block that tells the programmer
agent what already exists, what has been tested, and what must NOT be
re-implemented. This is the critical difference from the original
prompts.py which instructed a greenfield build.

Prompt construction is traceability-driven and sprint-scoped: every
prompt is composed from shared blocks plus sprint-specific narrative
that maps to FR/NFR IDs, spec sections, and artifacts declared in
completion_sprints.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from completion_sprints import (
    SprintDefinition,
    COMPLETION_SPRINTS_BY_ID,
    list_sprint_ids,
    get_sprint,
    get_existing_modules,
    get_component_test_scorecard,
    get_resolved_bugs,
)


# ---------------------------------------------------------------------------
# Prompt-fragment data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PromptPacket:
    """Composable prompt fragment produced by a completion sprint builder."""

    system_block: str
    guardrails_block: str
    codebase_awareness_block: str
    sprint_objective_block: str
    scope_block: str
    traceability_block: str
    exclusions_block: str
    testing_block: str
    output_format_block: str
    handoff_block: str

    def render(self) -> str:
        """Concatenate all blocks into a single prompt string."""
        blocks = [
            self.system_block,
            self.guardrails_block,
            self.codebase_awareness_block,
            self.sprint_objective_block,
            self.scope_block,
            self.traceability_block,
            self.exclusions_block,
            self.testing_block,
            self.output_format_block,
            self.handoff_block,
        ]
        return "\n\n".join(b for b in blocks if b.strip())


# ---------------------------------------------------------------------------
# Shared block builders
# ---------------------------------------------------------------------------

def _build_system_block() -> str:
    """System preamble shared across all completion sprints."""
    return """=== SYSTEM ===

You are a programmer agent completing an existing, component-tested codebase for the Report Synthesizer Agent. The governing specification is report_synthesizer_v4.md (v4.0). The codebase was produced by a prior 6-sprint build and has passed a 12-step component verification sequence covering every individual module.

Your job is to add integration glue — NOT to rewrite components. Every module listed in the codebase inventory below is implemented, tested, and working. You must import and call these modules by their actual interface. You must not re-implement any function, class, or utility that already exists.

You are writing Python code that will be added to the existing synthesizer/ package. All imports must use the actual module paths (e.g., 'from synthesizer.loaders.plan_loader import load_report_plan'). If you are unsure of an interface, use the module inventory below — it lists every module and its public exports.

=== END SYSTEM ==="""


def _build_guardrails_block() -> str:
    """Guardrails shared across all completion sprints."""
    return """=== GUARDRAILS ===

MANDATORY constraints — violations will cause the sprint to fail:

1. DO NOT re-implement any module that already exists. Import and call it.
2. DO NOT change the public interface (function signatures, class fields, return types) of any existing tested module. Downstream callers depend on the current interfaces.
3. DO NOT rename fields. The canonical field names were established during component testing (e.g., SectionState uses 'state' not 'lifecycle_state', DependencyEdge uses 'source_section_id'/'target_section_id'/'kind').
4. DO NOT duplicate logic from existing modules into new files. If lifecycle.py has invalidate_content_dependents(), call it — do not copy its logic into run.py.
5. DO NOT embed prompt text that belongs in the existing prompt/assembly.py or context_channels.py modules.
6. DO NOT hardcode open decisions (DR-XX). These must remain configurable via config.py values.
7. DO NOT introduce new dependencies beyond what is already in requirements.txt unless explicitly required by the sprint tasks.
8. All new code must include docstrings with FR/NFR traceability references.
9. All new files must include a module-level docstring stating their purpose and governing spec section.

=== END GUARDRAILS ==="""


def _build_codebase_awareness_block(sprint: SprintDefinition) -> str:
    """Codebase inventory and component test scorecard.

    This block tells the agent exactly what exists, what has been tested,
    and which modules are relevant to the current sprint.
    """
    modules = get_existing_modules()
    scorecard = get_component_test_scorecard()
    bugs = get_resolved_bugs()

    # Build module inventory
    module_lines = []
    for path, exports in sorted(modules.items()):
        # Mark modules that are integration targets for this sprint
        marker = " ◀ INTEGRATION TARGET" if path in sprint.integration_targets else ""
        module_lines.append(f"  {path}{marker}\n    Exports: {exports}")

    # Build sprint-specific relevance note
    target_list = "\n".join(f"  - {t}" for t in sprint.integration_targets)

    return f"""=== CODEBASE INVENTORY ===

The following modules exist and are TESTED. Do NOT re-implement them.

{chr(10).join(module_lines)}

--- Component Test Scorecard (all 12 steps PASS) ---

{chr(10).join(f"  {item}" for item in scorecard)}

--- Bugs Found and Resolved During Testing ---

{chr(10).join(f"  - {bug}" for bug in bugs)}

--- Modules Relevant to This Sprint ---

The following modules are integration targets for {sprint.sprint_id}:

{target_list}

You must import from these modules. Read their interfaces carefully before writing any code.

=== END CODEBASE INVENTORY ==="""


def _build_traceability_block(sprint: SprintDefinition) -> str:
    """Traceability to spec sections, FRs, and NFRs."""
    fr_list = ", ".join(sprint.functional_requirements) if sprint.functional_requirements else "(none)"
    nfr_list = ", ".join(sprint.non_functional_requirements) if sprint.non_functional_requirements else "(none)"
    spec_list = ", ".join(sprint.spec_sections) if sprint.spec_sections else "(none)"
    schema_list = ", ".join(sprint.schema_targets) if sprint.schema_targets else "(none)"
    dr_list = ", ".join(sprint.open_decisions_to_preserve) if sprint.open_decisions_to_preserve else "(none — all decisions resolved)"

    return f"""=== TRACEABILITY ===

Governing spec sections: {spec_list}
Functional requirements: {fr_list}
Non-functional requirements: {nfr_list}
Schema targets (consume or extend): {schema_list}
Open decisions to preserve (do NOT hardcode): {dr_list}

Every new function and class must include a docstring referencing the FR/NFR/spec section it implements.

=== END TRACEABILITY ==="""


def _build_testing_block(sprint: SprintDefinition) -> str:
    """Test requirements and done-definition."""
    tests = "\n".join(f"  {i}. {t}" for i, t in enumerate(sprint.tests_required, 1))
    done = "\n".join(f"  {i}. {d}" for i, d in enumerate(sprint.done_definition, 1))

    return f"""=== TESTING AND DONE DEFINITION ===

Required tests:

{tests}

Done definition (all must be true for sprint completion):

{done}

CRITICAL: No existing component test (Steps 1-12 in the scorecard) may be broken by your changes. If you modify an existing file, verify the module still imports and its existing functions still behave correctly.

=== END TESTING ==="""


def _build_output_format_block() -> str:
    """Output format instructions shared across all completion sprints."""
    return """=== OUTPUT FORMAT ===

Output all files as fenced code blocks with the full file path as the block label. Example:

### `synthesizer/orchestrator/run.py`
```python
# synthesizer/orchestrator/run.py
\"\"\"Module docstring with spec reference.\"\"\"
...
```

Include complete file contents for new files. For modified files, include the complete modified file (not a diff). The file path must be exact — it determines where the file is written.

Output files in dependency order: models/schemas first, then utilities, then the main implementation file, then tests.

=== END OUTPUT FORMAT ==="""


def _build_handoff_block(sprint: SprintDefinition) -> str:
    """Handoff requirements for downstream sprints."""
    handoff = "\n".join(f"  {i}. {h}" for i, h in enumerate(sprint.handoff_requirements, 1))

    return f"""=== HANDOFF ===

After this sprint, downstream sprints will depend on the following being stable:

{handoff}

Do not introduce interfaces that will need to change in later completion sprints. If an interface must be provisional (e.g., a parameter accepted but not yet implemented), document it clearly with a comment.

=== END HANDOFF ==="""


# ---------------------------------------------------------------------------
# Per-sprint scope and exclusions builders
# ---------------------------------------------------------------------------

def _build_scope_block(sprint: SprintDefinition, extra_context: str = "") -> str:
    """Artifacts in scope and implementation tasks."""
    artifacts = "\n".join(f"  - {a}" for a in sprint.artifacts_in_scope)
    tasks = "\n".join(f"  {t}" for t in sprint.implementation_tasks)

    context_section = ""
    if extra_context:
        context_section = f"""
--- Existing Code Reference ---

The following shows key interfaces from existing modules you must integrate with. Use these exact function signatures and types.

{extra_context}

--- End Existing Code Reference ---
"""

    return f"""=== SCOPE ===

Artifacts to produce or modify:

{artifacts}

Implementation tasks (execute in order):

{tasks}
{context_section}
=== END SCOPE ==="""


# ---------------------------------------------------------------------------
# Sprint-specific builders
# ---------------------------------------------------------------------------

def _build_completion_1(sprint: SprintDefinition, workspace_path: Optional[Path] = None) -> PromptPacket:
    """Build prompt for completion_1: Layer 3 semantic validation wiring."""

    existing_code = ""
    if workspace_path:
        existing_code = _read_workspace_files(workspace_path, [
            "synthesizer/validation/coordinator.py",
            "synthesizer/validation/layer3_semantic.py",
            "synthesizer/orchestrator/model_init.py",
            "synthesizer/models/validation_models.py",
        ])
    else:
        existing_code = """Key interfaces to use (read from workspace before coding):

synthesizer/validation/coordinator.py:
  - validate_section(raw_json, section_id, section_type, style, depth_level, attempt, ..., llm_client=None, skip_layer3=False) → ValidationPipelineResult
  - The llm_client parameter must flow through to layer3_semantic sub-checks
  - skip_layer3=False is the path you are completing

synthesizer/validation/layer3_semantic.py:
  - Contains three sub-check functions for: (A) tone compliance, (B) dependency contract, (C) unsupported claim detection
  - Each returns a ValidationResult with layer=ValidationLayer.SEMANTIC
  - If any sub-check is a stub/placeholder, implement it fully

synthesizer/orchestrator/model_init.py:
  - verify_model_availability() — returns client info or raises on failure

synthesizer/models/validation_models.py:
  - ValidationResult(layer, passed, attempt, violations, suggested_fix)
  - Violation(rule, description, severity, location)"""

    exclusions = """=== EXCLUSIONS ===

This sprint touches ONLY the validation subsystem. Do NOT:

- Create the orchestrator run loop (that is completion_2)
- Implement retry logic or escalation transitions (completion_2)
- Modify any model schemas in synthesizer/models/ (they are tested and stable)
- Modify the loaders, DAG builder, or prompt assembly modules
- Modify the retrieval adapter or extraction modules
- Add CLI entry points or __main__.py
- Compute or save run metrics

Your changes are limited to:
  synthesizer/validation/layer3_semantic.py (modify)
  synthesizer/validation/coordinator.py (modify if needed for L3 wiring)
  tests/test_layer3_integration.py (new)

=== END EXCLUSIONS ==="""

    return PromptPacket(
        system_block=_build_system_block(),
        guardrails_block=_build_guardrails_block(),
        codebase_awareness_block=_build_codebase_awareness_block(sprint),
        sprint_objective_block=f"=== SPRINT OBJECTIVE ===\n\nSprint: {sprint.sprint_id} — {sprint.title}\n\n{sprint.objective}\n\n=== END SPRINT OBJECTIVE ===",
        scope_block=_build_scope_block(sprint, existing_code),
        traceability_block=_build_traceability_block(sprint),
        exclusions_block=exclusions,
        testing_block=_build_testing_block(sprint),
        output_format_block=_build_output_format_block(),
        handoff_block=_build_handoff_block(sprint),
    )


def _build_completion_2(sprint: SprintDefinition, workspace_path: Optional[Path] = None) -> PromptPacket:
    """Build prompt for completion_2: Orchestrator run loop with retry/escalation."""

    existing_code = ""
    if workspace_path:
        existing_code = _read_workspace_files(workspace_path, [
            "synthesizer/orchestrator/lifecycle.py",
            "synthesizer/validation/coordinator.py",
            "synthesizer/prompt/assembly.py",
            "synthesizer/retrieval/adapter.py",
            "synthesizer/extraction/claim_extractor.py",
            "synthesizer/extraction/claim_validator.py",
            "synthesizer/extraction/summary_abstractifier.py",
            "synthesizer/observability/events.py",
            "synthesizer/observability/tokens.py",
            "synthesizer/loaders/plan_loader.py",
            "synthesizer/loaders/style_loader.py",
            "synthesizer/dag.py",
            "synthesizer/config.py",
            "synthesizer/models/state.py",
        ])
    else:
        existing_code = """Key interfaces to use (read from workspace before coding):

synthesizer/loaders/plan_loader.py:
  - load_report_plan(path: Path) → ReportPlan
    Loads and validates (FR-01, FR-02, FR-03).

synthesizer/loaders/style_loader.py:
  - load_style_sheet(path: Path) → StyleSheet
    Loads and validates (FR-04).

synthesizer/dag.py:
  - build_generation_dag(plan: ReportPlan) → DAG
  - build_finalization_dag(plan: ReportPlan) → DAG
  - iter_topological(dag: DAG) → List[str]

synthesizer/orchestrator/lifecycle.py:
  - check_generation_prerequisites(section_id, section_states, gen_dag) → bool
  - check_finalization_prerequisites(section_id, section_states, fin_dag) → bool
  - transition_state(section_state, new_state) — updates state + timestamp
  - check_assembly_readiness(section_states) → bool (raises AssemblyNotReadyError)

synthesizer/retrieval/adapter.py:
  - retrieve_chunks(queries: List[str], ...) → List[RankedChunk]
    Answer text already discarded (DR-05).

synthesizer/prompt/assembly.py:
  - assemble_generation_prompt(section, style, retrieved_chunks, upstream_claim_tables, upstream_summary_abstracts, retry_errors, retry_layer) → GenerationPrompt
    All exclusions enforced (DR-03, DR-05, DR-06).

synthesizer/validation/coordinator.py:
  - validate_section(raw_json, section_id, section_type, style, depth_level, attempt, ..., llm_client, skip_layer3=False) → ValidationPipelineResult
    Returns .passed, .failing_layer, .results, .parsed_output, .formatted_errors

synthesizer/extraction/claim_extractor.py:
  - extract_claim_table(section_text, section_id, retrieved_chunks, version, llm_client, retry_limit) → ClaimTable
    Returns partial=True on exhaustion (FR-22).

synthesizer/extraction/claim_validator.py:
  - validate_claim_table(claim_table, section_text, available_chunk_ids, ...) → ClaimValidationResult
    Four sub-checks (FR-21).

synthesizer/extraction/summary_abstractifier.py:
  - generate_summary_abstract(section_text, section_id, llm_client) → str
    Returns 2-3 sentence abstract.

synthesizer/observability/events.py:
  - emit_event(event_type, section_id, from_state, to_state, metadata) — structured log

synthesizer/observability/tokens.py:
  - TokenTracker class with .record_call(role, input_tokens, output_tokens, ...) and budget enforcement

synthesizer/config.py:
  - LAYER1_RETRY_LIMIT, LAYER2_RETRY_LIMIT, LAYER3_RETRY_LIMIT, CLAIM_EXTRACTION_RETRY_LIMIT
  - SYNTHESIZER_MODEL, SYNTHESIZER_OUTPUT_DIR, TOKEN_BUDGET_CEILING
  - REPORT_PLAN_PATH, STYLE_SHEET_PATH

synthesizer/models/state.py:
  - SectionState(section_id, state, version, validation_history, claim_table, summary_abstract, retry_counters, cascade_depth)
  - RunState(run_id, report_plan_version, section_states, generation_dag_edges, finalization_dag_edges, started_at, last_checkpoint_at, cumulative_input_tokens, cumulative_output_tokens)"""

    exclusions = """=== EXCLUSIONS ===

This sprint creates the run loop and retry/escalation logic. Do NOT:

- Implement cascade propagation (completion_3) — after a section finalizes, do NOT check for downstream invalidations. Just finalize and move on.
- Implement checkpoint/resume (completion_3) — accept the resume parameter but do nothing with it. Write run_state.json at the end (not after every transition — that is completion_3).
- Implement the assembler module (completion_3) — after all sections are processed, do NOT concatenate them into a final report. Just log that processing is complete.
- Compute or save run metrics (completion_4) — do not call build_run_metrics() or save_run_metrics().
- Modify any existing model schemas in synthesizer/models/
- Modify any existing validation layer implementation (L1, L2, L3)
- Modify the existing prompt assembly or context channel modules
- Modify the retrieval adapter

Your new files:
  synthesizer/orchestrator/run.py (new)
  synthesizer/__main__.py (new)
  tests/test_single_section_run.py (new)
  tests/test_retry_escalation.py (new)

Your modified files:
  synthesizer/orchestrator/__init__.py (add exports)

=== END EXCLUSIONS ==="""

    return PromptPacket(
        system_block=_build_system_block(),
        guardrails_block=_build_guardrails_block(),
        codebase_awareness_block=_build_codebase_awareness_block(sprint),
        sprint_objective_block=f"=== SPRINT OBJECTIVE ===\n\nSprint: {sprint.sprint_id} — {sprint.title}\n\n{sprint.objective}\n\n=== END SPRINT OBJECTIVE ===",
        scope_block=_build_scope_block(sprint, existing_code),
        traceability_block=_build_traceability_block(sprint),
        exclusions_block=exclusions,
        testing_block=_build_testing_block(sprint),
        output_format_block=_build_output_format_block(),
        handoff_block=_build_handoff_block(sprint),
    )


def _build_completion_3(sprint: SprintDefinition, workspace_path: Optional[Path] = None) -> PromptPacket:
    """Build prompt for completion_3: Cascade, checkpoint, and assembly."""

    existing_code = ""
    if workspace_path:
        existing_code = _read_workspace_files(workspace_path, [
            "synthesizer/orchestrator/run.py",
            "synthesizer/orchestrator/lifecycle.py",
            "synthesizer/models/state.py",
            "synthesizer/models/report_plan.py",
            "synthesizer/config.py",
        ])
    else:
        existing_code = """Key interfaces to use (read from workspace before coding):

synthesizer/orchestrator/run.py (FROM COMPLETION_2):
  - This is the file you are modifying. Read its full contents before making changes.
  - The run loop iterates sections in topological order and processes each through
    retrieval → generation → validation → claim extraction → finalization.
  - You must add: cascade hooks after finalization, atomic checkpoint writes after
    every state transition, resume logic on startup, and assembly call at the end.

synthesizer/orchestrator/lifecycle.py:
  - invalidate_content_dependents(section_id, section_states, gen_dag) → List[str]
    Returns list of section_ids that were invalidated. Call this after finalization.
  - trigger_reference_revalidation(section_id, section_states, fin_dag) → List[str]
    Returns list of section_ids needing re-validation. FR-25.
  - check_assembly_readiness(section_states) → bool
    Raises AssemblyNotReadyError if any section is not terminal. FR-27.

synthesizer/models/state.py:
  - RunState.model_dump_json() for serialization
  - RunState.model_validate_json() for deserialization
  - SectionState.cascade_depth field tracks cascade depth per section

synthesizer/config.py:
  - CASCADE_DEPTH_LIMIT (default: 3) — FR-24

synthesizer/models/report_plan.py:
  - ReportPlan.sections — ordered list, determines assembly order
  - SectionNode.depth_level — determines heading adjustment in assembly"""

    exclusions = """=== EXCLUSIONS ===

This sprint adds cascade, checkpoint, and assembly to the existing run loop. Do NOT:

- Modify the retry/escalation logic from completion_2 (it works — do not touch the inner validation loop)
- Compute or save run metrics (completion_4) — the completion phase should have a clear insertion point for metrics but should not call build_run_metrics()
- Implement acceptance tests (completion_4)
- Modify any existing model schemas
- Modify any validation layer, prompt assembly, retrieval, or extraction module

Your new files:
  synthesizer/assembly/assembler.py (new)
  tests/test_cascade_propagation.py (new)
  tests/test_checkpoint_resume.py (new)
  tests/test_assembly.py (new)

Your modified files:
  synthesizer/assembly/__init__.py (add exports)
  synthesizer/orchestrator/run.py (add cascade, checkpoint, assembly)
  synthesizer/__main__.py (--resume flag now functional)

=== END EXCLUSIONS ==="""

    return PromptPacket(
        system_block=_build_system_block(),
        guardrails_block=_build_guardrails_block(),
        codebase_awareness_block=_build_codebase_awareness_block(sprint),
        sprint_objective_block=f"=== SPRINT OBJECTIVE ===\n\nSprint: {sprint.sprint_id} — {sprint.title}\n\n{sprint.objective}\n\n=== END SPRINT OBJECTIVE ===",
        scope_block=_build_scope_block(sprint, existing_code),
        traceability_block=_build_traceability_block(sprint),
        exclusions_block=exclusions,
        testing_block=_build_testing_block(sprint),
        output_format_block=_build_output_format_block(),
        handoff_block=_build_handoff_block(sprint),
    )


def _build_completion_4(sprint: SprintDefinition, workspace_path: Optional[Path] = None) -> PromptPacket:
    """Build prompt for completion_4: Run metrics and acceptance tests."""

    existing_code = ""
    if workspace_path:
        existing_code = _read_workspace_files(workspace_path, [
            "synthesizer/orchestrator/run.py",
            "synthesizer/observability/metrics.py",
            "synthesizer/orchestrator/lifecycle.py",
            "synthesizer/models/state.py",
        ])
    else:
        existing_code = """Key interfaces to use (read from workspace before coding):

synthesizer/orchestrator/run.py (FROM COMPLETION_3):
  - This is the file you are modifying. Read its full contents.
  - The completion phase (after assembly) is where you add metrics computation.
  - Add: build_run_metrics(run_state) then save_run_metrics(metrics, output_dir).

synthesizer/observability/metrics.py:
  - compute_structural_compliance_rate(section_states) → float  (Target: ≥90%)
  - compute_style_compliance_rate(section_states) → float  (Target: ≥85%)
  - compute_dependency_completeness(section_states, gen_dag_edges, section_contents) → float  (Target: ≥80%)
  - compute_unsupported_claim_rate(section_states) → float  (Target: ≤10%)
  - compute_revision_churn_index(section_states) → float
  - compute_claim_table_completeness(section_states) → float  (Target: ≥90%)
  - compute_evidence_claim_agreement(section_states) → float  (Target: ≥85%)
  - build_run_metrics(run_state) → dict  — calls all seven metric functions
  - save_run_metrics(metrics, output_dir) → None  — writes run_metrics.json

  IMPORTANT: Verify that all seven functions are fully implemented (not returning
  placeholder 0.0). If any is a stub, implement it per the docstring and §17.2.

synthesizer/orchestrator/lifecycle.py:
  - check_generation_prerequisites() — used by acceptance test FR-08
  - check_assembly_readiness() — used by acceptance test FR-27

synthesizer/models/state.py:
  - SectionState, RunState — used throughout acceptance tests"""

    exclusions = """=== EXCLUSIONS ===

This sprint adds metrics and acceptance tests. Do NOT:

- Modify the run loop's section-processing logic (retry, generation, validation)
- Modify the assembler module
- Modify any validation layer behavior
- Modify any model schemas
- Change the cascade propagation or checkpoint/resume logic

Your new files:
  tests/test_end_to_end_smoke.py (new)
  synthesizer/acceptance/test_fr08_dependency_ordering.py (new)
  synthesizer/acceptance/test_fr18_semantic_validation.py (new)
  synthesizer/acceptance/test_fr23_cascade_invalidation.py (new)
  synthesizer/acceptance/test_fr26_assembly_headings.py (new)
  synthesizer/acceptance/test_fr27_assembly_readiness.py (new)

Your modified files:
  synthesizer/orchestrator/run.py (add metrics computation to completion phase)
  synthesizer/acceptance/__init__.py (complete truncated docstring and structure)

=== END EXCLUSIONS ==="""

    return PromptPacket(
        system_block=_build_system_block(),
        guardrails_block=_build_guardrails_block(),
        codebase_awareness_block=_build_codebase_awareness_block(sprint),
        sprint_objective_block=f"=== SPRINT OBJECTIVE ===\n\nSprint: {sprint.sprint_id} — {sprint.title}\n\n{sprint.objective}\n\n=== END SPRINT OBJECTIVE ===",
        scope_block=_build_scope_block(sprint, existing_code),
        traceability_block=_build_traceability_block(sprint),
        exclusions_block=exclusions,
        testing_block=_build_testing_block(sprint),
        output_format_block=_build_output_format_block(),
        handoff_block=_build_handoff_block(sprint),
    )


# ---------------------------------------------------------------------------
# Workspace file reader helper
# ---------------------------------------------------------------------------

def _read_workspace_files(workspace_path: Path, relative_paths: List[str]) -> str:
    """Read source files from the workspace for inclusion in prompts.

    Parameters
    ----------
    workspace_path : Path
        Root of the synthesizer workspace (parent of 'synthesizer/').
    relative_paths : list of str
        File paths relative to workspace_path.

    Returns
    -------
    str
        Concatenated file contents with path headers, suitable for
        embedding in a prompt's scope block.
    """
    sections = []
    for rel_path in relative_paths:
        full_path = workspace_path / rel_path
        if full_path.exists():
            try:
                content = full_path.read_text(encoding="utf-8")
                sections.append(
                    f"--- {rel_path} ---\n"
                    f"```python\n{content}\n```"
                )
            except Exception as exc:
                sections.append(
                    f"--- {rel_path} ---\n"
                    f"(Could not read: {exc})"
                )
        else:
            sections.append(
                f"--- {rel_path} ---\n"
                f"(File not found at {full_path}. Read it from your workspace before coding.)"
            )
    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Builder registry
# ---------------------------------------------------------------------------

_BUILDERS: Dict[str, Callable[[SprintDefinition, Optional[Path]], PromptPacket]] = {
    "completion_1": _build_completion_1,
    "completion_2": _build_completion_2,
    "completion_3": _build_completion_3,
    "completion_4": _build_completion_4,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_prompt_for_sprint(
    sprint_id: str,
    workspace_path: Optional[Path] = None,
) -> str:
    """Build the complete programmer-agent prompt for a completion sprint.

    Parameters
    ----------
    sprint_id : str
        One of 'completion_1' through 'completion_4'.
    workspace_path : Path, optional
        Root of the synthesizer workspace. If provided, the prompt will
        include full source code of relevant existing modules. If not
        provided, the prompt includes interface summaries instead.

    Returns
    -------
    str
        The fully composed prompt string.

    Raises
    ------
    KeyError
        If sprint_id is not in the completion registry.
    ValueError
        If sprint_id has no registered prompt builder.
    """
    sprint = get_sprint(sprint_id)

    if sprint_id not in _BUILDERS:
        raise ValueError(
            f"No prompt builder registered for sprint {sprint_id!r}. "
            f"Available builders: {sorted(_BUILDERS.keys())}"
        )

    builder = _BUILDERS[sprint_id]
    packet = builder(sprint, workspace_path)
    return packet.render()


def get_prompt_packet(
    sprint_id: str,
    workspace_path: Optional[Path] = None,
) -> PromptPacket:
    """Build and return the PromptPacket (not rendered) for inspection.

    Parameters
    ----------
    sprint_id : str
        One of 'completion_1' through 'completion_4'.
    workspace_path : Path, optional
        Root of the synthesizer workspace.

    Returns
    -------
    PromptPacket
        The prompt packet with all blocks populated.
    """
    sprint = get_sprint(sprint_id)
    builder = _BUILDERS[sprint_id]
    return builder(sprint, workspace_path)


# ---------------------------------------------------------------------------
# Coverage validation
# ---------------------------------------------------------------------------

def validate_completion_prompt_coverage() -> None:
    """Verify that every completion sprint has a prompt builder.

    Raises ValueError with a descriptive message on any gap.
    """
    registry_ids = set(list_sprint_ids())
    builder_ids = set(_BUILDERS)

    missing_builders = registry_ids - builder_ids
    orphan_builders = builder_ids - registry_ids

    errors: List[str] = []
    if missing_builders:
        errors.append(
            f"Sprints in registry with no prompt builder: "
            f"{sorted(missing_builders)}"
        )
    if orphan_builders:
        errors.append(
            f"Prompt builders with no matching sprint in registry: "
            f"{sorted(orphan_builders)}"
        )

    # Verify each builder can produce a prompt without error
    for sid in sorted(builder_ids & registry_ids):
        try:
            prompt = build_prompt_for_sprint(sid)
            if not prompt or len(prompt) < 500:
                errors.append(
                    f"Prompt for {sid} is suspiciously short "
                    f"({len(prompt)} chars)"
                )
        except Exception as exc:
            errors.append(f"Prompt builder for {sid} raised: {exc}")

    if errors:
        raise ValueError(
            "Completion prompt coverage validation failed:\n  "
            + "\n  ".join(errors)
        )


# ---------------------------------------------------------------------------
# Run coverage validation on import so gaps surface immediately.
# ---------------------------------------------------------------------------
validate_completion_prompt_coverage()