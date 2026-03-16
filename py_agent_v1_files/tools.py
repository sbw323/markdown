"""
config/tools.py
Python subprocess helpers and in-process MCP tool server for the Claude
development agent.

AUDIT FIXES APPLIED:
    F05 — Added validate_simulation_output tool for numerical plausibility
    F09 — inspect_csv and inspect_yaml pass file paths via sys.argv to
           prevent path injection from special characters

TOOLS PROVIDED:
    run_ruff              — Lint with ruff
    run_ruff_format       — Formatting check with ruff format
    run_pytest            — Execute pytest
    python_syntax_check   — Verify .py compiles (py_compile)
    run_mypy              — Static type checking
    inspect_csv           — CSV schema, shape, sample (safe path handling)
    inspect_yaml          — YAML structure (safe path handling)
    grep_codebase         — Regex search across .py files
    run_python_script     — Execute arbitrary Python
    check_imports         — Verify module imports cleanly
    validate_simulation_output — Domain-specific numerical plausibility checks
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
# MCP tool server builder
# ---------------------------------------------------------------------------

def build_python_mcp_server():
    """Create an in-process MCP server with Python development tools."""
    from claude_agent_sdk import tool, create_sdk_mcp_server

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

    # ── Data inspection (Fix F09: safe path handling) ──────────────────

    @tool(
        "inspect_csv",
        "Read a CSV and return schema, shape, dtypes, nulls, and sample rows.",
        {"file_path": str, "sample_rows": int},
    )
    async def inspect_csv(args):
        file_path = args["file_path"]
        n = args.get("sample_rows", 5)
        # Fix F09: pass file_path and sample_rows via sys.argv to avoid
        # path injection from quotes/spaces in filenames.
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
        # Fix F09: pass file_path via sys.argv
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
            "dead-code audits (sewer terms) and string constant verification."
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

    # ── Simulation output validation (Fix F05) ─────────────────────────

    @tool(
        "validate_simulation_output",
        (
            "Check that optimizer output files are physically and "
            "economically plausible.  Reads nsga2_results.csv and "
            "Optimal_Action_Plan.csv from a directory and validates: "
            "costs >= 0, no NaN/Inf, Total = Investment + Risk, budgets "
            "within gene bounds, action types in allowed set, conditions "
            "in [1,6].  Returns structured PASS/FAIL report."
        ),
        {"output_dir": str, "budget_min": float, "budget_max": float,
         "trigger_min": float, "trigger_max": float},
    )
    async def validate_simulation_output(args):
        output_dir = args.get("output_dir", "Optimization_Results_NSGA2")
        budget_min = args.get("budget_min", 10000.0)
        budget_max = args.get("budget_max", 2000000.0)
        trigger_min = args.get("trigger_min", 1.0)
        trigger_max = args.get("trigger_max", 3.5)
        # Fix F05: self-contained validation script with domain-specific
        # plausibility checks.  Encodes the physics/economic invariants
        # from the VERIFY prompt into an automated, single-call tool.
        script = (
            "import pandas as pd, sys, os, math\n"
            "output_dir = sys.argv[1]\n"
            "budget_min, budget_max = float(sys.argv[2]), float(sys.argv[3])\n"
            "trigger_min, trigger_max = float(sys.argv[4]), float(sys.argv[5])\n"
            "fails = []\n"
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
            "                fails.append(f'WARN: Budget values outside [{budget_min}, {budget_max}] bounds')\n"
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
            "            allowed = {'CIP_Replacement', 'Emergency_Replacement'}\n"
            "            bad = set(ap['Action'].unique()) - allowed\n"
            "            if bad:\n"
            "                fails.append(f'FAIL: Unknown action types: {bad}')\n"
            "            cip_n = (ap['Action'] == 'CIP_Replacement').sum()\n"
            "            emg_n = (ap['Action'] == 'Emergency_Replacement').sum()\n"
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
            "        fails.append(f'WARN: {fname} is suspiciously small ({os.path.getsize(fpath)} bytes)')\n"
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
        ]
        result = run_shell_cmd(cmd, timeout=60)
        return _format_result("validate_simulation_output", result)

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
            validate_simulation_output,
        ],
    )
    return server
