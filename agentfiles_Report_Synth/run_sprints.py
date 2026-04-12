#!/usr/bin/env python3
"""
run_sprints.py — Execution harness for the Report Synthesizer programmer agent.

Drives the programmer agent through sprints 1–6 defined in sprints.py,
sending each sprint's prompt (built by prompts.py) to the Anthropic API
along with the governing spec and accumulated code from prior sprints.

Parses code blocks from the agent's responses, writes files to the
workspace, and maintains a sprint-state ledger for resume support.

Usage:
    # Run all 6 sprints end-to-end
    python run_sprints.py

    # Resume from a specific sprint (prior sprints treated as complete)
    python run_sprints.py --start-from sprint_3

    # Run a single sprint only
    python run_sprints.py --sprint sprint_2

    # Preview prompts without calling the API
    python run_sprints.py --dry-run

    # Use a specific model
    python run_sprints.py --model claude-sonnet-4-20250514

Prerequisites:
    - Run setup_agent.sh first to create the workspace and install deps
    - Set ANTHROPIC_API_KEY in .env or environment
    - Ensure report_synthesizer_v4.md is present in the working directory
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Bootstrap: ensure we can import project modules
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# ---------------------------------------------------------------------------
# Project imports (validated on import by their own registries)
# ---------------------------------------------------------------------------

import sprints
import prompts

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger("run_sprints")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SPEC_FILENAME = "report_synthesizer_v4.md"
SPRINT_STATE_FILENAME = "sprint_state.json"
SPRINT_LOG_DIR_NAME = "sprint_logs"

# Default model for the programmer agent (overridden by --model or AGENT_MODEL env)
DEFAULT_AGENT_MODEL = "claude-sonnet-4-20250514"

# API parameters
MAX_OUTPUT_TOKENS = 16384
THINKING_BUDGET = 10000

# Files to skip when gathering context (binary, large, or irrelevant)
CONTEXT_SKIP_PATTERNS = {
    "__pycache__",
    ".pyc",
    ".pyo",
    "node_modules",
    ".git",
    ".env",
    "sprint_logs",
    "sprint_state.json",
}

# Max characters of accumulated code context per sprint to avoid blowing the
# context window.  ~200k tokens ≈ ~800k chars; spec is ~86k chars; prompt is
# ~10k chars; leave headroom for the response.
MAX_CONTEXT_CHARS = 500_000


# ---------------------------------------------------------------------------
# Sprint state ledger (resume support)
# ---------------------------------------------------------------------------

class SprintLedger:
    """Tracks which sprints have completed, their output manifests, and
    handoff notes.  Persisted to sprint_state.json for resume."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries: Dict[str, Dict[str, Any]] = {}
        if self.path.exists():
            with open(self.path, "r") as f:
                self.entries = json.load(f)
            logger.info(
                "Loaded sprint ledger: %d completed sprint(s)",
                sum(1 for e in self.entries.values() if e.get("status") == "completed"),
            )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self.entries, f, indent=2, default=str)

    def is_completed(self, sprint_id: str) -> bool:
        return self.entries.get(sprint_id, {}).get("status") == "completed"

    def mark_started(self, sprint_id: str) -> None:
        self.entries[sprint_id] = {
            "status": "in_progress",
            "started_at": _iso_now(),
            "files_written": [],
            "handoff_notes": "",
            "response_file": "",
        }
        self.save()

    def mark_completed(
        self,
        sprint_id: str,
        files_written: List[str],
        handoff_notes: str,
        response_file: str,
    ) -> None:
        self.entries[sprint_id] = {
            "status": "completed",
            "started_at": self.entries.get(sprint_id, {}).get("started_at", _iso_now()),
            "completed_at": _iso_now(),
            "files_written": files_written,
            "handoff_notes": handoff_notes,
            "response_file": response_file,
        }
        self.save()

    def mark_failed(self, sprint_id: str, error: str) -> None:
        entry = self.entries.get(sprint_id, {})
        entry["status"] = "failed"
        entry["error"] = error
        entry["failed_at"] = _iso_now()
        self.entries[sprint_id] = entry
        self.save()

    def get_completed_sprint_ids(self) -> List[str]:
        """Return completed sprint IDs in registry order."""
        all_ids = sprints.list_sprint_ids()
        return [sid for sid in all_ids if self.is_completed(sid)]

    def get_files_for_sprint(self, sprint_id: str) -> List[str]:
        return self.entries.get(sprint_id, {}).get("files_written", [])

    def get_handoff_notes(self, sprint_id: str) -> str:
        return self.entries.get(sprint_id, {}).get("handoff_notes", "")


