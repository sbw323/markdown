"""
orchestrator.py — Control-plane implementation for the Report Synthesizer Agent.

Governs the end-to-end lifecycle: initialisation, DAG-driven section sequencing,
per-section generation/validation/extraction/finalization, checkpoint/resume,
cascade propagation, final assembly, and completion reporting.

Governing specification: report_synthesizer_v4.md (v4.0)
"""

from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import tools
from tools import SynthesizerConfig
import sprints
import prompts


# ---------------------------------------------------------------------------
# §11.1  Legal state-transition table
# ---------------------------------------------------------------------------

# Maps (current_state, event) -> (next_state, checkpoint?)
_TRANSITION_TABLE: Dict[Tuple[str, str], Tuple[str, bool]] = {
    ("queued", "prerequisites_met"): ("generating", True),
    ("generating", "generation_complete"): ("drafted", True),
    ("generating", "generation_failed"): ("queued", True),
    ("drafted", "layer_1_pass"): ("drafted_pending_validation", True),
    ("drafted", "layer_1_fail"): ("generating", True),
    ("drafted", "layer_1_retry_exhausted"): ("escalated", True),
    ("drafted_pending_validation", "layer_2_pass"): ("drafted_pending_validation", False),
    ("drafted_pending_validation", "layer_2_fail"): ("generating", True),
    ("drafted_pending_validation", "layer_2_retry_exhausted"): ("escalated", True),
    ("drafted_pending_validation", "layer_3_pass"): ("validated", True),
    ("drafted_pending_validation", "layer_3_fail"): ("generating", True),
    ("drafted_pending_validation", "layer_3_retry_exhausted"): ("escalated", True),
    ("validated", "claim_table_pass"): ("finalized", True),
    ("validated", "claim_table_fail"): ("validated", True),
    ("finalized", "upstream_content_changed"): ("invalidated", True),
    ("finalized", "upstream_reference_changed"): ("finalized", False),
    ("finalized", "upstream_soft_dependency_changed"): ("finalized", False),
    ("stable", "upstream_content_changed"): ("invalidated", True),
    ("stable", "upstream_reference_changed"): ("stable", False),
    ("stable", "upstream_soft_dependency_changed"): ("stable", False),
    ("invalidated", "prerequisites_met"): ("generating", True),
    ("invalidated", "cascade_depth_exceeded"): ("escalated", True),
}


# ---------------------------------------------------------------------------
# Lightweight internal data holders (not Pydantic — those live in synthesizer/models)
# ---------------------------------------------------------------------------

class SectionState:
    """Mutable per-section state managed by the orchestrator."""

    def __init__(self, section_id: str) -> None:
        self.section_id: str = section_id
        self.state: str = "queued"
        self.version: int = 0
        self.retry_counters: Dict[str, int] = {
            "layer_1": 0,
            "layer_2": 0,
            "layer_3": 0,
            "claim_extraction": 0,
        }
        self.claim_table: Optional[Any] = None
        self.summary_abstract: Optional[str] = None
        self.draft_text: Optional[str] = None
        self.section_output: Optional[Any] = None
        self.retrieved_chunks: List[Dict[str, Any]] = []
        self.validation_history: List[Dict[str, Any]] = []
        self.last_transition_timestamp: str = tools.iso_now()
        self.cascade_depth: int = 0
        self.last_error_feedback: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "section_id": self.section_id,
            "state": self.state,
            "version": self.version,
            "retry_counters": self.retry_counters,
            "claim_table": self.claim_table,
            "summary_abstract": self.summary_abstract,
            "validation_history": self.validation_history,
            "last_transition_timestamp": self.last_transition_timestamp,
            "cascade_depth": self.cascade_depth,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SectionState":
        ss = cls(data["section_id"])
        ss.state = data.get("state", "queued")
        ss.version = data.get("version", 0)
        ss.retry_counters = data.get("retry_counters", ss.retry_counters)
        ss.claim_table = data.get("claim_table")
        ss.summary_abstract = data.get("summary_abstract")
        ss.validation_history = data.get("validation_history", [])
        ss.last_transition_timestamp = data.get("last_transition_timestamp", tools.iso_now())
        ss.cascade_depth = data.get("cascade_depth", 0)
        return ss


