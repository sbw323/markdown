"""
Programmer-agent prompt builders for Report Synthesizer implementation sprints.

Source of truth:
  - Governing v4 design specification (report_synthesizer_v4.md)
  - Sprint registry in sprints.py

This file does NOT define the synthesizer's runtime prompts (Generator,
Validator, Claim Extractor, Summary Abstractifier). Those are product-level
runtime contracts defined by the spec. This file only provides orchestrator-
facing prompts used to instruct a programmer agent during code-generation
sprints.

Prompt construction is traceability-driven and sprint-scoped: every sprint
prompt is composed from shared blocks plus sprint-specific narrative that
maps to FR/NFR IDs, spec sections, and artifacts declared in sprints.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Callable

from sprints import SprintDefinition, SPRINTS_BY_ID, list_sprint_ids, get_sprint


# ---------------------------------------------------------------------------
# Prompt-fragment data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PromptPacket:
    """Composable prompt fragment produced by a sprint prompt builder."""

    system_block: str
    guardrails_block: str
    sprint_objective_block: str
    scope_block: str
    traceability_block: str
    exclusions_block: str
    testing_block: str
    output_format_block: str
    handoff_block: str

    def render(self) -> str:
        """Concatenate all blocks into a single prompt string."""
        return "\n\n".join(
            block for block in [
                self.system_block,
                self.guardrails_block,
                self.sprint_objective_block,
                self.scope_block,
                self.traceability_block,
                self.exclusions_block,
                self.testing_block,
                self.output_format_block,
                self.handoff_block,
            ] if block
        )


# ---------------------------------------------------------------------------
# 4A. Global system prompt
# ---------------------------------------------------------------------------

def build_system_prompt() -> str:
    """Return the global system instruction block for the programmer agent."""
    return """\
## Global System Instructions

You are a programmer agent implementing the Report Synthesizer Agent.

Binding rules:
- The governing v4 design specification (report_synthesizer_v4.md) is authoritative. \
Do not invent behaviour that contradicts it.
- sprints.py controls sprint boundaries. Do not work outside the current sprint scope.
- Implementation must remain traceable to FR-XX and NFR-XX requirement IDs.
- Schemas (§10), lifecycle and state-machine rules (§11), integration boundaries \
(§9, §14), the configuration surface (§16), observability rules (§17), and \
acceptance criteria (§19) must all be respected exactly as specified.
- Stages 01–05 of the existing pipeline are wrapped, not refactored. Do not \
modify their internals; integrate through their public interfaces only.
- Open decisions (DR-XX) must remain configurable or be explicitly preserved \
as open. Never silently collapse an open decision into a hardcoded constant.
- Tests are required for every in-scope acceptance behaviour.
- Do not introduce out-of-scope behaviour."""


# ---------------------------------------------------------------------------
# 4B. Shared implementation guardrails
# ---------------------------------------------------------------------------

def build_shared_guardrails() -> str:
    """Return the shared implementation guardrails block."""
    return """\
## Implementation Guardrails

- Modify only artifacts listed in the current sprint's scope.
- Keep interfaces stable for downstream sprints; do not change signatures \
that other sprints depend on unless unavoidable and documented.
- Do not collapse open decisions (DR-XX) into constants unless the spec \
already fixes their value.
- Favour explicit, typed, readable code. Prefer Pydantic models, dataclasses, \
and typed dicts over untyped dictionaries.
- Preserve determinism for all rule-based and orchestration behaviours.
- Keep filesystem, state, validation, and integration behaviour spec-aligned.
- Report blockers clearly instead of improvising around missing contracts or \
ambiguous spec language.

### Edge Field-Name Canonicalization

The governing spec (§10.4) defines `DependencyEdge` with exactly three fields: \
`source_section_id`, `target_section_id`, and `kind` (a `DependencyKind` enum). \
These are the ONLY canonical field names. The planning-phase orchestrator sketch \
uses fallback lookups (`from_section_id`, `to_section_id`, `dependency_kind`) as \
a defensive coding pattern against loosely-typed dicts; these alternative names \
are NOT part of the spec and MUST NOT appear in generated code.

