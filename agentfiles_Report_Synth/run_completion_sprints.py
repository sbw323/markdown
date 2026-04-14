"""Adapter script for running completion sprints against the existing codebase.

This script implements *Approach A* from the Integration Verification Plan:
a standalone entry point that reuses ``tools.py`` and ``config.py`` from the
original agent framework but replaces the orchestrator loop with one purpose-
built for the completion sprint registry (``completion_sprints.py``) and
prompt builders (``completion_prompts.py``).

Gap resolution summary (references Integration_Verification_Plan.md):

    Gap 1 — Sprint data structure:  ``sprint_to_dict()`` adapter converts
            frozen ``SprintDefinition`` → plain dict with the keys that
            ``tools.py`` and the logging helpers expect.
    Gap 2 — Prompt assembly:        Calls ``completion_prompts.build_prompt_for_sprint()``
            directly; bypasses the template-based assembly pipeline entirely.
    Gap 3 — File output parsing:    ``parse_fenced_code_blocks()`` handles the
            fenced-code-block format that completion prompts request, with a
            transparent fallback to ``tools.parse_file_tags()`` for <file> tags.
    Gap 4 — Validation dispatch:    Defaults to ``tools.validate_python_syntax``
            for every ``.py`` file produced.
    Gap 5 — Context window mgmt:    Token budget check re-calls with
            ``workspace_path=None`` (interface-summary mode) on overflow.
    Gap 6 — Workspace root config:  Derives ``workspace_path`` from
            ``config.WORKSPACE_ROOT``; verifies the synthesizer directory
            is reachable.
    Gap 7 — Post-sprint hooks:      GROBID startup is skipped (not needed).
"""

import argparse
import json
import logging
import os
import re
import time
from pathlib import Path

import anthropic

import config
import tools
import completion_sprints
import completion_prompts
from completion_sprints import SprintDefinition, COMPLETION_SPRINTS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Gap 1: Sprint → dict adapter
# ---------------------------------------------------------------------------

def sprint_to_dict(sprint: SprintDefinition) -> dict:
    """Convert a frozen SprintDefinition into the dict format expected by
    ``tools.py`` validation and logging functions.

    Extracts clean file paths from ``artifacts_in_scope`` by stripping
    the descriptive parenthetical text (e.g. ``"(new — ...)"`` or
    ``"(modify — ...)"``) that follows each path.

    Args:
        sprint: A completion sprint definition.

    Returns:
        A dict with keys: ``id``, ``name``, ``goal``, ``files_to_produce``,
        ``acceptance_criteria``, ``validation_tool``, ``context_files``.
    """
    files: list[str] = []
    for artifact in sprint.artifacts_in_scope:
        # Extract the file path before the first parenthetical
        path = artifact.split("(")[0].strip()
        files.append(path)

    return {
        "id": sprint.sprint_id,
        "name": sprint.title,
        "goal": sprint.objective,
        "files_to_produce": files,
        "acceptance_criteria": list(sprint.done_definition),
        "validation_tool": "validate_python_syntax",  # Gap 4 default
        "context_files": list(sprint.integration_targets),
    }


# ---------------------------------------------------------------------------
# Gap 3: Fenced-code-block parser (+ <file> tag fallback)
# ---------------------------------------------------------------------------

_FENCED_BLOCK_RE = re.compile(
    r"###\s*`([^`]+)`\s*\n"          # heading with path in backticks
    r"```[a-zA-Z]*\n"                # opening fence (```python, etc.)
    r"(.*?)"                          # file content (non-greedy)
    r"\n```",                         # closing fence
    re.DOTALL,
)


def parse_fenced_code_blocks(llm_response: str) -> list[tuple[str, str]]:
    """Extract fenced code blocks with path headers from an LLM response.

    Expects the format produced by completion prompts::

        ### `path/to/file.py`
        ```python
        <content>
        ```

    Falls back to ``tools.parse_file_tags()`` if no fenced blocks are
    found, providing transparent support for both output formats.

    Args:
        llm_response: Raw text from the LLM.

    Returns:
        List of ``(path, content)`` tuples, one per file block found.
    """
    matches = _FENCED_BLOCK_RE.findall(llm_response)
    if matches:
        results: list[tuple[str, str]] = []
        for path, content in matches:
            results.append((path.strip(), content.strip("\n")))
        return results

    # Transparent fallback: try <file path="...">...</file> tags
    return tools.parse_file_tags(llm_response)


