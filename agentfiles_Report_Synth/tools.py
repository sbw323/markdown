"""
tools.py — Reusable support library for the Report Synthesizer Orchestrator.

Provides typed helpers, thin adapters, validation formatters, path builders,
state persistence wrappers, and logging/metrics emission helpers consumed by
the orchestrator and sprint-scoped modules.

Governing specification: report_synthesizer_v4.md (v4.0)
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, validator

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------

logger = logging.getLogger("synthesizer")

# ---------------------------------------------------------------------------
# §1  Configuration Normalization and Validation (§16, Sprint 1)
# ---------------------------------------------------------------------------

_DEFAULT_DATA_DIR = Path("data")


class SynthesizerConfig(BaseModel):
    """Validated configuration surface for the synthesizer (§16).

    Open decisions preserved as configurable fields:
      - DR-16: SYNTHESIZER_MODEL / per-role model overrides
      - DR-17: TOKEN_BUDGET_CEILING (None = no limit)
      - DR-18: per-role input token budgets (optional dict)
    """

    REPORT_PLAN_PATH: Path
    STYLE_SHEET_PATH: Path
    SYNTHESIZER_OUTPUT_DIR: Path = Field(
        default_factory=lambda: _DEFAULT_DATA_DIR / "synthesis"
    )
    CASCADE_DEPTH_LIMIT: int = 3
    LAYER1_RETRY_LIMIT: int = 3
    LAYER2_RETRY_LIMIT: int = 3
    LAYER3_RETRY_LIMIT: int = 2
    CLAIM_EXTRACTION_RETRY_LIMIT: int = 1
    SYNTHESIZER_MODEL: str = ""  # empty → falls back to PIPELINE_MODEL at runtime
    TOKEN_BUDGET_CEILING: Optional[int] = None  # DR-17: None = no limit

    # DR-16: optional per-role model overrides (generator, validator, claim_extractor, abstractifier)
    model_overrides: Dict[str, str] = Field(default_factory=dict)
    # DR-18: optional per-role input token budget caps
    input_token_budgets: Dict[str, int] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True

    @validator("CASCADE_DEPTH_LIMIT", "LAYER1_RETRY_LIMIT", "LAYER2_RETRY_LIMIT",
               "LAYER3_RETRY_LIMIT", "CLAIM_EXTRACTION_RETRY_LIMIT")
    def _positive_int(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"Limit must be non-negative, got {v}")
        return v

    @validator("TOKEN_BUDGET_CEILING")
    def _positive_ceiling(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v <= 0:
            raise ValueError(f"TOKEN_BUDGET_CEILING must be positive or None, got {v}")
        return v


def load_synthesizer_config(
    *,
    env_prefix: str = "SYNTHESIZER_",
    config_module: Any = None,
) -> SynthesizerConfig:
    """Load and validate synthesizer configuration from environment or a config module.

    Resolution order for each key:
      1. Environment variable (e.g. SYNTHESIZER_REPORT_PLAN_PATH)
      2. Attribute on *config_module* (e.g. config_module.REPORT_PLAN_PATH)
      3. SynthesizerConfig default

    Returns a validated SynthesizerConfig instance.
    """
    raw: Dict[str, Any] = {}

    fields = SynthesizerConfig.__fields__

    for name in fields:
        env_key = f"{env_prefix}{name}"
        env_val = os.environ.get(env_key)
        if env_val is not None:
            raw[name] = env_val
        elif config_module is not None and hasattr(config_module, name):
            raw[name] = getattr(config_module, name)

    # Resolve SYNTHESIZER_MODEL fallback to PIPELINE_MODEL
    if not raw.get("SYNTHESIZER_MODEL"):
        if config_module and hasattr(config_module, "PIPELINE_MODEL"):
            raw["SYNTHESIZER_MODEL"] = getattr(config_module, "PIPELINE_MODEL")
        elif "PIPELINE_MODEL" in os.environ:
            raw["SYNTHESIZER_MODEL"] = os.environ["PIPELINE_MODEL"]

    # Resolve SYNTHESIZER_OUTPUT_DIR from DATA_DIR if not explicitly set
    if "SYNTHESIZER_OUTPUT_DIR" not in raw:
        data_dir = None
        if config_module and hasattr(config_module, "DATA_DIR"):
            data_dir = Path(getattr(config_module, "DATA_DIR"))
        if data_dir:
            raw["SYNTHESIZER_OUTPUT_DIR"] = data_dir / "synthesis"

    return SynthesizerConfig(**raw)


# ---------------------------------------------------------------------------
# §2  Path and Artifact Helpers (§15, Sprint 2)
# ---------------------------------------------------------------------------

_SECTION_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")
_SECTION_ID_MAX_LEN = 64


def validate_section_id(section_id: str) -> None:
    """Validate section_id against §10.3 constraints: [a-z0-9_]+, max 64 chars.

    Raises ValueError on invalid input.
    """
    if not section_id:
        raise ValueError("section_id must not be empty")
    if len(section_id) > _SECTION_ID_MAX_LEN:
        raise ValueError(
            f"section_id exceeds {_SECTION_ID_MAX_LEN} chars: {section_id!r}"
        )
    if not _SECTION_ID_PATTERN.match(section_id):
        raise ValueError(
            f"section_id must match [a-z0-9_]+, got: {section_id!r}"
        )


def validate_version(version: int) -> None:
    """Validate a 1-indexed version number (§15.2)."""
    if not isinstance(version, int) or version < 1:
        raise ValueError(f"Version must be a positive integer, got {version!r}")


def _section_dir(output_dir: Path, section_id: str) -> Path:
    validate_section_id(section_id)
    return output_dir / "sections" / section_id


def draft_path(output_dir: Path, section_id: str, version: int) -> Path:
    """Return path: {output_dir}/sections/{section_id}/draft_v{N}.md"""
    validate_version(version)
    return _section_dir(output_dir, section_id) / f"draft_v{version}.md"


def claim_table_path(output_dir: Path, section_id: str, version: int) -> Path:
    """Return path: {output_dir}/sections/{section_id}/claim_table_v{N}.json"""
    validate_version(version)
    return _section_dir(output_dir, section_id) / f"claim_table_v{version}.json"


def validation_log_path(output_dir: Path, section_id: str) -> Path:
    """Return path: {output_dir}/sections/{section_id}/validation_log.json"""
    return _section_dir(output_dir, section_id) / "validation_log.json"


def provenance_path(output_dir: Path, section_id: str) -> Path:
    """Return path: {output_dir}/sections/{section_id}/provenance.json"""
    return _section_dir(output_dir, section_id) / "provenance.json"


def run_state_path(output_dir: Path) -> Path:
    """Return path: {output_dir}/run_state.json"""
    return output_dir / "run_state.json"


def run_metrics_path(output_dir: Path) -> Path:
    """Return path: {output_dir}/run_metrics.json"""
    return output_dir / "run_metrics.json"


def final_report_path(output_dir: Path) -> Path:
    """Return path: {output_dir}/report/literature_review.md"""
    return output_dir / "report" / "literature_review.md"


def scaffold_output_directory(output_dir: Path, section_ids: List[str]) -> None:
    """Create the full §15.1 directory tree for a run.

    The tree is derived output (DR-01) — mirrors the plan but never defines structure.
    Called by synthesizer/filesystem.py at run start.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    sections_dir = output_dir / "sections"
    sections_dir.mkdir(exist_ok=True)
    for sid in section_ids:
        validate_section_id(sid)
        (sections_dir / sid).mkdir(exist_ok=True)
    (output_dir / "report").mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# §3  Run-State and Checkpoint Load/Save Helpers (§10.13, §11.3, Sprint 2)
