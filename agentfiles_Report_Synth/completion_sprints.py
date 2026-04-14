"""
Completion sprint plan registry for the Report Synthesizer Agent.

Source of truth: report_synthesizer_v4.md (governing specification)
and the Report_Synth_Completion_Plan.md (integration gap analysis).

These sprints operate on an EXISTING, COMPONENT-TESTED codebase produced
by the original sprint_1 through sprint_6. All individual components
have passed a 12-step verification sequence. These completion sprints
add the integration glue: Layer 3 wiring, the orchestrator run loop,
retry/escalation, cascade propagation, checkpoint/resume, final assembly,
run metrics, and acceptance tests.

The original sprints.py and prompts.py are NOT imported. These completion
sprints form an independent registry with their own validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# SprintDefinition dataclass — identical structure to the original
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SprintDefinition:
    """A single completion sprint in the integration build plan."""

    sprint_id: str
    """Unique identifier, e.g. 'completion_1'."""

    title: str
    """Short human-readable sprint title."""

    objective: str
    """One-paragraph statement of what this sprint achieves."""

    spec_sections: List[str]
    """Governing spec sections (e.g. '§12.3', '§11') that apply."""

    functional_requirements: List[str]
    """FR-XX IDs in scope for this sprint."""

    non_functional_requirements: List[str]
    """NFR-XX IDs in scope for this sprint."""

    schema_targets: List[str]
    """Pydantic model / enum names from §10 that must be consumed or extended."""

    integration_targets: List[str]
    """Existing modules this sprint integrates with or modifies."""

    artifacts_in_scope: List[str]
    """Concrete code artifacts (files) to be produced or modified."""

    implementation_tasks: List[str]
    """Ordered list of implementation work items."""

    tests_required: List[str]
    """Concrete test cases required for done-ness."""

    dependencies: List[str]
    """sprint_id values that must be complete before this sprint starts."""

    done_definition: List[str]
    """Verifiable completion criteria."""

    open_decisions_to_preserve: List[str]
    """DR-XX or other open items that must NOT be silently hardcoded."""

    handoff_requirements: List[str]
    """What downstream sprints can treat as stable after this sprint ships."""


# ---------------------------------------------------------------------------
# Codebase inventory — shared reference for all completion sprints
# ---------------------------------------------------------------------------

EXISTING_MODULES: Dict[str, str] = {
    # Models
    "synthesizer/models/enums.py": "DependencyKind, SectionType, SectionLifecycleState, ValidationLayer, ConfidenceTag, ViolationSeverity",
    "synthesizer/models/report_plan.py": "ReportPlan, SectionNode, DependencyEdge",
    "synthesizer/models/style_sheet.py": "StyleSheet, LevelConstraint, EquationDelimiters",
    "synthesizer/models/section_output.py": "SectionOutput + 4 per-type subclasses, get_output_model()",
    "synthesizer/models/claims.py": "ClaimTable, ClaimEntry, TextSpan",
    "synthesizer/models/validation_models.py": "ValidationResult, Violation",
    "synthesizer/models/state.py": "SectionState, RunState",
    "synthesizer/models/provenance.py": "ProvenanceRecord",
    "synthesizer/models/validation.py": "Re-exports from validation_models",
    # Loaders
    "synthesizer/loaders/plan_loader.py": "load_report_plan() — FR-01, FR-02, FR-03",
    "synthesizer/loaders/style_loader.py": "load_style_sheet() — FR-04",
    # DAG
    "synthesizer/dag.py": "DAG, build_generation_dag(), build_finalization_dag(), iter_topological()",
    # Validation
    "synthesizer/validation/graph_validation.py": "validate_dependency_references(), validate_no_content_cycles(), validate_depth_levels()",
    "synthesizer/validation/layer1_structural.py": "validate_layer1() — FR-14",
    "synthesizer/validation/layer2_rules.py": "validate_layer2() — FR-16",
    "synthesizer/validation/layer3_semantic.py": "validate_layer3() — FR-18 (sub-checks A/B/C)",
    "synthesizer/validation/coordinator.py": "ValidationCoordinator or validate_section() — dispatches L1→L2→L3",
    # Retrieval
    "synthesizer/retrieval/adapter.py": "retrieve_chunks() — FR-09, FR-10, DR-05",
    "synthesizer/retrieval/planning_context.py": "load_planning_summaries() — DR-06",
    # Prompt
    "synthesizer/prompt/assembly.py": "assemble_generation_prompt() — FR-11, FR-12, FR-13",
    "synthesizer/prompt/context_channels.py": "Context channel packaging helpers",
    # Extraction
    "synthesizer/extraction/claim_extractor.py": "extract_claim_table() — FR-20, FR-22",
    "synthesizer/extraction/claim_validator.py": "validate_claim_table() — FR-21 (4 sub-checks)",
    "synthesizer/extraction/summary_abstractifier.py": "generate_summary_abstract()",
    # Orchestrator
    "synthesizer/orchestrator/lifecycle.py": "check_generation_prerequisites(), check_finalization_prerequisites(), transition_state(), invalidate_content_dependents(), trigger_reference_revalidation(), check_assembly_readiness()",
    "synthesizer/orchestrator/model_init.py": "verify_model_availability()",
    # Observability
    "synthesizer/observability/events.py": "emit_event(), EventType",
    "synthesizer/observability/metrics.py": "compute_structural_compliance_rate(), compute_style_compliance_rate(), compute_dependency_completeness(), compute_unsupported_claim_rate(), compute_revision_churn_index(), compute_claim_table_completeness(), compute_evidence_claim_agreement(), build_run_metrics(), save_run_metrics()",
    "synthesizer/observability/tokens.py": "TokenTracker, LLMCallRecord, TokenBudgetExceededError",
    # Config
    "synthesizer/config.py": "All §16 keys — REPORT_PLAN_PATH, STYLE_SHEET_PATH, SYNTHESIZER_OUTPUT_DIR, CASCADE_DEPTH_LIMIT, LAYER*_RETRY_LIMIT, SYNTHESIZER_MODEL, TOKEN_BUDGET_CEILING",
}

COMPONENT_TEST_SCORECARD: List[str] = [
    "Step 1:  Report plan loader + validation — PASS",
    "Step 2:  Style sheet loader + regex — PASS",
    "Step 3:  DAG construction (generation + finalization) — PASS",
    "Step 4:  Retrieval adapter — PASS",
    "Step 5:  Prompt assembly — PASS",
    "Step 6:  Generator LLM call — PASS",
    "Step 7:  Layer 1 structural validation — PASS",
    "Step 8:  Layer 2 rule-based validation — PASS",
    "Step 9:  Claim table extraction — PASS",
    "Step 10: Summary abstractifier — PASS",
    "Step 11: Lifecycle state transitions — PASS",
    "Step 12: Output directory structure — PASS",
]

RESOLVED_BUGS: List[str] = [
    "Truncation bugs fixed: graph_validation.py, lifecycle.py, acceptance/__init__.py, coordinator.py, summary_abstractifier.py",
    "RetrievalAdapter class vs function-based API mismatch resolved",
    "lifecycle_state vs state field name mismatch resolved (canonical: state)",
    "Backtick escape issues in CLI test scripts resolved",
    "Nonexistent citations field reference removed",
]


# ---------------------------------------------------------------------------
# Completion Sprint 1 — Layer 3 Semantic Validation Wiring
# ---------------------------------------------------------------------------

_COMPLETION_1 = SprintDefinition(
    sprint_id="completion_1",
    title="Layer 3 semantic validation wiring",

    objective=(
        "Wire the Anthropic LLM client into the validation coordinator's "
        "Layer 3 dispatch path so that the full L1→L2→L3 validation pipeline "
        "can execute with skip_layer3=False. Verify all three L3 sub-checks "
        "(tone compliance, dependency contract fulfillment, unsupported claim "
        "detection) produce valid ValidationResult objects from live LLM "
        "responses. This sprint touches only the validation subsystem — it "
        "does not create the orchestrator run loop or any other integration "
        "glue."
    ),

    spec_sections=["§12.3", "§9.2.3", "§10.10"],

    functional_requirements=["FR-18", "FR-19"],

    non_functional_requirements=["NFR-09"],

    schema_targets=["ValidationResult", "Violation"],

    integration_targets=[
        "synthesizer/validation/coordinator.py",
        "synthesizer/validation/layer3_semantic.py",
        "synthesizer/orchestrator/model_init.py",
    ],

    artifacts_in_scope=[
        "synthesizer/validation/layer3_semantic.py  (modify — verify/complete L3 sub-check prompt templates and response parsing for all three sub-checks)",
        "synthesizer/validation/coordinator.py  (modify — ensure llm_client parameter flows correctly through to L3 dispatch; verify skip_layer3=False path exercises all three sub-checks)",
        "tests/test_layer3_integration.py  (new — integration test that runs the coordinator with a live LLM client against a test section output)",
    ],

    implementation_tasks=[
        "1. Read the existing layer3_semantic.py end-to-end. Identify the three sub-check functions: (a) tone compliance, (b) dependency contract fulfillment, (c) unsupported claim detection. For each, verify it has a prompt template, an Anthropic API call, a response parser, and returns a proper ValidationResult with populated violations on failure.",
        "2. Read coordinator.py and trace the llm_client parameter from the constructor or function signature through to the L3 dispatch call. Confirm the wiring is complete — the client reaches layer3_semantic's sub-check functions without None guards silently skipping the checks.",
        "3. If any L3 sub-check function is a stub, placeholder, or returns a hardcoded pass, implement it fully. Sub-check A (tone compliance): compare section text against style_sheet.tone_register using an LLM prompt that returns pass/fail with specific violations. Sub-check B (dependency contract): verify that downstream section content engages with entries from upstream claim tables. Sub-check C (unsupported claim): verify that factual assertions in the section are traceable to retrieved evidence chunks.",
        "4. Each sub-check must parse the LLM response into a ValidationResult with: layer=ValidationLayer.SEMANTIC, passed=bool, attempt=int, violations=[...] with rule/description/severity populated. On a malformed LLM response, return a failure ValidationResult with a parse-error violation rather than raising an exception.",
        "5. Verify that model_init.py's verify_model_availability() returns a usable client object (or the information needed to construct one) that can be passed to the coordinator.",
        "6. Write tests/test_layer3_integration.py with these cases: (a) instantiate the coordinator with a live Anthropic client, submit a well-formed section output, assert all three L3 sub-checks execute and return valid ValidationResult objects; (b) submit a section with deliberately wrong tone → sub-check A returns failure; (c) submit a section that ignores upstream claim table entries → sub-check B returns failure; (d) submit a section with an unsupported factual claim → sub-check C returns failure.",
        "7. Verify L3 retry behavior: submit a section that fails a sub-check, confirm the coordinator's retry counter increments and formatted feedback (from the coordinator's existing feedback formatting logic) is available for inclusion in a retry prompt.",
    ],

    tests_required=[
        "Run coordinator with skip_layer3=False against a well-formed section output → all three sub-checks return ValidationResult objects with layer=SEMANTIC",
        "Submit section with wrong tone (e.g., casual when formal is required) → sub-check A returns failure with a tone violation",
        "Submit section that ignores upstream claim table entries → sub-check B returns failure identifying unengaged claims",
        "Submit section with unsupported factual claim (no matching evidence chunk) → sub-check C returns failure",
        "L3 retry counter increments on failure; formatted feedback string is non-empty",
        "Malformed LLM response → ValidationResult with parse-error violation (no unhandled exception)",
    ],

    dependencies=[],

    done_definition=[
        "coordinator.validate_section() (or equivalent) executes L1→L2→L3 with skip_layer3=False and returns a complete validation pipeline result",
        "All three L3 sub-checks produce valid ValidationResult objects from live LLM responses (not stubs or placeholders)",
        "L3 retry counter increments on failure and formatted feedback is available for the retry prompt",
        "test_layer3_integration.py passes with all test cases",
        "No existing component test (Steps 1-12) is broken by the changes",
    ],

    open_decisions_to_preserve=["DR-16"],

    handoff_requirements=[
        "coordinator.validate_section(skip_layer3=False) is a stable callable that completion_2 can invoke from the run loop without modification",
        "L3 sub-check prompt templates are finalized and not expected to change in later completion sprints",
        "The llm_client parameter interface (type, construction pattern) is documented so the run loop can instantiate and pass it",
    ],
)


# ---------------------------------------------------------------------------
# Completion Sprint 2 — Orchestrator Run Loop with Retry/Escalation
# ---------------------------------------------------------------------------

_COMPLETION_2 = SprintDefinition(
    sprint_id="completion_2",
    title="Orchestrator run loop with retry and escalation",

    objective=(
        "Create the main orchestrator entry point (run.py) that chains all "
        "existing components — loaders, DAG builder, retrieval adapter, "
        "prompt assembler, generator, validator coordinator, claim extractor, "
        "summary abstractifier, and lifecycle module — into a sequential "
        "pipeline run. Implement the per-layer retry-with-feedback inner "
        "loop and escalation on retry exhaustion. The run loop must call "
        "existing functions by their actual import paths — it must not "
        "re-implement any component logic. This sprint does NOT implement "
        "cascade propagation, checkpoint/resume, final assembly, or run "
        "metrics (those are completion_3 and completion_4)."
    ),

    spec_sections=["§6", "§11", "§12", "§13", "§14"],

    functional_requirements=[
        "FR-06", "FR-08", "FR-09", "FR-10", "FR-11", "FR-12", "FR-13",
        "FR-14", "FR-15", "FR-16", "FR-17", "FR-18", "FR-19",
        "FR-20", "FR-21", "FR-22",
    ],

    non_functional_requirements=["NFR-01", "NFR-02", "NFR-05", "NFR-06"],

    schema_targets=["RunState", "SectionState"],

    integration_targets=[
        "synthesizer/loaders/plan_loader.py",
        "synthesizer/loaders/style_loader.py",
        "synthesizer/dag.py",
        "synthesizer/retrieval/adapter.py",
        "synthesizer/retrieval/planning_context.py",
        "synthesizer/prompt/assembly.py",
        "synthesizer/validation/coordinator.py",
        "synthesizer/extraction/claim_extractor.py",
        "synthesizer/extraction/claim_validator.py",
        "synthesizer/extraction/summary_abstractifier.py",
        "synthesizer/orchestrator/lifecycle.py",
        "synthesizer/orchestrator/model_init.py",
        "synthesizer/observability/events.py",
        "synthesizer/observability/tokens.py",
        "synthesizer/config.py",
    ],

    artifacts_in_scope=[
        "synthesizer/orchestrator/run.py  (new — main orchestration loop with section processing and retry/escalation)",
        "synthesizer/__main__.py  (new — CLI entry point: 'python -m synthesizer --report-plan ... --style-sheet ...')",
        "synthesizer/orchestrator/__init__.py  (modify — export run function or SynthesizerRunner class)",
        "tests/test_single_section_run.py  (new — integration test: one section through the full pipeline)",
        "tests/test_retry_escalation.py  (new — tests for retry-with-feedback and escalation on exhaustion)",
    ],

    implementation_tasks=[
        "1. Read all existing component modules listed in integration_targets. Map each to the function/class you will call. Construct an import block that uses the actual module paths (e.g., 'from synthesizer.loaders.plan_loader import load_report_plan'). Do NOT re-implement any function that already exists.",
        "2. Create synthesizer/orchestrator/run.py. Define a run() function (or SynthesizerRunner class with a run() method) that accepts: report_plan_path (Path), style_sheet_path (Path), output_dir (Path), model (str, optional), and resume (bool, optional, default False). The resume parameter is accepted but ignored in this sprint — completion_3 implements it.",
        "3. Implement Phase 1 — Initialization: (a) load report plan via load_report_plan(report_plan_path), (b) load style sheet via load_style_sheet(style_sheet_path), (c) build generation DAG via build_generation_dag(plan) and finalization DAG via build_finalization_dag(plan), (d) get topological order via iter_topological(gen_dag), (e) initialize RunState with all sections in QUEUED state, (f) scaffold output directories via os.makedirs for each section_id under output_dir/sections/{section_id}/.",
        "4. Implement Phase 2 — Section Processing Loop: iterate sections in topological order. For each section: (a) check prerequisites via lifecycle.check_generation_prerequisites() — if not met, skip (section stays QUEUED for the next pass), (b) transition to GENERATING via lifecycle.transition_state(), (c) invoke retrieval adapter to get ranked chunks, (d) assemble generation prompt via prompt/assembly, (e) call Anthropic API with the assembled prompt to generate section content, (f) transition to DRAFTED, (g) invoke coordinator.validate_section() with skip_layer3=False.",
        "5. Implement the retry-with-feedback inner loop within the section processing: on validation failure at any layer, (a) read the coordinator's formatted feedback from the validation result, (b) re-assemble the generation prompt with the feedback appended as retry context, (c) re-invoke the Anthropic API, (d) re-validate. Respect per-layer retry limits from config: LAYER1_RETRY_LIMIT, LAYER2_RETRY_LIMIT, LAYER3_RETRY_LIMIT. Track attempt counts per layer per section in the SectionState.retry_counters dict.",
        "6. Implement escalation on retry exhaustion: when a layer's retry limit is exceeded, transition the section to ESCALATED state via lifecycle.transition_state(). The ESCALATED state is terminal — no further processing for this section. Log a clear message identifying the section and the layer that caused escalation.",
        "7. On full validation pass (all layers): (a) extract claim table via claim_extractor.extract_claim_table(), (b) validate claim table via claim_validator.validate_claim_table(), (c) handle claim extraction retry: on failure, retry up to CLAIM_EXTRACTION_RETRY_LIMIT; on exhaustion, mark claim table as partial (FR-22), (d) generate summary abstract via summary_abstractifier.generate_summary_abstract(), (e) write provenance record, (f) write draft, claim table, and validation log to the section's output directory, (g) transition to FINALIZED.",
        "8. Emit structured events at every state transition via observability/events.py. Each event must include: event_type, section_id, from_state, to_state, timestamp, and relevant metadata.",
        "9. Track token usage after every LLM call (generation, L3 validation, claim extraction, summary abstraction) via observability/tokens.py TokenTracker. Check budget ceiling after each call — if exceeded, halt with TokenBudgetExceededError.",
        "10. Create synthesizer/__main__.py with argparse: --report-plan (required), --style-sheet (required), --output-dir (optional, defaults to config), --model (optional, overrides SYNTHESIZER_MODEL), --resume (flag, accepted but no-op in this sprint). Call run() from run.py.",
        "11. Write tests/test_single_section_run.py: configure a 1-section report plan (use the example_report_plan.json introduction section), run the full loop against the example corpus, assert that draft_v1.md, claim_table_v1.json, and provenance.json are produced in the correct output directory.",
        "12. Write tests/test_retry_escalation.py: (a) mock the generator to produce output that fails L1 → verify retry with feedback → eventually pass, (b) mock the generator to always fail L1 → verify escalation after LAYER1_RETRY_LIMIT attempts, (c) mock claim extraction to fail → verify partial flag set after CLAIM_EXTRACTION_RETRY_LIMIT.",
    ],

    tests_required=[
        "Single-section run produces draft_v1.md, claim_table_v1.json, validation_log.json, and provenance.json in the correct output directory",
        "RunState checkpoint (run_state.json) is written to the output directory with at least one section in FINALIZED state",
        "Force L1 failure → retry prompt includes formatted error feedback → retry count increments → eventually pass or escalate",
        "Force L3 retry exhaustion → section transitions to ESCALATED state",
        "Claim extraction failure → retry up to limit → partial flag set on exhaustion",
        "Token tracker: cumulative_input_tokens and cumulative_output_tokens in RunState are > 0 after run",
        "Event log contains one structured event per state transition",
        "'python -m synthesizer --report-plan ... --style-sheet ...' runs without error (CLI entry point works)",
    ],

    dependencies=["completion_1"],

    done_definition=[
        "'python -m synthesizer --report-plan examples/example_report_plan.json --style-sheet examples/example_style_sheet.json' completes a single-section run end-to-end without error",
        "Output directory contains: sections/introduction/draft_v1.md, sections/introduction/claim_table_v1.json, sections/introduction/validation_log.json, sections/introduction/provenance.json, and run_state.json",
        "Retry-with-feedback loop fires on forced validation failure and includes the coordinator's formatted feedback in the retry prompt",
        "Escalation fires on retry exhaustion and the section reaches ESCALATED state",
        "test_single_section_run.py passes",
        "test_retry_escalation.py passes",
        "No existing component test (Steps 1-12) is broken by the changes",
    ],

    open_decisions_to_preserve=["DR-15", "DR-16", "DR-17", "DR-18"],

    handoff_requirements=[
        "run.py exposes a run() function (or SynthesizerRunner.run() method) with a clear signature that completion_3 can extend",
        "The section-processing loop has a clear post-finalization hook point where completion_3 will insert cascade propagation logic",
        "The run() function accepts a resume=bool parameter (currently no-op) that completion_3 will implement",
        "RunState is serialized to run_state.json at least once per section completion (completion_3 will tighten this to every state transition)",
        "The initialization phase has a clear checkpoint-load insertion point before DAG construction",
    ],
)


# ---------------------------------------------------------------------------
# Completion Sprint 3 — Cascade, Checkpoint, and Assembly
# ---------------------------------------------------------------------------

_COMPLETION_3 = SprintDefinition(
    sprint_id="completion_3",
    title="Cascade propagation, checkpoint/resume, and final assembly",

    objective=(
        "Extend the run loop from completion_2 with three capabilities: "
        "(1) cascade propagation that invalidates content dependents when "
        "upstream content changes after finalization, with depth limiting; "
        "(2) atomic checkpoint writes after every state transition with "
        "crash-resume support; and (3) a final assembler module that "
        "concatenates finalized sections into the output report with "
        "heading-level adjustment. This sprint does NOT compute or save "
        "run metrics (completion_4)."
    ),

    spec_sections=["§8", "§9.2.5", "§11.3", "§15"],

    functional_requirements=["FR-23", "FR-24", "FR-25", "FR-26", "FR-27"],

    non_functional_requirements=["NFR-03", "NFR-04"],

    schema_targets=["RunState"],

    integration_targets=[
        "synthesizer/orchestrator/run.py  (from completion_2)",
        "synthesizer/orchestrator/lifecycle.py",
        "synthesizer/models/state.py",
    ],

    artifacts_in_scope=[
        "synthesizer/assembly/assembler.py  (new — report concatenation with heading-level adjustment per depth_level)",
        "synthesizer/assembly/__init__.py  (modify — export assemble_report function)",
        "synthesizer/orchestrator/run.py  (modify — add cascade hooks after finalization, atomic checkpoint writes after every state transition, checkpoint resume on startup, and assembly call after all sections complete)",
        "tests/test_cascade_propagation.py  (new — multi-section cascade scenarios with depth limiting)",
        "tests/test_checkpoint_resume.py  (new — crash simulation and resume verification)",
        "tests/test_assembly.py  (new — heading-level adjustment and assembly readiness gate)",
    ],

    implementation_tasks=[
        "1. Read the existing lifecycle.py functions: invalidate_content_dependents(), trigger_reference_revalidation(), check_assembly_readiness(). These are the building blocks for cascade and assembly — call them, do not re-implement them.",
        "2. Implement cascade propagation in run.py: after a section transitions to FINALIZED, check all content-dependent downstream sections. If any were previously finalized and their upstream content has changed (new version), call lifecycle.invalidate_content_dependents() to transition them to INVALIDATED. Track cascade_depth per section in SectionState.cascade_depth. When cascade_depth reaches CASCADE_DEPTH_LIMIT (from config), escalate the section instead of invalidating it (FR-24).",
        "3. Implement reference-dependency re-validation in run.py: when an upstream reference dependency section is re-finalized, call lifecycle.trigger_reference_revalidation() for dependent sections — re-validate their reference pointers but do NOT re-generate content (FR-25).",
        "4. Modify the run loop's main iteration to handle multi-pass processing: cascade invalidations may put previously-finalized sections back into a processable state. The outer loop must repeat until no section changes state in a full pass (convergence). Guard against infinite loops: if a full pass produces no state changes and non-terminal sections remain, log a warning and break.",
        "5. Implement atomic checkpoint writes: after every state transition in the run loop (not just per section, but per transition), serialize RunState to a temporary file then os.rename() to run_state.json. This ensures that a crash mid-write never corrupts the checkpoint.",
        "6. Implement resume-on-restart: at the start of run(), if resume=True, check for existing run_state.json. If found: (a) deserialize into RunState, (b) compare report_plan_version — if mismatch, log warning, discard checkpoint, start fresh, (c) if match, apply resume policy: sections in GENERATING state revert to QUEUED (in-progress generation is lost per NFR-03), all other states preserved, (d) rebuild DAGs from the plan (DAGs are not serialized), (e) continue the main loop from the resumed state.",
        "7. Create synthesizer/assembly/assembler.py with an assemble_report() function. It takes: report_plan (ReportPlan), output_dir (Path), and optionally a base_heading_level (int, default 1). It reads each finalized section's latest draft (draft_v{N}.md where N is the highest version) from output_dir/sections/{section_id}/, concatenates them in the order specified by the report plan's sections array, and adjusts each section's internal markdown headings by its depth_level (e.g., a section at depth_level=2 has its # headings become ### headings). Writes the result to output_dir/report/literature_review.md.",
        "8. Wire assembly into the run loop: after the main iteration loop converges, call lifecycle.check_assembly_readiness() (FR-27). If all sections are in FINALIZED, STABLE, or ESCALATED state, invoke assemble_report(). If any section is in a non-terminal state, raise a descriptive error identifying the blocking sections.",
        "9. Update synthesizer/__main__.py: the --resume flag now triggers the resume logic in run().",
        "10. Write tests/test_cascade_propagation.py: (a) 3-section content chain A→B→C: finalize all three, then simulate re-generation of A with changed content → verify B transitions to INVALIDATED → verify C transitions to INVALIDATED when B is re-finalized with changed content; (b) set CASCADE_DEPTH_LIMIT=2, create a 4-deep chain → verify propagation stops at depth 2 and the section at depth 3 is escalated.",
        "11. Write tests/test_checkpoint_resume.py: (a) run a 2-section plan, let section 1 finalize, then create a partial RunState as if section 2 was in GENERATING when a crash occurred → resume → verify section 1 is still FINALIZED and section 2 restarts from QUEUED; (b) change the plan version in the checkpoint → resume → verify fresh start.",
        "12. Write tests/test_assembly.py: (a) create 4 mock section drafts at depth_levels 1, 2, 2, 1 → assemble → verify heading levels in the output are adjusted correctly (depth_level=1 keeps #, depth_level=2 adjusts to ##, etc.); (b) leave one section in DRAFTED state → attempt assembly → verify AssemblyNotReadyError with descriptive message.",
    ],

    tests_required=[
        "3-section content chain: root changes → dependents invalidated (FR-23)",
        "Cascade stops at CASCADE_DEPTH_LIMIT set to 2 for the test (FR-24)",
        "Reference dep change → re-validate only, no re-generation (FR-25)",
        "Checkpoint file is valid JSON after every state transition (atomic write)",
        "Resume: section in GENERATING reverts to QUEUED (NFR-03)",
        "Resume: plan version mismatch → fresh start with log warning",
        "Assembly: 4 sections at varying depths produce correctly adjusted heading levels (FR-26)",
        "Assembly blocked when a section is in non-terminal state with descriptive error (FR-27)",
        "Multi-section run (all example plan sections) completes end-to-end with assembled report",
    ],

    dependencies=["completion_2"],

    done_definition=[
        "Multi-section run with the full example report plan completes end-to-end and produces report/literature_review.md",
        "Cascade propagation fires when upstream content changes and respects CASCADE_DEPTH_LIMIT",
        "Killing the process mid-run and restarting with --resume recovers from the last checkpoint without re-generating finalized sections",
        "The assembled report has a coherent heading hierarchy matching the report plan's depth_level values",
        "test_cascade_propagation.py, test_checkpoint_resume.py, and test_assembly.py all pass",
        "The output directory matches §15.1 except for run_metrics.json (completion_4)",
        "No existing component test (Steps 1-12) is broken by the changes",
    ],

    open_decisions_to_preserve=["DR-04"],

    handoff_requirements=[
        "run.py produces a complete output directory: run_state.json, sections/{id}/* artifacts, and report/literature_review.md",
        "The only missing output artifact is run_metrics.json (completion_4 will add it to the completion phase)",
        "The run loop's completion phase has a clear insertion point after assembly where completion_4 will add metrics computation",
    ],
)


# ---------------------------------------------------------------------------
# Completion Sprint 4 — Run Metrics and Acceptance Tests
# ---------------------------------------------------------------------------

_COMPLETION_4 = SprintDefinition(
    sprint_id="completion_4",
    title="Run metrics wiring and acceptance test suite",

    objective=(
        "Wire the seven §17.2 metric computation functions (already "
        "implemented in observability/metrics.py) into the run loop's "
        "completion phase so that every run produces a run_metrics.json "
        "file. Implement the five priority acceptance tests from §19 and "
        "create an end-to-end smoke test that validates the full pipeline "
        "against the example corpus. This is the final sprint — on "
        "completion, the package is feature-complete per the governing spec."
    ),

    spec_sections=["§17", "§18", "§19"],

    functional_requirements=["FR-26", "FR-27"],

    non_functional_requirements=["NFR-07", "NFR-08"],

    schema_targets=[],

    integration_targets=[
        "synthesizer/orchestrator/run.py  (from completion_3)",
        "synthesizer/observability/metrics.py",
        "synthesizer/acceptance/",
    ],

    artifacts_in_scope=[
        "synthesizer/orchestrator/run.py  (modify — add build_run_metrics() and save_run_metrics() calls to the completion phase after assembly)",
        "synthesizer/acceptance/__init__.py  (modify — complete the truncated docstring and add module-level imports)",
        "synthesizer/acceptance/test_fr08_dependency_ordering.py  (new — FR-08: content dependency blocks generation until upstream finalized)",
        "synthesizer/acceptance/test_fr18_semantic_validation.py  (new — FR-18: section contradicting upstream claim → L3 failure)",
        "synthesizer/acceptance/test_fr23_cascade_invalidation.py  (new — FR-23: finalize chain → re-generate root → dependents invalidated)",
        "synthesizer/acceptance/test_fr26_assembly_headings.py  (new — FR-26: assembled heading levels match depth_level)",
        "synthesizer/acceptance/test_fr27_assembly_readiness.py  (new — FR-27: non-finalized section blocks assembly)",
        "tests/test_end_to_end_smoke.py  (new — full pipeline against example corpus → run_metrics.json + literature_review.md produced)",
    ],

    implementation_tasks=[
        "1. Read observability/metrics.py and confirm all seven metric computation functions are implemented (not stubs or placeholder 0.0 returns). The seven functions are: compute_structural_compliance_rate(), compute_style_compliance_rate(), compute_dependency_completeness(), compute_unsupported_claim_rate(), compute_revision_churn_index(), compute_claim_table_completeness(), compute_evidence_claim_agreement().",
        "2. In run.py, add a completion phase after assembly: call build_run_metrics(run_state) to compute all seven metrics from the final RunState, then call save_run_metrics(metrics, output_dir) to write run_metrics.json to the output directory. Ensure this runs even if assembly was skipped (e.g., some sections escalated).",
        "3. Verify that each metric produces a real value (not 0.0 placeholder) when given a RunState with actual validation history, claim tables, and section states from a completed run.",
        "4. Complete synthesizer/acceptance/__init__.py: fix the truncated docstring, add a module docstring referencing §19, and set up any shared test fixtures (e.g., example plan/style sheet loading, output directory setup/teardown).",
        "5. Implement test_fr08_dependency_ordering.py: create a 3-section plan with content dependencies A→B→C. Attempt to process C before A is finalized. Assert C remains in QUEUED state. Finalize A, then process B and C. Assert correct ordering.",
        "6. Implement test_fr18_semantic_validation.py: create a section whose content contradicts an upstream claim table entry. Run through the validator with skip_layer3=False. Assert L3 sub-check B (dependency contract fulfillment) returns failure identifying the unengaged or contradicted claim.",
        "7. Implement test_fr23_cascade_invalidation.py: create a 3-section content chain A→B→C. Finalize all three. Re-generate A with changed content. Assert B transitions to INVALIDATED. Re-process B; assert C transitions to INVALIDATED when B is re-finalized with changed content.",
        "8. Implement test_fr26_assembly_headings.py: finalize 4 sections at depth_levels 1, 2, 2, 1. Assemble the report. Assert heading levels in the output markdown match: depth 1 → level 1 headings, depth 2 → level 2 headings.",
        "9. Implement test_fr27_assembly_readiness.py: leave one section in DRAFTED state. Attempt assembly. Assert AssemblyNotReadyError is raised with a message identifying the non-finalized section.",
        "10. Create tests/test_end_to_end_smoke.py: load examples/example_report_plan.json and examples/example_style_sheet.json, point the output directory to a temporary path, run the full pipeline via run(). Assert: (a) run_metrics.json exists and contains all seven metric keys, (b) report/literature_review.md exists and is non-empty, (c) each section in the plan has a sections/{section_id}/provenance.json, (d) no metric value is the placeholder 0.0 (where data exists to compute it — escalated sections may legitimately produce 0.0 for some metrics).",
        "11. Run all existing component tests (Steps 1-12 equivalents) to verify no regressions.",
    ],

    tests_required=[
        "run_metrics.json is produced in the output directory with all 7 metric keys: structural_compliance_rate, style_compliance_rate, dependency_completeness, unsupported_claim_rate, revision_churn_index, claim_table_completeness, evidence_claim_agreement",
        "No metric returns placeholder 0.0 when actual run data is available to compute it",
        "Acceptance test FR-08 passes: content dependency ordering enforced",
        "Acceptance test FR-18 passes: L3 sub-check B detects contradiction",
        "Acceptance test FR-23 passes: cascade invalidation propagates",
        "Acceptance test FR-26 passes: assembly heading levels correct",
        "Acceptance test FR-27 passes: assembly blocked by non-finalized section",
        "End-to-end smoke test passes: full pipeline produces run_metrics.json + literature_review.md with real data",
    ],

    dependencies=["completion_3"],

    done_definition=[
        "Every run produces run_metrics.json with all seven §17.2 metrics computed from actual run data",
        "All five priority acceptance tests (FR-08, FR-18, FR-23, FR-26, FR-27) pass",
        "End-to-end smoke test passes against the example corpus with the example report plan and style sheet",
        "The full output directory matches §15.1: run_state.json, run_metrics.json, sections/{id}/* artifacts, report/literature_review.md",
        "'python -m synthesizer --report-plan examples/example_report_plan.json --style-sheet examples/example_style_sheet.json' produces a complete report with metrics — this is the user-facing definition of done",
        "No existing component test (Steps 1-12) is broken",
        "The package is feature-complete per the governing specification",
    ],

    open_decisions_to_preserve=[],

    handoff_requirements=[
        "The package is feature-complete — no further implementation sprints are planned",
        "Tutorial documents 01–05 accurately describe the runnable workflow and only need the addition of concrete CLI commands (cosmetic update, not a sprint)",
        "The acceptance test suite provides a regression safety net for any future maintenance",
    ],
)


# ---------------------------------------------------------------------------
# Sprint registry
# ---------------------------------------------------------------------------

COMPLETION_SPRINTS: List[SprintDefinition] = [
    _COMPLETION_1,
    _COMPLETION_2,
    _COMPLETION_3,
    _COMPLETION_4,
]

COMPLETION_SPRINTS_BY_ID: Dict[str, SprintDefinition] = {
    s.sprint_id: s for s in COMPLETION_SPRINTS
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_sprint(sprint_id: str) -> SprintDefinition:
    """Return a completion sprint by ID or raise KeyError."""
    if sprint_id not in COMPLETION_SPRINTS_BY_ID:
        raise KeyError(
            f"Unknown sprint_id: {sprint_id!r}. "
            f"Valid IDs: {list_sprint_ids()}"
        )
    return COMPLETION_SPRINTS_BY_ID[sprint_id]


def list_sprint_ids() -> List[str]:
    """Return ordered list of completion sprint IDs."""
    return [s.sprint_id for s in COMPLETION_SPRINTS]


def get_existing_modules() -> Dict[str, str]:
    """Return the codebase inventory of existing modules and their exports."""
    return dict(EXISTING_MODULES)


def get_component_test_scorecard() -> List[str]:
    """Return the 12-step component test verification results."""
    return list(COMPONENT_TEST_SCORECARD)


def get_resolved_bugs() -> List[str]:
    """Return the list of bugs found and resolved during component testing."""
    return list(RESOLVED_BUGS)


def validate_completion_sprint_registry() -> None:
    """Check the registry for duplicate IDs and missing dependency references.

    Also verifies that no completion sprint depends on the original
    sprint_1 through sprint_6 (those are already completed and are
    not in this registry).

    Raises ValueError with a descriptive message on any violation.
    """
    seen_ids: set[str] = set()
    errors: List[str] = []

    for sprint in COMPLETION_SPRINTS:
        if sprint.sprint_id in seen_ids:
            errors.append(f"Duplicate sprint_id: {sprint.sprint_id!r}")
        seen_ids.add(sprint.sprint_id)

    for sprint in COMPLETION_SPRINTS:
        for dep in sprint.dependencies:
            if dep not in seen_ids:
                errors.append(
                    f"Sprint {sprint.sprint_id!r} depends on {dep!r} "
                    f"which is not in the completion registry"
                )

    # Verify no dependency on original sprint IDs
    original_ids = {f"sprint_{i}" for i in range(1, 7)}
    for sprint in COMPLETION_SPRINTS:
        for dep in sprint.dependencies:
            if dep in original_ids:
                errors.append(
                    f"Sprint {sprint.sprint_id!r} depends on original "
                    f"sprint {dep!r} — original sprints are already "
                    f"completed and should not be referenced"
                )

    # Verify dependency ordering is acyclic (simple topological check)
    resolved: set[str] = set()
    remaining = list(COMPLETION_SPRINTS)
    max_passes = len(remaining) + 1
    for _ in range(max_passes):
        if not remaining:
            break
        next_remaining = []
        for sprint in remaining:
            if all(dep in resolved for dep in sprint.dependencies):
                resolved.add(sprint.sprint_id)
            else:
                next_remaining.append(sprint)
        if len(next_remaining) == len(remaining):
            cycle_ids = [s.sprint_id for s in next_remaining]
            errors.append(
                f"Dependency cycle detected among: {cycle_ids}"
            )
            break
        remaining = next_remaining

    if errors:
        raise ValueError(
            "Completion sprint registry validation failed:\n  "
            + "\n  ".join(errors)
        )


# ---------------------------------------------------------------------------
# Run validation on import so errors surface immediately.
# ---------------------------------------------------------------------------
validate_completion_sprint_registry()