Binding rules:
- All edge-handling code must use `source_section_id`, `target_section_id`, \
and `kind` exclusively — no fallback aliases.
- The `DependencyEdge` Pydantic model must reject unknown fields \
(`model_config = ConfigDict(extra="forbid")` or Pydantic v1 equivalent).
- DAG builders, cascade propagation, prerequisite checks, and any other \
logic that iterates dependency edges must access the canonical names directly, \
not via `edge.get("X") or edge.get("Y")` fallback chains.

### Orchestrator Sketch Authority Boundary

The planning package includes an `orchestrator.py` file that sketches the \
complete runtime lifecycle — initialisation, DAG construction, the \
generation/validation loop, cascade propagation, assembly, and metrics. \
This file is a **reference-level behavioural specification**, not the modular \
decomposition. It exists to demonstrate intended control flow and component \
interactions, not to serve as copy-paste source code.

When `sprints.py` assigns an artifact to a specific file path (e.g., \
`synthesizer/models/state.py`, `synthesizer/dag.py`, \
`synthesizer/validation/coordinator.py`), that sprint-designated path is \
authoritative. The mapping takes precedence over the sketch's inline layout.

Binding rules:
- Implement each component in the module path declared by `sprints.py` → \
`artifacts_in_scope`, not inline in a single orchestrator file.
- The runtime `orchestrator.py` must import from those sprint-designated \
modules rather than defining the logic itself. For example, `SectionState` \
and `RunState` must live in `synthesizer/models/state.py` and be imported \
by the orchestrator — not defined inside it.
- Use the sketch's logic (state transitions, DAG algorithms, validation \
sequencing, cascade rules) as behavioural specification: the *what*, not \
the *where*. Re-implement in the correct module with the correct interfaces.
- Never duplicate a component that already exists in a sprint-designated \
module. If a prior sprint has already shipped a stable interface (e.g., \
`dag.build_generation_dag()`), the orchestrator must call it, not \
re-implement the algorithm.
- If the sketch contains implementation details that conflict with the \
governing spec or with `sprints.py` artifact assignments, the spec and \
sprint registry win."""


# ---------------------------------------------------------------------------
# 4C. Shared testing and traceability block
# ---------------------------------------------------------------------------

def build_shared_testing_block() -> str:
    """Return the shared testing and traceability requirements block."""
    return """\
## Testing and Traceability Requirements

- Write tests for every in-scope FR/NFR acceptance behaviour touched by \
this sprint.
- Each test must reference the relevant requirement ID(s) in its docstring \
or name.
- In the implementation summary, explicitly note which spec sections were \
implemented.
- Provide a concise unresolved-issues note listing anything the spec leaves \
ambiguous or that could not be completed.
- Provide a handoff note describing what downstream sprints can now rely on."""


# ---------------------------------------------------------------------------
# 4D. Shared output-format block
# ---------------------------------------------------------------------------

def build_output_format_block() -> str:
    """Return the shared deliverable-format instructions."""
    return """\
## Required Deliverable Format

1. **Code changes only** — modified and new files with complete content.
2. **Implementation summary** — concise paragraph listing spec sections \
and FR/NFR IDs implemented.
3. **Tests added / updated** — list of test functions with the requirement \
ID each covers.
4. **Unresolved issues** — any ambiguities, spec gaps, or deferred items.
5. **Handoff notes** — what the next sprint can treat as stable."""


# ---------------------------------------------------------------------------
# Sprint metadata renderer (pulls from SprintDefinition)
# ---------------------------------------------------------------------------

def _render_sprint_header(sprint: SprintDefinition) -> str:
    """Render the sprint name, objective, and traceability metadata."""
    fr_list = ", ".join(sprint.functional_requirements) or "(none)"
    nfr_list = ", ".join(sprint.non_functional_requirements) or "(none)"
    sections = ", ".join(sprint.spec_sections) or "(none)"
    deps = ", ".join(sprint.dependencies) or "(none)"
    return f"""\