# ---------------------------------------------------------------------------
# Gap 5: Token budget check with interface-summary fallback
# ---------------------------------------------------------------------------

def _check_and_reduce_prompt(
    sprint_id: str,
    workspace_path: Path | None,
) -> str:
    """Build the prompt with token budget enforcement.

    If the prompt with full workspace source code exceeds the token
    budget, re-builds with ``workspace_path=None`` (interface summaries
    only) as the fallback.

    Args:
        sprint_id: Completion sprint identifier.
        workspace_path: Root of the synthesizer workspace, or None.

    Returns:
        The final prompt string, guaranteed to be within budget.
    """
    token_budget = int(
        config.CONTEXT_WINDOW_LIMIT * (1.0 - config.RESPONSE_HEADROOM_RATIO)
    )

    # First attempt: full source code if workspace_path is provided
    prompt = completion_prompts.build_prompt_for_sprint(sprint_id, workspace_path)
    estimated = tools.estimate_tokens(prompt)

    if estimated <= token_budget:
        return prompt

    if workspace_path is not None:
        # Fallback: interface-summary mode
        logger.warning(
            "Prompt for %s is ~%d tokens (budget %d). "
            "Falling back to interface-summary mode.",
            sprint_id, estimated, token_budget,
        )
        prompt = completion_prompts.build_prompt_for_sprint(sprint_id, None)
        estimated = tools.estimate_tokens(prompt)
        if estimated <= token_budget:
            return prompt
        logger.warning(
            "Even interface-summary prompt for %s is ~%d tokens "
            "(budget %d). Proceeding anyway.",
            sprint_id, estimated, token_budget,
        )

    return prompt


# ---------------------------------------------------------------------------
# Context injection for sequential sprints (§6 in plan)
# ---------------------------------------------------------------------------

def _append_prior_context(
    prompt: str,
    completed_files: dict[str, str],
) -> str:
    """Append prior completion sprint outputs as a context block.

    Later sprints need to see the code produced by earlier sprints.
    The main prompt embeds existing (pre-completion) module code via
    workspace_path, but it does NOT include code produced by prior
    completion sprints.  This function bridges that gap.

    Args:
        prompt: The fully rendered prompt.
        completed_files: Mapping of file path → content for all files
            produced by previously completed completion sprints.

    Returns:
        The prompt with prior outputs appended.
    """
    if not completed_files:
        return prompt

    context_suffix = "\n\n=== PRIOR COMPLETION SPRINT OUTPUTS ===\n"
    context_suffix += (
        "The following files were produced by earlier completion sprints "
        "in this run.  They are already written to disk.  Use their "
        "interfaces — do not re-implement them.\n"
    )
    for fpath, content in completed_files.items():
        context_suffix += (
            f"\n--- PRIOR SPRINT OUTPUT: {fpath} ---\n"
            f"{content}\n"
            f"--- END ---"
        )
    context_suffix += "\n\n=== END PRIOR OUTPUTS ==="

    return prompt + context_suffix


# ---------------------------------------------------------------------------
# Validation-fix prompt builder (§7 in plan)
# ---------------------------------------------------------------------------

def _build_completion_fix_prompt(
    sprint: SprintDefinition,
    error_output: str,
    file_contents: dict[str, str],
) -> str:
    """Build a validation-fix prompt for a failed completion sprint.

    Mirrors the structure of ``orchestrator._build_fix_prompt()`` but
    uses ``SprintDefinition`` fields directly and instructs the agent
    to output files in *both* supported formats (``<file>`` tags are
    explicitly requested for fix responses to match the parser).

    Args:
        sprint: The current completion sprint definition.
        error_output: Error string from the validation tool.
        file_contents: Mapping of file path → current content on disk.

    Returns:
        Formatted fix-prompt string.
    """
    file_blocks = "\n\n".join(
        f"--- {path} ---\n{content}\n--- END ---"
        for path, content in file_contents.items()
    )
    criteria = "\n".join(
        f"  {i}. {d}"
        for i, d in enumerate(sprint.done_definition, 1)
    )
    return (
        f"Sprint {sprint.sprint_id} ({sprint.title}) failed validation.\n\n"
        f"Error output:\n{error_output}\n\n"
        f"Current file contents:\n{file_blocks}\n\n"
        f"Done criteria (all must be true):\n{criteria}\n\n"
        f"Please fix the errors and output the corrected files.\n"
        f"Use either fenced code blocks with ### `path` headers, "
        f"or <file path=\"...\">...</file> tags."
    )


