"""
config/tools.py
Python subprocess helpers and in-process MCP tool server for the Claude
development agent.

AUDIT FIXES APPLIED:
    F05 — validate_simulation_output tool for numerical plausibility
    F09 — inspect_csv/yaml pass file paths via sys.argv (safe path handling)

CHECKPOINT GAPS FILLED:
    Gap 14 — validate_simulation_output now checks nsga2_checkpoint.pkl
             is cleaned up after successful run
    Gap 15 — New inspect_checkpoint tool for verifying pickle integrity
             and checkpoint.json state during preemption resume testing

TOOLS PROVIDED:
    run_ruff              — Lint with ruff
    run_ruff_format       — Formatting check
    run_pytest            — Execute pytest
    python_syntax_check   — Verify .py compiles
    run_mypy              — Static type checking
    inspect_csv           — CSV schema, shape, sample
    inspect_yaml          — YAML structure
    grep_codebase         — Regex search across .py files
    run_python_script     — Execute arbitrary Python
    check_imports         — Verify module imports cleanly
    validate_simulation_output — Domain-specific plausibility + checkpoint cleanup
    inspect_checkpoint    — Verify checkpoint.json state and pickle integrity

OPTIONAL DEPENDENCIES:
    claude_agent_sdk — Only required for build_python_mcp_server().
                       All other functions work without it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Low-level shell command runner
# ---------------------------------------------------------------------------

def run_shell_cmd(
    cmd: list[str],
    timeout: int = 120,
    cwd: Optional[str | Path] = None,
    env: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    """Execute a shell command and return stdout/stderr/returncode.

    Args:
        cmd: Command as a list of strings.
        timeout: Maximum seconds before killing.
        cwd: Working directory.  If None, inherits from calling process.
        env: Optional environment variable overrides.

    Returns:
        dict with keys 'stdout', 'stderr', 'returncode' (all strings).
    """
    import os

    run_env = None
    if env:
        run_env = {**os.environ, **env}

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
            env=run_env,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": str(result.returncode),
        }
    except FileNotFoundError:
        tool_name = cmd[0] if cmd else "unknown"
        return {
            "stdout": "",
            "stderr": (
                f"ERROR: '{tool_name}' not found on PATH. "
                f"Install it with: pip install {tool_name}"
            ),
            "returncode": "-1",
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"ERROR: Command timed out after {timeout}s: {' '.join(cmd)}",
            "returncode": "-2",
        }


# ---------------------------------------------------------------------------
# Convenience wrappers (usable without MCP server)
# ---------------------------------------------------------------------------

def run_pytest_cmd(
    target: str = "tests/",
    flags: str = "-v",
    timeout: int = 300,
    cwd: Optional[str | Path] = None,
) -> dict[str, str]:
    """Run pytest on a target path with optional flags."""
    cmd = ["python", "-m", "pytest"] + flags.split() + [target]
    return run_shell_cmd(cmd, timeout=timeout, cwd=cwd)


def run_ruff_cmd(
    target: str,
    fix: bool = False,
    timeout: int = 60,
    cwd: Optional[str | Path] = None,
) -> dict[str, str]:
    """Run ruff linter on a target file or directory."""
    cmd = ["python", "-m", "ruff", "check", target]
    if fix:
        cmd.append("--fix")
    return run_shell_cmd(cmd, timeout=timeout, cwd=cwd)


# ---------------------------------------------------------------------------
# Domain-specific validation tools (used by orchestrator dispatch)
# ---------------------------------------------------------------------------

def validate_simulation_output(
    output_dir: str = "Optimization_Results_NSGA2",
    budget_min: float = 10000.0,
    budget_max: float = 2000000.0,
    trigger_min: float = 1.0,
    trigger_max: float = 3.5,
    checkpoint_pkl_path: str = "nsga2_checkpoint.pkl",
    cwd: Optional[str | Path] = None,
) -> dict[str, str]:
    """Check optimizer outputs for plausibility and checkpoint cleanup.

    Runs as a subprocess so it doesn't pollute the orchestrator's
    import environment with pandas/numpy.

    Returns:
        dict with 'stdout', 'stderr', 'returncode' keys.
    """
    script = (
        "import pandas as pd, sys, os, math\n"
        "output_dir = sys.argv[1]\n"
        "budget_min, budget_max = float(sys.argv[2]), float(sys.argv[3])\n"
        "trigger_min, trigger_max = float(sys.argv[4]), float(sys.argv[5])\n"
        "checkpoint_pkl = sys.argv[6]\n"
        "fails = []\n"
        "\n"
        "# --- Checkpoint cleanup check (Gap 14) ---\n"
        "if os.path.exists(checkpoint_pkl):\n"
        "    fails.append(\n"
        "        f'FAIL: {checkpoint_pkl} still exists after optimization. '\n"
        "        'opt_ckpt.cleanup() was not called or was called before '\n"
        "        'output files were written. A stale pickle causes the next '\n"
        "        'run to resume from old state instead of starting fresh.'\n"
        "    )\n"
        "else:\n"
        "    print(f'Checkpoint cleanup: {checkpoint_pkl} correctly removed.')\n"
        "\n"
        "# --- Pareto front checks ---\n"
        "pareto_path = os.path.join(output_dir, 'nsga2_results.csv')\n"
        "if not os.path.exists(pareto_path):\n"
        "    fails.append('FAIL: nsga2_results.csv not found')\n"
        "else:\n"
        "    df = pd.read_csv(pareto_path)\n"
        "    if len(df) == 0:\n"
        "        fails.append('FAIL: nsga2_results.csv is empty')\n"
        "    else:\n"
        "        for col in ['Investment_Cost', 'Risk_Cost', 'Total_Cost']:\n"
        "            if col not in df.columns:\n"
        "                fails.append(f'FAIL: missing column {col}')\n"
        "            elif (df[col] < 0).any():\n"
        "                fails.append(f'FAIL: negative values in {col}')\n"
        "            elif df[col].isna().any() or df[col].apply(lambda x: math.isinf(x)).any():\n"
        "                fails.append(f'FAIL: NaN or Inf in {col}')\n"
        "        if 'Total_Cost' in df.columns and 'Investment_Cost' in df.columns and 'Risk_Cost' in df.columns:\n"
        "            diff = abs(df['Total_Cost'] - df['Investment_Cost'] - df['Risk_Cost'])\n"
        "            if (diff > 1.0).any():\n"
        "                fails.append('FAIL: Total != Investment + Risk (tolerance 1.0)')\n"
        "        if 'Budget' in df.columns:\n"
        "            if (df['Budget'] < budget_min * 0.9).any() or (df['Budget'] > budget_max * 1.1).any():\n"
        "                fails.append(f'WARN: Budget outside [{budget_min}, {budget_max}]')\n"
        "        if 'Rehab_Trigger' in df.columns:\n"
        "            if (df['Rehab_Trigger'] < trigger_min * 0.9).any() or (df['Rehab_Trigger'] > trigger_max * 1.1).any():\n"
        "                fails.append(f'WARN: Rehab_Trigger outside [{trigger_min}, {trigger_max}]')\n"
        "        print(f'Pareto front: {len(df)} solutions')\n"
        "        print(f'  Investment: ${df[\"Investment_Cost\"].min():,.0f} - ${df[\"Investment_Cost\"].max():,.0f}')\n"
        "        print(f'  Risk:       ${df[\"Risk_Cost\"].min():,.0f} - ${df[\"Risk_Cost\"].max():,.0f}')\n"
        "        print(f'  Total min:  ${df[\"Total_Cost\"].min():,.0f}')\n"
        "\n"
        "# --- Action plan checks ---\n"
        "plan_path = os.path.join(output_dir, 'Optimal_Action_Plan.csv')\n"
        "if not os.path.exists(plan_path):\n"
        "    fails.append('FAIL: Optimal_Action_Plan.csv not found')\n"
        "else:\n"
        "    ap = pd.read_csv(plan_path)\n"
        "    if len(ap) == 0:\n"
        "        fails.append('FAIL: Action plan is empty')\n"
        "    else:\n"
        "        required = ['Year', 'PipeID', 'Action', 'Cost', 'Priority', 'Condition_Before']\n"
        "        missing = [c for c in required if c not in ap.columns]\n"
        "        if missing:\n"
        "            fails.append(f'FAIL: Action plan missing columns: {missing}')\n"
        "        if 'Action' in ap.columns:\n"
        "            # Allowed action types — must match leyp_config.py constants:\n"
        "            #   ACTION_CIP_REPLACEMENT = 'CIP_Replacement'\n"
        "            #   ACTION_EMERGENCY_REPLACEMENT = 'Emergency_Replacement'\n"
        "            allowed = {'CIP_Replacement', 'Emergency_Replacement'}\n"
        "            bad = set(ap['Action'].unique()) - allowed\n"
        "            if bad:\n"
        "                fails.append(f'FAIL: Unknown action types: {bad}')\n"
        "            cip_n = (ap['Action'] == 'CIP_Replacement').sum()   # leyp_config.ACTION_CIP_REPLACEMENT\n"
        "            emg_n = (ap['Action'] == 'Emergency_Replacement').sum()   # leyp_config.ACTION_EMERGENCY_REPLACEMENT\n"
        "            print(f'Action plan: {len(ap)} entries (CIP: {cip_n}, Emergency: {emg_n})')\n"
        "        if 'Cost' in ap.columns and (ap['Cost'] < 0).any():\n"
        "            fails.append('FAIL: Negative costs in action plan')\n"
        "        if 'Condition_Before' in ap.columns:\n"
        "            conds = ap['Condition_Before']\n"
        "            if (conds < 0.9).any() or (conds > 6.1).any():\n"
        "                fails.append('FAIL: Condition_Before outside [1, 6]')\n"
        "\n"
        "# --- Output files ---\n"
        "for fname in ['optimization_curve.png', 'validation_curve.png']:\n"
        "    fpath = os.path.join(output_dir, fname)\n"
        "    if not os.path.exists(fpath):\n"
        "        fails.append(f'FAIL: {fname} not found')\n"
        "    elif os.path.getsize(fpath) < 1000:\n"
        "        fails.append(f'WARN: {fname} suspiciously small ({os.path.getsize(fpath)} bytes)')\n"
        "\n"
        "# --- Verdict ---\n"
        "if fails:\n"
        "    print('\\n--- ISSUES ---')\n"
        "    for f in fails:\n"
        "        print(f'  {f}')\n"
        "    has_fail = any(f.startswith('FAIL') for f in fails)\n"
        "    print(f'\\nVerdict: {\"FAIL\" if has_fail else \"WARN\"}')\n"
        "    sys.exit(1 if has_fail else 0)\n"
        "else:\n"
        "    print('\\nAll checks passed.')\n"
        "    print('Verdict: PASS')\n"
    )
    cmd = [
        "python", "-c", script,
        output_dir,
        str(budget_min), str(budget_max),
        str(trigger_min), str(trigger_max),
        checkpoint_pkl_path,
    ]
    return run_shell_cmd(cmd, timeout=60, cwd=cwd)


def inspect_checkpoint(
    file_path: str,
    mode: str = "auto",
    cwd: Optional[str | Path] = None,
) -> dict[str, str]:
    """Inspect checkpoint.json or nsga2_checkpoint.pkl state.

    Returns:
        dict with 'stdout', 'stderr', 'returncode' keys.
    """
    script = (
        "import sys, os, json\n"
        "fp = sys.argv[1]\n"
        "mode = sys.argv[2]\n"
        "\n"
        "if not os.path.exists(fp):\n"
        "    print(f'FILE NOT FOUND: {fp}')\n"
        "    sys.exit(1)\n"
        "\n"
        "fsize = os.path.getsize(fp)\n"
        "print(f'File: {fp} ({fsize:,} bytes)')\n"
        "\n"
        "# Auto-detect mode from extension\n"
        "if mode == 'auto':\n"
        "    mode = 'pickle' if fp.endswith('.pkl') else 'json'\n"
        "\n"
        "if mode == 'json':\n"
        "    with open(fp) as f:\n"
        "        data = json.load(f)\n"
        "    print(f'Project: {data.get(\"project\", \"unknown\")}')\n"
        "    print(f'Preemption count: {data.get(\"preemption_count\", 0)}')\n"
        "    print(f'Total elapsed: {data.get(\"total_elapsed_seconds\", 0):.0f}s')\n"
        "    print(f'Last checkpoint: {data.get(\"last_checkpoint\", \"never\")}')\n"
        "    sprints = data.get('sprints', {})\n"
        "    print(f'Sprints tracked: {len(sprints)}')\n"
        "    for sid, sdata in sorted(sprints.items()):\n"
        "        status = sdata.get('status', 'unknown')\n"
        "        phases = sdata.get('phases', {})\n"
        "        completed = sum(1 for p in phases.values() if p.get('status') in ('completed', 'skipped'))\n"
        "        total = len(phases)\n"
        "        print(f'  {sid}: {status} ({completed}/{total} phases done)')\n"
        "    checksums = data.get('file_checksums', {})\n"
        "    print(f'File checksums: {len(checksums)} files tracked')\n"
        "\n"
        "elif mode == 'pickle':\n"
        "    import pickle\n"
        "    try:\n"
        "        with open(fp, 'rb') as f:\n"
        "            algo = pickle.load(f)\n"
        "        n_gen = getattr(algo, 'n_gen', None)\n"
        "        pop_size = None\n"
        "        if hasattr(algo, 'pop') and algo.pop is not None:\n"
        "            pop_size = len(algo.pop)\n"
        "        print(f'PICKLE OK: loaded successfully')\n"
        "        print(f'  Algorithm type: {type(algo).__name__}')\n"
        "        print(f'  Generation (n_gen): {n_gen}')\n"
        "        print(f'  Population size: {pop_size}')\n"
        "        if hasattr(algo, 'opt') and algo.opt is not None:\n"
        "            print(f'  Current best solutions: {len(algo.opt)}')\n"
        "        print(f'  Resumable: {\"YES\" if n_gen and n_gen > 0 else \"NO (fresh)\"}')\n"
        "    except (pickle.UnpicklingError, EOFError, AttributeError, ModuleNotFoundError) as e:\n"
        "        print(f'PICKLE CORRUPT: {type(e).__name__}: {e}')\n"
        "        sys.exit(1)\n"
        "else:\n"
        "    print(f'Unknown mode: {mode}. Use json or pickle.')\n"
        "    sys.exit(1)\n"
    )
    cmd = ["python", "-c", script, file_path, mode]
    return run_shell_cmd(cmd, timeout=30, cwd=cwd)


# ---------------------------------------------------------------------------
# MCP tool server builder
# ---------------------------------------------------------------------------

def build_python_mcp_server():
    """Create an in-process MCP server with Python development tools.

    Requires the optional ``claude_agent_sdk`` package.  If not installed,
    raises ``ImportError`` with installation instructions.
    """
    try:
        from claude_agent_sdk import tool, create_sdk_mcp_server
    except ModuleNotFoundError:
        raise ImportError(
            "claude_agent_sdk is required for the MCP server but is not "
            "installed.  Install it with:  pip install claude-agent-sdk"
        ) from None

    # ── Static analysis ────────────────────────────────────────────────

    @tool(
        "run_ruff",
        "Run ruff linter on a Python file or directory.  Pass fix=true to auto-fix.",
        {"target": str, "fix": bool},
    )
    async def run_ruff(args):
        target = args["target"]
        fix = args.get("fix", False)
        cmd = ["python", "-m", "ruff", "check", target, "--output-format=text"]
        if fix:
            cmd.append("--fix")
        result = run_shell_cmd(cmd, timeout=60)
        return _format_result("ruff check", result)

    @tool(
        "run_ruff_format",
        "Check formatting compliance.  Pass fix=true to apply formatting.",
        {"target": str, "fix": bool},
    )
    async def run_ruff_format(args):
        target = args["target"]
        fix = args.get("fix", False)
        cmd = ["python", "-m", "ruff", "format", target]
        if not fix:
            cmd.extend(["--check", "--diff"])
        result = run_shell_cmd(cmd, timeout=60)
        return _format_result("ruff format", result)

    # ── Testing ────────────────────────────────────────────────────────

    @tool(
        "run_pytest",
        "Execute pytest.  Default flags: -v --tb=short.  Override with flags param.",
        {"target": str, "flags": str},
    )
    async def run_pytest(args):
        target = args.get("target", "tests/")
        flags = args.get("flags", "-v --tb=short")
        cmd = ["python", "-m", "pytest"] + flags.split() + [target]
        result = run_shell_cmd(cmd, timeout=300)
        return _format_result("pytest", result)

    # ── Syntax and type checking ───────────────────────────────────────

    @tool(
        "python_syntax_check",
        "Check if a .py file compiles without syntax errors (py_compile).",
        {"file_path": str},
    )
    async def python_syntax_check(args):
        file_path = args["file_path"]
        cmd = ["python", "-m", "py_compile", file_path]
        result = run_shell_cmd(cmd, timeout=30)
        if result["returncode"] == "0":
            result["stdout"] = f"SYNTAX OK: {file_path}"
        return _format_result("py_compile", result)

    @tool(
        "run_mypy",
        "Run mypy type checker.  Catches signature mismatches after refactoring.",
        {"target": str, "flags": str},
    )
    async def run_mypy(args):
        target = args.get("target", ".")
        flags = args.get("flags", "--ignore-missing-imports")
        cmd = ["python", "-m", "mypy"] + flags.split() + [target]
        result = run_shell_cmd(cmd, timeout=120)
        return _format_result("mypy", result)

    # ── Data inspection (safe path handling via sys.argv) ──────────────

    @tool(
        "inspect_csv",
        "Read a CSV and return schema, shape, dtypes, nulls, and sample rows.",
        {"file_path": str, "sample_rows": int},
    )
    async def inspect_csv(args):
        file_path = args["file_path"]
        n = args.get("sample_rows", 5)
        script = (
            "import pandas as pd, sys\n"
            "fp, n = sys.argv[1], int(sys.argv[2])\n"
            "df = pd.read_csv(fp)\n"
            "print(f'Shape: {df.shape[0]} rows x {df.shape[1]} columns')\n"
            "print(f'\\nColumns and dtypes:')\n"
            "for col in df.columns:\n"
            "    nulls = df[col].isna().sum()\n"
            "    print(f'  {col:30s} {str(df[col].dtype):12s} nulls={nulls}')\n"
            "print(f'\\nFirst {min(n, len(df))} rows:')\n"
            "print(df.head(n).to_string(index=False))\n"
            "print(f'\\nNumeric summary:')\n"
            "print(df.describe().to_string())\n"
        )
        cmd = ["python", "-c", script, file_path, str(n)]
        result = run_shell_cmd(cmd, timeout=30)
        return _format_result("inspect_csv", result)

    @tool(
        "inspect_yaml",
        "Read a YAML file and return its parsed structure.",
        {"file_path": str},
    )
    async def inspect_yaml(args):
        file_path = args["file_path"]
        script = (
            "import yaml, json, sys\n"
            "with open(sys.argv[1]) as f:\n"
            "    data = yaml.safe_load(f)\n"
            "print(json.dumps(data, indent=2, default=str))\n"
        )
        cmd = ["python", "-c", script, file_path]
        result = run_shell_cmd(cmd, timeout=15)
        return _format_result("inspect_yaml", result)

    # ── Codebase auditing ──────────────────────────────────────────────

    @tool(
        "grep_codebase",
        (
            "Search for a regex pattern across all .py files.  Use for "
            "dead-code audits and string constant verification."
        ),
        {"pattern": str, "directory": str},
    )
    async def grep_codebase(args):
        pattern = args["pattern"]
        directory = args.get("directory", ".")
        cmd = [
            "grep", "-rn", "--include=*.py",
            "--exclude-dir=__pycache__",
            "--exclude-dir=.git",
            "--exclude-dir=node_modules",
            "--exclude-dir=.mypy_cache",
            pattern, directory,
        ]
        result = run_shell_cmd(cmd, timeout=30)
        if result["returncode"] == "1" and not result["stderr"]:
            result["stdout"] = f"No matches found for pattern: {pattern}"
            result["returncode"] = "0"
        return _format_result("grep", result)

    # ── Script execution ───────────────────────────────────────────────

    @tool(
        "run_python_script",
        "Execute a Python script or inline command.  Set inline=true for -c mode.",
        {"script_path": str, "inline": bool, "timeout": int},
    )
    async def run_python_script(args):
        script_path = args["script_path"]
        inline = args.get("inline", False)
        timeout = args.get("timeout", 120)
        if inline:
            cmd = ["python", "-c", script_path]
        else:
            cmd = ["python", script_path]
        result = run_shell_cmd(cmd, timeout=timeout)
        return _format_result("python", result)

    # ── Import verification ────────────────────────────────────────────

    @tool(
        "check_imports",
        (
            "Verify a Python module imports without errors.  Catches "
            "missing deps, circular imports, references to deleted modules."
        ),
        {"module_name": str},
    )
    async def check_imports(args):
        module_name = args["module_name"]
        script = (
            "import sys\n"
            f"import {module_name}\n"
            f"attrs = [a for a in dir({module_name}) if not a.startswith('_')]\n"
            f"print(f'OK: {module_name} imported successfully')\n"
            f"print(f'Public attributes ({{len(attrs)}}): {{attrs}}')\n"
        )
        cmd = ["python", "-c", script]
        result = run_shell_cmd(cmd, timeout=30)
        return _format_result("import check", result)

    # ── Simulation output validation (F05 + Gap 14) ────────────────────

    @tool(
        "validate_simulation_output",
        (
            "Check optimizer output files for plausibility AND verify "
            "checkpoint cleanup.  Reads nsga2_results.csv, "
            "Optimal_Action_Plan.csv, checks for stale checkpoint pickle. "
            "Returns structured PASS/FAIL report."
        ),
        {"output_dir": str, "budget_min": float, "budget_max": float,
         "trigger_min": float, "trigger_max": float,
         "checkpoint_pkl_path": str},
    )
    async def validate_simulation_output_handler(args):
        result = validate_simulation_output(
            output_dir=args.get("output_dir", "Optimization_Results_NSGA2"),
            budget_min=args.get("budget_min", 10000.0),
            budget_max=args.get("budget_max", 2000000.0),
            trigger_min=args.get("trigger_min", 1.0),
            trigger_max=args.get("trigger_max", 3.5),
            checkpoint_pkl_path=args.get("checkpoint_pkl_path", "nsga2_checkpoint.pkl"),
        )
        return _format_result("validate_simulation_output", result)

    # ── Checkpoint inspection (Gap 15) ─────────────────────────────────

    @tool(
        "inspect_checkpoint",
        (
            "Inspect checkpoint state files for the preemption resume test "
            "in S08.  Can inspect two file types:\n"
            "  mode='json' — reads checkpoint.json and reports sprint/phase "
            "completion status, preemption count, elapsed time.\n"
            "  mode='pickle' — loads nsga2_checkpoint.pkl and reports the "
            "algorithm generation number, population size, and whether the "
            "pickle is loadable without corruption.\n"
            "Use during S08 INTEGRATE phase to verify preemption resume."
        ),
        {"file_path": str, "mode": str},
    )
    async def inspect_checkpoint_handler(args):
        result = inspect_checkpoint(
            file_path=args["file_path"],
            mode=args.get("mode", "auto"),
        )
        return _format_result("inspect_checkpoint", result)

    # ── Helper ─────────────────────────────────────────────────────────

    def _format_result(tool_label: str, result: dict[str, str]) -> dict:
        """Format subprocess result into MCP tool response."""
        parts = []
        if result["stdout"]:
            parts.append(f"STDOUT:\n{result['stdout']}")
        if result["stderr"]:
            parts.append(f"STDERR:\n{result['stderr']}")
        parts.append(f"Return code: {result['returncode']}")
        return {
            "content": [
                {"type": "text", "text": f"[{tool_label}] " + "\n".join(parts)}
            ]
        }

    # ── Build and return server ────────────────────────────────────────

    server = create_sdk_mcp_server(
        name="python-dev-tools",
        tools=[
            run_ruff,
            run_ruff_format,
            run_pytest,
            python_syntax_check,
            run_mypy,
            inspect_csv,
            inspect_yaml,
            grep_codebase,
            run_python_script,
            check_imports,
            validate_simulation_output_handler,
            inspect_checkpoint_handler,
        ],
    )
    return server