class RunState:
    """Top-level run state holding all section states and token counters."""

    def __init__(self, report_plan_version: str, section_ids: List[str]) -> None:
        self.report_plan_version: str = report_plan_version
        self.section_states: Dict[str, SectionState] = {
            sid: SectionState(sid) for sid in section_ids
        }
        self.cumulative_input_tokens: int = 0
        self.cumulative_output_tokens: int = 0
        self.started_at: str = tools.iso_now()
        self.completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_plan_version": self.report_plan_version,
            "section_states": {
                sid: ss.to_dict() for sid, ss in self.section_states.items()
            },
            "cumulative_input_tokens": self.cumulative_input_tokens,
            "cumulative_output_tokens": self.cumulative_output_tokens,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    def json(self, indent: int = 2) -> str:  # noqa: A003 — compat with tools.save_checkpoint
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunState":
        section_ids = list(data.get("section_states", {}).keys())
        rs = cls(data.get("report_plan_version", ""), section_ids)
        for sid, ss_data in data.get("section_states", {}).items():
            rs.section_states[sid] = SectionState.from_dict(ss_data)
        rs.cumulative_input_tokens = data.get("cumulative_input_tokens", 0)
        rs.cumulative_output_tokens = data.get("cumulative_output_tokens", 0)
        rs.started_at = data.get("started_at", tools.iso_now())
        rs.completed_at = data.get("completed_at")
        return rs


# ---------------------------------------------------------------------------
# DAG helpers
# ---------------------------------------------------------------------------

def _build_dag(
    sections: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    edge_kinds: Set[str],
) -> Dict[str, List[str]]:
    """Build adjacency list: target -> [predecessors] for edges of given kinds."""
    section_ids = {s["section_id"] for s in sections}
    dag: Dict[str, List[str]] = {sid: [] for sid in section_ids}
    for edge in edges:
        if edge.get("kind") in edge_kinds or edge.get("dependency_kind") in edge_kinds:
            src = edge.get("source_section_id") or edge.get("from_section_id")
            tgt = edge.get("target_section_id") or edge.get("to_section_id")
            if src in section_ids and tgt in section_ids:
                dag[tgt].append(src)
    return dag


def _topological_order(dag: Dict[str, List[str]]) -> List[str]:
    """Kahn's algorithm. Raises on cycle."""
    in_degree: Dict[str, int] = {n: 0 for n in dag}
    forward: Dict[str, List[str]] = {n: [] for n in dag}
    for node, preds in dag.items():
        for p in preds:
            forward[p].append(node)
            in_degree[node] += 1
    queue: deque[str] = deque(n for n, d in in_degree.items() if d == 0)
    order: List[str] = []
    while queue:
        n = queue.popleft()
        order.append(n)
        for succ in forward[n]:
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)
    if len(order) != len(dag):
        raise ValueError("Content-dependency cycle detected (FR-03)")
    return order


def _content_dependents(
    section_id: str,
    edges: List[Dict[str, Any]],
) -> List[str]:
    """Return direct content-dependent section IDs of a given section."""
    dependents: List[str] = []
    for edge in edges:
        kind = edge.get("kind") or edge.get("dependency_kind")
        src = edge.get("source_section_id") or edge.get("from_section_id")
        tgt = edge.get("target_section_id") or edge.get("to_section_id")
        if kind == "content" and src == section_id:
            dependents.append(tgt)
    return dependents


def _reference_dependents(
    section_id: str,
    edges: List[Dict[str, Any]],
) -> List[str]:
    dependents: List[str] = []
    for edge in edges:
        kind = edge.get("kind") or edge.get("dependency_kind")
        src = edge.get("source_section_id") or edge.get("from_section_id")
        tgt = edge.get("target_section_id") or edge.get("to_section_id")
        if kind == "reference" and src == section_id:
            dependents.append(tgt)
    return dependents


# ---------------------------------------------------------------------------
# Budget-exceeded sentinel
# ---------------------------------------------------------------------------

class BudgetExceededError(RuntimeError):
    """Raised when TOKEN_BUDGET_CEILING is reached (NFR-02)."""


# ---------------------------------------------------------------------------
# SynthesizerOrchestrator
# ---------------------------------------------------------------------------

