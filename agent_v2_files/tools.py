"""
config/tools.py
MATLAB subprocess helper and in-process MCP tool server for the Claude agent.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Low-level MATLAB command runner
# ---------------------------------------------------------------------------

def run_matlab_cmd(
    cmd: str,
    timeout: int = 120,
    cwd: Optional[str | Path] = None,
) -> dict[str, str]:
    """Execute a MATLAB -batch command and return stdout/stderr/returncode.

    Parameters
    ----------
    cmd : str
        MATLAB command string passed to ``matlab -batch``.
    timeout : int
        Maximum seconds to wait before killing the process.
    cwd : str or Path or None
        Working directory for the subprocess.  If None, inherits from the
        calling process (typically the sprint directory set by the orchestrator).
    """
    try:
        result = subprocess.run(
            ["matlab", "-batch", cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": str(result.returncode),
        }
    except FileNotFoundError:
        return {
            "stdout": "",
            "stderr": (
                "ERROR: 'matlab' not found on PATH. "
                "MATLAB is required for verification phases."
            ),
            "returncode": "-1",
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"ERROR: MATLAB command timed out after {timeout}s",
            "returncode": "-2",
        }


# ---------------------------------------------------------------------------
# MCP tool server builder
# ---------------------------------------------------------------------------

def build_matlab_mcp_server():
    """Create an in-process MCP server with MATLAB-specific tools.

    Each tool invokes MATLAB headlessly via ``matlab -batch``.  The agent
    can call these tools to run static analysis, execute tests, check
    syntax, and inspect .mat file contents.

    Note: the ``cwd`` for each tool call defaults to None (inherited from
    the ClaudeSDKClient's ``cwd`` option, which the orchestrator sets to
    the sprint directory).  For commands that need an explicit working
    directory, the agent should ``cd('...')`` inside the MATLAB command.
    """
    from claude_agent_sdk import create_sdk_mcp_server
    from claude_agent_sdk.tools import tool as sdk_tool

    @sdk_tool(
        "run_mlint",
        "Run MATLAB mlint/checkcode static analysis on a .m file and return warnings",
    )
    async def run_mlint(file_path: str) -> str:
        cmd = (
            f"msgs = checkcode('{file_path}', '-string'); "
            f"if isempty(msgs), disp('CLEAN: No warnings.'); "
            f"else, disp(msgs); end"
        )
        result = run_matlab_cmd(cmd)
        return (
            f"STDOUT:\n{result['stdout']}\n"
            f"STDERR:\n{result['stderr']}\n"
            f"Return code: {result['returncode']}"
        )

    @sdk_tool(
        "run_matlab_tests",
        "Execute MATLAB unit tests in a directory and return results",
    )
    async def run_matlab_tests(test_path: str, source_path: str = "src") -> str:
        cmd = (
            f"addpath('{source_path}'); "
            f"results = runtests('{test_path}'); "
            f"disp(table(results)); "
            f"if any([results.Failed]), exit(1); end"
        )
        result = run_matlab_cmd(cmd, timeout=300)
        return (
            f"STDOUT:\n{result['stdout']}\n"
            f"STDERR:\n{result['stderr']}\n"
            f"Return code: {result['returncode']}"
        )

    @sdk_tool(
        "matlab_syntax_check",
        "Check if a .m file parses without syntax errors",
    )
    async def matlab_syntax_check(file_path: str) -> str:
        cmd = (
            f"try, "
            f"  pcode('{file_path}', '-inplace'); "
            f"  delete(strrep('{file_path}', '.m', '.p')); "
            f"  disp('SYNTAX OK'); "
            f"catch e, "
            f"  fprintf('SYNTAX ERROR: %s\\n', e.message); "
            f"  exit(1); "
            f"end"
        )
        result = run_matlab_cmd(cmd, timeout=60)
        return (
            f"STDOUT:\n{result['stdout']}\n"
            f"STDERR:\n{result['stderr']}\n"
            f"Return code: {result['returncode']}"
        )

    @sdk_tool(
        "read_mat_summary",
        "Read a .mat file and return variable names, sizes, and types",
    )
    async def read_mat_summary(mat_path: str) -> str:
        cmd = (
            f"s = whos('-file', '{mat_path}'); "
            f"for i = 1:numel(s), "
            f"  fprintf('%s: size=%s class=%s\\n', "
            f"    s(i).name, mat2str(s(i).size), s(i).class); "
            f"end"
        )
        result = run_matlab_cmd(cmd, timeout=60)
        return f"STDOUT:\n{result['stdout']}\nSTDERR:\n{result['stderr']}"

    server = create_sdk_mcp_server(
        name="matlab-tools",
        tools=[run_mlint, run_matlab_tests, matlab_syntax_check, read_mat_summary],
    )
    return server
