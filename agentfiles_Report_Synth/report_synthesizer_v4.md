# Report Synthesizer Agent Design Specification

**Version:** 4.0 (Governing Design Specification)
**Status:** Governing — this document is the authoritative specification for the Report Synthesizer Agent. All implementation work, sprint planning, and acceptance testing derive from this document.
**Date:** 2026-04-11

---

## §1 Purpose and Document Status

This document is the **governing design specification** for the Report Synthesizer Agent, a system that generates structured scientific literature reviews from the outputs of an existing six-stage PDF processing pipeline (stages 01–06). It defines the functional and non-functional requirements, data schemas, orchestration lifecycle, validation design, prompt contracts, integration boundaries, and operational parameters that collectively govern the system's implementation.

This is not a proposal, context review, or pre-specification discussion document. Every normative statement in this specification is binding on the implementation. Open decisions are explicitly marked as such in the Decision Register (§21). All other content represents committed design decisions.

**Versioning:** This document supersedes v3.0 (post-QA revision). The v3 problem statement, context review, and pipeline summary are preserved as appendices for reference but carry no normative weight.

---

## §2 Scope and Non-Goals

### 2.1 Scope

The Report Synthesizer Agent consumes the outputs of pipeline stages 01–06 and produces a structured, multi-section scientific literature review governed by a user-supplied report plan and style sheet. The system performs retrieval-augmented generation with three-layer validation, claim-table extraction, dependency-aware orchestration, and deterministic final assembly.

### 2.2 Non-Goals

The following capabilities are explicitly outside the scope of this system:

1. **Autonomous research or experimentation.** The system synthesizes existing pipeline outputs; it does not design experiments, collect data, or generate novel hypotheses beyond what the source material supports.

2. **Source PDF modification.** The system does not edit, annotate, or modify the original PDF files processed by stages 01–02.

3. **External citation resolution.** The system does not resolve citations to external bibliographic databases (e.g., CrossRef, Semantic Scholar). Citation formatting uses metadata already extracted by stage 01.

4. **Real-time multi-user collaboration.** The system operates as a single-user batch process. Concurrent multi-user access to the same report run is not supported.

5. **Pipeline stage refactoring.** The system does not replace or refactor pipeline stages 01–05. It integrates with them via stable interfaces defined in §14.

6. **Unconstrained content generation.** The system does not generate content outside the sections declared in the report plan. It does not autonomously expand the report plan's structure.

7. **Autonomous report plan expansion.** The system does not add, remove, or reorder sections beyond what the report plan specifies. Structural decisions are the user's responsibility.

---

## §3 Assumptions and Prerequisites

1. **Pipeline completion.** All prerequisite pipeline stages (01–04) have been run successfully and their outputs (manifest.json, parsed markdown files, chunk files, ChromaDB collection, BM25 index) exist before the synthesizer is invoked.

2. **Stage 05 availability.** The `HybridRetriever` class from `05_query.py` is importable and functional, with its required dependencies (ChromaDB, sentence-transformers, rank-bm25) installed.

3. **Stage 06 availability.** The `load_all_summaries()` function from `06_review.py` is importable and returns valid `PaperSummary` objects.

4. **Anthropic API access.** A valid `ANTHROPIC_API_KEY` is configured and the specified model is available.

5. **Report plan and style sheet.** The user has prepared a valid report plan (conforming to the ReportPlan schema, §10) and style sheet (conforming to the StyleSheet schema, §10) before invoking the synthesizer.

6. **Filesystem permissions.** The synthesizer has read access to pipeline output directories and write access to its configured output directory.

7. **Utility modules.** The `utils.metadata` module required by stage 01 must be audited or stubbed before synthesizer development. The `utils.equation_handler` module is required by stage 02 but is not directly consumed by the synthesizer.

---

## §4 Functional Requirements

### Report Plan Ingestion and Validation

**FR-01:** The system shall load a report plan from the path specified by `REPORT_PLAN_PATH` and parse it into a validated `ReportPlan` object (§10).

*Rationale:* The report plan is the primary structural input; all downstream processing depends on its validity.

*Verification:* Unit test — provide a valid report plan JSON; assert successful parsing into ReportPlan with all fields populated. Provide a malformed JSON; assert a descriptive validation error.

**FR-02:** The system shall validate that every `section_id` referenced in `dependency_edges` exists as a declared section in the report plan.

*Rationale:* Dangling dependency references would cause runtime failures during DAG construction.

*Verification:* Unit test — provide a report plan with a dependency edge referencing a non-existent section_id; assert validation error identifying the dangling reference.

**FR-03:** The system shall validate that the report plan's dependency graph contains no cycles among content-type dependencies.

*Rationale:* Content dependencies impose a generation ordering (DR-07); cycles would create deadlocks.

*Verification:* Unit test — provide a report plan with a content-dependency cycle (A→B→C→A); assert validation error identifying the cycle.

### Style Sheet Ingestion and Validation

**FR-04:** The system shall load a style sheet from the path specified by `STYLE_SHEET_PATH` and parse it into a validated `StyleSheet` object (§10).

*Rationale:* The style sheet governs formatting, tone, and structural constraints applied during generation and validation.

*Verification:* Unit test — provide a valid style sheet; assert successful parsing. Provide a style sheet with an invalid citation_pattern regex; assert validation error.

**FR-05:** The system shall apply per-section-type style overrides when a section's `section_type` has a matching entry in the style sheet's `per_type_overrides`.

*Rationale:* Different section types (e.g., evidence tables vs narrative synthesis) have different formatting requirements.

*Verification:* Unit test — configure a style sheet with an override for `evidence_table` type; generate a section of that type; assert the override constraints are applied in the Layer 2 validation check.

### DAG Construction

**FR-06:** The system shall construct a directed acyclic graph (generation DAG) from the report plan's `dependency_edges`, representing the generation ordering of sections.

*Rationale:* The generation DAG determines which sections can be generated and in what order.

*Verification:* Unit test — provide a report plan with 5 sections and known dependency edges; assert the constructed DAG has correct adjacency and topological ordering.

**FR-07:** The system shall construct a finalization DAG that incorporates reference dependencies in addition to content dependencies.

*Rationale:* Reference dependencies block finalization but not generation (DR-08); a separate DAG tracks finalization ordering.

*Verification:* Unit test — provide a plan where section B has a reference dependency on section C; assert B can enter `generating` before C is finalized, but cannot enter `finalized` until C is finalized.

**FR-08:** The system shall not begin generating a section until all of its content-dependency predecessors have reached `finalized` state.

*Rationale:* Content dependencies represent semantic prerequisites (DR-07).

*Verification:* Integration test — 3-section chain A→B→C with content dependencies. Attempt to generate C before A is finalized. Assert C remains in `queued` state until A reaches `finalized`.

### Per-Section Retrieval

**FR-09:** The system shall invoke `HybridRetriever.query()` (Stage 05) for each section using the section's `source_queries` from the report plan.

*Rationale:* Retrieval provides the evidence base for generation.

*Verification:* Integration test — configure a section with two source queries; assert both queries are executed and their ranked chunk results are aggregated.

**FR-10:** The system shall pass the ranked chunk list (with chunk IDs, text, metadata, and retrieval scores) to the generation prompt, and shall discard the answer text returned by Stage 05 (DR-05).

*Rationale:* The answer text is unvalidated synthesis; only primary chunk evidence is admissible.

*Verification:* Inspection — examine the assembled generation prompt for a test section; assert chunk data is present and answer text is absent.

### Generation Prompt Assembly

**FR-11:** The system shall assemble generation prompts containing: retrieved chunks, upstream claim tables (for content dependencies), upstream summary abstracts (for thematic context), section description and type from the report plan, and relevant style sheet constraints.

*Rationale:* These are the context channels defined in §13; each provides a distinct information type required for generation.

*Verification:* Unit test — assemble a prompt for a section with one content dependency and one thematic dependency; assert the prompt contains the upstream claim table, the upstream summary abstract, retrieved chunks, section description, and style constraints.

**FR-12:** The system shall exclude raw upstream prose from generation prompts (DR-03). Downstream sections receive only claim tables and summary abstracts from upstream sections.

*Rationale:* Prevents prompt bloat and ensures structured information flow.

*Verification:* Inspection — examine generation prompts for downstream sections; assert no full section text from upstream sections appears.

**FR-13:** The system shall format generation prompt output expectations to conform to the type-specific `SectionOutput` schema (§10) for the section being generated.

*Rationale:* Structured output enables deterministic Layer 1 validation.

*Verification:* Unit test — generate output for each section type; assert each output parses as the correct type-specific SectionOutput subclass.

### Three-Layer Validation

**FR-14:** After generation, the system shall validate section output through Layer 1 (structural validation): schema conformance, required field presence, and basic type checks against the `SectionOutput` schema.

*Rationale:* Catches malformed LLM output before more expensive validation layers.

*Verification:* Unit test — submit a SectionOutput with a missing required field; assert Layer 1 returns failure with field-level error.

**FR-15:** On Layer 1 failure, the system shall append the error list to the regeneration prompt and retry, up to the configured `LAYER1_RETRY_LIMIT` (default: 3, DR-11).

*Rationale:* Error feedback enables the model to self-correct structural issues.

*Verification:* Unit test — submit output that fails Layer 1; assert retry prompt includes the error description; assert retry count does not exceed limit.

**FR-16:** After Layer 1 pass, the system shall validate through Layer 2 (rule-based validation): word count limits, heading level correctness, citation format compliance, forbidden phrase detection, and other style sheet constraints.

*Rationale:* Deterministic rule checks enforce style sheet compliance without LLM cost.

*Verification:* Unit test — submit a SectionOutput with word_count exceeding the style sheet maximum; assert Layer 2 returns failure identifying the constraint.

**FR-17:** On Layer 2 failure, the system shall append violations to the regeneration prompt and retry, up to `LAYER2_RETRY_LIMIT` (default: 3, DR-12).