class SynthesizerOrchestrator:
    """Central control-plane for the Report Synthesizer end-to-end lifecycle.

    Public interface:
        __init__(*, config_module, retriever, generator, validator,
                 claim_extractor, summary_abstractifier, assembler)
        run() -> Path   — execute the full lifecycle, return final report path
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        *,
        config_module: Any = None,
        retriever: Any = None,
        generator: Any = None,
        validator: Any = None,
        claim_extractor: Any = None,
        summary_abstractifier: Any = None,
        assembler: Any = None,
        planning_loader: Optional[Callable[[], List[Any]]] = None,
    ) -> None:
        # Phase 1 — Initialisation (§6 step 1)
        self.config: SynthesizerConfig = tools.load_synthesizer_config(
            config_module=config_module,
        )
        self.retriever = retriever
        self.generator = generator
        self.validator = validator
        self.claim_extractor = claim_extractor
        self.summary_abstractifier = summary_abstractifier
        self.assembler = assembler
        self.planning_loader = planning_loader

        # Will be populated during _initialise()
        self.report_plan: Dict[str, Any] = {}
        self.style_sheet: Dict[str, Any] = {}
        self.sections: List[Dict[str, Any]] = []
        self.edges: List[Dict[str, Any]] = []
        self.generation_dag: Dict[str, List[str]] = {}
        self.finalization_dag: Dict[str, List[str]] = {}
        self.topo_order: List[str] = []
        self.run_state: RunState = RunState("", [])
        self.planning_summaries: List[Any] = []
        self.output_dir: Path = self.config.SYNTHESIZER_OUTPUT_DIR

    # ------------------------------------------------------------------
    # Phase 1: Initialisation
    # ------------------------------------------------------------------

    def _load_report_plan(self) -> Dict[str, Any]:
        """Load and validate the report plan from config path (FR-01, FR-02, FR-03)."""
        plan_path = Path(self.config.REPORT_PLAN_PATH)
        with open(plan_path, "r") as f:
            plan = json.load(f)

        # Validate section IDs
        sections = plan.get("sections", [])
        section_ids = set()
        for s in sections:
            sid = s.get("section_id", "")
            tools.validate_section_id(sid)
            if sid in section_ids:
                raise ValueError(f"Duplicate section_id in plan: {sid!r}")
            section_ids.add(sid)

        # Validate dependency references (FR-02)
        edges = plan.get("dependency_edges", [])
        for edge in edges:
            src = edge.get("source_section_id") or edge.get("from_section_id")
            tgt = edge.get("target_section_id") or edge.get("to_section_id")
            if src not in section_ids:
                raise ValueError(
                    f"Dangling dependency source: {src!r} not in plan sections (FR-02)"
                )
            if tgt not in section_ids:
                raise ValueError(
                    f"Dangling dependency target: {tgt!r} not in plan sections (FR-02)"
                )

        return plan

    def _load_style_sheet(self) -> Dict[str, Any]:
        """Load and validate the style sheet (FR-04)."""
        ss_path = Path(self.config.STYLE_SHEET_PATH)
        with open(ss_path, "r") as f:
            sheet = json.load(f)

        # Validate citation_pattern as compilable regex (FR-04)
        import re
        pattern = sheet.get("citation_pattern", "")
        if pattern:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(
                    f"citation_pattern is not a valid regex (FR-04): {exc}"
                ) from exc

        return sheet

    def _initialise(self) -> None:
        """Execute all Phase 1 steps."""
        # Step 1: config already loaded in __init__

        # Step 2: report plan
        self.report_plan = self._load_report_plan()
        self.sections = self.report_plan.get("sections", [])
        self.edges = self.report_plan.get("dependency_edges", [])

        # Step 3: style sheet
        self.style_sheet = self._load_style_sheet()

        # Step 4: build DAGs (FR-06, FR-07)
        self.generation_dag = _build_dag(self.sections, self.edges, {"content"})
        self.finalization_dag = _build_dag(
            self.sections, self.edges, {"content", "reference"}
        )
        # Topological order from generation DAG (FR-03 — will raise on cycle)
        self.topo_order = _topological_order(self.generation_dag)

        # Step 5: scaffold output directory
        section_ids = [s["section_id"] for s in self.sections]
        tools.scaffold_output_directory(self.output_dir, section_ids)

        # Step 6: checkpoint resume
        existing = tools.load_checkpoint(self.output_dir)
        if existing is not None:
            plan_version = self.report_plan.get("version", "")
            ckpt_version = existing.get("report_plan_version", "")
            if ckpt_version and ckpt_version != plan_version:
                tools.emit_event(
                    "checkpoint_version_mismatch",
                    section_id=None,
                    from_state=None,
                    to_state=None,
                    metadata={
                        "checkpoint_version": ckpt_version,
                        "plan_version": plan_version,
                    },
                )
            # Apply resume policy
            ckpt_sections = existing.get("section_states", {})
            tools.apply_resume_policy(ckpt_sections)
            self.run_state = RunState.from_dict(existing)
            # Ensure any new sections in plan that aren't in checkpoint get added
            for sid in section_ids:
                if sid not in self.run_state.section_states:
                    self.run_state.section_states[sid] = SectionState(sid)
        else:
            plan_version = self.report_plan.get("version", "")
            self.run_state = RunState(plan_version, section_ids)

        # Step 7: emit run_started
        tools.emit_event(
            "run_started",
            section_id=None,
            from_state=None,
            to_state=None,
            metadata={"report_plan_version": self.report_plan.get("version", "")},
        )

        # Step 8: load planning context (DR-06 — planning only)
        if self.planning_loader is not None:
            self.planning_summaries = tools.load_planning_summaries(self.planning_loader)

    # ------------------------------------------------------------------
    # State transition engine (§11)
    # ------------------------------------------------------------------

    def _transition(self, section_id: str, event: str) -> str:
        """Execute a legal state transition. Returns the new state.

        Raises ValueError on illegal transitions (defensive programming).
        """
        ss = self.run_state.section_states[section_id]
        current = ss.state
        key = (current, event)
        if key not in _TRANSITION_TABLE:
            raise ValueError(
                f"Illegal transition: section={section_id!r} "
                f"state={current!r} event={event!r}"
            )
        next_state, should_checkpoint = _TRANSITION_TABLE[key]
        from_state = current
        ss.state = next_state
        ss.last_transition_timestamp = tools.iso_now()

        tools.emit_event(
            "state_transition",
            section_id=section_id,
            from_state=from_state,
            to_state=next_state,
            metadata={"event": event},
        )

        if should_checkpoint:
            tools.save_checkpoint(self.run_state, self.output_dir)

        return next_state

    # ------------------------------------------------------------------
    # Helper: resolve model for a role (DR-16)
    # ------------------------------------------------------------------

    def _model_for_role(self, role: str) -> str:
        """Return model string for a given role, respecting DR-16 overrides."""
        return self.config.model_overrides.get(role, self.config.SYNTHESIZER_MODEL)

    # ------------------------------------------------------------------
    # Helper: record tokens + budget check
    # ------------------------------------------------------------------

    def _record_and_check_budget(
        self, input_tokens: int, output_tokens: int
    ) -> None:
        """Record token usage and raise BudgetExceededError if ceiling hit (NFR-02)."""
        tools.record_token_usage(self.run_state, input_tokens, output_tokens)
        if tools.check_budget_ceiling(self.run_state, self.config.TOKEN_BUDGET_CEILING):
            raise BudgetExceededError(
                f"Token budget ceiling reached: "
                f"{self.config.TOKEN_BUDGET_CEILING} (NFR-02)"
            )

    # ------------------------------------------------------------------
    # Phase 2: Section Processing
    # ------------------------------------------------------------------

    def _prerequisites_met(self, section_id: str) -> bool:
        """Check all content-dependency predecessors are finalized (FR-08)."""
        preds = self.generation_dag.get(section_id, [])
        for pred in preds:
            pred_state = self.run_state.section_states[pred].state
            if pred_state not in ("finalized", "stable"):
                return False
        return True

    def _gather_upstream_claim_tables(self, section_id: str) -> List[Any]:
        """Collect claim tables from content-dependency predecessors (§13.1)."""
        tables: List[Any] = []
        preds = self.generation_dag.get(section_id, [])
        for pred in preds:
            ct = self.run_state.section_states[pred].claim_table
            if ct is not None:
                tables.append(ct)
        return tables

    def _gather_upstream_summaries(self, section_id: str) -> List[str]:
        """Collect summary abstracts from thematic-dependency predecessors (§13.2)."""
        summaries: List[str] = []
        for edge in self.edges:
            kind = edge.get("kind") or edge.get("dependency_kind")
            tgt = edge.get("target_section_id") or edge.get("to_section_id")
            src = edge.get("source_section_id") or edge.get("from_section_id")
            if kind == "thematic" and tgt == section_id:
                sa = self.run_state.section_states.get(src)
                if sa and sa.summary_abstract:
                    summaries.append(sa.summary_abstract)
        return summaries

    def _get_section_def(self, section_id: str) -> Dict[str, Any]:
        """Return the section definition dict from the report plan."""
        for s in self.sections:
            if s["section_id"] == section_id:
                return s
        raise KeyError(f"Section {section_id!r} not in plan")

    def _build_generation_context(
        self,
        section_id: str,
        chunks: List[Dict[str, Any]],
        error_feedback: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Assemble all context channels for the generation prompt (§9.2.1, §13).

        Excludes raw upstream prose (DR-03) and answer text (DR-05).
        """
        section_def = self._get_section_def(section_id)
        return {
            "section": section_def,
            "style_sheet": self.style_sheet,
            "retrieved_chunks": chunks,  # DR-05 enforced by tools.retrieve_chunks
            "upstream_claim_tables": self._gather_upstream_claim_tables(section_id),  # §13.1
            "upstream_summaries": self._gather_upstream_summaries(section_id),  # §13.2
            "error_feedback": error_feedback,
            "model": self._model_for_role("generator"),
        }

    # -- Step 2b: Retrieval ------------------------------------------------

    def _retrieve(self, section_id: str) -> List[Dict[str, Any]]:
        """Invoke retriever for section source queries (FR-09, DR-05)."""
        section_def = self._get_section_def(section_id)
        queries = section_def.get("source_queries", [])
        if not queries:
            return []
        return tools.retrieve_chunks(self.retriever, queries)

    # -- Step 2c: Generation -----------------------------------------------

    def _generate_section(
        self,
        section_id: str,
        chunks: List[Dict[str, Any]],
        error_feedback: Optional[str] = None,
    ) -> Any:
        """Invoke the generator LLM and return the raw response.

        Records tokens, checks latency and budget.
        """
        context = self._build_generation_context(section_id, chunks, error_feedback)
        t0 = time.monotonic()
        response = self.generator.generate(context)
        elapsed = time.monotonic() - t0

        # Token accounting
        input_tokens = getattr(response, "input_tokens", 0) or 0
        output_tokens = getattr(response, "output_tokens", 0) or 0
        self._record_and_check_budget(input_tokens, output_tokens)

        # Latency check (NFR-01)
        warning = tools.check_generation_latency(elapsed)
        if warning:
            tools.emit_event(
                "latency_warning",
                section_id=section_id,
                from_state=None,
                to_state=None,
                metadata={"warning": warning, "elapsed_seconds": elapsed},
            )

        return response

    # -- Step 2d: Validation -----------------------------------------------

    def _validate_layer1(self, section_id: str, response: Any) -> Tuple[bool, Any]:
        """Layer 1 — structural validation (§12.1). Returns (passed, violations)."""
        result = self.validator.validate_layer1(response)
        passed = getattr(result, "passed", False)
        violations = getattr(result, "violations", [])
        self.run_state.section_states[section_id].validation_history.append({
            "layer": "layer_1",
            "attempt": self.run_state.section_states[section_id].retry_counters["layer_1"] + 1,
            "passed": passed,
            "timestamp": tools.iso_now(),
        })
        return passed, violations

    def _validate_layer2(self, section_id: str, section_output: Any) -> Tuple[bool, Any]:
        """Layer 2 — rule-based validation (§12.2)."""
        result = self.validator.validate_layer2(section_output, self.style_sheet)
        passed = getattr(result, "passed", False)
        violations = getattr(result, "violations", [])
        self.run_state.section_states[section_id].validation_history.append({
            "layer": "layer_2",
            "attempt": self.run_state.section_states[section_id].retry_counters["layer_2"] + 1,
            "passed": passed,
            "timestamp": tools.iso_now(),
        })
        return passed, violations

    def _validate_layer3(
        self,
        section_id: str,
        section_output: Any,
        chunks: List[Dict[str, Any]],
    ) -> Tuple[bool, Any]:
        """Layer 3 — semantic validation with three sub-checks (§12.3, §9.2.2)."""
        upstream_tables = self._gather_upstream_claim_tables(section_id)

        # Sub-check A: tone compliance
        tone_result = self.validator.validate_tone(
            section_output, self.style_sheet,
            model=self._model_for_role("validator"),
        )
        self._record_and_check_budget(
            getattr(tone_result, "input_tokens", 0) or 0,
            getattr(tone_result, "output_tokens", 0) or 0,
        )

        # Sub-check B: dependency contract fulfillment
        dep_result = self.validator.validate_dependency_contract(
            section_output, upstream_tables,
            model=self._model_for_role("validator"),
        )
        self._record_and_check_budget(
            getattr(dep_result, "input_tokens", 0) or 0,
            getattr(dep_result, "output_tokens", 0) or 0,
        )

        # Sub-check C: unsupported claim detection
        claim_result = self.validator.validate_unsupported_claims(
            section_output, chunks, upstream_tables,
            model=self._model_for_role("validator"),
        )
        self._record_and_check_budget(
            getattr(claim_result, "input_tokens", 0) or 0,
            getattr(claim_result, "output_tokens", 0) or 0,
        )

        all_passed = (
            getattr(tone_result, "passed", False)
            and getattr(dep_result, "passed", False)
            and getattr(claim_result, "passed", False)
        )

        # Merge results for feedback formatting
        combined_result = {
            "passed": all_passed,
            "violations": (
                getattr(tone_result, "violations", [])
                + getattr(dep_result, "violations", [])
                + getattr(claim_result, "violations", [])
            ),
            "suggested_fix": (
                getattr(tone_result, "suggested_fix", None)
                or getattr(dep_result, "suggested_fix", None)
                or getattr(claim_result, "suggested_fix", None)
            ),
        }

        self.run_state.section_states[section_id].validation_history.append({
            "layer": "layer_3",
            "attempt": self.run_state.section_states[section_id].retry_counters["layer_3"] + 1,
            "passed": all_passed,
            "timestamp": tools.iso_now(),
        })

        return all_passed, combined_result

    # -- Step 2e: Claim table extraction -----------------------------------

    def _extract_claim_table(
        self,
        section_id: str,
        section_output: Any,
        chunks: List[Dict[str, Any]],
    ) -> Tuple[bool, Any]:
        """Invoke claim extractor and validate (§12.4, §9.2.3)."""
        result = self.claim_extractor.extract(
            section_output, chunks,
            model=self._model_for_role("claim_extractor"),
        )
        self._record_and_check_budget(
            getattr(result, "input_tokens", 0) or 0,
            getattr(result, "output_tokens", 0) or 0,
        )
        claim_table = getattr(result, "claim_table", result)
        validation = self.claim_extractor.validate_claim_table(claim_table)
        passed = getattr(validation, "passed", False)
        return passed, claim_table

    # -- Step 2e cont.: summary abstractifier ------------------------------

    def _abstractify(self, section_id: str, section_output: Any) -> str:
        """Invoke summary abstractifier (§9.2.4)."""
        result = self.summary_abstractifier.abstractify(
            section_output,
            model=self._model_for_role("abstractifier"),
        )
        self._record_and_check_budget(
            getattr(result, "input_tokens", 0) or 0,
            getattr(result, "output_tokens", 0) or 0,
        )
        return getattr(result, "summary", str(result))

    # -- Full per-section pipeline -----------------------------------------

    def _process_section(self, section_id: str) -> None:
        """Run the full generation→validation→extraction pipeline for one section."""
        ss = self.run_state.section_states[section_id]

        # Step 2a: prerequisite check (FR-08)
        if not self._prerequisites_met(section_id):
            return  # will be revisited later

        tools.emit_event(
            "prerequisites_met",
            section_id=section_id,
            from_state=ss.state,
            to_state=None,
        )

        # Step 2b: retrieval
        chunks = self._retrieve(section_id)
        ss.retrieved_chunks = chunks

        # Transition queued/invalidated → generating
        if ss.state in ("queued", "invalidated"):
            self._transition(section_id, "prerequisites_met")

        # Step 2c–2e: generation/validation loop
        self._generation_validation_loop(section_id, chunks)

    def _generation_validation_loop(
        self,
        section_id: str,
        chunks: List[Dict[str, Any]],
    ) -> None:
        """Drive generation → L1 → L2 → L3 → claim extraction for a section."""
        ss = self.run_state.section_states[section_id]

        while ss.state == "generating":
            # Generate
            error_feedback = ss.last_error_feedback
            ss.last_error_feedback = None

            try:
                response = self._generate_section(section_id, chunks, error_feedback)
            except BudgetExceededError:
                raise
            except Exception:
                self._transition(section_id, "generation_failed")
                ss.retry_counters["layer_1"] += 0  # API failure, not a layer retry
                return

            ss.version += 1
            # Write draft
            draft_p = tools.draft_path(self.output_dir, section_id, ss.version)
            draft_p.parent.mkdir(parents=True, exist_ok=True)
            draft_text = getattr(response, "text", str(response))
            draft_p.write_text(draft_text)
            ss.draft_text = draft_text
            ss.section_output = response

            self._transition(section_id, "generation_complete")
            # Now state is 'drafted'

            # --- Layer 1 ---
            l1_passed, l1_violations = self._validate_layer1(section_id, response)
            if l1_passed:
                self._transition(section_id, "layer_1_pass")
            else:
                ss.retry_counters["layer_1"] += 1
                if ss.retry_counters["layer_1"] > self.config.LAYER1_RETRY_LIMIT:
                    self._transition(section_id, "layer_1_retry_exhausted")
                    tools.emit_event(
                        "escalation_triggered",
                        section_id=section_id,
                        from_state="drafted",
                        to_state="escalated",
                        metadata={"layer": "layer_1"},
                    )
                    return
                ss.last_error_feedback = tools.format_layer1_errors(l1_violations)
                self._transition(section_id, "layer_1_fail")
                continue  # loop back to generating

            # --- Layer 2 ---
            section_output = ss.section_output
            l2_passed, l2_violations = self._validate_layer2(section_id, section_output)
            if l2_passed:
                # No checkpoint on L2 pass — transition table says False
                pass
            else:
                ss.retry_counters["layer_2"] += 1
                if ss.retry_counters["layer_2"] > self.config.LAYER2_RETRY_LIMIT:
                    self._transition(section_id, "layer_2_retry_exhausted")
                    tools.emit_event(
                        "escalation_triggered",
                        section_id=section_id,
                        from_state="drafted_pending_validation",
                        to_state="escalated",
                        metadata={"layer": "layer_2"},
                    )
                    return
                ss.last_error_feedback = tools.format_layer2_violations(l2_violations)
                self._transition(section_id, "layer_2_fail")
                continue

            # --- Layer 3 ---
            l3_passed, l3_result = self._validate_layer3(
                section_id, section_output, chunks
            )
            if l3_passed:
                self._transition(section_id, "layer_3_pass")
            else:
                ss.retry_counters["layer_3"] += 1
                if ss.retry_counters["layer_3"] > self.config.LAYER3_RETRY_LIMIT:
                    self._transition(section_id, "layer_3_retry_exhausted")
                    tools.emit_event(
                        "escalation_triggered",
                        section_id=section_id,
                        from_state="drafted_pending_validation",
                        to_state="escalated",
                        metadata={"layer": "layer_3"},
                    )
                    return
                ss.last_error_feedback = tools.format_layer3_feedback(l3_result)
                self._transition(section_id, "layer_3_fail")
                continue

            # --- Claim table extraction (Step 2e) ---
            ct_passed, claim_table = self._extract_claim_table(
                section_id, section_output, chunks
            )
            if ct_passed:
                self._transition(section_id, "claim_table_pass")
            else:
                ss.retry_counters["claim_extraction"] += 1
                if ss.retry_counters["claim_extraction"] > self.config.CLAIM_EXTRACTION_RETRY_LIMIT:
                    # Mark partial, proceed to finalized (FR-22)
                    if hasattr(claim_table, "partial"):
                        claim_table.partial = True
                    elif isinstance(claim_table, dict):
                        claim_table["partial"] = True
                    self._transition(section_id, "claim_table_pass")
                else:
                    self._transition(section_id, "claim_table_fail")
                    # Re-extract on next pass — but state stays 'validated'
                    ct_passed2, claim_table2 = self._extract_claim_table(
                        section_id, section_output, chunks
                    )
                    if ct_passed2:
                        claim_table = claim_table2
                    else:
                        if hasattr(claim_table2, "partial"):
                            claim_table2.partial = True
                        elif isinstance(claim_table2, dict):
                            claim_table2["partial"] = True
                        claim_table = claim_table2
                    self._transition(section_id, "claim_table_pass")

            # Write claim table
            ct_path = tools.claim_table_path(self.output_dir, section_id, ss.version)
            ct_path.parent.mkdir(parents=True, exist_ok=True)
            ct_data = claim_table if isinstance(claim_table, dict) else (
                claim_table.dict() if hasattr(claim_table, "dict") else str(claim_table)
            )
            ct_path.write_text(json.dumps(ct_data, indent=2, default=str))

            # Summary abstractifier (§9.2.4)
            summary = self._abstractify(section_id, section_output)

            # Post-finalization (Step 2f)
            ss.claim_table = claim_table
            ss.summary_abstract = summary

            # Write provenance
            prov_path = tools.provenance_path(self.output_dir, section_id)
            prov_path.parent.mkdir(parents=True, exist_ok=True)
            prov_path.write_text(json.dumps({
                "section_id": section_id,
                "version": ss.version,
                "timestamp": tools.iso_now(),
                "chunk_ids": [c.get("id", "") for c in chunks],
            }, indent=2))

            tools.save_checkpoint(self.run_state, self.output_dir)
            return  # section fully processed

    # ------------------------------------------------------------------
    # Phase 3: Change Propagation and Cascades
    # ------------------------------------------------------------------

    def _propagate_cascades(self, changed_section_id: str) -> None:
        """Propagate changes after a section is re-finalized (FR-23, FR-24, FR-25)."""

        # Content dependents: invalidate (FR-23)
        for dep_id in _content_dependents(changed_section_id, self.edges):
            dep_ss = self.run_state.section_states.get(dep_id)
            if dep_ss is None:
                continue
            if dep_ss.state in ("finalized", "stable"):
                # Check cascade depth (FR-24, NFR-04)
                dep_ss.cascade_depth = (
                    self.run_state.section_states[changed_section_id].cascade_depth + 1
                )
                if tools.check_cascade_depth(
                    dep_ss.cascade_depth, self.config.CASCADE_DEPTH_LIMIT
                ):
                    self._transition(dep_id, "upstream_content_changed")
                    self._transition(dep_id, "cascade_depth_exceeded")
                    tools.emit_event(
                        "cascade_triggered",
                        section_id=dep_id,
                        from_state="invalidated",
                        to_state="escalated",
                        metadata={"depth": dep_ss.cascade_depth},
                    )
                    tools.emit_event(
                        "escalation_triggered",
                        section_id=dep_id,
                        from_state="invalidated",
                        to_state="escalated",
                        metadata={"reason": "cascade_depth_exceeded"},
                    )
                else:
                    self._transition(dep_id, "upstream_content_changed")
                    tools.emit_event(
                        "cascade_triggered",
                        section_id=dep_id,
                        from_state="finalized",
                        to_state="invalidated",
                        metadata={"depth": dep_ss.cascade_depth},
                    )
                    # Clear claim table and summary
                    dep_ss.claim_table = None
                    dep_ss.summary_abstract = None
                    dep_ss.retry_counters = {k: 0 for k in dep_ss.retry_counters}

        # Reference dependents: re-validate pointers only (FR-25)
        for dep_id in _reference_dependents(changed_section_id, self.edges):
            dep_ss = self.run_state.section_states.get(dep_id)
            if dep_ss and dep_ss.state in ("finalized", "stable"):
                self._transition(dep_id, "upstream_reference_changed")

        # Thematic / source: soft dependency — log only
        for edge in self.edges:
            kind = edge.get("kind") or edge.get("dependency_kind")
            src = edge.get("source_section_id") or edge.get("from_section_id")
            tgt = edge.get("target_section_id") or edge.get("to_section_id")
            if src == changed_section_id and kind in ("thematic", "source"):
                dep_ss = self.run_state.section_states.get(tgt)
                if dep_ss and dep_ss.state in ("finalized", "stable"):
                    self._transition(tgt, "upstream_soft_dependency_changed")

    # ------------------------------------------------------------------
    # Phase 4: Final Assembly
    # ------------------------------------------------------------------

    def _assemble(self) -> Path:
        """Check readiness and invoke assembler (FR-26, FR-27, §9.2.5)."""
        # Check readiness
        state_map = {
            sid: ss.state for sid, ss in self.run_state.section_states.items()
        }
        blocking = tools.check_assembly_readiness(state_map)
        if blocking:
            raise RuntimeError(
                f"Assembly blocked — sections not ready: {blocking}"
            )

        tools.emit_event(
            "assembly_started",
            section_id=None,
            from_state=None,
            to_state=None,
        )

        # Gather finalized section outputs in plan order
        ordered_outputs: List[Any] = []
        for s in self.sections:
            sid = s["section_id"]
            ss = self.run_state.section_states[sid]
            ordered_outputs.append({
                "section_id": sid,
                "section_output": ss.section_output,
                "draft_text": ss.draft_text,
                "depth_level": s.get("depth_level", 1),
            })

        final_text = self.assembler.assemble(ordered_outputs)

        report_path = tools.final_report_path(self.output_dir)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(final_text)

        tools.emit_event(
            "assembly_completed",
            section_id=None,
            from_state=None,
            to_state=None,
        )

        return report_path

    # ------------------------------------------------------------------
    # Phase 5: Completion and Metrics
    # ------------------------------------------------------------------

    def _complete(self) -> None:
        """Compute metrics, persist, emit terminal event."""
        metrics = tools.build_run_metrics(self.run_state)
        tools.save_run_metrics(metrics, self.output_dir)

        escalated = any(
            ss.state == "escalated"
            for ss in self.run_state.section_states.values()
        )
        self.run_state.completed_at = tools.iso_now()

        event = "run_failed" if escalated else "run_completed"
        tools.emit_event(
            event,
            section_id=None,
            from_state=None,
            to_state=None,
            metadata={"metrics": metrics},
        )

        # Final checkpoint
        tools.save_checkpoint(self.run_state, self.output_dir)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> Path:
        """Execute the full synthesizer lifecycle. Returns path to final report."""

        # Phase 1
        self._initialise()

        # Phase 2: section processing loop (DR-15: sequential)
        # Iterate in topological order; repeat until no progress
        progress = True
        while progress:
            progress = False
            for section_id in self.topo_order:
                ss = self.run_state.section_states[section_id]
                if ss.state in ("finalized", "stable", "escalated"):
                    continue
                if not self._prerequisites_met(section_id):
                    continue

                old_state = ss.state
                self._process_section(section_id)

                if ss.state != old_state:
                    progress = True

                # Phase 3: if section just finalized, propagate cascades
                if ss.state == "finalized":
                    self._propagate_cascades(section_id)
                    progress = True  # cascades may unlock or invalidate others

        # Phase 4: assembly
        report_path = self._assemble()

        # Phase 5: completion
        self._complete()

        return report_path