# ---------------------------------------------------------------------------

def iso_now() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def save_checkpoint(run_state: Any, output_dir: Path) -> None:
    """Atomically persist RunState to run_state.json (write-then-rename).

    *run_state* must support `.json()` or `.model_dump_json()` (Pydantic v1/v2).
    """
    target = run_state_path(output_dir)
    target.parent.mkdir(parents=True, exist_ok=True)

    if hasattr(run_state, "model_dump_json"):
        data = run_state.model_dump_json(indent=2)
    elif hasattr(run_state, "json"):
        data = run_state.json(indent=2)
    else:
        data = json.dumps(run_state, indent=2, default=str)

    # Atomic write: write to temp file then rename
    fd, tmp_path = tempfile.mkstemp(
        dir=str(target.parent), suffix=".tmp", prefix="run_state_"
    )
    try:
        with os.fdopen(fd, "w") as f:
            f.write(data)
        Path(tmp_path).replace(target)
    except BaseException:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    emit_event("checkpoint_written", section_id=None, from_state=None, to_state=None)


def load_checkpoint(output_dir: Path) -> Optional[Dict[str, Any]]:
    """Load and return existing checkpoint as a dict, or None if absent.

    The caller (orchestrator) is responsible for parsing the dict into a
    validated RunState model.
    """
    target = run_state_path(output_dir)
    if not target.exists():
        return None
    with open(target, "r") as f:
        return json.load(f)