# ---------------------------------------------------------------------------
# Code block parser
# ---------------------------------------------------------------------------

# Regex patterns for extracting file paths and code blocks from LLM responses.
#
# Supports the following conventions commonly used by Claude:
#
#   Convention 1 — fenced block with filename annotation:
#       ```python:synthesizer/models/enums.py
#       ...code...
#       ```
#
#   Convention 2 — header + fenced block:
#       ### `synthesizer/models/enums.py`
#       ```python
#       ...code...
#       ```
#
#   Convention 3 — FILE: marker:
#       **FILE: synthesizer/models/enums.py**
#       ```python
#       ...code...
#       ```
#
#   Convention 4 — bold or backtick path on its own line preceding a fence:
#       **synthesizer/models/enums.py**
#       ```python
#       ...code...
#       ```

_FILE_MARKER_RE = re.compile(
    r"(?:"
    # Conv 1: ```lang:path
    r"```\w*:([\w./\-]+\.\w+)"
    r"|"
    # Conv 2/3/4: header, bold, or backtick path preceding a code fence
    r"(?:^|\n)"
    r"(?:#{1,6}\s+)?"                           # optional heading markers
    r"(?:\*\*)?(?:FILE:\s*)?"                    # optional **FILE:
    r"[`\"]?([\w./\-]+\.(?:py|json|md|toml|cfg|txt|yaml|yml|sh|ini))[`\"]?"
    r"(?:\*\*)?"                                 # closing bold
    r"\s*\n"                                     # newline before fence
    r"(?=```)"                                   # lookahead for opening fence
    r")",
    re.MULTILINE,
)

_FENCED_BLOCK_RE = re.compile(
    r"```[\w]*(?::[\w./\-]+\.\w+)?\s*\n(.*?)```",
    re.DOTALL,
)


def parse_code_blocks(response_text: str) -> List[Tuple[str, str]]:
    """Extract (filepath, content) pairs from a Claude response.

    Returns a list of tuples.  If a code block cannot be associated with a
    file path, it is skipped (but logged).
    """
    results: List[Tuple[str, str]] = []
    seen_paths: set[str] = set()

    # Strategy: walk through the text, find file-path markers, then capture
    # the immediately following fenced code block.
    lines = response_text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]

        filepath = _extract_filepath_from_line(line)
        if filepath:
            # Look for the next fenced code block
            code, end_idx = _capture_next_fence(lines, i + 1)
            if code is not None:
                # Normalise path: strip leading slash or ./
                filepath = filepath.lstrip("/").lstrip("./")
                if filepath not in seen_paths:
                    results.append((filepath, code))
                    seen_paths.add(filepath)
                else:
                    # Later occurrence replaces earlier (agent may revise)
                    results = [
                        (p, c) if p != filepath else (filepath, code)
                        for p, c in results
                    ]
                i = end_idx + 1
                continue
        i += 1

    # Fallback: try Convention 1 (```lang:path) which embeds the path in the
    # fence line itself.
    for match in re.finditer(r"```\w+:([\w./\-]+\.\w+)\s*\n(.*?)```", response_text, re.DOTALL):
        fp = match.group(1).lstrip("/").lstrip("./")
        code = match.group(2)
        if fp not in seen_paths:
            results.append((fp, code))
            seen_paths.add(fp)

    if not results:
        logger.warning("No file-associated code blocks found in response")

    return results