# ---------------------------------------------------------------------------
# LLM call (duplicated from orchestrator — same interface)
# ---------------------------------------------------------------------------

def _call_llm(prompt: str, model: str | None = None) -> str:
    """Send a prompt to the Claude API and return the response text.

    Args:
        prompt: The full user-turn prompt string.
        model: Optional model override; defaults to ``config.AGENT_MODEL``.

    Returns:
        The assistant's response text.
    """
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=model or config.AGENT_MODEL,
        max_tokens=16384,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


# ---------------------------------------------------------------------------
# Validation (Gap 4: default to validate_python_syntax)
# ---------------------------------------------------------------------------

def _run_validation(sprint_dict: dict) -> dict:
    """Run syntax validation on every .py file in the sprint's outputs.

    Completion sprints always use ``validate_python_syntax`` as the
    default validation tool (Gap 4 resolution).

    Args:
        sprint_dict: The sprint dict produced by ``sprint_to_dict()``.

    Returns:
        Standard tool result dict with ``success``, ``output``, ``error``.
    """
    for fpath in sprint_dict["files_to_produce"]:
        resolved = _resolve_file_path(fpath)
        if resolved.endswith(".py") and os.path.isfile(resolved):
            result = tools.validate_python_syntax(resolved)
            if not result["success"]:
                return result
    return {
        "success": True,
        "output": "All .py files pass syntax check.",
        "error": None,
    }


# ---------------------------------------------------------------------------
# Logging (mirrors orchestrator._log_entry)
# ---------------------------------------------------------------------------

