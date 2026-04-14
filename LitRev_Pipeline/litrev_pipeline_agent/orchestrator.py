"""Orchestrator for the LLM-Assisted Literature Review agent framework.

This module implements the main sprint-execution loop.  It sequences sprints
from ``sprints.py``, assembles prompts from ``prompts.py``, calls the Claude
API, dispatches tool calls via ``tools.py``, and validates outputs — all
configured through ``config.py``.
"""

import argparse
import json
import logging
import os
import time

import anthropic

import config
import prompts
import sprints
import tools

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gather_context(
    sprint: dict,
    completed_files: dict,
) -> str:
    """Build the context-injection string from context_files and prior outputs.

    Args:
        sprint: The current sprint dictionary.
        completed_files: Mapping of file path → content for all files
            produced by previously completed sprints.

    Returns:
        A formatted string suitable for insertion into
        ``prompts.CONTEXT_INJECTION``.
    """
    context_paths: list[str] = sprint.get("context_files", [])

    # Also include files from completed sprints not already in context_files
    prior_paths = [p for p in completed_files if p not in context_paths]

    blocks: list[str] = []
    for fpath in context_paths + prior_paths:
        content = completed_files.get(fpath)
        if content is None:
            result = tools.read_file(fpath)
            if result["success"]:
                content = result["output"]
            else:
                logger.warning("Could not read context file %s: %s", fpath, result["error"])
                continue
        blocks.append(
            f"--- BEGIN FILE: {fpath} ---\n{content}\n--- END FILE ---"
        )

    if not blocks:
        return ""

    return prompts.CONTEXT_INJECTION.format(context_blocks="\n\n".join(blocks))


def _format_sprint_instructions(sprint: dict) -> str:
    """Format the sprint instructions template with sprint data.

    Args:
        sprint: The current sprint dictionary.

    Returns:
        Formatted sprint instructions string.
    """
    files_str = "\n".join(f"- {fp}" for fp in sprint["files_to_produce"])
    criteria_str = "\n".join(
        f"{i}. {ac}" for i, ac in enumerate(sprint["acceptance_criteria"], 1)
    )
    return prompts.SPRINT_INSTRUCTIONS.format(
        sprint_id=sprint["id"],
        sprint_name=sprint["name"],
        goal=sprint["goal"],
        files_to_produce=files_str,
        acceptance_criteria=criteria_str,
    )


def _assemble_prompt(sprint: dict, completed_files: dict) -> str:
    """Assemble the full CODE_GENERATION prompt for a sprint.

    Manages context-window budget: if the assembled prompt exceeds the
    token limit, falls back to skeleton extraction for prior-sprint files.

    Args:
        sprint: The current sprint dictionary.
        completed_files: Prior sprint file contents.

    Returns:
        The fully assembled prompt string.
    """
    system_text = prompts.SYSTEM_DEVELOPER
    context_text = _gather_context(sprint, completed_files)
    instructions_text = _format_sprint_instructions(sprint)

    full_prompt = prompts.CODE_GENERATION.format(
        system=system_text,
        context=context_text,
        instructions=instructions_text,
    )

    token_budget = int(
        config.CONTEXT_WINDOW_LIMIT * (1.0 - config.RESPONSE_HEADROOM_RATIO)
    )
    estimated = tools.estimate_tokens(full_prompt)

    if estimated <= token_budget:
        return full_prompt

    # --- Over budget: replace prior-sprint files with skeletons -----------
    logger.warning(
        "Prompt for %s is ~%d tokens (budget %d). Reducing context via skeletons.",
        sprint["id"], estimated, token_budget,
    )
    skeleton_files: dict = {}
    for fpath, content in completed_files.items():
        if fpath.endswith(".py") and fpath not in sprint.get("context_files", []):
            skel_result = tools.extract_skeleton(fpath)
            if skel_result["success"]:
                skeleton_files[fpath] = skel_result["output"]
            else:
                skeleton_files[fpath] = content
        else:
            skeleton_files[fpath] = content

    context_text = _gather_context(sprint, skeleton_files)
    return prompts.CODE_GENERATION.format(
        system=system_text,
        context=context_text,
        instructions=instructions_text,
    )


def _call_llm(prompt: str) -> str:
    """Send a prompt to the Claude API and return the response text.

    Args:
        prompt: The full user-turn prompt string.

    Returns:
        The assistant's response text.
    """
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=config.AGENT_MODEL,
        max_tokens=16384,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def _run_validation(sprint: dict) -> dict:
    """Dispatch the sprint's designated validation tool.

    Args:
        sprint: The current sprint dictionary.

    Returns:
        Standard tool result dict with ``success``, ``output``, ``error``.
    """
    tool_name = sprint["validation_tool"]
    tool_fn = getattr(tools, tool_name)

    if tool_name == "validate_file_structure":
        return tool_fn(sprint["files_to_produce"])
    elif tool_name == "validate_python_syntax":
        # Validate each produced .py file
        for fpath in sprint["files_to_produce"]:
            if fpath.endswith(".py"):
                result = tool_fn(fpath)
                if not result["success"]:
                    return result
        return {"success": True, "output": "All files pass syntax check.", "error": None}
    elif tool_name == "run_python_script":
        # Run the first script in files_to_produce
        return tool_fn(sprint["files_to_produce"][0])
    else:
        return tool_fn(sprint["files_to_produce"][0])