def _extract_filepath_from_line(line: str) -> Optional[str]:
    """Try to extract a file path from a single line."""
    stripped = line.strip()

    # Remove markdown heading markers
    heading_stripped = re.sub(r"^#{1,6}\s+", "", stripped)

    # Remove bold markers
    heading_stripped = heading_stripped.replace("**", "")

    # Remove backticks
    heading_stripped = heading_stripped.replace("`", "")

    # Remove FILE: prefix
    heading_stripped = re.sub(r"^FILE:\s*", "", heading_stripped, flags=re.IGNORECASE)

    # Check if what remains looks like a file path
    candidate = heading_stripped.strip()
    if re.match(r"^[\w./\-]+\.(?:py|json|md|toml|cfg|txt|yaml|yml|sh|ini)$", candidate):
        return candidate

    return None


def _capture_next_fence(lines: List[str], start: int) -> Tuple[Optional[str], int]:
    """Starting from line index `start`, find the next fenced code block.

    Returns (code_content, end_line_index) or (None, start) if not found
    within 5 lines (allowing for blank lines between header and fence).
    """
    # Allow up to 3 blank/whitespace lines between the path header and the
    # opening fence.
    search_limit = min(start + 4, len(lines))
    fence_start = None

    for j in range(start, search_limit):
        if lines[j].strip().startswith("```"):
            fence_start = j
            break

    if fence_start is None:
        return None, start

    # Now find the closing fence
    code_lines: List[str] = []
    for k in range(fence_start + 1, len(lines)):
        if lines[k].strip().startswith("```"):
            return "\n".join(code_lines), k
        code_lines.append(lines[k])

    # Unclosed fence — return what we have
    return "\n".join(code_lines), len(lines) - 1


# ---------------------------------------------------------------------------
# Handoff-note extractor
# ---------------------------------------------------------------------------

def extract_handoff_notes(response_text: str) -> str:
    """Pull the handoff notes section from the agent's response."""
    # Look for a section titled "Handoff" (various heading levels)
    match = re.search(
        r"(?:^|\n)#{1,4}\s+.*?[Hh]andoff.*?\n(.*?)(?=\n#{1,4}\s|\Z)",
        response_text,
        re.DOTALL,
    )
    if match:
        return match.group(1).strip()

    # Fallback: look for numbered section "5. Handoff"
    match = re.search(
        r"(?:^|\n)\d+\.\s+\*?\*?[Hh]andoff.*?\*?\*?\s*\n(.*?)(?=\n\d+\.\s|\Z)",
        response_text,
        re.DOTALL,
    )
    if match:
        return match.group(1).strip()

    return ""


# ---------------------------------------------------------------------------
# Context accumulator
# ---------------------------------------------------------------------------

def gather_prior_context(
    workspace: Path,
    ledger: SprintLedger,
    completed_sprints: List[str],
) -> str:
    """Build a context string containing code written in prior sprints.

    Prioritises the synthesizer/ module tree and tests/ directory.
    Falls back to the file manifest in the ledger if reading fails.
    """
    context_parts: List[str] = []
    total_chars = 0

    # Gather handoff notes first (compact, high signal)
    for sid in completed_sprints:
        notes = ledger.get_handoff_notes(sid)
        if notes:
            block = f"--- Handoff notes from {sid} ---\n{notes}\n"
            context_parts.append(block)
            total_chars += len(block)

    # Then gather actual file contents from the workspace
    file_paths: List[Path] = []
    synth_dir = workspace / "synthesizer"
    tests_dir = workspace / "tests"

    for scan_dir in [synth_dir, tests_dir]:
        if scan_dir.exists():
            for p in sorted(scan_dir.rglob("*.py")):
                if not any(skip in str(p) for skip in CONTEXT_SKIP_PATTERNS):
                    file_paths.append(p)

    for fpath in file_paths:
        if total_chars >= MAX_CONTEXT_CHARS:
            context_parts.append(
                "\n[... remaining files omitted to stay within context budget ...]\n"
            )
            break
        try:
            content = fpath.read_text()
            if not content.strip():
                continue
            rel = fpath.relative_to(workspace)
            block = f"--- FILE: {rel} ---\n{content}\n"
            if total_chars + len(block) > MAX_CONTEXT_CHARS:
                context_parts.append(
                    f"\n[... {rel} and remaining files omitted — context budget ...]\n"
                )
                break
            context_parts.append(block)
            total_chars += len(block)
        except Exception as exc:
            logger.warning("Could not read %s: %s", fpath, exc)

    return "\n".join(context_parts)