## Sprint: {sprint.title}
**Sprint ID:** {sprint.sprint_id}
**Objective:** {sprint.objective}

**Spec sections in scope:** {sections}
**Functional requirements:** {fr_list}
**Non-functional requirements:** {nfr_list}
**Sprint dependencies:** {deps}"""


def _render_artifacts(sprint: SprintDefinition) -> str:
    """Render the artifacts-in-scope list."""
    items = "\n".join(f"- {a}" for a in sprint.artifacts_in_scope)
    return f"## Artifacts in Scope\n\n{items}"


def _render_schema_targets(sprint: SprintDefinition) -> str:
    """Render schema targets if any."""
    if not sprint.schema_targets:
        return ""
    items = ", ".join(sprint.schema_targets)
    return f"**Schema targets:** {items}"


def _render_integration_targets(sprint: SprintDefinition) -> str:
    if not sprint.integration_targets:
        return ""
    items = "\n".join(f"- {t}" for t in sprint.integration_targets)
    return f"## Integration Targets\n\n{items}"


def _render_implementation_tasks(sprint: SprintDefinition) -> str:
    items = "\n".join(f"{i+1}. {t}" for i, t in enumerate(sprint.implementation_tasks))
    return f"## Implementation Tasks\n\n{items}"


def _render_tests_required(sprint: SprintDefinition) -> str:
    items = "\n".join(f"- {t}" for t in sprint.tests_required)
    return f"## Required Tests\n\n{items}"


def _render_done_definition(sprint: SprintDefinition) -> str:
    items = "\n".join(f"- {d}" for d in sprint.done_definition)
    return f"## Done Definition\n\n{items}"


def _render_open_decisions(sprint: SprintDefinition) -> str:
    if not sprint.open_decisions_to_preserve:
        return ""
    items = "\n".join(f"- {d}" for d in sprint.open_decisions_to_preserve)
    return (
        "## Open Decisions — Do NOT Hardcode\n\n"
        "The following decisions are explicitly open in the spec. Preserve them "
        "as configurable or deferred; do not silently resolve them.\n\n"
        f"{items}"
    )


def _render_handoff(sprint: SprintDefinition) -> str:
    items = "\n".join(f"- {h}" for h in sprint.handoff_requirements)
    return f"## Handoff Requirements\n\n{items}"


# ---------------------------------------------------------------------------
# Sprint-specific narrative instructions (the part NOT in SprintDefinition)
# ---------------------------------------------------------------------------

_SPRINT_EXCLUSIONS: Dict[str, str] = {
    "sprint_1": """\
## Explicit Exclusions — Out of Scope

Do NOT implement any of the following in this sprint:
- Retrieval orchestration (Sprint 3)
- Validation layers (Sprint 4)
- Claim extraction (Sprint 5)
- Final report assembly (Sprint 5)
- Observability or metrics infrastructure (Sprint 6)
- Hardcoding any open operational decision (DR-16, DR-17, DR-18)""",

    "sprint_2": """\
## Explicit Exclusions — Out of Scope

Do NOT implement any of the following in this sprint:
- Semantic validation logic (Sprint 4)
- Claim extraction (Sprint 5)
- Observability hardening beyond what is minimally required for checkpoint \
support (Sprint 6)
- Runtime prompt text for Generator / Validator (product-level contracts)""",

    "sprint_3": """\
## Explicit Exclusions — Out of Scope

Do NOT implement any of the following in this sprint:
- Writing the synthesizer runtime Generator prompt text as a freeform \
product artifact outside the spec-defined contract boundaries. The prompt \
assembly function composes the prompt structure; the actual Generator \
system-prompt wording is a runtime contract owned by the spec.
- Using Stage 05 answer text as evidence (FR-10, DR-05 — enforced exclusion).
- Injecting raw upstream prose (content_markdown) into downstream prompts \
(FR-12, DR-03 — enforced exclusion).
- Validation logic (Sprint 4)
- Claim extraction or summary abstraction (Sprint 5)""",

    "sprint_4": """\
