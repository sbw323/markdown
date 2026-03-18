"""
orchestrator.py
Sprint-based agent orchestrator with crash-safe checkpointing for
preemptible VMs.

Executes the LEYP-Water refactoring sprint catalogue by calling the
Anthropic API in a multi-turn tool-use loop for each sprint phase.
Integrates with config/checkpoint.py for three layers of crash safety:

  Layer 1: Phase-granularity checkpointing (checkpoint.json)
  Layer 2: SIGTERM handler for GCP spot VM preemption (exit code 3)
  Layer 3: NSGA-II generation-level checkpointing (transparent to this
           file — wired into leyp_optimizer.py by Sprint S03)

USAGE:
    # First run (no checkpoint exists)
    python orchestrator.py

    # Resume after preemption (checkpoint.json exists)
    python orchestrator.py

    # Start fresh even if checkpoint exists
    python orchestrator.py --fresh

    # Run a single sprint
    python orchestrator.py --sprint S03

    # Dry run — show what would execute without calling the API
    python orchestrator.py --dry-run

EXIT CODES:
    0  — All sprints completed successfully
    1  — A sprint failed after exhausting retries
    2  — File integrity check failed on resume (manual review needed)
    3  — VM preemption detected (restart expected)

DEPLOYMENT:
    Recommended systemd unit for GCP spot VMs:

        [Service]
        ExecStart=/usr/bin/python3 /opt/leyp/orchestrator.py
        Restart=on-failure
        RestartPreventExitStatus=0 1 2
        # Exit code 3 triggers restart; 0/1/2 are terminal.

DEPS:
    anthropic (Python SDK), config.checkpoint, config.sprints, config.prompts
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import textwrap
import time
from pathlib import Path
from typing import Any

import anthropic

from config.checkpoint import (
    CheckpointManager,
    EXIT_INTEGRITY,
    EXIT_PREEMPTED,
    install_preemption_handler,
    safe_write_file,
)
from config.prompts import BASE_CONTEXT, PHASE_PROMPTS
from config.sprints import SPRINTS, Sprint, SprintPhase
from config.tools import run_shell_cmd

logger = logging.getLogger("orchestrator")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_API_RETRIES = 3          # Retries on transient API errors (429, 500, etc.)
API_RETRY_BACKOFF = 10       # Seconds between API retries
TOOL_RESULT_TRUNCATE = 12000 # Max chars per tool result sent back to model


# ---------------------------------------------------------------------------
# Tool definitions for the Anthropic API
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict] = [
    # ── File manipulation tools ────────────────────────────────────────
    {
        "name": "read_file",
        "description": (
            "Read the contents of a file.  Returns the full text.  "
            "Use this before editing any file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to read.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "edit_file",
        "description": (
            "Replace the first occurrence of old_str with new_str in a file.  "
            "old_str must match exactly and be unique in the file.  "
            "Set new_str to empty string to delete the matched text."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to edit.",
                },
                "old_str": {
                    "type": "string",
                    "description": "Exact string to find (must be unique).",
                },
                "new_str": {
                    "type": "string",
                    "description": "Replacement string.",
                },
            },
            "required": ["path", "old_str", "new_str"],
        },
    },
    {
        "name": "create_file",
        "description": "Create a new file with the given content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path for the new file.",
                },
                "content": {
                    "type": "string",
                    "description": "Full file content.",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "delete_file",
        "description": (
            "Delete a file.  Idempotent — returns success if the file "
            "does not exist."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to delete.",
                },
            },
            "required": ["path"],
        },
    },

    # ── Development tools (delegated to run_shell_cmd) ─────────────────
    {
        "name": "run_ruff",
        "description": "Run ruff linter.  Pass fix=true to auto-fix.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "File or directory."},
                "fix": {"type": "boolean", "description": "Auto-fix issues."},
            },
            "required": ["target"],
        },
    },
    {
        "name": "run_ruff_format",
        "description": "Check formatting.  Pass fix=true to apply.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {"type": "string"},
                "fix": {"type": "boolean"},
            },
            "required": ["target"],
        },
    },
    {
        "name": "run_pytest",
        "description": "Execute pytest.  Default flags: -v --tb=short.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Test path."},
                "flags": {"type": "string", "description": "Pytest flags."},
            },
        },
    },
    {
        "name": "python_syntax_check",
        "description": "Verify a .py file compiles (py_compile).",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "run_mypy",
        "description": "Run mypy type checker.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {"type": "string"},
                "flags": {"type": "string"},
            },
        },
    },
    {
        "name": "inspect_csv",
        "description": "Read a CSV and return schema, shape, sample rows.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "sample_rows": {"type": "integer"},
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "inspect_yaml",
        "description": "Read a YAML file and return its structure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "grep_codebase",
        "description": "Regex search across all .py files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "directory": {"type": "string"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "run_python_script",
        "description": "Execute a Python script or inline command (-c).",
        "input_schema": {
            "type": "object",
            "properties": {
                "script_path": {"type": "string", "description": "Script path or inline code."},
                "inline": {"type": "boolean", "description": "True for -c mode."},
                "timeout": {"type": "integer"},
            },
            "required": ["script_path"],
        },
    },
    {
        "name": "check_imports",
        "description": "Verify a Python module imports without errors.",
        "input_schema": {
            "type": "object",
            "properties": {
                "module_name": {"type": "string"},
            },
            "required": ["module_name"],
        },
    },
    {
        "name": "validate_simulation_output",
        "description": (
            "Check optimizer output files for plausibility and "
            "checkpoint cleanup."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "output_dir": {"type": "string"},
                "budget_min": {"type": "number"},
                "budget_max": {"type": "number"},
                "trigger_min": {"type": "number"},
                "trigger_max": {"type": "number"},
                "checkpoint_pkl_path": {"type": "string"},
            },
        },
    },
    {
        "name": "inspect_checkpoint",
        "description": (
            "Inspect checkpoint.json (mode=json) or nsga2_checkpoint.pkl "
            "(mode=pickle).  Auto-detects from extension."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "mode": {
                    "type": "string",
                    "enum": ["json", "pickle", "auto"],
                },
            },
            "required": ["file_path"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

def dispatch_tool(
    name: str,
    args: dict[str, Any],
    project_root: Path,
) -> str:
    """Execute a tool call and return the result as a string.

    File tools operate relative to project_root.  Dev tools delegate
    to run_shell_cmd with cwd=project_root.

    Args:
        name: Tool name from the API response.
        args: Tool input arguments.
        project_root: Working directory for file and shell operations.

    Returns:
        String result to send back as tool_result content.
    """
    try:
        if name == "read_file":
            return _tool_read_file(args, project_root)
        elif name == "edit_file":
            return _tool_edit_file(args, project_root)
        elif name == "create_file":
            return _tool_create_file(args, project_root)
        elif name == "delete_file":
            return _tool_delete_file(args, project_root)
        else:
            return _tool_shell(name, args, project_root)
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


def _resolve(path_str: str, root: Path) -> Path:
    """Resolve a path and verify it stays within the project root.

    Both relative and absolute paths are resolved and checked.
    Raises ValueError if the resolved path escapes the sandbox.

    Args:
        path_str: Path string from the agent's tool call.
        root: Project root directory (sandbox boundary).

    Returns:
        Resolved absolute Path guaranteed to be within root.

    Raises:
        ValueError: If the resolved path is outside the project root.
    """
    root_resolved = root.resolve()
    p = Path(path_str)

    if p.is_absolute():
        resolved = p.resolve()
    else:
        resolved = (root_resolved / p).resolve()

    if not resolved.is_relative_to(root_resolved):
        raise ValueError(
            f"Path escapes project root: {path_str!r} "
            f"(resolves to {resolved}, root is {root_resolved})"
        )

    return resolved


def _tool_read_file(args: dict, root: Path) -> str:
    path = _resolve(args["path"], root)
    if not path.exists():
        return f"ERROR: File not found: {path}"
    try:
        content = path.read_text()
        lines = content.splitlines()
        numbered = "\n".join(
            f"{i+1:5d}\t{line}" for i, line in enumerate(lines)
        )
        return f"File: {args['path']} ({len(lines)} lines)\n\n{numbered}"
    except UnicodeDecodeError:
        return f"ERROR: Binary file, cannot read as text: {path}"


def _tool_edit_file(args: dict, root: Path) -> str:
    path = _resolve(args["path"], root)
    if not path.exists():
        return f"ERROR: File not found: {path}"

    content = path.read_text()
    old_str = args["old_str"]
    new_str = args["new_str"]

    count = content.count(old_str)
    if count == 0:
        return (
            f"ERROR: old_str not found in {args['path']}. "
            f"Re-read the file to get current contents."
        )
    if count > 1:
        return (
            f"ERROR: old_str matches {count} times in {args['path']}. "
            f"Make old_str more specific so it matches exactly once."
        )

    new_content = content.replace(old_str, new_str, 1)
    safe_write_file(path, new_content)
    return f"OK: Edit applied to {args['path']}."


def _tool_create_file(args: dict, root: Path) -> str:
    path = _resolve(args["path"], root)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_write_file(path, args["content"])
    return f"OK: Created {args['path']} ({len(args['content'])} bytes)."


def _tool_delete_file(args: dict, root: Path) -> str:
    path = _resolve(args["path"], root)
    if path.exists():
        path.unlink()
        return f"OK: Deleted {args['path']}."
    return f"OK: {args['path']} does not exist (already deleted)."


def _tool_shell(name: str, args: dict, root: Path) -> str:
    """Dispatch a dev tool to a shell command."""
    cmd: list[str] = []
    timeout = 120

    if name == "run_ruff":
        cmd = ["python", "-m", "ruff", "check", args["target"], "--output-format=text"]
        if args.get("fix"):
            cmd.append("--fix")
        timeout = 60

    elif name == "run_ruff_format":
        cmd = ["python", "-m", "ruff", "format", args["target"]]
        if not args.get("fix"):
            cmd.extend(["--check", "--diff"])
        timeout = 60

    elif name == "run_pytest":
        target = args.get("target", "tests/")
        flags = args.get("flags", "-v --tb=short")
        cmd = ["python", "-m", "pytest"] + flags.split() + [target]
        timeout = 300

    elif name == "python_syntax_check":
        cmd = ["python", "-m", "py_compile", args["file_path"]]
        timeout = 30

    elif name == "run_mypy":
        target = args.get("target", ".")
        flags = args.get("flags", "--ignore-missing-imports")
        cmd = ["python", "-m", "mypy"] + flags.split() + [target]
        timeout = 120

    elif name == "inspect_csv":
        fp = args["file_path"]
        n = str(args.get("sample_rows", 5))
        script = (
            "import pandas as pd, sys\n"
            "fp, n = sys.argv[1], int(sys.argv[2])\n"
            "df = pd.read_csv(fp)\n"
            "print(f'Shape: {df.shape[0]} rows x {df.shape[1]} columns')\n"
            "print(f'\\nColumns and dtypes:')\n"
            "for col in df.columns:\n"
            "    nulls = df[col].isna().sum()\n"
            "    print(f'  {col:30s} {str(df[col].dtype):12s} nulls={nulls}')\n"
            "print(f'\\nFirst {min(int(n), len(df))} rows:')\n"
            "print(df.head(int(n)).to_string(index=False))\n"
        )
        cmd = ["python", "-c", script, fp, n]
        timeout = 30

    elif name == "inspect_yaml":
        script = (
            "import yaml, json, sys\n"
            "with open(sys.argv[1]) as f:\n"
            "    data = yaml.safe_load(f)\n"
            "print(json.dumps(data, indent=2, default=str))\n"
        )
        cmd = ["python", "-c", script, args["file_path"]]
        timeout = 15

    elif name == "grep_codebase":
        directory = args.get("directory", ".")
        cmd = [
            "grep", "-rn", "--include=*.py",
            "--exclude-dir=__pycache__", "--exclude-dir=.git",
            "--exclude-dir=.mypy_cache",
            args["pattern"], directory,
        ]
        timeout = 30

    elif name == "run_python_script":
        script_path = args["script_path"]
        timeout = args.get("timeout", 120)
        if args.get("inline"):
            cmd = ["python", "-c", script_path]
        else:
            cmd = ["python", script_path]

    elif name == "check_imports":
        module = args["module_name"]
        script = (
            f"import {module}\n"
            f"attrs = [a for a in dir({module}) if not a.startswith('_')]\n"
            f"print(f'OK: {module} imported successfully')\n"
            f"print(f'Public attributes ({{len(attrs)}}): {{attrs}}')\n"
        )
        cmd = ["python", "-c", script]
        timeout = 30

    elif name == "validate_simulation_output":
        return _tool_validate_output(args, root)

    elif name == "inspect_checkpoint":
        return _tool_inspect_checkpoint(args, root)

    else:
        return f"ERROR: Unknown tool: {name}"

    result = run_shell_cmd(cmd, timeout=timeout, cwd=str(root))

    # Normalize grep "no match" exit code 1
    if name == "grep_codebase" and result["returncode"] == "1" and not result["stderr"]:
        return f"No matches found for pattern: {args['pattern']}"

    parts = []
    if result["stdout"]:
        parts.append(result["stdout"])
    if result["stderr"]:
        parts.append(f"STDERR:\n{result['stderr']}")
    parts.append(f"[exit code {result['returncode']}]")
    return "\n".join(parts)


def _tool_validate_output(args: dict, root: Path) -> str:
    """Run the validate_simulation_output script from tools.py."""
    output_dir = args.get("output_dir", "Optimization_Results_NSGA2")
    budget_min = str(args.get("budget_min", 10000.0))
    budget_max = str(args.get("budget_max", 2000000.0))
    trigger_min = str(args.get("trigger_min", 1.0))
    trigger_max = str(args.get("trigger_max", 3.5))
    pkl = args.get("checkpoint_pkl_path", "nsga2_checkpoint.pkl")

    script = (
        "import pandas as pd, sys, os, math\n"
        "output_dir, budget_min, budget_max = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])\n"
        "trigger_min, trigger_max, pkl = float(sys.argv[4]), float(sys.argv[5]), sys.argv[6]\n"
        "fails = []\n"
        "if os.path.exists(pkl):\n"
        "    fails.append(f'FAIL: {pkl} still exists — cleanup() not called')\n"
        "else:\n"
        "    print(f'Checkpoint cleanup: {pkl} correctly removed.')\n"
        "pareto = os.path.join(output_dir, 'nsga2_results.csv')\n"
        "if not os.path.exists(pareto):\n"
        "    fails.append('FAIL: nsga2_results.csv not found')\n"
        "else:\n"
        "    df = pd.read_csv(pareto)\n"
        "    for c in ['Investment_Cost','Risk_Cost','Total_Cost']:\n"
        "        if c not in df.columns: fails.append(f'FAIL: missing {c}')\n"
        "        elif (df[c]<0).any(): fails.append(f'FAIL: negative {c}')\n"
        "    print(f'Pareto: {len(df)} solutions')\n"
        "plan = os.path.join(output_dir, 'Optimal_Action_Plan.csv')\n"
        "if not os.path.exists(plan):\n"
        "    fails.append('FAIL: Optimal_Action_Plan.csv not found')\n"
        "for f in ['optimization_curve.png','validation_curve.png']:\n"
        "    if not os.path.exists(os.path.join(output_dir, f)):\n"
        "        fails.append(f'FAIL: {f} not found')\n"
        "if fails:\n"
        "    for f in fails: print(f'  {f}')\n"
        "    print('Verdict: FAIL')\n"
        "    sys.exit(1)\n"
        "else:\n"
        "    print('Verdict: PASS')\n"
    )
    result = run_shell_cmd(
        ["python", "-c", script, output_dir, budget_min, budget_max,
         trigger_min, trigger_max, pkl],
        timeout=60, cwd=str(root),
    )
    return (result["stdout"] + result["stderr"]).strip()


def _tool_inspect_checkpoint(args: dict, root: Path) -> str:
    """Inspect a checkpoint file (JSON or pickle)."""
    fp = args["file_path"]
    mode = args.get("mode", "auto")
    script = (
        "import sys, os, json\n"
        "fp, mode = sys.argv[1], sys.argv[2]\n"
        "if not os.path.exists(fp):\n"
        "    print(f'FILE NOT FOUND: {fp}'); sys.exit(1)\n"
        "print(f'File: {fp} ({os.path.getsize(fp):,} bytes)')\n"
        "if mode == 'auto':\n"
        "    mode = 'pickle' if fp.endswith('.pkl') else 'json'\n"
        "if mode == 'json':\n"
        "    data = json.load(open(fp))\n"
        "    print(f'Preemptions: {data.get(\"preemption_count\",0)}')\n"
        "    sprints = data.get('sprints',{})\n"
        "    for sid, s in sorted(sprints.items()):\n"
        "        phases = s.get('phases',{})\n"
        "        done = sum(1 for p in phases.values() if p.get('status') in ('completed','skipped'))\n"
        "        print(f'  {sid}: {s.get(\"status\")} ({done}/{len(phases)} phases)')\n"
        "elif mode == 'pickle':\n"
        "    import pickle\n"
        "    try:\n"
        "        algo = pickle.load(open(fp,'rb'))\n"
        "        print(f'PICKLE OK: gen={getattr(algo,\"n_gen\",None)}')\n"
        "    except Exception as e:\n"
        "        print(f'PICKLE CORRUPT: {e}'); sys.exit(1)\n"
    )
    result = run_shell_cmd(
        ["python", "-c", script, fp, mode],
        timeout=30, cwd=str(root),
    )
    return (result["stdout"] + result["stderr"]).strip()


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def build_system_prompt(sprint: Sprint, phase: SprintPhase) -> str:
    """Construct the system prompt for a sprint/phase combination.

    Combines the domain preamble, coding standards, and phase-specific
    instructions.
    """
    return BASE_CONTEXT + "\n\n" + PHASE_PROMPTS[phase]


def build_user_message(sprint: Sprint, phase: SprintPhase) -> str:
    """Construct the initial user message for a sprint/phase.

    Provides the sprint objective, acceptance criteria, file manifest,
    and any phase-specific context (e.g., test command for UNIT_TEST).
    """
    parts = [
        f"# Sprint {sprint.id}: {sprint.title}",
        f"## Phase: {phase.value}",
        "",
        "## Objective",
        sprint.objective,
        "",
        "## Acceptance Criteria",
    ]
    for i, crit in enumerate(sprint.acceptance_criteria, 1):
        parts.append(f"  {i}. {crit}")

    parts.append("")
    if sprint.files_to_create:
        parts.append(f"**Files to create**: {', '.join(sprint.files_to_create)}")
    if sprint.files_to_modify:
        parts.append(f"**Files to modify**: {', '.join(sprint.files_to_modify)}")
    if sprint.files_to_delete:
        parts.append(f"**Files to delete**: {', '.join(sprint.files_to_delete)}")
    if sprint.reference_files:
        parts.append(f"**Reference files**: {', '.join(sprint.reference_files)}")
    if sprint.test_cmd:
        parts.append(f"**Test command**: `{sprint.test_cmd}`")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Agent turn loop — executes one phase of one sprint
# ---------------------------------------------------------------------------

def run_phase(
    client: anthropic.Anthropic,
    sprint: Sprint,
    phase: SprintPhase,
    mgr: CheckpointManager,
    project_root: Path,
) -> bool:
    """Execute a single sprint phase via multi-turn API conversation.

    Returns True if the phase completed successfully, False if it
    exhausted its turn limit without finishing.

    Args:
        client: Anthropic API client.
        sprint: The Sprint being executed.
        phase: The SprintPhase to run.
        mgr: CheckpointManager (for turn tracking).
        project_root: Working directory.

    Returns:
        True on success, False on turn limit exhaustion.
    """
    max_turns = sprint.max_turns_per_phase.get(phase, 10)
    system_prompt = build_system_prompt(sprint, phase)
    user_msg = build_user_message(sprint, phase)

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": user_msg},
    ]

    logger.info(
        "Starting %s.%s (max %d turns, model %s)",
        sprint.id, phase.value, max_turns, sprint.model,
    )

    for turn in range(1, max_turns + 1):
        turn_count = mgr.increment_turn(sprint.id, phase)
        logger.debug("  Turn %d/%d", turn_count, max_turns)

        # ── Call the API with retry on transient errors ────────────
        response = _api_call_with_retry(
            client, sprint.model, system_prompt, messages,
        )
        if response is None:
            logger.error("API call failed after %d retries.", MAX_API_RETRIES)
            return False

        # ── Process response ──────────────────────────────────────
        assistant_content = response.content
        stop_reason = response.stop_reason

        # Append assistant message to conversation
        messages.append({
            "role": "assistant",
            "content": [_block_to_dict(b) for b in assistant_content],
        })

        # If the model stopped naturally (no tool use), phase is done
        if stop_reason == "end_turn":
            logger.info(
                "  %s.%s finished at turn %d.",
                sprint.id, phase.value, turn,
            )
            return True

        # If the model wants to use tools, dispatch them
        if stop_reason == "tool_use":
            tool_results = []
            for block in assistant_content:
                if block.type == "tool_use":
                    logger.debug("  Tool call: %s", block.name)
                    result_str = dispatch_tool(
                        block.name, block.input, project_root,
                    )
                    # Truncate very large results
                    if len(result_str) > TOOL_RESULT_TRUNCATE:
                        result_str = (
                            result_str[:TOOL_RESULT_TRUNCATE]
                            + f"\n\n... [truncated, {len(result_str)} total chars]"
                        )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    })

            messages.append({"role": "user", "content": tool_results})
            continue

        # Unexpected stop reason
        logger.warning(
            "  Unexpected stop_reason: %s at turn %d", stop_reason, turn,
        )
        return True  # Treat as completed — let VERIFY catch issues

    # Exhausted turn limit
    logger.warning(
        "%s.%s exhausted %d turns without completing.",
        sprint.id, phase.value, max_turns,
    )
    return False


def _api_call_with_retry(
    client: anthropic.Anthropic,
    model: str,
    system: str,
    messages: list[dict],
) -> Any | None:
    """Call the Anthropic API with exponential backoff on transient errors."""
    for attempt in range(1, MAX_API_RETRIES + 1):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=16384,
                system=system,
                messages=messages,
                tools=TOOL_SCHEMAS,
            )
            return response
        except anthropic.RateLimitError:
            wait = API_RETRY_BACKOFF * attempt
            logger.warning("Rate limited — waiting %ds (attempt %d)", wait, attempt)
            time.sleep(wait)
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                wait = API_RETRY_BACKOFF * attempt
                logger.warning("Server error %d — retrying in %ds", e.status_code, wait)
                time.sleep(wait)
            else:
                logger.error("API error (non-retryable): %s", e)
                return None
        except anthropic.APIConnectionError as e:
            wait = API_RETRY_BACKOFF * attempt
            logger.warning("Connection error — retrying in %ds: %s", wait, e)
            time.sleep(wait)
    return None


def _block_to_dict(block: Any) -> dict:
    """Convert an API response content block to a serializable dict."""
    if block.type == "text":
        return {"type": "text", "text": block.text}
    elif block.type == "tool_use":
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": block.input,
        }
    return {"type": block.type}


# ---------------------------------------------------------------------------
# Sprint execution with retry
# ---------------------------------------------------------------------------

def run_sprint(
    client: anthropic.Anthropic,
    sprint: Sprint,
    mgr: CheckpointManager,
    project_root: Path,
) -> bool:
    """Execute all phases of a sprint with retry logic.

    Each phase runs in a fresh conversation.  If a phase fails, the
    sprint retries from that phase (not from the beginning).  After
    retry_limit failures on the same phase, the sprint is marked
    as failed.

    Args:
        client: Anthropic API client.
        sprint: The Sprint to execute.
        mgr: CheckpointManager.
        project_root: Working directory.

    Returns:
        True if all phases completed, False if the sprint failed.
    """
    logger.info(
        "=" * 60 + "\nSprint %s: %s\n" + "=" * 60,
        sprint.id, sprint.title,
    )

    for phase in SprintPhase:
        # Skip phases the sprint opts out of
        if phase in sprint.skip_phases:
            mgr.mark_phase_skipped(sprint.id, phase)
            logger.info("  %s.%s — skipped (per sprint config)", sprint.id, phase.value)
            continue

        # Skip already-completed phases (resume after preemption)
        if mgr.is_phase_completed(sprint.id, phase):
            logger.info("  %s.%s — already completed", sprint.id, phase.value)
            continue

        # Execute the phase with retry
        success = False
        for attempt in range(1, sprint.retry_limit + 1):
            mgr.mark_phase_started(sprint.id, phase)
            logger.info(
                "  %s.%s — attempt %d/%d",
                sprint.id, phase.value, attempt, sprint.retry_limit,
            )

            phase_ok = run_phase(client, sprint, phase, mgr, project_root)

            if phase_ok:
                files_changed = sprint.files_to_create + sprint.files_to_modify
                mgr.mark_phase_completed(sprint.id, phase, files_modified=files_changed)
                success = True
                break
            else:
                retry_count = mgr.increment_retry(sprint.id, phase)
                logger.warning(
                    "  %s.%s failed — retry %d/%d",
                    sprint.id, phase.value, retry_count, sprint.retry_limit,
                )
                if attempt < sprint.retry_limit:
                    mgr.reset_phase_for_retry(sprint.id, phase)

        if not success:
            mgr.mark_phase_failed(sprint.id, phase)
            mgr.mark_sprint_failed(sprint.id)
            logger.error(
                "Sprint %s FAILED at phase %s after %d retries.",
                sprint.id, phase.value, sprint.retry_limit,
            )
            return False

    mgr.mark_sprint_completed(sprint.id)
    logger.info("Sprint %s COMPLETED.", sprint.id)
    return True


# ---------------------------------------------------------------------------
# File integrity handling on resume
# ---------------------------------------------------------------------------

def handle_integrity_violations(
    violations: list[dict[str, str]],
    mgr: CheckpointManager,
) -> set[str]:
    """Process file integrity violations and determine sprints to re-run.

    For each corrupted file, identifies the last sprint that modified
    it and marks that sprint for re-execution by resetting its status.

    Args:
        violations: List of violation dicts from verify_file_integrity().
        mgr: CheckpointManager.

    Returns:
        Set of sprint IDs that need to be re-run.
    """
    sprints_to_rerun = set()

    for v in violations:
        sprint_id = v["last_modified_by"]
        logger.warning(
            "Integrity violation: %s (expected %s, got %s, last modified by %s)",
            v["file"], v["expected"], v["actual"], sprint_id,
        )
        if sprint_id != "unknown":
            sprints_to_rerun.add(sprint_id)

    # Reset affected sprints to in-progress so they re-run
    for sid in sprints_to_rerun:
        ss = mgr.state.sprints.get(sid)
        if ss is not None:
            from config.checkpoint import SprintStatus, PhaseStatus
            ss.status = SprintStatus.IN_PROGRESS
            ss.completed_at = None
            # Reset all phases to pending so the sprint re-runs fully
            for ps in ss.phases.values():
                if ps.status in (PhaseStatus.COMPLETED, PhaseStatus.SKIPPED):
                    ps.status = PhaseStatus.PENDING
            logger.warning("Sprint %s reset for re-run due to file corruption.", sid)

    mgr.save()
    return sprints_to_rerun


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Entry point.  Returns exit code."""

    # ── CLI arguments ─────────────────────────────────────────────────
    parser = argparse.ArgumentParser(
        description="LEYP-Water refactoring agent orchestrator.",
    )
    parser.add_argument(
        "--checkpoint-path", default="checkpoint.json",
        help="Path to checkpoint file (default: checkpoint.json)",
    )
    parser.add_argument(
        "--project-root", default=".",
        help="Project root directory (default: current directory)",
    )
    parser.add_argument(
        "--fresh", action="store_true",
        help="Ignore existing checkpoint and start fresh.",
    )
    parser.add_argument(
        "--sprint", type=str, default=None,
        help="Run only this sprint ID (e.g., S03).  Dependencies must be met.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show execution plan without calling the API.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging.",
    )
    args = parser.parse_args()

    # ── Logging ───────────────────────────────────────────────────────
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(name)-14s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )

    project_root = Path(args.project_root).resolve()
    logger.info("Project root: %s", project_root)

    # ── Checkpoint manager + preemption handler ───────────────────────
    mgr = CheckpointManager(
        checkpoint_path=args.checkpoint_path,
        project_root=str(project_root),
    )
    install_preemption_handler(mgr)

    if args.fresh:
        logger.info("--fresh flag: ignoring existing checkpoint.")
        mgr.state.start_time = (
            __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat()
        )
    else:
        mgr.load()

    # ── File integrity check on resume ────────────────────────────────
    if not args.fresh and mgr.state.preemption_count > 0:
        logger.info("Resuming after %d preemption(s) — checking file integrity.",
                     mgr.state.preemption_count)
        violations = mgr.verify_file_integrity()
        if violations:
            rerun_sprints = handle_integrity_violations(violations, mgr)
            logger.warning(
                "File integrity violations found.  Sprints to re-run: %s",
                ", ".join(sorted(rerun_sprints)),
            )
            # Continue execution — affected sprints have been reset

    # ── Progress summary ──────────────────────────────────────────────
    logger.info("Current progress:\n%s", mgr.get_progress_summary())

    # ── Determine which sprints to run ────────────────────────────────
    if args.sprint:
        sprint_filter = {args.sprint}
    else:
        sprint_filter = None

    # ── Dry run ───────────────────────────────────────────────────────
    if args.dry_run:
        logger.info("=== DRY RUN — no API calls ===")
        for sprint in SPRINTS:
            if sprint_filter and sprint.id not in sprint_filter:
                continue
            if mgr.is_sprint_completed(sprint.id):
                logger.info("  %s: SKIP (completed)", sprint.id)
                continue
            if not mgr.are_dependencies_met(sprint):
                deps = [d for d in sprint.depends_on if not mgr.is_sprint_completed(d)]
                logger.info("  %s: BLOCKED (waiting on %s)", sprint.id, ", ".join(deps))
                continue
            phases = [
                p.value for p in SprintPhase
                if p not in sprint.skip_phases
                and not mgr.is_phase_completed(sprint.id, p)
            ]
            logger.info("  %s: WOULD RUN phases [%s]", sprint.id, ", ".join(phases))
        return 0

    # ── Initialize Anthropic client ───────────────────────────────────
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error(
            "ANTHROPIC_API_KEY not set.  Export it before running:\n"
            "  export ANTHROPIC_API_KEY='sk-ant-...'"
        )
        return 1

    client = anthropic.Anthropic(api_key=api_key)

    # ── Main sprint execution loop ────────────────────────────────────
    any_failed = False

    for sprint in SPRINTS:
        if sprint_filter and sprint.id not in sprint_filter:
            continue

        if mgr.is_sprint_completed(sprint.id):
            logger.info("Sprint %s: already completed — skipping.", sprint.id)
            continue

        if not mgr.are_dependencies_met(sprint):
            unmet = [
                d for d in sprint.depends_on
                if not mgr.is_sprint_completed(d)
            ]
            logger.warning(
                "Sprint %s: dependencies not met (%s) — skipping.",
                sprint.id, ", ".join(unmet),
            )
            continue

        ok = run_sprint(client, sprint, mgr, project_root)
        if not ok:
            any_failed = True
            logger.error(
                "Sprint %s failed.  Stopping execution.\n"
                "Fix the issue and re-run to resume from this sprint.",
                sprint.id,
            )
            break

    # ── Final summary ─────────────────────────────────────────────────
    logger.info("Final state:\n%s", mgr.get_progress_summary())

    if any_failed:
        return 1

    completed = sum(1 for s in SPRINTS if mgr.is_sprint_completed(s.id))
    total = len(SPRINTS) if sprint_filter is None else len(sprint_filter)
    if completed >= total:
        logger.info("All sprints completed successfully.")
    else:
        logger.info("%d/%d sprints completed.", completed, len(SPRINTS))

    return 0


if __name__ == "__main__":
    sys.exit(main())