def apply_resume_policy(section_states: Dict[str, Any]) -> Dict[str, Any]:
    """Apply §11.3 resume algorithm: reset 'generating' → 'queued', retain others.

    Accepts and returns a dict mapping section_id → section-state dict (or
    Pydantic model with a `state` attribute).  Mutates and returns the same
    mapping for convenience.
    """
    for sid, ss in section_states.items():
        if isinstance(ss, dict):
            if ss.get("state") == "generating":
                ss["state"] = "queued"
        elif hasattr(ss, "state"):
            if ss.state == "generating":  # type: ignore[union-attr]
                ss.state = "queued"       # type: ignore[union-attr]
    return section_states


# ---------------------------------------------------------------------------
# §4  Logging and Metrics Emission Helpers (§17, Sprint 6)
# ---------------------------------------------------------------------------

def emit_event(
    event_type: str,
    section_id: Optional[str],
    from_state: Optional[str],
    to_state: Optional[str],
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Emit a structured JSON log event conforming to §17.1.

    Event types: state_transition, run_started, run_completed, run_failed,
    cascade_triggered, escalation_triggered, checkpoint_written,
    assembly_started, assembly_completed.
    """
    event: Dict[str, Any] = {
        "event_type": event_type,
        "section_id": section_id,
        "from_state": from_state,
        "to_state": to_state,
        "timestamp": iso_now(),
    }
    if metadata:
        event["metadata"] = metadata
    logger.info(json.dumps(event, default=str))


def build_run_metrics(run_state: Any) -> Dict[str, Any]:
    """Compute the seven §17.2 post-run metrics from a RunState object.

    Returns a dict suitable for JSON serialisation to run_metrics.json.

    The RunState must expose `section_states: Dict[str, SectionState]` where
    each SectionState has `validation_history`, `claim_table`, `version`, etc.
    """
    section_states: Dict[str, Any] = (
        run_state.section_states
        if hasattr(run_state, "section_states")
        else run_state.get("section_states", {})
    )

    total_sections = len(section_states)
    if total_sections == 0:
        return {
            "structural_compliance_rate": 0.0,
            "style_compliance_rate": 0.0,
            "dependency_completeness": 0.0,
            "unsupported_claim_rate": 0.0,
            "revision_churn": 0.0,
            "claim_table_completeness": 0.0,
            "evidence_claim_agreement": 0.0,
        }

    # Helpers to access SectionState as dict or object
    def _get(obj: Any, attr: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(attr, default)
        return getattr(obj, attr, default)

    # 1. Structural compliance rate: % passing Layer 1 on first attempt
    l1_first_pass = 0
    for ss in section_states.values():
        history = _get(ss, "validation_history", [])
        for vr in history:
            layer = _get(vr, "layer", "")
            if layer in ("structural", "layer_1", "Layer 1"):
                attempt = _get(vr, "attempt", 1)
                if attempt == 1 and _get(vr, "passed", False):
                    l1_first_pass += 1
                break
    structural_compliance = l1_first_pass / total_sections

    # 2. Style compliance rate: % passing Layer 2 on first attempt
    l2_first_pass = 0
    for ss in section_states.values():
        history = _get(ss, "validation_history", [])
        for vr in history:
            layer = _get(vr, "layer", "")
            if layer in ("rule_based", "layer_2", "Layer 2"):
                attempt = _get(vr, "attempt", 1)
                if attempt == 1 and _get(vr, "passed", False):
                    l2_first_pass += 1
                break
    style_compliance = l2_first_pass / total_sections

    # 3. Dependency completeness: placeholder — requires cross-referencing
    #    upstream claim tables against downstream engagement. Orchestrator
    #    must supply engagement data; we return 0.0 if not available.
    dependency_completeness = 0.0

    # 4. Unsupported claim rate: placeholder — requires claim-level analysis
    unsupported_claim_rate = 0.0

    # 5. Revision churn: average generation attempts (version) per section
    total_versions = sum(
        _get(ss, "version", 1) for ss in section_states.values()
    )
    revision_churn = total_versions / total_sections

    # 6. Claim-table completeness: % of sections with non-partial claim tables
    ct_complete = 0
    for ss in section_states.values():
        ct = _get(ss, "claim_table", None)
        if ct is not None and not _get(ct, "partial", False):
            ct_complete += 1
    claim_table_completeness = ct_complete / total_sections

    # 7. Evidence-claim agreement: placeholder — requires LLM or detailed analysis
    evidence_claim_agreement = 0.0

    return {
        "structural_compliance_rate": round(structural_compliance, 4),
        "style_compliance_rate": round(style_compliance, 4),
        "dependency_completeness": round(dependency_completeness, 4),
        "unsupported_claim_rate": round(unsupported_claim_rate, 4),
        "revision_churn": round(revision_churn, 4),
        "claim_table_completeness": round(claim_table_completeness, 4),
        "evidence_claim_agreement": round(evidence_claim_agreement, 4),
    }


def save_run_metrics(metrics: Dict[str, Any], output_dir: Path) -> None:
    """Write run_metrics.json to {output_dir}/run_metrics.json."""
    target = run_metrics_path(output_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w") as f:
        json.dump(metrics, f, indent=2, default=str)


def record_token_usage(
    run_state: Any,
    input_tokens: int,
    output_tokens: int,
) -> None:
    """Update RunState cumulative token counters.

    Mutates run_state in place (works with Pydantic models or dicts).
    """
    if isinstance(run_state, dict):
        run_state["cumulative_input_tokens"] = (
            run_state.get("cumulative_input_tokens", 0) + input_tokens
        )
        run_state["cumulative_output_tokens"] = (
            run_state.get("cumulative_output_tokens", 0) + output_tokens
        )
    else:
        run_state.cumulative_input_tokens += input_tokens
        run_state.cumulative_output_tokens += output_tokens


def check_budget_ceiling(
    run_state: Any,
    ceiling: Optional[int],
) -> bool:
    """Return True if the token budget ceiling has been reached (NFR-02).

    If ceiling is None, always returns False (no limit).
    """
    if ceiling is None:
        return False
    if isinstance(run_state, dict):
        total = run_state.get("cumulative_input_tokens", 0) + run_state.get(
            "cumulative_output_tokens", 0
        )
    else:
        total = run_state.cumulative_input_tokens + run_state.cumulative_output_tokens
    return total >= ceiling


def check_generation_latency(
    elapsed_seconds: float,
    limit: float = 120.0,
) -> Optional[str]:
    """Return a warning string if generation latency exceeds limit (NFR-01).

    Returns None if within limit.
    """
    if elapsed_seconds > limit:
        return (
            f"Generation latency {elapsed_seconds:.1f}s exceeds "
            f"limit of {limit:.0f}s (NFR-01)"
        )
    return None


# ---------------------------------------------------------------------------
# §5  Validation Feedback Formatting Helpers (§12, Sprints 4-5)
# ---------------------------------------------------------------------------

def format_layer1_errors(violations: List[Any]) -> str:
    """Format Layer 1 (structural) violations for inclusion in a Generator retry prompt.

    Produces clear, structured text suitable for LLM consumption (FR-15).
    """
    if not violations:
        return ""
    lines = ["## Structural Validation Errors (Layer 1)", ""]
    for i, v in enumerate(violations, 1):
        rule = _get_violation_field(v, "rule")
        desc = _get_violation_field(v, "description")
        loc = _get_violation_field(v, "location")
        line = f"{i}. [{rule}] {desc}"
        if loc:
            line += f" (at: {loc})"
        lines.append(line)
    lines.append("")
    lines.append("Fix ALL errors above and regenerate the section output.")
    return "\n".join(lines)


def format_layer2_violations(violations: List[Any]) -> str:
    """Format Layer 2 (rule-based) violations for retry (FR-17).

    Covers: word count, citation format, forbidden phrases, heading level.
    """
    if not violations:
        return ""
    lines = ["## Style Compliance Violations (Layer 2)", ""]
    for i, v in enumerate(violations, 1):
        rule = _get_violation_field(v, "rule")
        desc = _get_violation_field(v, "description")
        severity = _get_violation_field(v, "severity")
        loc = _get_violation_field(v, "location")
        line = f"{i}. [{severity}] {rule}: {desc}"
        if loc:
            line += f" (at: {loc})"
        lines.append(line)
    lines.append("")
    lines.append("Correct ALL violations above and regenerate.")
    return "\n".join(lines)


def format_layer3_feedback(validation_result: Any) -> str:
    """Format Layer 3 (semantic) sub-check results for retry (FR-19).

    Accepts a ValidationResult or dict with `violations` and optional
    `suggested_fix`.
    """
    violations = (
        _get_attr_or_key(validation_result, "violations") or []
    )
    suggested_fix = _get_attr_or_key(validation_result, "suggested_fix")

    lines = ["## Semantic Validation Feedback (Layer 3)", ""]
    if violations:
        for i, v in enumerate(violations, 1):
            rule = _get_violation_field(v, "rule")
            desc = _get_violation_field(v, "description")
            lines.append(f"{i}. [{rule}] {desc}")
    if suggested_fix:
        lines.append("")
        lines.append(f"Suggested fix: {suggested_fix}")
    lines.append("")
    lines.append("Address ALL issues above and regenerate the section.")
    return "\n".join(lines)


def format_claim_table_errors(violations: List[Any]) -> str:
    """Format claim-table validation sub-check failures for re-extraction."""
    if not violations:
        return ""
    lines = ["## Claim Table Validation Errors", ""]
    for i, v in enumerate(violations, 1):
        rule = _get_violation_field(v, "rule")
        desc = _get_violation_field(v, "description")
        lines.append(f"{i}. [{rule}] {desc}")
    lines.append("")
    lines.append("Re-extract the claim table addressing the errors above.")
    return "\n".join(lines)


def _get_violation_field(v: Any, field_name: str) -> str:
    """Extract a field from a Violation object or dict."""
    if isinstance(v, dict):
        return str(v.get(field_name, ""))
    return str(getattr(v, field_name, ""))


def _get_attr_or_key(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


# ---------------------------------------------------------------------------
# §6  Thin Adapters for External Stage Interfaces (§14, Sprint 3)
# ---------------------------------------------------------------------------

def retrieve_chunks(
    retriever: Any,
    queries: List[str],
) -> List[Dict[str, Any]]:
    """Call retriever.query() for each query, aggregate ranked chunks.

    Enforces DR-05: answer_text is discarded; only ranked_chunks are returned.
    """
    all_chunks: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    for q in queries:
        answer_text, ranked_chunks = retriever.query(q)
        # DR-05: discard answer_text
        for chunk in ranked_chunks:
            chunk_id = chunk.get("id", "")
            if chunk_id not in seen_ids:
                seen_ids.add(chunk_id)
                all_chunks.append(chunk)
    return all_chunks


def load_planning_summaries(loader_fn: Callable[[], List[Any]]) -> List[Any]:
    """Thin wrapper around load_all_summaries() returning PaperSummary objects.

    DR-06: These summaries are for planning context ONLY. They must NEVER be
    injected into generation prompts as evidence.
    """
    return loader_fn()


# ---------------------------------------------------------------------------
# §7  Additional Small Deterministic Helpers
# ---------------------------------------------------------------------------

def count_words(markdown_text: str) -> int:
    """Count words in Markdown content (used by Layer 2 validation, §12.2)."""
    return len(markdown_text.split())


def extract_first_heading_level(markdown_text: str) -> Optional[int]:
    """Parse the first Markdown heading and return its level (1-6).

    Returns None if no heading is found.
    """
    for line in markdown_text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            level = 0
            for ch in stripped:
                if ch == "#":
                    level += 1
                else:
                    break
            if 1 <= level <= 6:
                return level
    return None


def check_citation_format(
    text: str,
    citation_pattern: str,
) -> List[str]:
    """Match all citations in text against a compiled regex pattern.

    Returns a list of non-matching citation-like strings found in the text.
    Uses a broad heuristic to find parenthetical references, then checks each
    against the provided pattern.
    """
    compiled = re.compile(citation_pattern)
    # Broad heuristic: parenthetical strings that look like citations
    candidates = re.findall(r"\([A-Z][^)]{2,60}\)", text)
    non_matching: List[str] = []
    for c in candidates:
        if not compiled.search(c):
            non_matching.append(c)
    return non_matching


def scan_forbidden_phrases(
    text: str,
    forbidden_phrases: List[str],
) -> List[Dict[str, Any]]:
    """Scan text for occurrences of forbidden phrases.

    Returns list of dicts with 'phrase', 'start', 'end' for each match.
    """
    matches: List[Dict[str, Any]] = []
    text_lower = text.lower()
    for phrase in forbidden_phrases:
        phrase_lower = phrase.lower()
        start = 0
        while True:
            idx = text_lower.find(phrase_lower, start)
            if idx == -1:
                break
            matches.append({
                "phrase": phrase,
                "start": idx,
                "end": idx + len(phrase),
            })
            start = idx + 1
    return matches


# Terminal-or-done states for assembly readiness (FR-27)
_ASSEMBLY_READY_STATES = {"finalized", "stable", "escalated"}


def check_assembly_readiness(
    section_states: Dict[str, str],
) -> List[str]:
    """Return section IDs not in a terminal/done state (FR-27).

    All sections must be 'finalized', 'stable', or 'escalated' for assembly
    to proceed. Returns an empty list if all are ready.
    """
    not_ready: List[str] = []
    for sid, state in section_states.items():
        # Handle both raw string states and enum values
        state_str = state if isinstance(state, str) else str(state)
        # Strip enum class prefix if present
        if "." in state_str:
            state_str = state_str.rsplit(".", 1)[-1]
        if state_str not in _ASSEMBLY_READY_STATES:
            not_ready.append(sid)
    return not_ready


def check_cascade_depth(
    cascade_depth: int,
    limit: int,
) -> bool:
    """Return True if cascade_depth has exceeded the configured limit (FR-24, NFR-04).

    Uses the configurable CASCADE_DEPTH_LIMIT, never a hardcoded value.
    """
    return cascade_depth >= limit