## Explicit Exclusions — Out of Scope

Do NOT implement any of the following in this sprint:
- Silently downgrading a failed semantic validation result into a warning.
- Bypassing retry limits under any circumstances.
- Introducing validation layers not defined in the spec (Layers 1, 2, 3 \
are exhaustive for v1).
- Claim extraction (Sprint 5)
- Observability metrics (Sprint 6)""",

    "sprint_5": """\
## Explicit Exclusions — Out of Scope

Do NOT implement any of the following in this sprint:
- Assembling a report before state preconditions are satisfied (all sections \
must be finalized / stable / escalated).
- Blocking forever on claim extraction when partial mode is allowed by the \
spec (FR-22).
- Reinterpreting the source-of-truth hierarchy during assembly (plan is \
Tier 1, always).
- Observability metrics or token budgets (Sprint 6)
- Changing prior sprint interfaces unless necessary and documented.""",

    "sprint_6": """\
## Explicit Exclusions — Out of Scope

Do NOT implement any of the following in this sprint:
- Collapsing open token-budget decisions (DR-17, DR-18) into undocumented \
constants.
- Changing prior sprint interfaces unless strictly necessary and documented \
in handoff notes.
- Introducing parallel execution as a v1 default if the spec preserves \
sequential behaviour (DR-15).
- Altering runtime prompt contracts (Generator, Validator, Claim Extractor, \
Summary Abstractifier) — those are product-level, not orchestrator-level.""",
}


_SPRINT_SELF_CHECKS: Dict[str, str] = {
    "sprint_1": """\
## Self-Checks Before Submission

- [ ] All six enums match §10.1 values exactly.
- [ ] ReportPlan, SectionNode, DependencyEdge enforce every field constraint \
from §10.2–10.4.
- [ ] StyleSheet, LevelConstraint, EquationDelimiters enforce every field \
constraint from §10.5.
- [ ] Plan loader rejects dangling refs with a descriptive error.
- [ ] Plan loader rejects content-dependency cycles with a descriptive error.
- [ ] Style-sheet loader rejects uncompilable citation_pattern.
- [ ] Config surface exposes all §16 keys with documented defaults.
- [ ] DR-16, DR-17, DR-18 are configurable, not hardcoded.
- [ ] All listed tests pass.""",

    "sprint_2": """\
## Self-Checks Before Submission

- [ ] SectionState and RunState validate per §10.12–10.13.
- [ ] Generation DAG uses content edges only; finalization DAG uses \
content + reference edges.
- [ ] Topological iterator produces correct order for any valid plan.
- [ ] Content-dependency gating blocks premature generation.
- [ ] Reference-dependency gating blocks premature finalization but not \
generation.
- [ ] Cascade invalidation stops at CASCADE_DEPTH_LIMIT.
- [ ] Checkpoint round-trips correctly; resume resets generating→queued.
- [ ] Directory scaffolder creates §15 layout.
- [ ] Assembly pre-check rejects non-finalized sections.
- [ ] DR-15 preserved (sequential execution).
- [ ] All listed tests pass.""",

    "sprint_3": """\
## Self-Checks Before Submission

- [ ] Retrieval adapter calls HybridRetriever.query() for every source_query.
- [ ] answer_text from Stage 05 is provably excluded from all prompts.
- [ ] Raw upstream content_markdown is provably excluded.
- [ ] Stage 06 summaries are used for planning only, never as generation \
evidence.
- [ ] Prompt assembly includes all five context channels from §9.2.1.
- [ ] Section-type dispatch selects correct SectionOutput subclass.
- [ ] DR-05, DR-06 enforced; DR-18 remains open.
- [ ] All listed tests pass.""",

    "sprint_4": """\
## Self-Checks Before Submission