*Rationale:* Same as FR-15.

*Verification:* Unit test — trigger Layer 2 failure; assert retry with violation feedback; assert limit enforced.

**FR-18:** After Layer 2 pass, the system shall validate through Layer 3 (semantic validation) using three LLM-based sub-checks: tone compliance, dependency contract fulfillment, and unsupported claim detection.

*Rationale:* Semantic quality cannot be assessed deterministically; LLM judgment is required.

*Verification:* Integration test — submit a section that contradicts an upstream claim table entry; assert the dependency contract sub-check returns failure identifying the unengaged claim.

**FR-19:** On Layer 3 failure, the system shall retry up to `LAYER3_RETRY_LIMIT` (default: 2, DR-13). On exhaustion, the section transitions to `escalated` state.

*Rationale:* Semantic failures after retry exhaustion require human review.

*Verification:* Integration test — trigger Layer 3 failure 3 times (exceeding limit of 2); assert section state transitions to `escalated`.

### Claim Table Extraction and Validation

**FR-20:** After a section passes all three validation layers, the system shall invoke the claim extractor to produce a `ClaimTable` (§10) from the finalized section text and its retrieval chunks.

*Rationale:* Claim tables are the primary context channel consumed by downstream sections (§13).

*Verification:* Integration test — finalize a section; assert a ClaimTable is produced with at least one ClaimEntry.

**FR-21:** The system shall validate the extracted claim table through four sub-checks: completeness (key claims covered), traceability (each claim has ≥1 source_chunk_id), label consistency (confidence_tag matches claim content), and cross-validation (claims do not contradict section text).

*Rationale:* Claim tables must be reliable before downstream consumption (DR-02).

*Verification:* Unit test — submit a ClaimTable with a claim missing source_chunk_ids; assert traceability sub-check fails.

**FR-22:** If claim extraction fails after `CLAIM_EXTRACTION_RETRY_LIMIT` (default: 1, DR-14) retries, the system shall mark the claim table as `partial` and allow downstream sections to proceed with a warning.

*Rationale:* Partial claims are better than blocking the entire pipeline.

*Verification:* Unit test — simulate extraction failure; assert claim table is marked partial; assert downstream sections receive the partial flag.

### Change Propagation and Cascade Management

**FR-23:** When a section's content changes after finalization (re-generation due to upstream cascade), the system shall invalidate all sections that have a content dependency on the changed section.

*Rationale:* Content dependents may have consumed stale claim tables or summary abstracts.

*Verification:* Integration test — finalize sections A→B→C; re-generate A; assert B transitions to `invalidated`; assert C transitions to `invalidated` when B is re-finalized with changed content.

**FR-24:** The system shall terminate change propagation cascades at the configured `CASCADE_DEPTH_LIMIT` (default: 3, DR-04).

*Rationale:* Prevents unbounded re-generation cost.

*Verification:* Integration test — create a 5-section chain; trigger cascade from the root; assert propagation stops after depth 3.

**FR-25:** When an upstream reference dependency changes, the system shall re-validate (but not re-generate) the dependent section's reference pointers.

*Rationale:* Reference dependencies affect structural pointers, not content substance (DR-08).

*Verification:* Unit test — change a referenced section's heading; assert the referencing section's validation is re-triggered but content is not re-generated.

### Final Assembly

**FR-26:** The system shall assemble the final report by concatenating all finalized `SectionOutput` objects in the order specified by the report plan hierarchy, adjusting heading levels according to each section's `depth_level`.

*Rationale:* The assembled report must reflect the report plan's intended structure.

*Verification:* Integration test — finalize 4 sections at varying depth levels; assemble; assert heading levels in the output match depth_level + base offset.

**FR-27:** The system shall not begin final assembly until all sections in the report plan have reached `finalized` or `stable` state, or have been explicitly marked as `escalated`.

*Rationale:* Partial assembly would produce an incomplete report.

*Verification:* Integration test — leave one section in `drafted` state; attempt assembly; assert assembly is blocked with a descriptive error identifying the non-finalized section.

---

## §5 Non-Functional Requirements

**NFR-01:** Maximum generation latency per section shall not exceed 120 seconds wall-clock time (excluding retrieval).

*Target:* ≤120s per section generation call.

*Verification:* Instrumented timing in the orchestrator; alert on exceedance.

**NFR-02:** Total token budget per report run shall be configurable and enforced. The system shall track cumulative input and output tokens across all LLM calls and halt generation if the ceiling is reached.

*Target:* Configurable ceiling (see DR-17, open).

*Verification:* Integration test — set a low token ceiling; run a multi-section report; assert the system halts with a budget-exceeded error before completing all sections.

**NFR-03:** The system shall support checkpoint and resume after process failure. On crash, no more than one section's in-progress generation is lost.

*Target:* Resume from last completed state transition.

*Verification:* Integration test — kill the process mid-generation; restart; assert all previously finalized sections are intact and the interrupted section restarts from `queued`.

**NFR-04:** Maximum cascade depth shall be configurable (default: 3, DR-04).

*Target:* CASCADE_DEPTH_LIMIT config key.

*Verification:* Unit test — set limit to 2; trigger cascade on a 4-deep chain; assert propagation stops at depth 2.

**NFR-05:** Retry limits per validation layer shall be independently configurable (defaults: Layer 1 = 3, Layer 2 = 3, Layer 3 = 2, Claim extraction = 1; DR-11 through DR-14).

*Target:* Per-layer config keys.

*Verification:* Unit test — set Layer 1 limit to 1; trigger failure; assert only 1 retry occurs.

**NFR-06:** The system shall emit structured log events at every section state transition, conforming to the event schema defined in §17.

*Target:* Every state transition logged with: event_type, section_id, from_state, to_state, timestamp, metadata.

*Verification:* Integration test — run a full report; parse log output; assert every state transition in RunState has a corresponding log event.

**NFR-07:** The system shall produce a `run_metrics.json` file at the conclusion of each run, containing all metrics defined in §17.

*Target:* File written to SYNTHESIZER_OUTPUT_DIR.

*Verification:* Integration test — complete a report run; assert file exists and contains all seven metric keys.

**NFR-08:** The system shall complete a 10-section report (with typical dependency complexity) within 30 minutes wall-clock time under sequential execution.

*Target:* ≤30 minutes end-to-end for 10 sections.

*Verification:* Benchmark test — run a 10-section report plan; measure wall-clock time.

**NFR-09:** The system shall operate correctly with the configured `SYNTHESIZER_MODEL` and degrade gracefully (descriptive error) if the model is unavailable.

*Target:* Clear error message on model unavailability; no silent failures.

*Verification:* Unit test — configure an invalid model string; assert the system raises a descriptive error at initialization, not mid-generation.

---

## §6 Architecture Overview

The Report Synthesizer Agent operates as a single-process orchestrator that coordinates five functional roles (§9) over a DAG-ordered set of sections defined by a report plan (§7).

### 6.1 Component Summary

**Orchestrator:** The central control loop. Maintains `RunState` (§10.13), traverses the generation DAG in topological order, dispatches sections to the appropriate role, manages state transitions (§11), and writes checkpoints.

**Generator:** LLM role that produces section content from retrieval evidence and upstream context channels (§9.2.1).

**Validator:** Three-layer validation pipeline — Layer 1 (structural, deterministic), Layer 2 (rule-based, deterministic), Layer 3 (semantic, LLM-based) — plus claim-table extraction and validation (§12).

**Retriever:** Wraps Stage 05 `HybridRetriever` to execute per-section source queries and return ranked evidence chunks (§14).

**Assembler:** Deterministic function that concatenates finalized sections into the report output (§9.2.5).

### 6.2 Data Flow

```
Report Plan + Style Sheet
        │
        ▼
   ┌─────────────┐
   │ Orchestrator │──── RunState checkpoint (§15)
   └──────┬──────┘
          │ for each section in topo order:
          ▼
   ┌─────────────┐     ┌──────────────┐
   │  Retriever   │────▶│  Generator    │
   │  (Stage 05)  │     │  (LLM call)  │
   └─────────────┘     └──────┬───────┘
                              │ SectionOutput
                              ▼
                       ┌─────────────┐
                       │  Validator   │
                       │  L1→L2→L3   │
                       └──────┬──────┘
                              │ on pass
                              ▼
                       ┌──────────────┐
                       │ Claim Extractor│──▶ ClaimTable → downstream sections
                       └──────┬───────┘
                              │
                              ▼
                       ┌──────────────┐
                       │ Summary       │──▶ summary_abstract → downstream sections
                       │ Abstractifier │
                       └──────────────┘
                              │
          after all sections finalized:
                              ▼
                       ┌─────────────┐
                       │  Assembler   │──▶ Final Report
                       └─────────────┘
```

---

## §7 Source of Truth Hierarchy

The system operates under a strict three-tier precedence for structural and formatting authority. This hierarchy is a binding decision (DR-01).

**Tier 1 — Report Plan (highest authority).** The `ReportPlan` (§10) is the sole canonical source for: section existence, section ordering, section hierarchy (parent-child), section types, dependency edges, and section descriptions. No other artifact may add, remove, reorder, or reclassify sections.

**Tier 2 — Style Sheet.** The `StyleSheet` (§10) is the canonical source for: citation format, tone register, per-level word count constraints, per-type formatting overrides, forbidden phrases, and equation delimiters. The style sheet constrains how content is expressed but does not define what content exists.

**Tier 3 — Directory Tree (derived, never canonical).** The filesystem layout (§15) mirrors the report plan's structure but is strictly derived output. If the directory tree diverges from the report plan — due to partial runs, manual edits, or filesystem errors — the report plan takes precedence. The orchestrator recreates directory structure from the report plan at each run.

---

## §8 Dependency Taxonomy

Four dependency kinds govern the relationships between sections. Each kind imposes different ordering and validation constraints. These definitions are preserved from v3 with the addition of `DependencyEdge` schema references (§10.4).