# ---------------------------------------------------------------------------
# File writer
# ---------------------------------------------------------------------------

def write_sprint_files(
    workspace: Path,
    file_pairs: List[Tuple[str, str]],
) -> List[str]:
    """Write parsed code blocks to the workspace.  Returns list of
    relative paths written."""
    written: List[str] = []
    for rel_path, content in file_pairs:
        target = workspace / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        written.append(rel_path)
        logger.info("  wrote: %s (%d chars)", rel_path, len(content))

    # Ensure __init__.py exists in every new Python package directory
    init_dirs: set[Path] = set()
    for rel_path, _ in file_pairs:
        if rel_path.endswith(".py"):
            parts = Path(rel_path).parts
            for depth in range(1, len(parts)):
                pkg_dir = workspace / Path(*parts[:depth])
                if pkg_dir.is_dir() and pkg_dir != workspace:
                    init_dirs.add(pkg_dir)

    for pkg_dir in init_dirs:
        init_file = pkg_dir / "__init__.py"
        if not init_file.exists():
            init_file.write_text("")
            logger.info("  created: %s", init_file.relative_to(workspace))

    return written


# ---------------------------------------------------------------------------
# Anthropic API caller
# ---------------------------------------------------------------------------

def call_programmer_agent(
    *,
    api_key: str,
    model: str,
    system_prompt: str,
    user_message: str,
    max_tokens: int = MAX_OUTPUT_TOKENS,
    thinking_budget: int = THINKING_BUDGET,
) -> Tuple[str, Dict[str, Any]]:
    """Send a prompt to the Anthropic API and return (response_text, usage_dict).

    Uses extended thinking when supported by the model.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    # Build the messages payload
    messages = [{"role": "user", "content": user_message}]

    # Attempt with extended thinking first; fall back without if unsupported
    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            thinking={
                "type": "enabled",
                "budget_tokens": thinking_budget,
            },
            system=system_prompt,
            messages=messages,
        )
    except (anthropic.BadRequestError, anthropic.APIError) as exc:
        if "thinking" in str(exc).lower():
            logger.info("Extended thinking not supported; retrying without it")
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=0,
                system=system_prompt,
                messages=messages,
            )
        else:
            raise

    # Extract text from content blocks (skip thinking blocks)
    text_parts: List[str] = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            text_parts.append(block.text)

    response_text = "\n".join(text_parts)

    usage = {
        "input_tokens": getattr(response.usage, "input_tokens", 0),
        "output_tokens": getattr(response.usage, "output_tokens", 0),
        "model": model,
    }

    return response_text, usage


# ---------------------------------------------------------------------------
# System prompt for the harness (wraps prompts.py output)
# ---------------------------------------------------------------------------

def build_harness_system_prompt(spec_text: str) -> str:
    """Build the outer system prompt that frames the spec and output format."""
    return f"""\
You are a programmer agent tasked with implementing the Report Synthesizer \
Agent according to the governing design specification provided below.

Your sprint-specific instructions will arrive in the user message.  The \
governing specification is authoritative — every implementation decision \
must be traceable to it.

CRITICAL OUTPUT FORMAT RULE:
When you produce code files, you MUST use the following format so the \
automated harness can extract and write them:

For each file, output a heading line with the file path, immediately \
followed by a fenced code block.  Example:

### `synthesizer/models/enums.py`
```python
# synthesizer/models/enums.py
\"\"\"Enumerations for the Report Synthesizer (§10.1).\"\"\"
...
```