- [ ] ValidationResult and Violation models match §10.10.
- [ ] Layer 1 catches all schema violations with field-level errors.
- [ ] Layer 2 enforces every style-sheet constraint from §12.2.
- [ ] Layer 3 executes all three sub-checks (tone, dependency contract, \
unsupported claims).
- [ ] Retry counters respect per-layer configurable limits (NFR-05).
- [ ] Escalation fires on retry exhaustion at any layer.
- [ ] Error/violation feedback is correctly formatted for retry prompts.
- [ ] Validation history accumulates in SectionState.
- [ ] DR-16, DR-18 remain open and configurable.
- [ ] All listed tests pass.""",

    "sprint_5": """\
## Self-Checks Before Submission

- [ ] ClaimEntry, TextSpan, ClaimTable, ProvenanceRecord validate per \
§10.6–10.7, §10.11.
- [ ] Claim extractor produces validated ClaimTable.
- [ ] All four claim-table validation sub-checks enforce §12.4 rules.
- [ ] Partial claim-table fallback sets partial=True with downstream warning.
- [ ] Summary abstractifier produces 2–3 sentence summaries within word \
limits.
- [ ] Cascade propagation respects CASCADE_DEPTH_LIMIT.
- [ ] Reference-change triggers re-validation, not re-generation.
- [ ] Assembler concatenates in plan order with correct heading levels.
- [ ] Assembly is blocked if any section is not finalized/stable/escalated.
- [ ] Provenance records are written on finalization.
- [ ] DR-14, DR-16, DR-18 preserved.
- [ ] All listed tests pass.""",

    "sprint_6": """\
## Self-Checks Before Submission