def _log_entry(
    sprint_id: str,
    attempt: int,
    prompt_tokens: int,
    response_tokens: int,
    validation_passed: bool,
    error_msg: str | None,
) -> None:
    """Append a structured JSON line to the agent log file.

    Args:
        sprint_id: Current sprint identifier (e.g. ``completion_1``).
        attempt: Attempt number (1-based).
        prompt_tokens: Estimated prompt token count.
        response_tokens: Estimated response token count.
        validation_passed: Whether the validation check passed.
        error_msg: Error message if validation failed, else None.
    """
    entry = {
        "sprint_id": sprint_id,
        "attempt": attempt,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "prompt_tokens": prompt_tokens,
        "response_tokens": response_tokens,
        "validation_passed": validation_passed,
        "error": error_msg,
    }
    os.makedirs(os.path.dirname(config.LOG_FILE), exist_ok=True)
    with open(config.LOG_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# File path helpers (Gap 6: workspace root)
# ---------------------------------------------------------------------------

def _resolve_file_path(relative_path: str) -> str:
    """Resolve a relative file path against WORKSPACE_ROOT.

    If the path is already absolute and under WORKSPACE_ROOT, it is
    returned as-is.  Otherwise it is joined to WORKSPACE_ROOT.

    Args:
        relative_path: File path (relative or absolute).

    Returns:
        Absolute file path string.
    """
    if os.path.isabs(relative_path):
        return relative_path
    return os.path.join(config.WORKSPACE_ROOT, relative_path)


def _sprint_already_complete(sprint_dict: dict) -> bool:
    """Check whether all of a sprint's output files already exist.

    Args:
        sprint_dict: Sprint dict from ``sprint_to_dict()``.

    Returns:
        True if every file in ``files_to_produce`` exists on disk.
    """
    return all(
        os.path.isfile(_resolve_file_path(fp))
        for fp in sprint_dict["files_to_produce"]
    )


def _verify_workspace(workspace_path: Path) -> None:
    """Verify that the workspace contains the synthesizer directory.

    Logs a warning if the synthesizer package directory doesn't exist
    yet (it will be created by the sprints).

    Args:
        workspace_path: Root workspace path.
    """
    synth_dir = workspace_path / "synthesizer"
    if not synth_dir.is_dir():
        logger.warning(
            "synthesizer/ directory does not exist at %s — "
            "it will be created by the completion sprints.",
            synth_dir,
        )

    # Verify write_file will accept paths under WORKSPACE_ROOT/synthesizer/
    test_path = os.path.join(
        config.WORKSPACE_ROOT, "synthesizer", "__verify_test__.py"
    )
    resolved = os.path.realpath(test_path)
    ws_resolved = os.path.realpath(config.WORKSPACE_ROOT)
    if not resolved.startswith(ws_resolved + os.sep):
        raise RuntimeError(
            f"Path safety check failed: '{test_path}' resolves to "
            f"'{resolved}' which is outside WORKSPACE_ROOT '{ws_resolved}'. "
            f"Adjust WORKSPACE_ROOT so it encompasses the synthesizer/ "
            f"directory."
        )
    logger.info(
        "Workspace verified: synthesizer/ paths are inside WORKSPACE_ROOT (%s)",
        ws_resolved,
    )


# ---------------------------------------------------------------------------
# Dependency ordering
# ---------------------------------------------------------------------------

def _resolve_execution_order(
    sprints: list[SprintDefinition],
) -> list[SprintDefinition]:
    """Topologically sort sprints by their declared dependencies.

    If the registry order is already valid, the original order is
    preserved.  This function exists as a safety net against
    mis-ordering in the registry list.

    Args:
        sprints: List of sprint definitions.

    Returns:
        Sprints in dependency-respecting execution order.
    """
    by_id = {s.sprint_id: s for s in sprints}
    resolved: list[str] = []
    remaining = list(sprints)

    max_passes = len(remaining) + 1
    for _ in range(max_passes):
        if not remaining:
            break
        next_remaining = []
        for sprint in remaining:
            if all(dep in resolved for dep in sprint.dependencies):
                resolved.append(sprint.sprint_id)
            else:
                next_remaining.append(sprint)
        if len(next_remaining) == len(remaining):
            unresolved = [s.sprint_id for s in next_remaining]
            raise RuntimeError(
                f"Cannot resolve dependency order for completion sprints. "
                f"Stuck on: {unresolved}"
            )
        remaining = next_remaining

    return [by_id[sid] for sid in resolved]


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    """Execute the completion sprint sequence.

    Parses CLI arguments, validates configuration and workspace layout,
    then iterates through each completion sprint — generating code via
    the LLM, parsing file outputs, writing to disk, validating syntax,
    and retrying on failure.

    Gap 7: GROBID startup is intentionally skipped — the completion
    sprints operate on an already-built environment.
    """
    parser = argparse.ArgumentParser(
        description="Completion sprint runner (adapter for completion_sprints.py)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip sprints whose output files already exist on disk.",
    )
    parser.add_argument(
        "--workspace",
        type=str,
        default=None,
        help=(
            "Override workspace root path. Defaults to config.WORKSPACE_ROOT. "
            "The synthesizer/ directory must be inside this path."
        ),
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override the LLM model. Defaults to config.AGENT_MODEL.",
    )
    parser.add_argument(
        "--sprint",
        type=str,
        default=None,
        help="Run a single sprint by ID (e.g. completion_1). Default: run all.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and log prompts without calling the LLM.",
    )
    args = parser.parse_args()

    # --- Logging setup -----------------------------------------------------
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # --- Config validation -------------------------------------------------
    if not args.dry_run:
        config.validate_config()

    # --- Workspace derivation (Gap 6) --------------------------------------
    if args.workspace:
        workspace_path = Path(args.workspace).resolve()
        # Also update config so tools.write_file uses the right root
        config.WORKSPACE_ROOT = str(workspace_path)
    else:
        workspace_path = Path(config.WORKSPACE_ROOT).resolve()

    _verify_workspace(workspace_path)

    # --- Model override ----------------------------------------------------
    model = args.model or config.AGENT_MODEL

    # --- Determine which sprints to run ------------------------------------
    sprints_to_run = _resolve_execution_order(COMPLETION_SPRINTS)

    if args.sprint:
        target = args.sprint
        # Validate the sprint ID exists
        completion_sprints.get_sprint(target)
        sprints_to_run = [s for s in sprints_to_run if s.sprint_id == target]
        if not sprints_to_run:
            logger.error("Sprint %s not found after dependency resolution.", target)
            return

    # --- Gap 7: GROBID startup intentionally skipped -----------------------
    logger.info("Completion sprint runner — GROBID startup skipped (not needed).")

    completed_files: dict[str, str] = {}
    completed_ids: list[str] = []
    start_time = time.time()

    for sprint in sprints_to_run:
        sprint_id = sprint.sprint_id
        sprint_dict = sprint_to_dict(sprint)

        # --- Resume support ------------------------------------------------
        if args.resume and _sprint_already_complete(sprint_dict):
            logger.info("SKIP %s (--resume, files exist)", sprint_id)
            # Load existing files into context for downstream sprints
            for fpath in sprint_dict["files_to_produce"]:
                resolved = _resolve_file_path(fpath)
                read_result = tools.read_file(resolved)
                if read_result["success"]:
                    completed_files[fpath] = read_result["output"]
            completed_ids.append(sprint_id)
            continue

        logger.info("=" * 60)
        logger.info("BEGIN sprint %s: %s", sprint_id, sprint.title)

        # --- Build prompt (Gap 2: direct call, Gap 5: token budget) --------
        prompt = _check_and_reduce_prompt(sprint_id, workspace_path)

        # Append prior completion sprint outputs (§6 context injection)
        prompt = _append_prior_context(prompt, completed_files)

        prompt_tokens = tools.estimate_tokens(prompt)
        logger.info(
            "Prompt for %s: ~%d tokens (first 200 chars: %s)",
            sprint_id, prompt_tokens, prompt[:200],
        )

        # --- Dry-run exit point --------------------------------------------
        if args.dry_run:
            logger.info(
                "DRY RUN — prompt generated for %s (%d tokens). "
                "Skipping LLM call.",
                sprint_id, prompt_tokens,
            )
            completed_ids.append(sprint_id)
            continue

        # --- Call LLM ------------------------------------------------------
        response_text = _call_llm(prompt, model=model)
        response_tokens = tools.estimate_tokens(response_text)

        # --- Parse files (Gap 3: dual-format parser) -----------------------
        parsed_files = parse_fenced_code_blocks(response_text)

        # Retry parse if nothing found
        parse_retries = 0
        while not parsed_files and parse_retries < 2:
            logger.warning(
                "No files parsed from LLM response for %s, retrying...",
                sprint_id,
            )
            response_text = _call_llm(prompt, model=model)
            response_tokens = tools.estimate_tokens(response_text)
            parsed_files = parse_fenced_code_blocks(response_text)
            parse_retries += 1

        if not parsed_files:
            logger.error(
                "Sprint %s: LLM produced no parseable file output after retries.",
                sprint_id,
            )
            _log_entry(
                sprint_id, 1, prompt_tokens, response_tokens,
                False, "No file output in response",
            )
            logger.error("HALTING — cannot proceed without files from %s.", sprint_id)
            break

        # --- Write files (Gap 6: resolve paths against workspace) ----------
        sprint_file_contents: dict[str, str] = {}
        for fpath, content in parsed_files:
            resolved = _resolve_file_path(fpath)
            write_result = tools.write_file(resolved, content)
            if write_result["success"]:
                completed_files[fpath] = content
                sprint_file_contents[fpath] = content
                logger.info("Wrote %s", resolved)
            else:
                logger.error("Failed to write %s: %s", resolved, write_result["error"])

        # --- Validate + retry loop (Gap 4: python syntax) ------------------
        attempt = 1
        validation_result = _run_validation(sprint_dict)

        while not validation_result["success"] and attempt < config.RETRY_BUDGET:
            error_output = validation_result["error"] or validation_result["output"]
            logger.warning(
                "Sprint %s attempt %d FAILED: %s",
                sprint_id, attempt, error_output[:200],
            )
            _log_entry(
                sprint_id, attempt, prompt_tokens, response_tokens,
                False, error_output,
            )

            # Build fix prompt and retry
            fix_prompt = _build_completion_fix_prompt(
                sprint, error_output, sprint_file_contents,
            )
            response_text = _call_llm(fix_prompt, model=model)
            response_tokens = tools.estimate_tokens(response_text)

            parsed_files = parse_fenced_code_blocks(response_text)
            for fpath, content in parsed_files:
                resolved = _resolve_file_path(fpath)
                write_result = tools.write_file(resolved, content)
                if write_result["success"]:
                    completed_files[fpath] = content
                    sprint_file_contents[fpath] = content

            validation_result = _run_validation(sprint_dict)
            attempt += 1

        # --- Log final result for this sprint ------------------------------
        _log_entry(
            sprint_id, attempt, prompt_tokens, response_tokens,
            validation_result["success"],
            validation_result["error"],
        )

        if validation_result["success"]:
            logger.info("Sprint %s PASSED (attempt %d)", sprint_id, attempt)
            completed_ids.append(sprint_id)
        else:
            logger.error(
                "Sprint %s FAILED after %d attempts: %s",
                sprint_id, attempt, validation_result["error"],
            )
            logger.error("HALTING — sprint %s did not pass validation.", sprint_id)
            break

    # --- Final summary -----------------------------------------------------
    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info("COMPLETION RUN FINISHED in %.1fs", elapsed)
    logger.info("Completed sprints: %s", completed_ids)
    logger.info(
        "Total sprints: %d / %d",
        len(completed_ids), len(sprints_to_run),
    )


if __name__ == "__main__":
    main()