Rules:
- The path in the heading must be the relative workspace path \
(e.g. synthesizer/models/enums.py, tests/test_plan_loader.py).
- Include COMPLETE file contents — not partial snippets or diffs.
- One fenced code block per file.  Do not combine files.
- After all code files, include the five deliverable sections: \
Implementation Summary, Tests Added, Unresolved Issues, Handoff Notes.
- The Handoff Notes section is mandatory — downstream sprints depend on it.

=== GOVERNING SPECIFICATION (report_synthesizer_v4.md) ===

{spec_text}

=== END SPECIFICATION ==="""


# ---------------------------------------------------------------------------
# Sprint executor
# ---------------------------------------------------------------------------

def execute_sprint(
    *,
    sprint_id: str,
    workspace: Path,
    ledger: SprintLedger,
    spec_text: str,
    api_key: str,
    model: str,
    dry_run: bool = False,
) -> None:
    """Execute a single sprint: build prompt, call API, parse, write files."""
    sprint_def = sprints.get_sprint(sprint_id)
    logger.info("=" * 72)
    logger.info("SPRINT: %s — %s", sprint_id, sprint_def.title)
    logger.info("=" * 72)

    # 1. Check dependencies (skip in dry-run mode to allow prompt preview)
    if not dry_run:
        for dep in sprint_def.dependencies:
            if not ledger.is_completed(dep):
                raise RuntimeError(
                    f"Sprint {sprint_id} depends on {dep} which is not completed.  "
                    f"Run it first or use --start-from to mark prior sprints as done."
                )

    # 2. Build the sprint prompt from prompts.py
    sprint_prompt = prompts.build_prompt_for_sprint(sprint_id)

    # 3. Gather prior-sprint context
    completed = ledger.get_completed_sprint_ids()
    prior_context = gather_prior_context(workspace, ledger, completed)

    # 4. Compose the full user message
    user_message_parts: List[str] = []

    if prior_context:
        user_message_parts.append(
            "=== ACCUMULATED CODE FROM PRIOR SPRINTS ===\n\n"
            f"{prior_context}\n\n"
            "=== END PRIOR SPRINT CODE ===\n"
        )

    user_message_parts.append(
        "=== SPRINT INSTRUCTIONS ===\n\n"
        f"{sprint_prompt}\n\n"
        "=== END SPRINT INSTRUCTIONS ==="
    )

    user_message = "\n\n".join(user_message_parts)

    # 5. Build system prompt (includes spec)
    system_prompt = build_harness_system_prompt(spec_text)

    # 6. Log prompt size
    total_prompt_chars = len(system_prompt) + len(user_message)
    logger.info(
        "Prompt size: system=%d chars, user=%d chars, total=%d chars (~%d tokens)",
        len(system_prompt),
        len(user_message),
        total_prompt_chars,
        total_prompt_chars // 4,
    )

    if dry_run:
        # Write prompt to log directory for inspection
        log_dir = workspace / SPRINT_LOG_DIR_NAME
        log_dir.mkdir(parents=True, exist_ok=True)
        prompt_file = log_dir / f"{sprint_id}_prompt.md"
        prompt_file.write_text(
            f"# System Prompt\n\n{system_prompt}\n\n"
            f"# User Message\n\n{user_message}"
        )
        logger.info("[DRY RUN] Prompt written to %s", prompt_file)
        return

    # 7. Mark started
    ledger.mark_started(sprint_id)

    # 8. Call the API
    logger.info("Calling Anthropic API (model=%s)...", model)
    t0 = time.monotonic()

    try:
        response_text, usage = call_programmer_agent(
            api_key=api_key,
            model=model,
            system_prompt=system_prompt,
            user_message=user_message,
        )
    except Exception as exc:
        ledger.mark_failed(sprint_id, str(exc))
        raise RuntimeError(f"API call failed for {sprint_id}: {exc}") from exc

    elapsed = time.monotonic() - t0
    logger.info(
        "API response received in %.1fs  (input=%d tokens, output=%d tokens)",
        elapsed,
        usage.get("input_tokens", 0),
        usage.get("output_tokens", 0),
    )

    # 9. Save raw response
    log_dir = workspace / SPRINT_LOG_DIR_NAME
    log_dir.mkdir(parents=True, exist_ok=True)
    response_file = log_dir / f"{sprint_id}_response.md"
    response_file.write_text(response_text)
    logger.info("Raw response saved to %s", response_file)

    # Save usage metadata
    meta_file = log_dir / f"{sprint_id}_meta.json"
    meta_file.write_text(json.dumps({
        "sprint_id": sprint_id,
        "model": model,
        "elapsed_seconds": round(elapsed, 2),
        "usage": usage,
        "timestamp": _iso_now(),
        "prompt_chars": total_prompt_chars,
        "response_chars": len(response_text),
    }, indent=2))

    # 10. Parse code blocks
    file_pairs = parse_code_blocks(response_text)
    logger.info("Parsed %d file(s) from response", len(file_pairs))

    if not file_pairs:
        logger.warning(
            "No code blocks extracted.  The raw response has been saved to %s "
            "for manual inspection.  You may need to re-run this sprint.",
            response_file,
        )
        ledger.mark_failed(sprint_id, "No code blocks parsed from response")
        return

    # 11. Write files to workspace
    written = write_sprint_files(workspace, file_pairs)
    logger.info("Wrote %d file(s) to workspace", len(written))

    # 12. Extract handoff notes
    handoff = extract_handoff_notes(response_text)
    if not handoff:
        logger.warning("No handoff notes found in response for %s", sprint_id)

    # 13. Mark completed
    ledger.mark_completed(
        sprint_id,
        files_written=written,
        handoff_notes=handoff,
        response_file=str(response_file.relative_to(workspace)),
    )

    logger.info("Sprint %s completed: %d files written", sprint_id, len(written))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_env_file(workspace: Path) -> None:
    """Load .env file from workspace into os.environ (simple key=value only)."""
    env_file = workspace / ".env"
    if not env_file.exists():
        return
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = value


def resolve_workspace() -> Path:
    """Determine the workspace directory.

    Priority:
      1. WORKSPACE_ROOT environment variable
      2. Current working directory (if it looks like a workspace)
      3. ./workspace/lit_review_pipeline (setup_agent.sh default)
    """
    if "WORKSPACE_ROOT" in os.environ:
        return Path(os.environ["WORKSPACE_ROOT"])

    cwd = Path.cwd()
    # If sprints.py and the spec exist here, we're in the workspace
    if (cwd / "sprints.py").exists() and (cwd / SPEC_FILENAME).exists():
        return cwd

    # Try the setup_agent.sh default location
    default = SCRIPT_DIR / "workspace" / "lit_review_pipeline"
    if default.exists():
        return default

    # Fall back to cwd
    return cwd


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execute programmer-agent sprints for the Report Synthesizer.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  python run_sprints.py                        # run all 6 sprints
  python run_sprints.py --start-from sprint_3  # resume from sprint 3
  python run_sprints.py --sprint sprint_1      # run sprint 1 only
  python run_sprints.py --dry-run              # preview prompts
  python run_sprints.py --model claude-opus-4-20250514  # use a specific model
""",
    )
    parser.add_argument(
        "--sprint",
        type=str,
        help="Run a single sprint by ID (e.g. sprint_1)",
    )
    parser.add_argument(
        "--start-from",
        type=str,
        dest="start_from",
        help="Start from this sprint, marking all prior sprints as completed",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and save prompts without calling the API",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help=f"Model to use for the programmer agent (default: AGENT_MODEL env or {DEFAULT_AGENT_MODEL})",
    )
    parser.add_argument(
        "--workspace",
        type=str,
        default=None,
        help="Path to the workspace directory (default: auto-detected)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear the sprint ledger and start fresh",
    )
    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # 1. Resolve workspace
    if args.workspace:
        workspace = Path(args.workspace).resolve()
    else:
        workspace = resolve_workspace()

    logger.info("Workspace: %s", workspace)

    # 2. Load .env
    _load_env_file(workspace)

    # 3. Resolve model
    model = (
        args.model
        or os.environ.get("AGENT_MODEL")
        or os.environ.get("PIPELINE_MODEL")
        or DEFAULT_AGENT_MODEL
    )
    logger.info("Agent model: %s", model)

    # 4. Resolve API key
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key and not args.dry_run:
        logger.error(
            "ANTHROPIC_API_KEY not set.  Export it or add it to %s/.env",
            workspace,
        )
        sys.exit(1)

    # 5. Load spec document
    spec_path = workspace / SPEC_FILENAME
    if not spec_path.exists():
        # Also check the script directory
        spec_path = SCRIPT_DIR / SPEC_FILENAME
    if not spec_path.exists():
        logger.error(
            "Governing spec not found: %s.  Ensure %s is in the workspace or script directory.",
            SPEC_FILENAME,
            SPEC_FILENAME,
        )
        sys.exit(1)

    spec_text = spec_path.read_text()
    logger.info("Loaded spec: %s (%d chars)", spec_path.name, len(spec_text))

    # 6. Initialise sprint ledger
    ledger_path = workspace / SPRINT_STATE_FILENAME
    if args.reset and ledger_path.exists():
        ledger_path.unlink()
        logger.info("Sprint ledger reset")

    ledger = SprintLedger(ledger_path)

    # 7. Determine which sprints to run
    all_sprint_ids = sprints.list_sprint_ids()

    if args.sprint:
        # Single sprint mode
        if args.sprint not in all_sprint_ids:
            logger.error(
                "Unknown sprint: %s.  Valid IDs: %s",
                args.sprint,
                all_sprint_ids,
            )
            sys.exit(1)
        target_ids = [args.sprint]
    elif args.start_from:
        # Resume mode: mark all sprints before start_from as completed
        if args.start_from not in all_sprint_ids:
            logger.error(
                "Unknown sprint: %s.  Valid IDs: %s",
                args.start_from,
                all_sprint_ids,
            )
            sys.exit(1)
        target_ids = []
        reached = False
        for sid in all_sprint_ids:
            if sid == args.start_from:
                reached = True
            if not reached:
                if not ledger.is_completed(sid):
                    logger.info(
                        "Marking %s as completed (prior to --start-from)", sid
                    )
                    ledger.mark_completed(sid, [], "(assumed complete via --start-from)", "")
            else:
                target_ids.append(sid)
    else:
        # Full run: skip already-completed sprints
        target_ids = [sid for sid in all_sprint_ids if not ledger.is_completed(sid)]

    if not target_ids:
        logger.info("All sprints already completed.  Use --reset to start over.")
        return

    logger.info("Sprints to execute: %s", target_ids)

    # 8. Execute sprints
    for sprint_id in target_ids:
        if ledger.is_completed(sprint_id):
            logger.info("Skipping %s (already completed)", sprint_id)
            continue

        try:
            execute_sprint(
                sprint_id=sprint_id,
                workspace=workspace,
                ledger=ledger,
                spec_text=spec_text,
                api_key=api_key,
                model=model,
                dry_run=args.dry_run,
            )
        except RuntimeError as exc:
            logger.error("Sprint %s failed: %s", sprint_id, exc)
            logger.error("Fix the issue and re-run.  Completed sprints will be skipped.")
            sys.exit(1)
        except KeyboardInterrupt:
            logger.warning("Interrupted during %s.  Re-run to resume.", sprint_id)
            sys.exit(130)

    # 9. Summary
    logger.info("=" * 72)
    if args.dry_run:
        logger.info("DRY RUN complete.  Prompts saved to %s/", SPRINT_LOG_DIR_NAME)
    else:
        completed = ledger.get_completed_sprint_ids()
        logger.info(
            "All target sprints executed.  Completed: %d/%d",
            len(completed),
            len(all_sprint_ids),
        )
        for sid in all_sprint_ids:
            entry = ledger.entries.get(sid, {})
            status = entry.get("status", "pending")
            n_files = len(entry.get("files_written", []))
            logger.info("  %s: %s (%d files)", sid, status, n_files)

    logger.info("=" * 72)


if __name__ == "__main__":
    main()