- [ ] Structured log events emitted for every state transition per §17.1.
- [ ] run_metrics.json written with all seven §17.2 metrics.
- [ ] All three placeholder metrics (dependency_completeness, \
unsupported_claim_rate, evidence_claim_agreement) have real computation \
logic, not 0.0 stubs from planning-phase tools.py.
- [ ] Token accounting tracks cumulative tokens across all LLM calls.
- [ ] TOKEN_BUDGET_CEILING enforcement halts generation when reached.
- [ ] Model availability check raises descriptive error on unavailable model.
- [ ] Per-section latency tracked; alert on >120 s.
- [ ] Acceptance harness maps FR/NFR IDs to test results.
- [ ] DR-16, DR-17, DR-18 remain open.
- [ ] No prior sprint interface changed without documentation.
- [ ] All listed tests pass.""",
}


# ---------------------------------------------------------------------------
# Sprint prompt builders
# ---------------------------------------------------------------------------

def _build_sprint_prompt(sprint_id: str) -> str:
    """Core builder: compose a full prompt from shared blocks + sprint metadata + narrative."""
    sprint = get_sprint(sprint_id)

    parts: List[str] = []

    # 1. Global system prompt
    parts.append(build_system_prompt())

    # 2. Shared guardrails
    parts.append(build_shared_guardrails())

    # 3. Sprint header (objective, spec sections, FR/NFR IDs)
    parts.append(_render_sprint_header(sprint))

    # 4. Schema targets
    schema_block = _render_schema_targets(sprint)
    if schema_block:
        parts.append(schema_block)

    # 5. Integration targets
    integ_block = _render_integration_targets(sprint)
    if integ_block:
        parts.append(integ_block)

    # 6. Artifacts in scope
    parts.append(_render_artifacts(sprint))

    # 7. Implementation tasks
    parts.append(_render_implementation_tasks(sprint))

    # 8. Open decisions
    open_block = _render_open_decisions(sprint)
    if open_block:
        parts.append(open_block)

    # 9. Exclusions (sprint-specific narrative)
    exclusions = _SPRINT_EXCLUSIONS.get(sprint_id, "")
    if exclusions:
        parts.append(exclusions)

    # 10. Self-checks (sprint-specific narrative)
    checks = _SPRINT_SELF_CHECKS.get(sprint_id, "")
    if checks:
        parts.append(checks)

    # 11. Required tests
    parts.append(_render_tests_required(sprint))

    # 12. Done definition
    parts.append(_render_done_definition(sprint))

    # 13. Shared testing / traceability
    parts.append(build_shared_testing_block())

    # 14. Output format
    parts.append(build_output_format_block())

    # 15. Handoff requirements
    parts.append(_render_handoff(sprint))

    return "\n\n".join(parts)


def build_sprint_1_prompt() -> str:
    """Prompt for Sprint 1: Foundation contracts and loaders."""
    return _build_sprint_prompt("sprint_1")


def build_sprint_2_prompt() -> str:
    """Prompt for Sprint 2: DAGs, section state, run state, checkpointing, and filesystem contract."""
    return _build_sprint_prompt("sprint_2")


def build_sprint_3_prompt() -> str:
    """Prompt for Sprint 3: Retrieval integration and generation prompt assembly."""
    return _build_sprint_prompt("sprint_3")


def build_sprint_4_prompt() -> str:
    """Prompt for Sprint 4: Validation engine and retry/escalation behaviour."""
    return _build_sprint_prompt("sprint_4")


def build_sprint_5_prompt() -> str:
    """Prompt for Sprint 5: Claim extraction, summary abstraction, cascades, and final assembly."""
    return _build_sprint_prompt("sprint_5")


def build_sprint_6_prompt() -> str:
    """Prompt for Sprint 6: Observability, metrics, budget control, model/error handling, and acceptance harness."""
    return _build_sprint_prompt("sprint_6")


# ---------------------------------------------------------------------------
# Public dispatch API
# ---------------------------------------------------------------------------

_BUILDERS: Dict[str, Callable[[], str]] = {
    "sprint_1": build_sprint_1_prompt,
    "sprint_2": build_sprint_2_prompt,
    "sprint_3": build_sprint_3_prompt,
    "sprint_4": build_sprint_4_prompt,
    "sprint_5": build_sprint_5_prompt,
    "sprint_6": build_sprint_6_prompt,
}


def build_prompt_for_sprint(sprint_id: str) -> str:
    """Return the fully-composed programmer-agent prompt for *sprint_id*.

    Raises KeyError if sprint_id is unknown.
    """
    if sprint_id not in _BUILDERS:
        raise KeyError(
            f"No prompt builder for sprint_id={sprint_id!r}. "
            f"Known IDs: {sorted(_BUILDERS)}"
        )
    return _BUILDERS[sprint_id]()


# ---------------------------------------------------------------------------
# Validation helper
# ---------------------------------------------------------------------------

def validate_prompt_coverage() -> None:
    """Verify every sprint in sprints.py has a corresponding prompt builder.

    Raises ValueError with a descriptive message on any gap.
    """
    registry_ids = set(list_sprint_ids())
    builder_ids = set(_BUILDERS)

    missing_builders = registry_ids - builder_ids
    orphan_builders = builder_ids - registry_ids

    errors: List[str] = []
    if missing_builders:
        errors.append(
            f"Sprints in registry with no prompt builder: {sorted(missing_builders)}"
        )
    if orphan_builders:
        errors.append(
            f"Prompt builders with no matching sprint in registry: {sorted(orphan_builders)}"
        )

    # Also verify each builder can actually produce a prompt without error.
    for sid in sorted(builder_ids & registry_ids):
        try:
            prompt = build_prompt_for_sprint(sid)
            if not prompt or len(prompt) < 200:
                errors.append(f"Prompt for {sid} is suspiciously short ({len(prompt)} chars)")
        except Exception as exc:
            errors.append(f"Prompt builder for {sid} raised: {exc}")

    if errors:
        raise ValueError(
            "Prompt coverage validation failed:\n  " + "\n  ".join(errors)
        )


# ---------------------------------------------------------------------------
# Run coverage validation on import so gaps surface immediately.
# ---------------------------------------------------------------------------
validate_prompt_coverage()