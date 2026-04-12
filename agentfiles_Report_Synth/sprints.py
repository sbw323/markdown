"""
Sprint plan registry for the Report Synthesizer Agent orchestrator.

Source of truth: the governing v4 design specification (report_synthesizer_v4.md).
Each sprint is traceable to specific functional requirements (FR-XX),
non-functional requirements (NFR-XX), schema definitions (§10), and
acceptance tests (§19).

Prompts are intentionally excluded from this file and belong in prompts.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class SprintDefinition:
    """A single implementation sprint in the orchestrator build plan."""

    sprint_id: str
    """Unique identifier, e.g. 'sprint_1'."""

    title: str
    """Short human-readable sprint title."""

    objective: str
    """One-paragraph statement of what this sprint achieves."""

    spec_sections: List[str]
    """Governing spec sections (e.g. '§4', '§10.2') that apply."""

    functional_requirements: List[str]
    """FR-XX IDs in scope for this sprint."""

    non_functional_requirements: List[str]
    """NFR-XX IDs in scope for this sprint."""

    schema_targets: List[str]
    """Pydantic model / enum names from §10 that must be implemented or consumed."""

    integration_targets: List[str]
    """External modules or interfaces this sprint integrates with."""

    artifacts_in_scope: List[str]
    """Concrete code artifacts (files, classes, functions) to be produced."""

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
# Sprint definitions
# ---------------------------------------------------------------------------

_SPRINT_1 = SprintDefinition(
    sprint_id="sprint_1",
    title="Foundation contracts and loaders",
    objective=(
        "Establish the synthesizer's configuration surface, all enumerations and "
        "foundational Pydantic schemas from §10, report-plan loading/validation "
        "(including dependency-reference validation and content-cycle detection), "
        "style-sheet loading/validation, and source-of-truth hierarchy enforcement. "
        "After this sprint every downstream sprint can import validated ReportPlan "
        "and StyleSheet objects and all shared enums/models."
    ),
    spec_sections=[
        "§1", "§2", "§3", "§7", "§10.1", "§10.2", "§10.3", "§10.4",
        "§10.5", "§16",
    ],
    functional_requirements=[
        "FR-01", "FR-02", "FR-03", "FR-04", "FR-05", "FR-06",
    ],
    non_functional_requirements=[
        "NFR-09",
    ],
    schema_targets=[
        "DependencyKind", "SectionType", "SectionLifecycleState",
        "ValidationLayer", "ConfidenceTag", "ViolationSeverity",
        "ReportPlan", "SectionNode", "DependencyEdge",
        "StyleSheet", "LevelConstraint", "EquationDelimiters",
    ],
    integration_targets=[
        "config.py (add synthesizer keys from §16)",
    ],
    artifacts_in_scope=[
        "synthesizer/models/enums.py",
        "synthesizer/models/report_plan.py",
        "synthesizer/models/style_sheet.py",
        "synthesizer/config.py (synthesizer-specific config surface)",
        "synthesizer/loaders/plan_loader.py",
        "synthesizer/loaders/style_loader.py",
        "synthesizer/validation/graph_validation.py",
        "tests/test_plan_loader.py",
        "tests/test_style_loader.py",
        "tests/test_graph_validation.py",
    ],
    implementation_tasks=[
        "Define all six enumerations from §10.1 as Python str/Enum classes",
        "Implement ReportPlan, SectionNode, DependencyEdge Pydantic models with all field constraints from §10.2–10.4",
        "Implement StyleSheet, LevelConstraint, EquationDelimiters Pydantic models with all field constraints from §10.5",
        "Add synthesizer configuration keys to config surface per §16 (REPORT_PLAN_PATH, STYLE_SHEET_PATH, SYNTHESIZER_OUTPUT_DIR, CASCADE_DEPTH_LIMIT, retry limits, SYNTHESIZER_MODEL, TOKEN_BUDGET_CEILING)",
        "Implement report-plan loader: read JSON from REPORT_PLAN_PATH, parse into ReportPlan, validate all section_ids in dependency_edges exist (FR-02)",
        "Implement content-dependency cycle detection via topological sort on content-type edges (FR-03)",
        "Implement style-sheet loader: read JSON from STYLE_SHEET_PATH, parse into StyleSheet, validate citation_pattern as compilable regex (FR-04)",
        "Implement depth_level consistency check: verify each section's depth_level equals its ancestor chain length",
        "Implement source-of-truth hierarchy rule: plan is Tier 1, style sheet is Tier 2, filesystem is derived (§7)",
        "Write unit tests for valid and invalid plan loading (FR-01 acceptance test)",
        "Write unit tests for dangling dependency ref detection (FR-02 acceptance test)",
        "Write unit tests for cycle detection (FR-03 acceptance test)",
        "Write unit tests for valid and invalid style-sheet loading (FR-04 acceptance test)",
        "Write unit test for per-type override presence check (FR-05 acceptance test, load-time only)",
        "Write unit test for DAG construction from valid edges (FR-06 acceptance test, structure only)",
    ],
    tests_required=[
        "test_load_valid_report_plan: valid JSON -> parsed ReportPlan with all fields",
        "test_load_malformed_report_plan: malformed JSON -> descriptive ValidationError",
        "test_dangling_dependency_ref: plan with nonexistent target_section_id -> error naming the ID",
        "test_content_cycle_detection: A->B->C->A content cycle -> error identifying cycle",
        "test_no_false_positive_cycle: thematic/reference/source edges forming a cycle do NOT trigger content-cycle error",
        "test_load_valid_style_sheet: valid JSON -> parsed StyleSheet",
        "test_invalid_citation_regex: style sheet with bad regex -> validation error",
        "test_depth_level_consistency: section depth != ancestor chain length -> error",
        "test_config_keys_present: all §16 keys are importable with correct defaults",
    ],
    dependencies=[],
    done_definition=[
        "All six enums importable and match §10.1 values exactly",
        "ReportPlan, SectionNode, DependencyEdge validate correct inputs and reject invalid ones per §10.2–10.4 constraints",
        "StyleSheet, LevelConstraint, EquationDelimiters validate correct inputs and reject invalid ones per §10.5 constraints",
        "Plan loader rejects dangling refs with descriptive error",
        "Plan loader rejects content-dependency cycles with descriptive error",
        "Style-sheet loader rejects uncompilable citation_pattern",
        "Config surface exposes all §16 keys with documented defaults",
        "All listed tests pass",
        "DR-16, DR-17, DR-18 remain configurable/open (not hardcoded)",
    ],
    open_decisions_to_preserve=[
        "DR-16 (model selection per role — SYNTHESIZER_MODEL is a placeholder)",
        "DR-17 (TOKEN_BUDGET_CEILING defaults to None / no limit)",
        "DR-18 (input token budgets per prompt role remain open)",
    ],
    handoff_requirements=[
        "Stable enum module importable by all downstream sprints",
        "Stable ReportPlan / SectionNode / DependencyEdge models",
        "Stable StyleSheet / LevelConstraint / EquationDelimiters models",
        "Stable plan-loader and style-loader interfaces returning validated objects",
        "Stable graph-validation helpers (cycle detection, dangling-ref check)",
        "Stable config surface with all §16 keys",
    ],
)

_SPRINT_2 = SprintDefinition(
    sprint_id="sprint_2",
    title="DAGs, section state, run state, checkpointing, and filesystem contract",
    objective=(
        "Build the generation DAG and finalization DAG from validated dependency "
        "edges, implement SectionState and RunState models, define lifecycle "
        "precondition evaluation (content-dependency gating), implement checkpoint "
        "persistence and resume, and enforce the directory/artifact layout from §15."
    ),
    spec_sections=[
        "§8", "§10.12", "§10.13", "§11", "§15",
    ],
    functional_requirements=[
        "FR-06", "FR-07", "FR-08", "FR-23", "FR-24", "FR-25", "FR-27",
    ],
    non_functional_requirements=[
        "NFR-03", "NFR-04",
    ],
    schema_targets=[
        "SectionState", "RunState", "SectionLifecycleState",
    ],
    integration_targets=[],
    artifacts_in_scope=[
        "synthesizer/models/state.py (SectionState, RunState)",
        "synthesizer/dag.py (generation DAG, finalization DAG, topo ordering)",
        "synthesizer/orchestrator/lifecycle.py (precondition checks, state transitions)",
        "synthesizer/orchestrator/checkpoint.py (persist / load RunState)",
        "synthesizer/filesystem.py (directory creation from plan, naming conventions)",
        "tests/test_dag.py",
        "tests/test_lifecycle.py",
        "tests/test_checkpoint.py",
        "tests/test_filesystem.py",
    ],
    implementation_tasks=[
        "Implement SectionState Pydantic model per §10.12 with all fields and defaults",
        "Implement RunState Pydantic model per §10.13 with all fields and defaults",
        "Build generation DAG from content-dependency edges only (FR-06)",
        "Build finalization DAG from content + reference edges (FR-07)",
        "Implement topological-order iterator over generation DAG",
        "Implement prerequisites_met check: all content predecessors in finalized state (FR-08)",
        "Implement finalization gating: reference predecessors must be finalized before section can finalize (FR-07)",
        "Implement cascade invalidation: on upstream content change, invalidate all content dependents recursively up to CASCADE_DEPTH_LIMIT (FR-23, FR-24)",
        "Implement reference-change re-validation trigger (FR-25): re-validate pointers without re-generating",
        "Implement checkpoint writer: serialize RunState to run_state.json after every checkpoint-worthy transition (§11.3)",
        "Implement checkpoint loader with resume algorithm from §11.3 (reset generating->queued, retain other states)",
        "Implement directory scaffolder: create §15 directory structure from report plan at run start",
        "Implement assembly pre-check: all sections must be finalized/stable/escalated before assembly (FR-27)",
        "Write tests for DAG construction correctness (FR-06 acceptance)",
        "Write tests for content-dependency gating (FR-08 acceptance: C queued until A finalized)",
        "Write tests for reference-dependency gating (FR-07 acceptance: gen before ref finalized OK, finalize blocked)",
        "Write tests for cascade propagation and depth limit (FR-23, FR-24 acceptance)",
        "Write tests for checkpoint round-trip (persist, kill, reload, verify states)",
        "Write tests for directory creation from plan",
    ],
    tests_required=[
        "test_generation_dag_adjacency: 5-section plan -> correct adjacency and topo order",
        "test_finalization_dag_includes_reference_edges: ref edges present in finalization DAG but not generation DAG",
        "test_content_dependency_blocks_generation: C stays queued until A finalized",
        "test_reference_dependency_blocks_finalization_not_generation: B generates before C finalized; B cannot finalize before C finalized",
        "test_cascade_invalidation: re-generate A -> B invalidated -> C invalidated on B re-finalization",
        "test_cascade_depth_limit: 5-section chain, cascade stops at depth 3",
        "test_reference_change_revalidates_not_regenerates: heading change triggers pointer re-validation only",
        "test_checkpoint_roundtrip: persist RunState, reload, verify identical section states",
        "test_resume_resets_generating_to_queued: section in generating at crash -> queued on resume",
        "test_assembly_blocked_if_section_not_finalized: one drafted section -> assembly blocked with descriptive error",
        "test_directory_structure_matches_plan: created dirs match §15 layout",
    ],
    dependencies=["sprint_1"],
    done_definition=[
        "SectionState and RunState models validate per §10.12–10.13",
        "Generation DAG contains only content edges; finalization DAG contains content + reference edges",
        "Topological iterator yields correct order",
        "Content-dependency gating prevents premature generation",
        "Reference-dependency gating prevents premature finalization",
        "Cascade invalidation respects CASCADE_DEPTH_LIMIT",
        "Checkpoint persist/load round-trips correctly",
        "Resume algorithm resets generating->queued per §11.3",
        "Directory scaffolder creates §15 layout from any valid plan",
        "Assembly pre-check rejects non-finalized sections",
        "All listed tests pass",
    ],
    open_decisions_to_preserve=[
        "DR-15 (sequential execution; schemas are concurrency-safe but orchestrator runs one section at a time)",
    ],
    handoff_requirements=[
        "Stable SectionState and RunState models",
        "Stable DAG construction and topological iterator",
        "Stable prerequisites_met and finalization-gating interfaces",
        "Stable cascade-invalidation interface",
        "Stable checkpoint persist/load contract",
        "Stable directory scaffolder",
    ],
)

_SPRINT_3 = SprintDefinition(
    sprint_id="sprint_3",
    title="Retrieval integration and generation prompt assembly",
    objective=(
        "Integrate with Stage 05 HybridRetriever for per-section retrieval, "
        "consume Stage 06 PaperSummary data for planning context only, assemble "
        "generation prompts with all context channels (chunks, upstream claim "
        "tables, upstream summary abstracts, section description, style constraints), "
        "enforce exclusion of Stage 05 answer text and raw upstream prose, and "
        "package generation inputs by section type."
    ),
    spec_sections=[
        "§9.2.1", "§13", "§14",
    ],
    functional_requirements=[
        "FR-09", "FR-10", "FR-11", "FR-12", "FR-13",
    ],
    non_functional_requirements=[],
    schema_targets=[
        "SectionOutput", "NarrativeSynthesisOutput", "EvidenceTableOutput",
        "CrossReferenceOutput", "MethodologyDescriptionOutput",
    ],
    integration_targets=[
        "05_query.py HybridRetriever.query()",
        "06_review.py load_all_summaries()",
    ],
    artifacts_in_scope=[
        "synthesizer/models/section_output.py (SectionOutput base + 4 subclasses)",
        "synthesizer/retrieval/adapter.py (thin wrapper around HybridRetriever)",
        "synthesizer/retrieval/planning_context.py (Stage 06 summary loader for planning only)",
        "synthesizer/prompt/context_channels.py (claim table packaging, summary abstract packaging, evidence pointer packaging)",
        "synthesizer/prompt/assembly.py (full prompt assembly per section type)",
        "tests/test_retrieval_adapter.py",
        "tests/test_prompt_assembly.py",
    ],
    implementation_tasks=[
        "Implement SectionOutput base Pydantic model per §10.8",
        "Implement four SectionOutput subclasses per §10.9 (NarrativeSynthesisOutput, EvidenceTableOutput, CrossReferenceOutput, MethodologyDescriptionOutput)",
        "Implement retrieval adapter: call HybridRetriever.query() for each source_query in SectionNode.source_queries, aggregate ranked chunks, discard answer_text (FR-09, FR-10, DR-05)",
        "Implement planning-context loader: call load_all_summaries() from 06_review.py, expose PaperSummary data for query construction only, never inject into generation prompts (DR-06)",
        "Implement claim-table context packager: serialize upstream ClaimTable objects for insertion into prompts (§13.1)",
        "Implement summary-abstract context packager: serialize upstream summary_abstract strings for thematic deps (§13.2)",
        "Implement evidence-pointer packager: format ranked chunks with ID, text, metadata, score (§13.3)",
        "Implement prompt assembly function: compose system prompt + user message per §9.2.1, including section description, section type, retrieved chunks, upstream claim tables (content deps), upstream summary abstracts (thematic deps), style constraints, and retry error feedback slot",
        "Enforce exclusion: assert no answer_text in assembled prompt (FR-10)",
        "Enforce exclusion: assert no raw upstream content_markdown in assembled prompt (FR-12, DR-03)",
        "Implement section-type dispatch: select correct SectionOutput subclass based on SectionNode.section_type (FR-13)",
        "Write integration test: section with 2 source_queries -> both executed, chunks aggregated (FR-09 acceptance)",
        "Write inspection test: assembled prompt contains chunks but no answer_text (FR-10 acceptance)",
        "Write inspection test: prompt for section with content+thematic deps contains claim table, summary abstract, chunks, description, style constraints (FR-11 acceptance)",
        "Write inspection test: no raw upstream prose in any downstream prompt (FR-12 acceptance)",
        "Write unit test: each section type output parses as correct subclass (FR-13 acceptance)",
    ],
    tests_required=[
        "test_retrieval_executes_all_source_queries: 2 queries -> both executed, chunks aggregated",
        "test_answer_text_discarded: assembled prompt does not contain Stage 05 answer text",
        "test_prompt_contains_all_context_channels: claim table + summary abstract + chunks + description + style constraints present",
        "test_no_raw_upstream_prose: no full content_markdown from upstream in prompt",
        "test_section_output_type_dispatch: narrative_synthesis -> NarrativeSynthesisOutput, etc.",
        "test_stage06_summaries_not_in_generation_prompt: PaperSummary data absent from generation prompt",
    ],
    dependencies=["sprint_1", "sprint_2"],
    done_definition=[
        "SectionOutput base + 4 subclasses validate per §10.8–10.9",
        "Retrieval adapter calls HybridRetriever.query() and returns ranked chunks only",
        "Answer text from Stage 05 is provably excluded from all prompts",
        "Raw upstream prose is provably excluded from all prompts",
        "Stage 06 summaries are consumed for planning only, never as generation evidence",
        "Prompt assembly produces a complete prompt with all five context-channel inputs from §9.2.1",
        "Section-type dispatch selects correct output subclass",
        "All listed tests pass",
    ],
    open_decisions_to_preserve=[
        "DR-05 (Stage 05 answer text exclusion — enforced, not optional)",
        "DR-06 (Stage 06 summaries for planning only — enforced, not optional)",
        "DR-18 (input token budgets per prompt role remain open; prompt assembly does not enforce a ceiling yet)",
    ],
    handoff_requirements=[
        "Stable SectionOutput base + 4 subclass models",
        "Stable retrieval adapter interface returning ranked chunks",
        "Stable prompt assembly interface producing complete generation prompts",
        "Stable context-channel packaging interfaces (claim tables, summary abstracts, evidence pointers)",
    ],
)

_SPRINT_4 = SprintDefinition(
    sprint_id="sprint_4",
    title="Validation engine and retry/escalation behavior",
    objective=(
        "Implement the three-layer validation pipeline (Layer 1 structural, "
        "Layer 2 rule-based, Layer 3 semantic), retry counters with error-feedback "
        "prompt re-assembly, escalation-state transitions on retry exhaustion, "
        "and validation history accumulation in SectionState."
    ),
    spec_sections=[
        "§9.2.2", "§10.10", "§11", "§12",
    ],
    functional_requirements=[
        "FR-14", "FR-15", "FR-16", "FR-17", "FR-18", "FR-19",
    ],
    non_functional_requirements=[
        "NFR-05",
    ],
    schema_targets=[
        "ValidationResult", "Violation", "ViolationSeverity", "ValidationLayer",
    ],
    integration_targets=[],
    artifacts_in_scope=[
        "synthesizer/models/validation.py (ValidationResult, Violation)",
        "synthesizer/validation/layer1_structural.py",
        "synthesizer/validation/layer2_rules.py",
        "synthesizer/validation/layer3_semantic.py",
        "synthesizer/validation/coordinator.py (sequential layer orchestration)",
        "synthesizer/validation/retry.py (retry counters, feedback assembly, escalation)",
        "tests/test_layer1.py",
        "tests/test_layer2.py",
        "tests/test_layer3.py",
        "tests/test_retry_escalation.py",
    ],
    implementation_tasks=[
        "Implement ValidationResult and Violation Pydantic models per §10.10",
        "Implement Layer 1 structural validation: parse Generator JSON output against type-specific SectionOutput model via Pydantic; return field-level errors on failure (FR-14)",
        "Implement Layer 1 retry: append error list to regeneration prompt, re-invoke Generator up to LAYER1_RETRY_LIMIT (FR-15)",
        "Implement Layer 2 rule-based validation: word count vs per_level_constraints, heading level check, citation_pattern regex match, forbidden_phrases scan, equation_delimiters check, per_type_overrides application (FR-16, FR-05)",
        "Implement Layer 2 retry: append violation list to regeneration prompt, re-invoke Generator up to LAYER2_RETRY_LIMIT (FR-17)",
        "Implement Layer 3 semantic validation with three sub-checks: tone compliance, dependency contract fulfillment, unsupported claim detection (FR-18)",
        "Implement Layer 3 retry: on any sub-check failure, re-generate entire section up to LAYER3_RETRY_LIMIT; on exhaustion transition to escalated (FR-19)",
        "Implement validation coordinator: run L1 -> L2 -> L3 sequentially; short-circuit on failure",
        "Implement retry-counter management in SectionState.retry_counters",
        "Implement error-feedback assembly: format validation errors/violations for inclusion in retry prompts",
        "Implement escalation transition: set SectionState.state to ESCALATED when any layer exhausts retries",
        "Accumulate ValidationResult objects in SectionState.validation_history",
        "Ensure retry limits are read from config (LAYER1_RETRY_LIMIT, LAYER2_RETRY_LIMIT, LAYER3_RETRY_LIMIT) and are independently configurable (NFR-05)",
        "Write unit test: SectionOutput with missing field -> Layer 1 failure with field-level error (FR-14 acceptance)",
        "Write unit test: Layer 1 failure -> retry prompt includes error; count <= LAYER1_RETRY_LIMIT (FR-15 acceptance)",
        "Write unit test: word_count exceeds max -> Layer 2 failure identifying constraint (FR-16 acceptance)",
        "Write unit test: Layer 2 failure -> retry with violations; limit enforced (FR-17 acceptance)",
        "Write integration test: section contradicts upstream claim -> dependency contract sub-check fails (FR-18 acceptance)",
        "Write integration test: Layer 3 fails 3x with limit=2 -> escalated (FR-19 acceptance)",
        "Write unit test: set LAYER1_RETRY_LIMIT=1 -> only 1 retry occurs (NFR-05 acceptance)",
    ],
    tests_required=[
        "test_layer1_missing_field: SectionOutput missing required field -> Layer 1 failure with field-level error",
        "test_layer1_retry_with_feedback: failure -> retry prompt includes error description; count respects limit",
        "test_layer1_retry_exhaustion_escalates: exceed LAYER1_RETRY_LIMIT -> escalated",
        "test_layer2_word_count_violation: word_count > max -> Layer 2 failure",
        "test_layer2_forbidden_phrase_detected: forbidden phrase present -> violation",
        "test_layer2_citation_format_violation: citation not matching pattern -> violation",
        "test_layer2_retry_with_violations: failure -> retry prompt includes violations; limit enforced",
        "test_layer2_retry_exhaustion_escalates: exceed LAYER2_RETRY_LIMIT -> escalated",
        "test_layer3_tone_compliance_failure: wrong tone -> sub-check A fails",
        "test_layer3_dependency_contract_failure: unengaged upstream claim -> sub-check B fails",
        "test_layer3_unsupported_claim_failure: claim not traceable -> sub-check C fails",
        "test_layer3_retry_exhaustion_escalates: exceed LAYER3_RETRY_LIMIT -> escalated",
        "test_retry_limits_independently_configurable: change one limit without affecting others",
        "test_validation_history_accumulated: all ValidationResults recorded in SectionState",
    ],
    dependencies=["sprint_1", "sprint_2", "sprint_3"],
    done_definition=[
        "ValidationResult and Violation models validate per §10.10",
        "Layer 1 catches all schema violations and returns field-level errors",
        "Layer 2 enforces all style-sheet constraints listed in §12.2",
        "Layer 3 executes all three sub-checks and aggregates results",
        "Retry counters respect per-layer configurable limits",
        "Escalation transitions fire on retry exhaustion at any layer",
        "Error/violation feedback is correctly formatted and included in retry prompts",
        "Validation history accumulates in SectionState",
        "All listed tests pass",
    ],
    open_decisions_to_preserve=[
        "DR-16 (Layer 3 may use a lighter model — model selection remains configurable per role)",
        "DR-18 (Layer 3 output token budget is 1000 per sub-check per spec, but input budget is open)",
    ],
    handoff_requirements=[
        "Stable ValidationResult / Violation models",
        "Stable Layer 1, Layer 2, Layer 3 validation interfaces",
        "Stable validation coordinator interface (run all layers sequentially)",
        "Stable retry-counter and escalation interfaces",
        "Stable error-feedback assembly interface for retry prompts",
    ],
)

_SPRINT_5 = SprintDefinition(
    sprint_id="sprint_5",
    title="Claim extraction, summary abstraction, cascades, and final assembly",
    objective=(
        "Implement claim-table extraction and its four validation sub-checks, "
        "partial claim-table fallback, summary abstract generation, cascade "
        "propagation on upstream content changes, deterministic final assembly "
        "with heading-level adjustment, and finalization gating."
    ),
    spec_sections=[
        "§9.2.3", "§9.2.4", "§9.2.5", "§10.6", "§10.7", "§10.8", "§10.11",
        "§11", "§12.4", "§13",
    ],
    functional_requirements=[
        "FR-20", "FR-21", "FR-22", "FR-23", "FR-24", "FR-25", "FR-26", "FR-27",
    ],
    non_functional_requirements=[
        "NFR-04",
    ],
    schema_targets=[
        "ClaimEntry", "TextSpan", "ClaimTable", "ProvenanceRecord",
    ],
    integration_targets=[],
    artifacts_in_scope=[
        "synthesizer/models/claims.py (ClaimEntry, TextSpan, ClaimTable)",
        "synthesizer/models/provenance.py (ProvenanceRecord)",
        "synthesizer/extraction/claim_extractor.py",
        "synthesizer/extraction/claim_validator.py (4 sub-checks)",
        "synthesizer/extraction/summary_abstractifier.py",
        "synthesizer/orchestrator/cascade.py (invalidation propagation)",
        "synthesizer/assembly/assembler.py (deterministic concatenation)",
        "tests/test_claim_extraction.py",
        "tests/test_claim_validation.py",
        "tests/test_summary_abstractifier.py",
        "tests/test_cascade.py",
        "tests/test_assembler.py",
    ],
    implementation_tasks=[
        "Implement ClaimEntry, TextSpan, ClaimTable Pydantic models per §10.6–10.7",
        "Implement ProvenanceRecord Pydantic model per §10.11",
        "Implement claim extractor: invoke LLM with finalized section text + retrieval chunks, parse ClaimTable JSON (§9.2.3, FR-20)",
        "Implement claim-table validation with four sub-checks: completeness (>=90% claims covered), traceability (each entry has >=1 source_chunk_id), label consistency (confidence_tag appropriate), cross-validation (no contradiction with section text) (FR-21)",
        "Implement partial claim-table fallback: on extraction retry exhaustion (CLAIM_EXTRACTION_RETRY_LIMIT), set partial=True and proceed (FR-22)",
        "Implement summary abstractifier: invoke LLM to produce 2-3 sentence summary (50-100 words) from finalized section text (§9.2.4)",
        "Implement summary abstractifier length-violation retry: if >100 words or <20 words, regenerate with tighter instruction; on second failure use truncation fallback",
        "Implement cascade propagation: when finalized section content changes, invalidate all content dependents recursively, respecting CASCADE_DEPTH_LIMIT (FR-23, FR-24, NFR-04)",
        "Implement reference-change re-validation: on upstream reference change, re-validate pointers without re-generating (FR-25)",
        "Implement deterministic assembler: traverse report plan hierarchy in order, adjust heading levels per depth_level, concatenate finalized content_markdown (FR-26, §9.2.5)",
        "Implement assembly pre-check: block assembly if any section is not finalized/stable/escalated (FR-27)",
        "Implement provenance record writer: write ProvenanceRecord JSON on section finalization",
        "Write integration test: finalized section -> ClaimTable with >=1 ClaimEntry (FR-20 acceptance)",
        "Write unit test: ClaimEntry missing source_chunk_ids -> traceability sub-check fails (FR-21 acceptance)",
        "Write unit test: extraction failure after retry -> partial=True, downstream warned (FR-22 acceptance)",
        "Write integration test: cascade from root of 5-section chain stops at depth 3 (FR-24 acceptance)",
        "Write integration test: 4 sections at varying depths -> assembled heading levels match depth_level (FR-26 acceptance)",
        "Write integration test: one section in drafted state -> assembly blocked (FR-27 acceptance)",
    ],
    tests_required=[
        "test_claim_table_produced: finalized section -> ClaimTable with >=1 entry",
        "test_claim_traceability_failure: entry missing source_chunk_ids -> traceability sub-check fails",
        "test_claim_completeness_check: <90% claims covered -> completeness fails",
        "test_claim_label_consistency: directly_stated tag on inferred claim -> label consistency fails",
        "test_claim_cross_validation: claim contradicts section text -> cross-validation fails",
        "test_partial_claim_fallback: extraction fails after CLAIM_EXTRACTION_RETRY_LIMIT -> partial=True, downstream warned",
        "test_summary_abstract_length: output 50-100 words, 2-3 sentences",
        "test_summary_abstract_length_violation_retry: >100 words -> regenerate; second failure -> truncation fallback",
        "test_cascade_invalidation_chain: A->B->C content chain, re-gen A -> B invalidated -> C invalidated",
        "test_cascade_depth_limit: 5-section chain, stops at CASCADE_DEPTH_LIMIT",
        "test_reference_revalidation_no_regeneration: ref target heading changes -> pointer re-validated, content unchanged",
        "test_assembler_heading_levels: sections at depth 0,1,2 -> headings at correct levels",
        "test_assembler_blocked_on_non_finalized: one drafted section -> descriptive error",
        "test_provenance_record_written: finalization -> provenance.json exists with required fields",
    ],
    dependencies=["sprint_2", "sprint_3", "sprint_4"],
    done_definition=[
        "ClaimEntry, TextSpan, ClaimTable, ProvenanceRecord models validate per §10.6–10.7, §10.11",
        "Claim extractor produces validated ClaimTable from finalized sections",
        "All four claim-table validation sub-checks implemented and enforce §12.4 rules",
        "Partial claim-table fallback sets partial=True and allows downstream to proceed with warning",
        "Summary abstractifier produces 2-3 sentence summaries within word limits",
        "Cascade propagation invalidates content dependents and respects depth limit",
        "Reference-change triggers re-validation without re-generation",
        "Assembler concatenates finalized sections in plan order with correct heading levels",
        "Assembly is blocked if any section is not finalized/stable/escalated",
        "Provenance records are written on finalization",
        "All listed tests pass",
    ],
    open_decisions_to_preserve=[
        "DR-14 (CLAIM_EXTRACTION_RETRY_LIMIT=1 is the default but remains configurable)",
        "DR-16 (claim extractor and summary abstractifier may use lighter models)",
        "DR-18 (claim extractor output budget is 2000 tokens, summary abstractifier is 200 tokens per spec; input budgets remain open)",
    ],
    handoff_requirements=[
        "Stable ClaimTable and ClaimEntry models",
        "Stable claim-extraction and claim-validation interfaces",
        "Stable summary-abstractifier interface",
        "Stable cascade-propagation interface",
        "Stable assembler interface producing final Markdown",
        "Stable ProvenanceRecord model and writer",
    ],
)

_SPRINT_6 = SprintDefinition(
    sprint_id="sprint_6",
    title="Observability, metrics, budget control, model/error handling, and acceptance harness",
    objective=(
        "Implement structured log events for all state transitions, post-run "
        "metrics computation and persistence, cumulative token accounting with "
        "budget ceiling enforcement, model availability checks with graceful "
        "degradation, and an acceptance-test harness supporting the traceability "
        "matrix from §18."
    ),
    spec_sections=[
        "§5", "§16", "§17", "§18", "§19", "§20",
    ],
    functional_requirements=[],
    non_functional_requirements=[
        "NFR-01", "NFR-02", "NFR-03", "NFR-04", "NFR-05",
        "NFR-06", "NFR-07", "NFR-08", "NFR-09",
    ],
    schema_targets=[],
    integration_targets=[
        "Anthropic API (model availability check)",
    ],
    artifacts_in_scope=[
        "synthesizer/observability/events.py (structured log event emitter)",
        "synthesizer/observability/metrics.py (run_metrics.json writer)",
        "synthesizer/observability/tokens.py (token accounting and budget enforcement)",
        "synthesizer/orchestrator/model_init.py (model availability check, graceful error)",
        "synthesizer/acceptance/harness.py (traceability verification helpers)",
        "tests/test_events.py",
        "tests/test_metrics.py",
        "tests/test_token_budget.py",
        "tests/test_model_init.py",
        "tests/test_acceptance_harness.py",
    ],
    implementation_tasks=[
        "Implement structured log event emitter: emit JSON event at every state transition per §17.1 schema (event_type, section_id, from_state, to_state, timestamp, metadata) (NFR-06)",
        "Implement additional event types: run_started, run_completed, run_failed, cascade_triggered, escalation_triggered, checkpoint_written, assembly_started, assembly_completed",
        "Implement run_metrics.json writer: compute all seven metrics from §17.2 (structural compliance rate, style compliance rate, dependency completeness, unsupported claim rate, revision churn, claim-table completeness, evidence-claim agreement) and write to SYNTHESIZER_OUTPUT_DIR (NFR-07)",
        "Replace placeholder metric stubs from planning-phase tools.py with spec-conformant computation: (a) dependency_completeness — iterate upstream ClaimTable entries across content-dependency edges, compute fraction engaged by downstream section text or claim table; (b) unsupported_claim_rate — for each section ClaimTable, count entries where source_chunk_ids is empty or all referenced chunk IDs are absent from retrieval set, divide by total entries; (c) evidence_claim_agreement — for each ClaimEntry verify confidence_tag is consistent with source material relationship, using heuristic rules or LLM-assisted check that respects TOKEN_BUDGET_CEILING and uses model_for_role('validator'). Do NOT carry forward 0.0 placeholders (NFR-07)",
        "Implement cumulative token accounting: track input and output tokens across all LLM calls in RunState.cumulative_input_tokens / cumulative_output_tokens",
        "Implement token budget ceiling enforcement: halt generation with budget-exceeded error if TOKEN_BUDGET_CEILING is set and reached (NFR-02)",
        "Implement per-section generation latency tracking and alert on >120s (NFR-01)",
        "Implement model availability check at initialization: configure SYNTHESIZER_MODEL, attempt a lightweight probe, raise descriptive error if unavailable (NFR-09)",
        "Verify checkpoint/resume contracts from Sprint 2 integrate correctly with event emission (NFR-03)",
        "Verify CASCADE_DEPTH_LIMIT and per-layer retry limits are correctly wired from config (NFR-04, NFR-05)",
        "Implement acceptance harness: helper functions that map FR-XX / NFR-XX IDs to test results, supporting the traceability matrix (§18)",
        "Write integration test: full report run -> parse log output -> every state transition has corresponding event (NFR-06 acceptance)",
        "Write integration test: completed run -> run_metrics.json exists with all 7 metric keys (NFR-07 acceptance)",
        "Write integration test: set low TOKEN_BUDGET_CEILING -> system halts with budget-exceeded error (NFR-02 acceptance)",
        "Write unit test: invalid SYNTHESIZER_MODEL -> descriptive error at initialization (NFR-09 acceptance)",
        "Write benchmark test placeholder: 10-section plan completes within 30 minutes (NFR-08 acceptance)",
    ],
    tests_required=[
        "test_state_transition_events_emitted: every transition produces a structured log event with required fields",
        "test_run_metrics_file_written: run_metrics.json exists after run with all 7 keys",
        "test_structural_compliance_rate_computed: metric reflects first-attempt Layer 1 pass rate",
        "test_token_accounting_tracks_cumulative: input+output tokens accumulated across LLM calls",
        "test_token_budget_ceiling_halts: low ceiling -> budget-exceeded error before all sections complete",
        "test_generation_latency_alert: section >120s -> alert logged",
        "test_invalid_model_descriptive_error: bad model string -> descriptive error at init, not mid-generation",
        "test_acceptance_harness_maps_fr_to_tests: FR-01 -> corresponding test result",
        "test_end_to_end_30min_benchmark: 10-section plan -> wall-clock < 30 minutes (may be a slow/integration test)",
    ],
    dependencies=["sprint_1", "sprint_2", "sprint_3", "sprint_4", "sprint_5"],
    done_definition=[
        "Structured log events emitted for every state transition matching §17.1 schema",
        "run_metrics.json written with all seven §17.2 metrics after every completed run",
        "Token accounting correctly tracks cumulative tokens across all LLM calls",
        "TOKEN_BUDGET_CEILING enforcement halts generation when ceiling is reached",
        "Model availability check raises descriptive error on unavailable model at init",
        "Per-section latency tracked and alerted if >120s",
        "Acceptance harness can map FR/NFR IDs to test results",
        "All listed tests pass",
        "No open decision is silently hardcoded",
    ],
    open_decisions_to_preserve=[
        "DR-16 (model selection per role remains configurable)",
        "DR-17 (TOKEN_BUDGET_CEILING defaults to None; production value not yet decided)",
        "DR-18 (input token budgets per prompt role remain open)",
    ],
    handoff_requirements=[
        "Stable event emission schema consumable by external log aggregators",
        "Stable run_metrics.json schema",
        "Stable token accounting interface",
        "Stable model initialization contract",
        "Complete acceptance harness covering §18 traceability matrix",
    ],
)


# ---------------------------------------------------------------------------
# Sprint registry
# ---------------------------------------------------------------------------

SPRINTS: List[SprintDefinition] = [
    _SPRINT_1,
    _SPRINT_2,
    _SPRINT_3,
    _SPRINT_4,
    _SPRINT_5,
    _SPRINT_6,
]

SPRINTS_BY_ID: Dict[str, SprintDefinition] = {s.sprint_id: s for s in SPRINTS}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_sprint(sprint_id: str) -> SprintDefinition:
    """Return a sprint by ID or raise KeyError."""
    if sprint_id not in SPRINTS_BY_ID:
        raise KeyError(f"Unknown sprint_id: {sprint_id!r}. Valid IDs: {list_sprint_ids()}")
    return SPRINTS_BY_ID[sprint_id]


def list_sprint_ids() -> List[str]:
    """Return ordered list of sprint IDs."""
    return [s.sprint_id for s in SPRINTS]


def validate_sprint_registry() -> None:
    """Check the registry for duplicate IDs and missing dependency references.

    Raises ValueError with a descriptive message on any violation.
    """
    seen_ids: set[str] = set()
    errors: List[str] = []

    for sprint in SPRINTS:
        if sprint.sprint_id in seen_ids:
            errors.append(f"Duplicate sprint_id: {sprint.sprint_id!r}")
        seen_ids.add(sprint.sprint_id)

    for sprint in SPRINTS:
        for dep in sprint.dependencies:
            if dep not in seen_ids:
                errors.append(
                    f"Sprint {sprint.sprint_id!r} depends on {dep!r} which is not in the registry"
                )

    if errors:
        raise ValueError("Sprint registry validation failed:\n  " + "\n  ".join(errors))


# Run validation on import so errors surface immediately.
validate_sprint_registry()