### 8.1 Content Dependency (`DependencyKind.CONTENT`)

A section with a content dependency on an upstream section requires the upstream section's substantive output (via claim table and summary abstract) to generate its own content. **Enforcement:** hard — blocks generation. The downstream section cannot transition from `queued` to `generating` until the upstream section reaches `finalized` state (DR-07, FR-08). Change propagation: upstream content changes invalidate the downstream section (FR-23).

### 8.2 Reference Dependency (`DependencyKind.REFERENCE`)

A section with a reference dependency points to another section structurally (cross-references, citations to other sections). **Enforcement:** medium — blocks finalization, not generation. The downstream section may generate freely but cannot transition to `finalized` until the referenced section is finalized (DR-08, FR-07). Change propagation: upstream reference changes trigger re-validation of structural pointers, not re-generation (FR-25).

### 8.3 Thematic Dependency (`DependencyKind.THEMATIC`)

A section with a thematic dependency shares framing, tone, or narrative thread with another section. **Enforcement:** soft — coherence check only. The downstream section may generate and finalize independently. The Layer 3 semantic validator checks thematic alignment as a quality signal (DR-09). Change propagation: upstream changes to thematically linked sections trigger a re-validation coherence check but do not invalidate the downstream section.

### 8.4 Source Dependency (`DependencyKind.SOURCE`)

A section with a source dependency shares evidence sources (retrieval chunks) with another section. **Enforcement:** informational — consistency check only. No ordering constraints are imposed (DR-10). The system logs shared source overlaps for manual review. Change propagation: none — source dependencies do not trigger cascades.

---

## §9 Section Types and Prompt Contracts

### 9.1 Section Types

Four section types are defined, each with distinct generation behavior and output schema. The type is declared in the report plan's `SectionNode.section_type` field (§10.3).

**Narrative Synthesis** (`narrative_synthesis`): Prose sections that synthesize findings across papers. Output: `NarrativeSynthesisOutput` (§10.9). Typical sections: introduction, discussion, conclusion, thematic groupings.

**Evidence Table** (`evidence_table`): Structured comparison tables with defined columns and rows. Output: `EvidenceTableOutput` (§10.9). Typical sections: methodology comparison, paper-by-paper summaries, quantitative result tables.

**Cross Reference** (`cross_reference`): Sections that explicitly compare or connect other sections. Output: `CrossReferenceOutput` (§10.9). Typical sections: consensus/contradiction analysis, cross-cutting themes.

**Methodology Description** (`methodology_description`): Technical descriptions of research methods, including equations and formal notation. Output: `MethodologyDescriptionOutput` (§10.9). Typical sections: mathematical models, experimental design descriptions.

### 9.2 Prompt Contracts

Five roles are defined: four LLM-facing and one deterministic. Each contract specifies inputs, outputs, and failure handling. Token budgets are open decisions (DR-18).

#### 9.2.1 Generator

**Purpose:** Produce section content conforming to the type-specific `SectionOutput` schema.

**System prompt content:** Role as scientific literature review writer; output format instructions referencing the target SectionOutput subclass; style sheet constraints (tone, citation format, word limits, forbidden phrases); equation delimiter configuration.

**User message composition:**
1. Section description and type from the report plan (`SectionNode.description`, `SectionNode.section_type`)
2. Retrieved chunks from Stage 05 (chunk ID, text, metadata, retrieval score) — per FR-10
3. Upstream claim tables for content dependencies (per §13, FR-11)
4. Upstream summary abstracts for thematic dependencies (per §13, FR-11)
5. Style sheet constraints relevant to this section's type and depth level (per FR-05)
6. On retry: validation error list from the failing layer (per FR-15, FR-17)

**Expected output:** JSON conforming to the type-specific SectionOutput schema (§10.8–10.9).

**Token budget:** Input: open (DR-18). Output: 4000 tokens.

**Failure modes:**
- Malformed JSON → Layer 1 structural failure; error appended to retry prompt (FR-15)
- Missing required fields → Layer 1 failure
- API call failure → section returns to `queued` with retry counter incremented

#### 9.2.2 Validator (Layer 3 — Semantic)

**Purpose:** Assess semantic quality through three independent sub-checks. Each sub-check produces a separate `ValidationResult`.

**Sub-check A — Tone compliance:**
- Input: section `content_markdown` + `StyleSheet.tone_register`
- Output: `ValidationResult` with `rule="tone_compliance"`
- Checks: tone matches register; no forbidden phrases missed by Layer 2; appropriate formality

**Sub-check B — Dependency contract fulfillment:**
- Input: section `content_markdown` + upstream `ClaimTable` objects for all content dependencies
- Output: `ValidationResult` with `rule="dependency_contract"`, `violations` listing unengaged claims
- Checks: downstream section engages with key claims from each upstream claim table (FR-18)

**Sub-check C — Unsupported claim detection:**
- Input: section `content_markdown` + retrieval chunks + upstream claim tables
- Output: `ValidationResult` with `rule="unsupported_claims"`, `violations` listing unsupported claims
- Checks: claims in the section are traceable to retrieval chunks or upstream claim tables

**Token budget:** Input: open (DR-18). Output: 1000 tokens per sub-check.

**Failure modes:** Sub-check failure → aggregated into Layer 3 ValidationResult; retry up to LAYER3_RETRY_LIMIT (FR-19).

#### 9.2.3 Claim Extractor

**Purpose:** Extract a structured `ClaimTable` (§10.7) from finalized section text.

**System prompt content:** Role as claim extraction specialist; output format as ClaimTable JSON; confidence tag definitions.

**User message composition:**
1. Finalized section `content_markdown`
2. Retrieval chunks used during generation (for source_chunk_id assignment)

**Expected output:** JSON conforming to `ClaimTable` schema (§10.7).

**Token budget:** Input: open (DR-18). Output: 2000 tokens.

**Failure modes:**
- Malformed JSON → retry (CLAIM_EXTRACTION_RETRY_LIMIT, DR-14)
- Incomplete extraction → mark `partial=True` (FR-22); downstream sections warned

#### 9.2.4 Summary Abstractifier

**Purpose:** Generate a 2–3 sentence summary abstract of a finalized section.

**System prompt content:** Role as scientific summarizer; length constraint (2-3 sentences, 50-100 words).

**User message composition:**
1. Finalized section `content_markdown`

**Expected output:** Plain text string, 2–3 sentences.

**Token budget:** Input: open (DR-18). Output: 200 tokens.

**Failure modes:**
- Length violation (>100 words or <20 words) → regenerate with tighter length instruction
- API failure → retry once; on second failure, use a truncation-based fallback

#### 9.2.5 Assembler (Deterministic)

**Purpose:** Concatenate finalized sections into the final report output. No LLM call.

**Interface:**
```python
def assemble(
    section_outputs: Dict[str, SectionOutput],  # Maps section_id → finalized output
    report_plan: ReportPlan                      # For ordering and hierarchy
) -> str:  # Assembled Markdown
```

**Behavior:** Traverses the report plan's section hierarchy in order. For each section, adjusts heading level based on `depth_level` and concatenates `content_markdown`. Inserts separator between sections.