def _build_fix_prompt(sprint: dict, error_output: str) -> str:
    """Assemble the VALIDATION_FIX prompt after a failed validation.

    Args:
        sprint: The current sprint dictionary.
        error_output: The error string from the validation tool.

    Returns:
        Formatted fix prompt string.
    """
    file_blocks: list[str] = []
    for fpath in sprint["files_to_produce"]:
        read_result = tools.read_file(fpath)
        if read_result["success"]:
            file_blocks.append(
                f"--- BEGIN FILE: {fpath} ---\n{read_result['output']}\n--- END FILE ---"
            )

    criteria_str = "\n".join(
        f"{i}. {ac}" for i, ac in enumerate(sprint["acceptance_criteria"], 1)
    )
    return prompts.VALIDATION_FIX.format(
        sprint_id=sprint["id"],
        error_output=error_output,
        file_contents="\n\n".join(file_blocks),
        acceptance_criteria=criteria_str,
    )


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
        sprint_id: Current sprint identifier.
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


def _sprint_already_complete(sprint: dict) -> bool:
    """Check whether all of a sprint's output files already exist.

    Args:
        sprint: The sprint dictionary.

    Returns:
        True if every file in ``files_to_produce`` exists on disk.
    """
    return all(os.path.exists(fp) for fp in sprint["files_to_produce"])


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    """Execute the agent's sprint sequence.

    Parses command-line arguments, validates configuration, optionally
    starts GROBID, and iterates through each sprint — generating code,
    validating, and retrying on failure up to ``config.RETRY_BUDGET`` times.
    """
    parser = argparse.ArgumentParser(description="Lit-review agent orchestrator")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip sprints whose output files already exist on disk.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config.validate_config()

    # --- Start GROBID (best-effort) ----------------------------------------
    grobid_result = tools.start_grobid()
    if grobid_result["success"]:
        logger.info("GROBID: %s", grobid_result["output"])
    else:
        logger.warning("GROBID startup failed: %s — continuing without it.", grobid_result["error"])

    completed_files: dict = {}
    completed_ids: list[str] = []
    start_time = time.time()

    for sprint in sprints.sprints:
        sprint_id = sprint["id"]
        sprint_name = sprint["name"]

        # --- Resume support ------------------------------------------------
        if args.resume and _sprint_already_complete(sprint):
            logger.info("SKIP %s (--resume, files exist)", sprint_id)
            # Load existing files into context for downstream sprints
            for fpath in sprint["files_to_produce"]:
                read_result = tools.read_file(fpath)
                if read_result["success"]:
                    completed_files[fpath] = read_result["output"]
            completed_ids.append(sprint_id)
            continue

        logger.info("=" * 60)
        logger.info("BEGIN sprint %s: %s", sprint_id, sprint_name)

        # --- Generate code ------------------------------------------------
        prompt = _assemble_prompt(sprint, completed_files)
        prompt_tokens = tools.estimate_tokens(prompt)

        response_text = _call_llm(prompt)
        response_tokens = tools.estimate_tokens(response_text)

        parsed_files = tools.parse_file_tags(response_text)

        # If no file tags found, retry the LLM call up to 2 times
        parse_retries = 0
        while not parsed_files and parse_retries < 2:
            logger.warning("No file tags parsed from LLM response for %s, retrying...", sprint_id)
            response_text = _call_llm(prompt)
            response_tokens = tools.estimate_tokens(response_text)
            parsed_files = tools.parse_file_tags(response_text)
            parse_retries += 1

        if not parsed_files:
            logger.error("Sprint %s: LLM produced no parseable file tags after retries.", sprint_id)
            _log_entry(sprint_id, 1, prompt_tokens, response_tokens, False, "No file tags in response")
            logger.error("HALTING — cannot proceed without files from %s.", sprint_id)
            break

        # --- Write files ---------------------------------------------------
        for fpath, content in parsed_files:
            write_result = tools.write_file(fpath, content)
            if write_result["success"]:
                completed_files[fpath] = content
                logger.info("Wrote %s", fpath)
            else:
                logger.error("Failed to write %s: %s", fpath, write_result["error"])

        # --- Validate + retry loop -----------------------------------------
        attempt = 1
        validation_result = _run_validation(sprint)

        while not validation_result["success"] and attempt < config.RETRY_BUDGET:
            error_output = validation_result["error"] or validation_result["output"]
            logger.warning(
                "Sprint %s attempt %d FAILED: %s", sprint_id, attempt, error_output[:200]
            )
            _log_entry(sprint_id, attempt, prompt_tokens, response_tokens, False, error_output)

            # --- Build fix prompt and retry --------------------------------
            fix_prompt = _build_fix_prompt(sprint, error_output)
            response_text = _call_llm(fix_prompt)
            response_tokens = tools.estimate_tokens(response_text)

            parsed_files = tools.parse_file_tags(response_text)
            for fpath, content in parsed_files:
                write_result = tools.write_file(fpath, content)
                if write_result["success"]:
                    completed_files[fpath] = content

            validation_result = _run_validation(sprint)
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

        # --- Post-sprint hooks ---------------------------------------------
        if sprint_id == "S0_scaffold":
            req_path = os.path.join(config.WORKSPACE_ROOT, "requirements.txt")
            dep_result = tools.install_dependencies(req_path)
            if dep_result["success"]:
                logger.info("Dependencies installed successfully.")
            else:
                logger.warning("Dependency install issues: %s", dep_result["error"])

        if sprint_id == "S10_integration_test":
            logger.info("Integration test sprint complete — pipeline is built.")

    # --- Final summary -----------------------------------------------------
    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info("AGENT RUN COMPLETE in %.1fs", elapsed)
    logger.info("Completed sprints: %s", completed_ids)
    logger.info("Total sprints: %d / %d", len(completed_ids), len(sprints.sprints))


if __name__ == "__main__":
    main()