**Failure modes:**
- Missing section output → error listing the missing section_id (FR-27)
- Heading level mismatch → error (heading_level in output doesn't match depth_level expectation)

---

## §10 Schema Definitions

All schemas are expressed as Pydantic model pseudocode. Field annotations specify: type, required/optional status, default (if optional), constraints, and description. These definitions are normative — implementation models must conform to these field-level contracts.

### 10.1 Enumerations

```python
class DependencyKind(str, Enum):
    """Type of dependency between sections. See §8 for enforcement rules."""
    CONTENT = "content"      # Hard: blocks generation (DR-07)
    REFERENCE = "reference"  # Medium: blocks finalization (DR-08)
    THEMATIC = "thematic"    # Soft: coherence check only (DR-09)
    SOURCE = "source"        # Informational: consistency check only (DR-10)

class SectionType(str, Enum):
    """Classification of section generation behavior. See §9 for prompt contracts."""
    NARRATIVE_SYNTHESIS = "narrative_synthesis"
    EVIDENCE_TABLE = "evidence_table"
    CROSS_REFERENCE = "cross_reference"
    METHODOLOGY_DESCRIPTION = "methodology_description"

class SectionLifecycleState(str, Enum):
    """Lifecycle state of a section. See §11 for transition table."""
    QUEUED = "queued"
    GENERATING = "generating"
    DRAFTED = "drafted"
    DRAFTED_PENDING_VALIDATION = "drafted_pending_validation"
    VALIDATED = "validated"
    FINALIZED = "finalized"
    STABLE = "stable"
    INVALIDATED = "invalidated"
    ESCALATED = "escalated"

class ValidationLayer(str, Enum):
    """Validation layer identifier. See §12 for semantics."""
    STRUCTURAL = "structural"       # Layer 1
    RULE_BASED = "rule_based"       # Layer 2
    SEMANTIC = "semantic"           # Layer 3
    CLAIM_TABLE = "claim_table"     # Post-finalization

class ConfidenceTag(str, Enum):
    """Confidence classification for extracted claims."""
    DIRECTLY_STATED = "directly_stated"  # Claim appears verbatim or near-verbatim in source
    INFERRED = "inferred"                # Claim is a reasonable inference from source
    SYNTHESIZED = "synthesized"          # Claim combines information from multiple sources

class ViolationSeverity(str, Enum):
    """Severity of a validation violation."""
    ERROR = "error"      # Must be fixed before progression
    WARNING = "warning"  # Should be fixed; does not block progression
```

### 10.2 ReportPlan

```python
class ReportPlan(BaseModel):
    """Top-level container for the report structure. Tier 1 source of truth (§7).
    Supports: FR-01, FR-02, FR-03, FR-06, FR-26."""

    plan_id: str              # Required. Unique identifier for this plan.
    title: str                # Required. Report title.
    version: str              # Required. Plan version string (semver recommended).
    sections: List[SectionNode]  # Required. Min length: 1. Ordered list of top-level and nested sections.
    global_metadata: Dict[str, Any] = {}  # Optional. Arbitrary metadata (e.g., target audience, domain).
```

### 10.3 SectionNode

```python
class SectionNode(BaseModel):
    """One section in the report plan. Defines structure, type, and dependencies.
    Supports: FR-01, FR-02, FR-06, FR-08, FR-09."""

    section_id: str           # Required. Unique within plan. Pattern: [a-z0-9_]+, max 64 chars.
    title: str                # Required. Human-readable section title.
    parent_id: Optional[str] = None  # Nullable. section_id of parent for hierarchy. None = top-level.
    section_type: SectionType # Required. Determines prompt contract and output schema.
    description: str          # Required. Prose guidance for generation (2-5 sentences).
    source_queries: List[str] # Required. Min length: 1. Queries for Stage 05 retrieval.
    dependency_edges: List[DependencyEdge] = []  # Optional. Dependencies on other sections.
    depth_level: int          # Required. Nesting depth (0 = top-level). Derived from parent chain.
                              # Constraint: must equal len(ancestor chain).
```

### 10.4 DependencyEdge

```python
class DependencyEdge(BaseModel):
    """Typed relationship between two sections. See §8 for enforcement rules.
    Supports: FR-02, FR-03, FR-06, FR-07, FR-08, FR-23, FR-25."""

    source_section_id: str    # Required. The section that depends (the downstream consumer).
    target_section_id: str    # Required. The section depended upon (the upstream provider).
    kind: DependencyKind      # Required. Type of dependency relationship.
```

### 10.5 StyleSheet

```python
class StyleSheet(BaseModel):
    """Formatting and tone rules applied during generation and validation. Tier 2 source of truth (§7).
    Supports: FR-04, FR-05, FR-16."""

    citation_pattern: str     # Required. Regex pattern for valid citations (e.g., r"\([A-Z][a-z]+ et al\., \d{4}\)").
    tone_register: str        # Required. Tone descriptor (e.g., "formal_academic", "technical_review").
    per_level_constraints: Dict[int, LevelConstraint]  # Required. Maps depth_level → constraints.
    per_type_overrides: Dict[SectionType, Dict[str, Any]] = {}  # Optional. Type-specific rule overrides.
    forbidden_phrases: List[str] = []  # Optional. Phrases that must not appear in generated text.
    equation_delimiters: EquationDelimiters = EquationDelimiters()  # Optional. LaTeX delimiter config.


class LevelConstraint(BaseModel):
    """Per-depth-level formatting constraints."""

    min_words: int            # Required. Minimum word count. Constraint: ≥0.
    max_words: int            # Required. Maximum word count. Constraint: > min_words.
    heading_format: str       # Required. Markdown heading format (e.g., "##", "###").


class EquationDelimiters(BaseModel):
    """LaTeX equation delimiter configuration."""

    inline: str = "$"         # Inline equation delimiter.
    display: str = "$$"       # Display equation delimiter.
```

### 10.6 ClaimEntry

```python
class ClaimEntry(BaseModel):
    """Single claim extracted from a finalized section.
    Supports: FR-20, FR-21."""

    claim_id: str             # Required. Unique within the parent ClaimTable. Pattern: claim_[0-9]+.
    claim_text: str           # Required. The claim statement as extracted.
    source_chunk_ids: List[str]  # Required. Min length: 1. Chunk IDs from retrieval that support this claim.
    confidence_tag: ConfidenceTag  # Required. Classification of claim confidence.
    section_text_span: TextSpan    # Required. Character offsets locating the claim in section text.


class TextSpan(BaseModel):
    """Character offset range within a text."""

    start: int                # Required. Start character offset (0-indexed, inclusive). Constraint: ≥0.
    end: int                  # Required. End character offset (exclusive). Constraint: > start.
```

### 10.7 ClaimTable

```python
class ClaimTable(BaseModel):
    """Collection of claims for a section. Primary context channel for downstream sections (§13).
    Supports: FR-20, FR-21, FR-22, FR-11."""

    section_id: str           # Required. Section this claim table belongs to.
    version: int              # Required. Extraction version (increments on re-extraction). Constraint: ≥1.
    claims: List[ClaimEntry]  # Required. Extracted claims.
    partial: bool = False     # Whether extraction was incomplete (DR-14).
    extraction_attempt: int   # Required. Which attempt produced this table. Constraint: ≥1.
```

### 10.8 SectionOutput (Base)

```python
class SectionOutput(BaseModel):
    """Base model for generated section content. Extended by per-type models.
    Supports: FR-13, FR-14, FR-26."""

    section_id: str           # Required. Must match the SectionNode.section_id.
    content_markdown: str     # Required. Generated Markdown content.
    word_count: int           # Required. Word count of content_markdown. Constraint: ≥1.
    heading_level: int        # Required. Markdown heading level (1-6). Derived from depth_level.
    metadata: Dict[str, Any] = {}  # Optional. Generation metadata (model, timestamp, etc.).
```

### 10.9 SectionOutput Per-Type Extensions

```python
class NarrativeSynthesisOutput(SectionOutput):
    """Output for narrative_synthesis sections. Extends base with synthesis-specific fields.
    Supports: FR-13."""

    themes_addressed: List[str] = []  # Thematic tags covered in this section.
    cross_references: List[str] = []  # section_ids referenced in the text.


class EvidenceTableOutput(SectionOutput):
    """Output for evidence_table sections. Extends base with tabular structure.
    Supports: FR-13."""

    column_definitions: List[str]  # Required. Column headers for the evidence table.
    rows: List[Dict[str, str]]     # Required. Table rows as column→value mappings.


class CrossReferenceOutput(SectionOutput):
    """Output for cross_reference sections. Extends base with reference mapping.
    Supports: FR-13."""

    referenced_sections: List[str]  # Required. section_ids this section cross-references.
    comparison_dimensions: List[str] = []  # Dimensions along which sections are compared.


class MethodologyDescriptionOutput(SectionOutput):
    """Output for methodology_description sections. Extends base with methodology fields.
    Supports: FR-13."""

    methodologies_described: List[str] = []  # Named methodologies covered.
    equations_referenced: List[str] = []     # LaTeX equation strings referenced.
```

### 10.10 ValidationResult

```python
class ValidationResult(BaseModel):
    """Output of a single validation pass. See §12 for layer semantics.
    Supports: FR-14 through FR-19."""

    layer: ValidationLayer    # Required. Which validation layer produced this result.
    passed: bool              # Required. Whether validation passed.
    attempt: int              # Required. Attempt number within this layer. Constraint: ≥1.
    violations: List[Violation] = []  # Violations found (empty if passed).
    suggested_fix: Optional[str] = None  # LLM-suggested fix text (Layer 3 only).


class Violation(BaseModel):
    """Single validation violation."""

    rule: str                 # Required. Rule identifier (e.g., "word_count_max", "tone_formal").
    description: str          # Required. Human-readable description of the violation.
    severity: ViolationSeverity  # Required. Error or warning.
    location: Optional[str] = None  # Character offset or field path where violation occurs.
```

### 10.11 ProvenanceRecord

```python
class ProvenanceRecord(BaseModel):
    """Audit trail for a finalized section. Written once on finalization.
    See Appendix D for an example.
    Supports: FR-26."""

    section_id: str                    # Required.
    finalized_at: str                  # Required. ISO 8601 timestamp.
    generation_model: str              # Required. Model identifier used for generation.
    generation_attempts: int           # Required. Total generation attempts. Constraint: ≥1.
    validation_history: List[ValidationResult]  # Required. All validation results across all attempts.
    claim_table_version: Optional[int] = None   # Version of the extracted claim table.
    claim_table_partial: bool = False  # Whether claim table is partial.
    source_chunk_ids: List[str]        # Required. All chunk IDs used as evidence.
    upstream_dependencies_consumed: Dict[str, List[str]]  # Required. Maps DependencyKind → list of section_ids.
    cascade_triggers_received: int = 0 # Number of cascade invalidations received.
    word_count: int                    # Required. Final word count.
    heading_level: int                 # Required. Final heading level.
```

### 10.12 SectionState

```python
class SectionState(BaseModel):
    """Per-section lifecycle state tracked by the orchestrator. See §11 for transitions.
    Supports: FR-08, FR-19, FR-23, FR-27."""

    section_id: str                    # Required.
    state: SectionLifecycleState       # Required. Current lifecycle state.
    version: int = 1                   # Draft version counter. Increments on each re-generation.
    last_transition_timestamp: str     # Required. ISO 8601 timestamp of last state change.
    validation_history: List[ValidationResult] = []  # Cumulative validation results.
    claim_table: Optional[ClaimTable] = None  # Current claim table (None until extraction).
    summary_abstract: Optional[str] = None    # 2-3 sentence summary (None until abstraction).
    retry_counters: Dict[str, int] = {}       # Maps layer name → current retry count.
    cascade_depth: int = 0             # Current cascade depth for this section.
```

### 10.13 RunState

```python
class RunState(BaseModel):
    """Checkpoint object for the full orchestrator run. Persisted to disk after every state transition (§11).
    Supports: NFR-03, FR-24."""

    run_id: str                        # Required. Unique run identifier (UUID).
    report_plan_version: str           # Required. Version of the report plan being executed.
    section_states: Dict[str, SectionState]  # Required. Maps section_id → SectionState.
    generation_dag_edges: List[DependencyEdge]  # Required. Content-dependency edges for generation ordering.
    finalization_dag_edges: List[DependencyEdge]  # Required. Content + reference edges for finalization ordering.
    started_at: str                    # Required. ISO 8601 timestamp.
    last_checkpoint_at: str            # Required. ISO 8601 timestamp of last checkpoint write.
    cumulative_input_tokens: int = 0   # Total input tokens consumed across all LLM calls.
    cumulative_output_tokens: int = 0  # Total output tokens consumed across all LLM calls.
```

---

## §11 Orchestration State Machine

### 11.1 State Transition Table

| Current State | Event | Next State | Actions | Checkpoint |
|---|---|---|---|---|
| queued | prerequisites_met | generating | Invoke Stage 05 retrieval with source_queries; assemble generation prompt (§9.2.1); invoke Generator LLM call | Yes |
| generating | generation_complete | drafted | Store draft to `sections/{id}/draft_v{N}.md`; begin Layer 1 validation | Yes |
| generating | generation_failed | queued | Increment retry counter; log failure | Yes |
| drafted | layer_1_pass | drafted_pending_validation | Proceed to Layer 2 validation | Yes |
| drafted | layer_1_fail | generating | Append error list to prompt; re-invoke Generator (if retries remain) | Yes |
| drafted | layer_1_retry_exhausted | escalated | Log exhaustion; flag for human review | Yes |
| drafted_pending_validation | layer_2_pass | drafted_pending_validation | Proceed to Layer 3 validation | No |
| drafted_pending_validation | layer_2_fail | generating | Append violations to prompt; re-invoke Generator (if retries remain) | Yes |
| drafted_pending_validation | layer_2_retry_exhausted | escalated | Log exhaustion; flag for human review | Yes |
| drafted_pending_validation | layer_3_pass | validated | All validation layers passed | Yes |
| drafted_pending_validation | layer_3_fail | generating | Append semantic feedback to prompt; re-invoke Generator (if retries remain) | Yes |
| drafted_pending_validation | layer_3_retry_exhausted | escalated | Log exhaustion; flag for human review | Yes |
| validated | claim_table_pass | finalized | Write provenance record; invoke Summary Abstractifier; store claim table and summary abstract in SectionState | Yes |
| validated | claim_table_fail | validated | If retries remain: re-extract. If exhausted: mark partial (FR-22); proceed to finalized with partial flag | Yes |
| finalized | upstream_content_changed | invalidated | Clear claim table and summary abstract; reset validation history | Yes |
| finalized | upstream_reference_changed | finalized | Re-validate reference pointers only (FR-25); no state change if valid | No |
| finalized | upstream_soft_dependency_changed | finalized | Trigger coherence re-check (Layer 3 tone sub-check); log result; no state change | No |
| stable | upstream_content_changed | invalidated | Same as finalized → invalidated | Yes |
| stable | upstream_reference_changed | stable | Re-validate reference pointers | No |
| stable | upstream_soft_dependency_changed | stable | Coherence re-check; log | No |
| invalidated | prerequisites_met | generating | Re-generate with updated upstream context; increment cascade_depth | Yes |
| invalidated | cascade_depth_exceeded | escalated | Log cascade depth exceeded (DR-04); flag for human review | Yes |
| escalated | (terminal) | — | No automatic transitions. Requires human intervention. | — |

### 11.2 Entry and Exit Conditions

**queued:** Entry — section is declared in report plan and has not yet started generation, or has been reset from `generating` after failure, or has been reset from `invalidated` after upstream cascade. Exit — all content-dependency predecessors are `finalized` (prerequisites_met event).

**generating:** Entry — prerequisites_met fired and retrieval completed. Exit (success) — LLM generation call returns parseable output (generation_complete). Exit (failure) — LLM call fails or times out (generation_failed → back to queued).

**drafted:** Entry — generation_complete fired and raw output stored. Exit — Layer 1 validation result (pass or fail).

**drafted_pending_validation:** Entry — Layer 1 passed. Exit — Layer 2 result, then Layer 3 result. Validation layers execute sequentially within this state.

**validated:** Entry — all three validation layers passed. Exit — claim table extraction result.

**finalized:** Entry — claim table passed validation (or marked partial after retry exhaustion). Provenance record written. Summary abstract generated. Exit — upstream change event (content, reference, or soft dependency change).

**stable:** Entry — section has been finalized and all downstream dependents have also been finalized without requiring changes to this section. Semantically identical to finalized but indicates the section is no longer at risk of cascade invalidation. Exit — upstream change event.

**invalidated:** Entry — upstream content dependency changed after this section was finalized. Exit — prerequisites_met (re-generation) or cascade_depth_exceeded (escalation).

**escalated:** Entry — retry exhaustion at any validation layer, or cascade depth limit exceeded. Terminal state — no automatic exit. Requires human review and manual re-queuing.

### 11.3 Checkpoint and Resumability Contract

**Checkpoint frequency:** `RunState` (§10.13) is persisted to `{SYNTHESIZER_OUTPUT_DIR}/run_state.json` after every state transition marked "Yes" in the checkpoint column above.

**Resume algorithm:**
1. On startup, check for existing `run_state.json`.
2. If found, load and validate against the current report plan version.
3. Sections in `generating` state at crash time are reset to `queued` (in-progress LLM calls are assumed lost).
4. Sections in all other states retain their state.
5. Recompute the generation DAG from the report plan.
6. Resume processing from sections in `queued` state whose prerequisites are met.

**Data loss bound:** At most one section's in-progress generation is lost on crash (NFR-03).

---

## §12 Validation Design

Validation is organized in three layers plus a post-validation claim-table extraction step. Layers execute sequentially; a section must pass each layer before proceeding to the next.

### 12.1 Layer 1 — Structural Validation (Deterministic)

**What it checks:** Schema conformance of the Generator's JSON output against the type-specific `SectionOutput` model (§10.8–10.9). Required field presence, type correctness, enum membership, constraint satisfaction (e.g., word_count > 0).

**Implementation:** Pydantic model validation. No LLM call.

**On failure:** Error list (field names, expected types, actual values) appended to the Generator retry prompt. Retry up to `LAYER1_RETRY_LIMIT` (default: 3, DR-11).

**On retry exhaustion:** Section transitions to `escalated`.

### 12.2 Layer 2 — Rule-Based Validation (Deterministic)

**What it checks:** Style sheet compliance. Specific checks:
- Word count within `StyleSheet.per_level_constraints[depth_level].{min_words, max_words}`
- Heading level matches `StyleSheet.per_level_constraints[depth_level].heading_format`
- Citation format matches `StyleSheet.citation_pattern` regex
- No occurrences of `StyleSheet.forbidden_phrases`
- Equation delimiters match `StyleSheet.equation_delimiters`
- Per-type overrides from `StyleSheet.per_type_overrides` applied and checked

**Implementation:** Deterministic rule engine. No LLM call.

**On failure:** Violation list (rule ID, description, severity, location) appended to the Generator retry prompt. Retry up to `LAYER2_RETRY_LIMIT` (default: 3, DR-12).

**On retry exhaustion:** Section transitions to `escalated`.

### 12.3 Layer 3 — Semantic Validation (LLM-Based)

Three independent sub-checks as defined in §9.2.2. All three must pass for Layer 3 to pass. Each sub-check produces a `ValidationResult`.

**Retry scope:** On any sub-check failure, the entire section is re-generated (not just the failing sub-check), because semantic issues typically require content-level changes. Retry up to `LAYER3_RETRY_LIMIT` (default: 2, DR-13).

**On retry exhaustion:** Section transitions to `escalated`.

### 12.4 Claim Table Extraction and Validation

After all three layers pass, the Claim Extractor (§9.2.3) produces a `ClaimTable`. The claim table is validated through four sub-checks:

1. **Completeness:** Key claims from the section text are represented. Target: ≥90% of identifiable claims.
2. **Traceability:** Every `ClaimEntry` has ≥1 `source_chunk_id`. No orphan claims.
3. **Label consistency:** `confidence_tag` values are appropriate (e.g., a `directly_stated` claim should closely match source chunk text).
4. **Cross-validation:** Claims do not contradict the section text they were extracted from.

**On failure:** Re-extract up to `CLAIM_EXTRACTION_RETRY_LIMIT` (default: 1, DR-14). On exhaustion, mark `ClaimTable.partial = True` and proceed (FR-22).

### 12.5 Retry and Escalation Summary

| Layer | Type | Retry Limit | On Exhaustion | Config Key |
|---|---|---|---|---|
| Layer 1 (Structural) | Deterministic | 3 | Escalate | LAYER1_RETRY_LIMIT |
| Layer 2 (Rule-based) | Deterministic | 3 | Escalate | LAYER2_RETRY_LIMIT |
| Layer 3 (Semantic) | LLM | 2 | Escalate | LAYER3_RETRY_LIMIT |
| Claim Extraction | LLM | 1 | Mark partial | CLAIM_EXTRACTION_RETRY_LIMIT |

---

## §13 Context Channels

Three structured context channels carry information from upstream sections to downstream generation prompts. Raw upstream prose is explicitly excluded (DR-03, FR-12).

### 13.1 Claim Tables

**Source:** `SectionState.claim_table` (§10.12) for each upstream content dependency.

**Consumer:** Generator prompt (§9.2.1, input item 3) and Validator Layer 3 sub-checks B and C (§9.2.2).

**Content:** Structured list of `ClaimEntry` objects with claim text, source chunk IDs, and confidence tags. Provides the substantive factual basis that downstream sections must engage with.

**Availability rule:** Claim tables are available to downstream sections only after passing all four validation sub-checks (DR-02). Partial claim tables (FR-22) are available but carry a `partial` flag that is surfaced to the Generator.

### 13.2 Summary Abstracts

**Source:** `SectionState.summary_abstract` (§10.12), generated by the Summary Abstractifier (§9.2.4).

**Consumer:** Generator prompt (§9.2.1, input item 4) for thematic dependencies.

**Content:** 2–3 sentence plain-text summary of the upstream section's key points. Provides high-level thematic context without injecting detailed claims.

**Availability rule:** Generated after finalization. Available to sections with thematic or content dependencies on the upstream section.

### 13.3 Evidence Pointers

**Source:** Retrieval chunks from Stage 05 (`HybridRetriever.query()`, §14).

**Consumer:** Generator prompt (§9.2.1, input item 2).

**Content:** Ranked chunk list with chunk IDs, full text, metadata (paper title, authors, year, section), and retrieval scores. This is the primary evidence base for generation.

**Availability rule:** Retrieved per-section using `SectionNode.source_queries`. Stage 05 answer text is discarded (DR-05).

---

## §14 Integration Contracts

### 14.1 Interface Contract Table

| Integration Point | Interface | Inputs | Outputs | Side Effects | Error Behavior | Strategy |
|---|---|---|---|---|---|---|
| Stage 05 HybridRetriever | `query(query_text: str) → Tuple[str, List[Dict]]` | Query string | (answer_text, ranked_chunks). Each chunk dict contains: id, text, metadata, score, method, rrf_score | Network calls (ChromaDB, BM25 queries) | Raises exception on failure | Import and call directly. Use `ranked_chunks` only; discard `answer_text` (DR-05). |
| Stage 06 PaperSummary | `load_all_summaries() → List[PaperSummary]` | Summaries directory path (implicit via config) | List of PaperSummary objects with: paper_id, title, authors, year, objective, methodology, key_equations, key_findings, limitations, relevance_tags | Filesystem reads | Raises FileNotFoundError if directory/files missing | Import and call directly. Planning context only — never injected into generation prompts as evidence (DR-06). |
| Config module | `config.py` imports | N/A | Path constants (DATA_DIR, PDFS_DIR, PARSED_DIR, VECTORSTORE_DIR, SUMMARIES_DIR), model config (PIPELINE_MODEL, EMBEDDING_MODEL), API key (ANTHROPIC_API_KEY), chunk config (MAX_CHUNK_SIZE, CHUNK_OVERLAP) | None | Missing keys raise on import | Add new synthesizer keys (§16). Do not modify existing keys. |

### 14.2 Integration Strategy Statement

The synthesizer wraps existing pipeline code as library imports. It does not refactor stages 01–05. It does not require those stages to change their interfaces, outputs, or behavior. If a future version needs to modify retrieval behavior (e.g., different scoring, filtered queries), it will do so via a thin adapter layer over `HybridRetriever`, not by modifying `05_query.py`.

Stage 06's map-reduce review (`06_review.py`) is consumed only for its `PaperSummary` data model via `load_all_summaries()`. The synthesizer does not invoke stage 06's `main()`, `map_phase()`, or `reduce_phase()` functions.

---

## §15 File Layout and Artifact Conventions

### 15.1 Directory Structure

```
{SYNTHESIZER_OUTPUT_DIR}/
├── run_state.json                    # RunState checkpoint (§10.13)
├── run_metrics.json                  # Post-run metrics (§17)
├── sections/
│   └── {section_id}/
│       ├── draft_v{N}.md            # Generated drafts (versioned, N ≥ 1)
│       ├── claim_table_v{N}.json    # Extracted claim tables (versioned)
│       ├── validation_log.json      # Cumulative ValidationResult list
│       └── provenance.json          # ProvenanceRecord (written on finalization)
└── report/
    └── literature_review.md         # Final assembled report
```

### 15.2 Naming Conventions

- `{section_id}` matches `SectionNode.section_id` from the report plan (pattern: `[a-z0-9_]+`).
- `{N}` is a 1-indexed integer that increments on each re-generation or re-extraction.
- `run_state.json` is overwritten on each checkpoint (latest state only).
- `validation_log.json` is append-only within a run; reset on re-generation.

### 15.3 Artifact Classification

**Intermediate artifacts:** `draft_v{N}.md`, `claim_table_v{N}.json`, `validation_log.json`. Retained for debugging and provenance. May be cleaned up after successful report assembly.

**Final artifacts:** `provenance.json`, `run_metrics.json`, `report/literature_review.md`. Retained as deliverables.

**Checkpoint artifact:** `run_state.json`. Required for resume capability (NFR-03). Retained until run completion.

### 15.4 Directory Creation

The orchestrator creates the directory structure from the report plan at run start. Missing directories are created; existing directories are reused. The directory tree is derived output (DR-01, §7) — it mirrors the report plan but never defines structure.

---

## §16 Configuration Surface

The following keys are added to `config.py` for the synthesizer. Existing pipeline keys are not modified.

| Key | Type | Required | Default | Description |
|---|---|---|---|---|
| REPORT_PLAN_PATH | Path | Yes | — | Path to the report plan JSON file (§10.2). |
| STYLE_SHEET_PATH | Path | Yes | — | Path to the style sheet JSON file (§10.5). |
| SYNTHESIZER_OUTPUT_DIR | Path | No | `DATA_DIR / "synthesis"` | Root directory for all synthesizer outputs (§15). |
| CASCADE_DEPTH_LIMIT | int | No | 3 | Maximum cascade depth for change propagation (DR-04, FR-24). |
| LAYER1_RETRY_LIMIT | int | No | 3 | Max regeneration attempts after Layer 1 failure (DR-11, FR-15). |
| LAYER2_RETRY_LIMIT | int | No | 3 | Max regeneration attempts after Layer 2 failure (DR-12, FR-17). |
| LAYER3_RETRY_LIMIT | int | No | 2 | Max retry attempts for Layer 3 semantic validation (DR-13, FR-19). |
| CLAIM_EXTRACTION_RETRY_LIMIT | int | No | 1 | Max re-extraction attempts for claim tables (DR-14, FR-22). |
| SYNTHESIZER_MODEL | str | No | `PIPELINE_MODEL` | Model identifier for synthesizer LLM calls (DR-16, open). |
| TOKEN_BUDGET_CEILING | int | No | None | Maximum cumulative tokens (input+output) per run. None = no limit (DR-17, open, NFR-02). |

---

## §17 Observability and Metrics

### 17.1 Structured Log Event Catalog

The orchestrator emits a structured log event at every section state transition (NFR-06). Each event contains:

```json
{
  "event_type": "state_transition",
  "section_id": "methodology_comparison",
  "from_state": "drafted",
  "to_state": "drafted_pending_validation",
  "timestamp": "2026-04-11T14:22:03Z",
  "metadata": {
    "trigger_event": "layer_1_pass",
    "attempt": 1,
    "model": "claude-sonnet-4-20250514",
    "input_tokens": 3200,
    "output_tokens": 1100
  }
}
```

Additional event types: `run_started`, `run_completed`, `run_failed`, `cascade_triggered`, `escalation_triggered`, `checkpoint_written`, `assembly_started`, `assembly_completed`.

### 17.2 Post-Run Metrics

Seven metrics are computed at the end of each run and written to `{SYNTHESIZER_OUTPUT_DIR}/run_metrics.json` (NFR-07). Preserved from v3 §7.

| Metric | Definition | Target |
|---|---|---|
| Structural compliance rate | % of sections passing Layer 1 on first attempt | ≥90% |
| Style compliance rate | % of sections passing Layer 2 on first attempt | ≥85% |
| Dependency completeness | % of upstream claim table entries engaged by downstream sections | ≥80% |
| Unsupported claim rate | % of claims in generated sections not traceable to evidence | ≤10% |
| Revision churn | Average number of generation attempts per section | ≤2.0 |
| Claim-table completeness | % of sections with non-partial claim tables | ≥90% |
| Evidence-claim agreement | % of claim table entries whose confidence_tag is consistent with source material | ≥85% |

### 17.3 Model Selection Table

| Role | Model | Status |
|---|---|---|
| Generator | SYNTHESIZER_MODEL (default: PIPELINE_MODEL) | Open (DR-16) |
| Validator (Layer 3) | SYNTHESIZER_MODEL | Open — may use lighter model |
| Claim Extractor | SYNTHESIZER_MODEL | Open |
| Summary Abstractifier | SYNTHESIZER_MODEL | Open — may use lighter model |

### 17.4 Token Budget Table

| Role | Input Limit | Output Limit | Status |
|---|---|---|---|
| Generator | Open (DR-18) | 4000 tokens | Partially open |
| Validator (Layer 3) | Open | 1000 tokens per sub-check | Partially open |
| Claim Extractor | Open | 2000 tokens | Partially open |
| Summary Abstractifier | Open | 200 tokens | Partially open |

### 17.5 Concurrency Policy

v1 operates sequentially: one section at a time, processed in topological order of the generation DAG (DR-15). The `RunState` and `SectionState` schemas are designed with no shared mutable state between sections, enabling future parallel execution without schema changes. Parallel execution is a deferred capability.

---

## §18 Traceability Matrix

| Requirement ID | Schema(s) | Orchestrator Behavior | Validation Method | Acceptance Test |
|---|---|---|---|---|
| FR-01 | ReportPlan, SectionNode | — | Pydantic parse_obj | Valid JSON → parsed; malformed → error |
| FR-02 | ReportPlan, DependencyEdge | — | Graph validation at load | Dangling ref → error |
| FR-03 | DependencyEdge | — | Cycle detection (topological sort) | Cycle → error |
| FR-04 | StyleSheet | — | Pydantic parse_obj | Valid → parsed; invalid regex → error |
| FR-05 | StyleSheet, SectionOutput | — | Layer 2 rule check | Override applied for matching type |
| FR-06 | DependencyEdge, RunState | — | DAG construction | Correct adjacency and topo order |
| FR-07 | DependencyEdge, SectionState | — | Finalization-DAG check | Gen before ref finalized OK; finalize blocked |
| FR-08 | SectionState, DependencyEdge | Section stays `queued` until all content predecessors `finalized`; checked before each generation-DAG step | Generation-DAG prerequisite check (Layer 0) | C queued until A finalized |
| FR-09 | — | Invoke HybridRetriever.query() per source_query; aggregate results | Integration test | Both queries executed; chunks aggregated |
| FR-10 | — | Discard answer_text; pass ranked_chunks to prompt | Inspection of assembled prompt | Chunks present; answer text absent |
| FR-11 | ClaimTable, SectionOutput | Assemble prompt with all context channels per §13 | Inspection of assembled prompt | All channels present |
| FR-12 | — | Exclude raw upstream content_markdown from prompt assembly | Inspection | No raw upstream prose |
| FR-13 | SectionOutput (per-type) | Generator output expected as type-specific JSON | Layer 1 (Pydantic schema validation) | Correct subclass parse |
| FR-14 | SectionOutput, ValidationResult | Layer 1 runs immediately after generation_complete | Layer 1 (Pydantic schema validation) | Missing field → failure |
| FR-15 | ValidationResult | On L1 fail: append errors to prompt, re-invoke Generator | Layer 1 retry loop | Error in retry prompt; limit enforced |
| FR-16 | StyleSheet, ValidationResult | Layer 2 runs after Layer 1 pass | Layer 2 (deterministic rules) | Word count violation detected |
| FR-17 | ValidationResult | On L2 fail: append violations to prompt, re-invoke Generator | Layer 2 retry loop | Violations in retry; limit enforced |
| FR-18 | ClaimTable, ValidationResult | Layer 3 sub-check B compares section against upstream claim tables | Layer 3 (LLM semantic check) | Contradiction detected |
| FR-19 | SectionState, ValidationResult | On L3 retry exhaustion: transition to `escalated` | Layer 3 retry + escalation | Escalated after limit |
| FR-20 | ClaimTable, ClaimEntry | After L1-L3 pass, invoke Claim Extractor | Claim extraction prompt | ≥1 entry produced |
| FR-21 | ClaimTable, ClaimEntry | Validate claim table via 4 sub-checks before making available | Claim table validation (§12.4) | Missing source → fail |
| FR-22 | ClaimTable | On extraction retry exhaustion: set partial=True, proceed | Partial flag logic | Partial flag set; downstream warned |
| FR-23 | SectionState, DependencyEdge | On upstream content change: invalidate all content dependents | Cascade invalidation traversal | Dependents invalidated |
| FR-24 | RunState | Track cascade_depth per section; stop at CASCADE_DEPTH_LIMIT | Depth check before re-generation | Stops at limit |
| FR-25 | SectionState, DependencyEdge | On upstream ref change: re-validate pointers, don't re-generate | Reference re-validation | Re-validated, not re-generated |
| FR-26 | SectionOutput, ReportPlan | Assembler traverses plan hierarchy, adjusts heading levels | Assembler (deterministic) | Heading levels match depth |
| FR-27 | SectionState | Assembler checks all sections finalized/stable/escalated before proceeding | Assembler pre-check | Blocked if non-finalized |

---

## §19 Acceptance Criteria

Each functional requirement has at least one acceptance test defined below. These tests are referenced in the Traceability Matrix (§18).

| Requirement | Acceptance Test |
|---|---|
| FR-01 | Load valid ReportPlan JSON → parsed object with all fields. Load malformed JSON → descriptive error. |
| FR-02 | Report plan with dangling dependency ref → validation error naming the missing section_id. |
| FR-03 | Report plan with content-dependency cycle A→B→C→A → validation error identifying the cycle. |
| FR-04 | Load valid StyleSheet → parsed object. Invalid citation_pattern → validation error. |
| FR-05 | Section of type `evidence_table` with per_type_override → override constraints applied in Layer 2. |
| FR-06 | 5-section plan with known edges → DAG with correct adjacency and topological order. |
| FR-07 | Section B ref-depends on C → B can generate before C finalized; B cannot finalize before C finalized. |
| FR-08 | 3-section content chain A→B→C → C stays `queued` until A is `finalized`. |
| FR-09 | Section with 2 source_queries → both executed; ranked chunks aggregated. |
| FR-10 | Generation prompt contains chunk data; answer text absent. |
| FR-11 | Prompt for section with content+thematic deps → contains upstream claim table, summary abstract, chunks, description, style constraints. |
| FR-12 | No full upstream section text in any downstream generation prompt. |
| FR-13 | Each section type's output parses as correct SectionOutput subclass. |
| FR-14 | SectionOutput with missing field → Layer 1 failure with field-level error. |
| FR-15 | Layer 1 failure → retry prompt includes error; retry count ≤ LAYER1_RETRY_LIMIT. |
| FR-16 | Word count exceeds max → Layer 2 failure identifying the constraint. |
| FR-17 | Layer 2 failure → retry with violations; limit enforced. |
| FR-18 | Section contradicts upstream claim → dependency contract sub-check fails. |
| FR-19 | Layer 3 fails 3× (limit=2) → section transitions to `escalated`. |
| FR-20 | Finalized section → ClaimTable produced with ≥1 ClaimEntry. |
| FR-21 | ClaimEntry missing source_chunk_ids → traceability sub-check fails. |
| FR-22 | Extraction failure after retry → claim table marked `partial`; downstream warned. |
| FR-23 | Re-generate A in chain A→B→C → B invalidated; C invalidated on B re-finalization. |
| FR-24 | 5-section chain, cascade from root → propagation stops at depth 3. |
| FR-25 | Referenced section heading changes → referencing section re-validated, not re-generated. |
| FR-26 | 4 sections at varying depths → assembled heading levels match depth_level. |
| FR-27 | One section in `drafted` → assembly blocked with descriptive error. |

---

## §20 Risks

### 20.1 Preserved Risks (from v3 §12)

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R-01 | LLM output fails structural validation repeatedly, exhausting retries | Medium | High — section escalated, report incomplete | Layer 1 error feedback in retry prompts; configurable retry limits; escalation path |
| R-02 | Claim extraction produces partial tables, degrading downstream quality | Medium | Medium — downstream sections operate with incomplete context | Partial flag propagated; downstream Generator warned; metric tracking (claim-table completeness) |
| R-03 | Cascade propagation causes excessive re-generation cost | Low | High — token budget exhausted on cascades | CASCADE_DEPTH_LIMIT (DR-04); token budget ceiling (NFR-02) |
| R-04 | Style sheet constraints conflict with section type requirements | Low | Medium — Layer 2 failures on valid content | Per-type overrides in StyleSheet; conflict detection at load time |
| R-05 | Large report plans exceed model context window | Medium | High — generation fails | Token budget tracking per prompt role; chunked retrieval; prompt size monitoring |
| R-06 | Stage 05 retrieval returns low-relevance chunks | Medium | Medium — generated content poorly grounded | Multiple source_queries per section; retrieval score thresholds; unsupported claim detection (Layer 3 sub-check C) |

### 20.2 Additional Risk: Stage 05 Answer Text Re-Introduction

If a future maintainer removes the answer-text exclusion (DR-05) and injects Stage 05's pre-generated answers into generation prompts, the synthesizer would build on unvalidated synthesis rather than primary evidence. Mitigation: the exclusion is documented as a decided item in the Decision Register and enforced by the prompt assembly code path.

### 20.3 Dependency Classification

| Module | Classification | Action |
|---|---|---|
| `utils.metadata` (MetadataExtractor) | Required by Stage 01; not directly consumed by synthesizer | Audit or stub before synthesizer development to ensure Stage 01 can run |
| `utils.equation_handler` (EquationHandler) | Required by Stage 02; not consumed by synthesizer | Deferred — no action needed for synthesizer |
| `anthropic` package | Required by synthesizer and Stages 05/06 | Already a pipeline dependency; verify version compatibility |
| `chromadb`, `sentence-transformers`, `rank-bm25` | Required by Stage 05; consumed indirectly via HybridRetriever | Already pipeline dependencies; no changes needed |

### 20.4 Prerequisite Assumption

All prerequisite pipeline stages (01–04) must have been run successfully and their outputs must exist before the synthesizer is invoked (§3). The synthesizer validates the existence of required upstream artifacts (`manifest.json`, chunk files, ChromaDB collection, BM25 index) at startup and fails fast with descriptive errors if any are missing.

---

## §21 Decision Register

| ID | Description | Status | Rationale | Date |
|---|---|---|---|---|
| DR-01 | Directory tree is derived output, never canonical. The report plan is the sole structural authority; the filesystem mirrors it but does not define it. | Decided | Prevents drift between plan and output; single source of truth for structure. | v3 |
| DR-02 | Claim tables are validated before availability to downstream sections. A section's claim table must pass all four sub-checks (completeness, traceability, label consistency, cross-validation) before dependent sections may consume it. | Decided | Ensures downstream sections build on verified claims, not raw extraction output. | v3 |
| DR-03 | Raw upstream prose is excluded from downstream generation prompts. Downstream sections receive claim tables and summary abstracts, never the full text of upstream sections. | Decided | Prevents prompt bloat and uncontrolled context injection; forces structured information flow. | v3 |
| DR-04 | Cascade depth limit is 3. Change propagation from an upstream content change triggers re-generation of dependents, but the cascade terminates after 3 levels regardless of remaining graph depth. | Decided | Bounds worst-case re-generation cost and prevents infinite cascades in cyclic-adjacent structures. | v3 |
| DR-05 | Stage 05 answer text is excluded from generation prompts. The synthesizer uses the ranked chunk list from `HybridRetriever.query()` but discards the pre-generated answer text. | Decided | The answer text is a convenience summary for human readers; including it in generation prompts would inject unvalidated synthesis. | v3 |
| DR-06 | Stage 06 summaries are used for planning only, not as generation evidence. `PaperSummary` objects inform retrieval query construction but are never injected into generation prompts as source material. | Decided | Summaries are abstractions; generation must be grounded in primary chunk evidence from the vector store. | v3 |
| DR-07 | Content dependencies block generation (hard enforcement). A section with a content dependency on another section cannot begin generation until the upstream section reaches `finalized` state. | Decided | Content dependencies represent semantic prerequisites; generating without them produces unsupported content. | v3 |
| DR-08 | Reference dependencies block finalization, not generation. A section with a reference dependency may generate freely but cannot transition to `finalized` until the referenced section is finalized. | Decided | References are structural pointers (cross-refs, citations); the referring section's content does not depend on the referent's substance. | v3 |
| DR-09 | Thematic dependencies are soft (coherence check only). Thematic dependencies trigger a coherence validation check but do not block generation or finalization. | Decided | Thematic links represent tone/framing alignment, which is a quality signal, not a hard prerequisite. | v3 |
| DR-10 | Source dependencies are informational (consistency check only). Source dependencies flag shared evidence sources for consistency review but impose no ordering constraints. | Decided | Source overlap is a potential conflict indicator, not a generation dependency. | v3 |
| DR-11 | Layer 1 (structural) validation retry limit: 3. | Decided | Balances error recovery against cost. Three attempts provide sufficient signal that the generation prompt or model is systematically failing. | v3 |
| DR-12 | Layer 2 (rule-based) validation retry limit: 3. | Decided | Same rationale as DR-11. | v3 |
| DR-13 | Layer 3 (semantic) validation retry limit: 2. | Decided | Semantic validation is more expensive (LLM call); fewer retries are justified before escalation. | v3 |
| DR-14 | Claim extraction retry limit: 1. | Decided | Claim extraction failure after one retry is treated as partial extraction; the system proceeds with a `partial` flag rather than blocking the pipeline. | v3 |
| DR-15 | Concurrency model: v1 operates sequentially (one section at a time in topological order). Parallel execution is deferred. | Deferred | Sequential execution simplifies the initial implementation. Schemas and state machine are designed to be concurrency-safe for future parallel support. | v3/plan |
| DR-16 | Model selection per LLM role (Generator, Validator, Claim Extractor, Summary Abstractifier). | Open | May use a single model for all roles or differentiate by cost/capability. Requires benchmarking. | — |
| DR-17 | Cost ceiling per report run. | Open | No maximum token or dollar budget is currently specified. Should be defined before production use. | — |
| DR-18 | Token budget limits per prompt role (input context size, output token cap). | Open | Depends on model context window and empirical prompt sizing. | — |

---

## Preservation Map

| v3 Section | v4 Destination | Revision Type |
|---|---|---|
| §1 Problem Statement | Appendix A | Relocate |
| §2 Source of Truth Hierarchy | §7 | Formalize |
| §3 Dependency Taxonomy | §8 | Preserve + add schema refs |
| §4 Section Types | §9 | Extend with prompt contracts |
| §5 Validator Contract | §12 | Formalize with retry tables |
| §6 Context Channels | §13 | Preserve + add cross-refs |
| §7 Evaluation Metrics | §17 | Extend with output spec |
| §8 Section Lifecycle | §11 | Formalize into state table |
| §9 Provenance Record | §10 (schema) + Appendix D (example) | Formalize |
| §10 Context Review | Appendix B | Relocate |
| §11 Pipeline Summary | Appendix C | Relocate |
| §12 Risks | §20 | Extend |

---

## Appendix A: Problem Statement

*[Relocated from v3 §1. Contains the original problem statement motivating the Report Synthesizer Agent: the need for a system that transforms fragmented pipeline outputs (parsed PDFs, chunks, embeddings, retrieval results, per-paper summaries) into a coherent, structured literature review with proper citation, cross-referencing, and evidence grounding.]*

---

## Appendix B: Context Review and Related Systems

*[Relocated from v3 §10. Contains the survey of related approaches to automated literature review, report generation, and multi-document synthesis systems that informed the design.]*

---

## Appendix C: Existing Pipeline Summary

*[Relocated from v3 §11. Contains the pipeline architecture table describing stages 01–06, their inputs, outputs, and dependencies. Key integration points referenced in §14.]*

### Pipeline Stage Summary

| Stage | Script | Purpose | Key Inputs | Key Outputs |
|---|---|---|---|---|
| 01 | `01_ingest.py` | PDF intake and metadata extraction | `data/pdfs/*.pdf` | `data/manifest.json` |
| 02 | `02_parse.py` | PDF-to-Markdown with equation enhancement | `manifest.json`, PDFs | `data/parsed/*_merged.md` |
| 03 | `03_chunk.py` | Section-aware chunking with equation preservation | `manifest.json`, merged `.md` files | `data/parsed/*_chunks.json`, `all_chunks.json` |
| 04 | `04_index.py` | Dual indexing (ChromaDB + BM25) | `all_chunks.json` | `data/vectorstore/` (ChromaDB collection + `bm25_index.pkl`) |
| 05 | `05_query.py` | Hybrid retrieval and answer generation | Query string, vector store | `(answer_text, ranked_chunks)` |
| 06 | `06_review.py` | Map-reduce literature review | `manifest.json`, chunks, Anthropic API | `data/summaries/*_summary.json`, `literature_review.md` |

---

## Appendix D: Provenance Record Example

*[Relocated from v3 §9. The JSON example below illustrates the audit trail captured for each finalized section. The formal schema definition is in §10 (ProvenanceRecord).]*

```json
{
  "section_id": "methodology_comparison",
  "finalized_at": "2026-04-11T14:30:00Z",
  "generation_model": "claude-sonnet-4-20250514",
  "generation_attempts": 2,
  "validation_history": [
    {"layer": "structural", "attempt": 1, "passed": true},
    {"layer": "rule_based", "attempt": 1, "passed": false, "violations": ["word_count_exceeded"]},
    {"layer": "structural", "attempt": 2, "passed": true},
    {"layer": "rule_based", "attempt": 2, "passed": true},
    {"layer": "semantic", "attempt": 1, "passed": true}
  ],
  "claim_table_version": 1,
  "claim_table_partial": false,
  "source_chunk_ids": ["paper_a_intro_0_0", "paper_b_methods_1_3", "paper_c_results_0_7"],
  "upstream_dependencies_consumed": {
    "content": ["background_overview"],
    "reference": [],
    "thematic": ["research_gaps"]
  },
  "cascade_triggers_received": 0,
  "word_count": 847,
  "heading_level": 2
}
```

---

### Sprint 1 Handoff Note

**Sections drafted:** §1 Purpose and Document Status, §2 Scope and Non-Goals, §3 Assumptions and Prerequisites, §21 Decision Register (18 entries: 14 decided, 1 deferred, 3 open), Appendices A–D, Preservation Map, all remaining sections as titled placeholders.

**Decision register entries:** 18 (exceeds the ≥15 minimum).

**Ambiguities noted for later sprints:**
- The v3 spec and QA report are not available as standalone files; design content is reconstructed from the major revision plan's detailed references and the pipeline source code. Sprint 2 should verify requirement extraction against the plan's coverage areas rather than v3 prose directly.
- The `drafted-pending-validation` state is listed in the plan but its relationship to `drafted` is not fully described; Sprint 4 must define the distinction.
- Appendices A, B contain placeholder descriptions rather than verbatim v3 text since the v3 document is not available as a file. If the v3 text becomes available, these should be replaced with the original content.

---

## Approval Gate Checklist

| # | Gate Condition | Status |
|---|---|---|
| G-1 | All FRs numbered with unique stable IDs (FR-01 through FR-27) | **Pass** — 27 FRs, contiguous, no duplicates |
| G-2 | All NFRs numbered with unique stable IDs (NFR-01 through NFR-09) | **Pass** — 9 NFRs, contiguous, no duplicates |
| G-3 | Every named artifact has field-level schema definition | **Pass** — §10 defines: ReportPlan, SectionNode, DependencyEdge, StyleSheet, LevelConstraint, EquationDelimiters, ClaimEntry, TextSpan, ClaimTable, SectionOutput (base), NarrativeSynthesisOutput, EvidenceTableOutput, CrossReferenceOutput, MethodologyDescriptionOutput, ValidationResult, Violation, ProvenanceRecord, SectionState, RunState + 6 enums |
| G-4 | All lifecycle states have defined transitions | **Pass** — §11 transition table covers all 9 states and all 17 events; every state has ≥1 outgoing transition |
| G-5 | All LLM-facing prompt roles have I/O contracts | **Pass** — §9 defines: Generator, Validator (3 sub-checks), Claim Extractor, Summary Abstractifier + Assembler |
| G-6 | All integration boundaries documented | **Pass** — §14 contracts for Stage 05, Stage 06, config module; integration strategy statement present |
| G-7 | Every FR maps to ≥1 acceptance criterion | **Pass** — §19 contains one acceptance test per FR |
| G-8 | Traceability matrix complete | **Pass** — §18 contains one row per FR with all 5 columns populated |
| G-9 | Decision register distinguishes decided/open/deferred | **Pass** — §21 contains 18 entries (14 decided, 1 deferred, 3 open) |
| G-10 | Document self-identifies as governing specification | **Pass** — §1 explicitly states governing status |

**Result:** All 10 gate conditions pass. Document is ready for implementation planning handoff.

### QA Coverage Verification

| QA Finding | Addressed In |
|---|---|
| QA-01: Not yet a governing spec | §1 Purpose and Document Status |
| QA-02: No requirements list | §4 (27 FRs), §5 (9 NFRs) |
| QA-03: Schemas named but not defined | §10 Schema Definitions (19 models + 6 enums) |
| QA-04: Source-of-truth ambiguity | §7 Source of Truth Hierarchy + DR-01 |
| QA-05: Orchestration lifecycle underspecified | §11 Orchestration State Machine |
| QA-06: Validation semantics undefined | §12 Validation Design + ValidationResult schema |
| QA-07: Prompt contracts missing | §9 Section Types and Prompt Contracts |
| QA-08: Integration contracts missing | §14 Integration Contracts |
| QA-09: Filesystem contract missing | §15 File Layout and Artifact Conventions |
| QA-10: Testability undefined | §19 Acceptance Criteria + §18 Traceability Matrix |
| QA-11: Missing dependency risks | §20 Risks (dependency classification) |
| QA-12: No non-goals | §2 Scope and Non-Goals (7 non-goals) |
| QA-13: No decision log | §21 Decision Register (18 entries) |
| QA-14: Operational concerns absent | §16 Config + §17 Observability |

All 14 QA findings addressed.