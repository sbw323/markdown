"""Tool functions for the LLM-Assisted Literature Review agent framework.

Every concrete action the agent can take on the filesystem and runtime
environment is defined here. Functions that interact with the OS return a
standardised dict: ``{"success": bool, "output": str, "error": str | None}``.
Pure-data helpers (``parse_file_tags``, ``estimate_tokens``) have their own
return types documented in their signatures.
"""

import ast as _ast_module  # underscore alias to avoid shadowing with local names
import logging
import os
import py_compile
import re
import subprocess
import sys
import textwrap
import time
import urllib.request
import urllib.error

import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. write_file
# ---------------------------------------------------------------------------

def write_file(path: str, content: str) -> dict:
    """Write *content* to *path*, creating parent directories as needed.

    Rejects paths that would escape ``config.WORKSPACE_ROOT`` via ``..``
    traversal.  Overwrites existing files (idempotent).

    Args:
        path: Target file path (relative or absolute).
        content: Text content to write.

    Returns:
        Standard result dict with ``success``, ``output``, ``error`` keys.

    Side-effects:
        Creates or overwrites the file at *path* and any missing parent
        directories.
    """
    resolved = os.path.realpath(path)
    workspace_resolved = os.path.realpath(config.WORKSPACE_ROOT)
    if not resolved.startswith(workspace_resolved + os.sep) and resolved != workspace_resolved:
        return {
            "success": False,
            "output": "",
            "error": (
                f"Path '{path}' resolves to '{resolved}' which is outside "
                f"WORKSPACE_ROOT '{workspace_resolved}'. Write rejected for safety."
            ),
        }
    try:
        os.makedirs(os.path.dirname(resolved), exist_ok=True)
        with open(resolved, "w", encoding="utf-8") as fh:
            fh.write(content)
        logger.debug("Wrote %d chars to %s", len(content), resolved)
        return {"success": True, "output": resolved, "error": None}
    except OSError as exc:
        return {"success": False, "output": "", "error": str(exc)}


# ---------------------------------------------------------------------------
# 2. read_file
# ---------------------------------------------------------------------------

def read_file(path: str) -> dict:
    """Read and return the text contents of *path*.

    Args:
        path: File to read.

    Returns:
        Standard result dict.  ``output`` contains the file text on success.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        return {"success": True, "output": text, "error": None}
    except OSError as exc:
        return {
            "success": False,
            "output": "",
            "error": f"Cannot read '{path}': {exc}",
        }


# ---------------------------------------------------------------------------
# 3. list_directory
# ---------------------------------------------------------------------------

def list_directory(path: str) -> dict:
    """Return a recursive directory listing (up to 2 levels deep).

    Args:
        path: Root directory to list.

    Returns:
        Standard result dict.  ``output`` contains the tree as a newline-
        separated string.
    """
    if not os.path.isdir(path):
        return {
            "success": False,
            "output": "",
            "error": f"'{path}' is not a directory or does not exist.",
        }
    lines: list[str] = []
    try:
        for root, dirs, files in os.walk(path):
            depth = root.replace(path, "").count(os.sep)
            if depth >= 2:
                dirs.clear()
                continue
            indent = "  " * depth
            lines.append(f"{indent}{os.path.basename(root)}/")
            sub_indent = "  " * (depth + 1)
            for fname in sorted(files):
                lines.append(f"{sub_indent}{fname}")
            dirs[:] = sorted(dirs)
        return {"success": True, "output": "\n".join(lines), "error": None}
    except OSError as exc:
        return {"success": False, "output": "", "error": str(exc)}


# ---------------------------------------------------------------------------
# 4. run_shell
# ---------------------------------------------------------------------------

def run_shell(command: str, timeout: int = config.SHELL_TIMEOUT) -> dict:
    """Execute a shell command and capture its output.

    Args:
        command: Shell command string.
        timeout: Maximum seconds to wait (defaults to
            ``config.SHELL_TIMEOUT``).

    Returns:
        Standard result dict.  ``output`` contains combined stdout + stderr.
    """
    logger.info("run_shell: %s (timeout=%ds)", command, timeout)
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        combined = result.stdout + result.stderr
        logger.debug(
            "run_shell exit=%d stdout[:500]=%s",
            result.returncode,
            combined[:500],
        )
        return {
            "success": result.returncode == 0,
            "output": combined,
            "error": combined if result.returncode != 0 else None,
        }
    except subprocess.TimeoutExpired:
        msg = f"Command timed out after {timeout}s: {command}"
        logger.warning(msg)
        return {"success": False, "output": "", "error": msg}
    except OSError as exc:
        return {"success": False, "output": "", "error": str(exc)}


# ---------------------------------------------------------------------------
# 5. validate_python_syntax
# ---------------------------------------------------------------------------

def validate_python_syntax(path: str) -> dict:
    """Check whether *path* is syntactically valid Python.

    This function **does not** modify the file.

    Args:
        path: Path to a ``.py`` file.

    Returns:
        Standard result dict.
    """
    try:
        py_compile.compile(path, doraise=True)
        return {
            "success": True,
            "output": f"{path} has valid Python syntax.",
            "error": None,
        }
    except py_compile.PyCompileError as exc:
        return {
            "success": False,
            "output": "",
            "error": f"Syntax error in '{path}': {exc}",
        }


# ---------------------------------------------------------------------------
# 6. validate_file_structure
# ---------------------------------------------------------------------------

def validate_file_structure(expected_paths: list[str]) -> dict:
    """Verify that every path in *expected_paths* exists on disk.

    This function **does not** create or modify any files.

    Args:
        expected_paths: List of file or directory paths to check.

    Returns:
        Standard result dict.  ``output`` lists missing paths if any.
    """
    missing = [p for p in expected_paths if not os.path.exists(p)]
    if missing:
        msg = "Missing paths:\n" + "\n".join(f"  - {p}" for p in missing)
        return {"success": False, "output": msg, "error": msg}
    return {
        "success": True,
        "output": f"All {len(expected_paths)} expected paths exist.",
        "error": None,
    }


# ---------------------------------------------------------------------------
# 7. run_python_script
# ---------------------------------------------------------------------------

def run_python_script(path: str, timeout: int = config.SCRIPT_TIMEOUT) -> dict:
    """Execute a Python script as a subprocess.

    Args:
        path: Path to the ``.py`` script.
        timeout: Maximum seconds (defaults to ``config.SCRIPT_TIMEOUT``).

    Returns:
        Standard result dict with stdout/stderr in ``output``.
    """
    return run_shell(f"{sys.executable} {path}", timeout=timeout)


# ---------------------------------------------------------------------------
# 8. parse_file_tags
# ---------------------------------------------------------------------------

_FILE_TAG_RE = re.compile(
    r'<file\s+path\s*=\s*"([^"]+)"\s*>(.*?)</file>',
    re.DOTALL,
)


def parse_file_tags(llm_response: str) -> list[tuple[str, str]]:
    """Extract ``<file path="...">...</file>`` blocks from an LLM response.

    Handles bare tags, tags wrapped in markdown code fences, multiple files
    in one response, and extra whitespace around tags.

    Args:
        llm_response: Raw text from the LLM.

    Returns:
        List of ``(path, content)`` tuples, one per file block found.
    """
    # Strip markdown code fences that may wrap the entire response
    cleaned = llm_response
    cleaned = re.sub(r"```[a-zA-Z]*\n?", "", cleaned)
    cleaned = re.sub(r"```", "", cleaned)
    matches = _FILE_TAG_RE.findall(cleaned)
    results: list[tuple[str, str]] = []
    for path, content in matches:
        # Strip one leading and one trailing newline that the LLM often adds
        # immediately inside the tags
        content = content.strip("\n")
        results.append((path.strip(), content))
    return results


# ---------------------------------------------------------------------------
# 9. install_dependencies
# ---------------------------------------------------------------------------

def install_dependencies(requirements_path: str) -> dict:
    """Install Python packages from a requirements file.

    Idempotent — already-installed packages are skipped by pip.

    Args:
        requirements_path: Path to ``requirements.txt``.

    Returns:
        Standard result dict.
    """
    if not os.path.isfile(requirements_path):
        return {
            "success": False,
            "output": "",
            "error": (
                f"Requirements file not found at '{requirements_path}'. "
                "Ensure the scaffold sprint produced it."
            ),
        }
    return run_shell(
        f"{sys.executable} -m pip install -r {requirements_path}",
        timeout=600,
    )


# ---------------------------------------------------------------------------
# 10. start_grobid
# ---------------------------------------------------------------------------

def start_grobid() -> dict:
    """Start GROBID via Docker if not already running, then wait for readiness.

    Checks the health endpoint at ``config.GROBID_URL`` before attempting
    to launch a new container.  Idempotent.

    Returns:
        Standard result dict.
    """
    health_url = config.GROBID_URL.rstrip("/") + "/api/isalive"

    # --- Check if already running ------------------------------------------
    if _grobid_is_alive(health_url):
        return {
            "success": True,
            "output": f"GROBID already running at {config.GROBID_URL}",
            "error": None,
        }

    # --- Start container ---------------------------------------------------
    port = config.GROBID_URL.split(":")[-1].split("/")[0]
    start_result = run_shell(
        f"docker run -d -p {port}:{port} lfoppiano/grobid:0.8.1",
        timeout=config.SHELL_TIMEOUT,
    )
    if not start_result["success"]:
        return {
            "success": False,
            "output": start_result["output"],
            "error": (
                f"Failed to start GROBID Docker container: "
                f"{start_result['error']}"
            ),
        }

    # --- Wait for readiness ------------------------------------------------
    deadline = time.time() + 60
    while time.time() < deadline:
        if _grobid_is_alive(health_url):
            return {
                "success": True,
                "output": f"GROBID started and healthy at {config.GROBID_URL}",
                "error": None,
            }
        time.sleep(2)

    return {
        "success": False,
        "output": "",
        "error": (
            f"GROBID container started but health check at '{health_url}' "
            "did not respond within 60 seconds."
        ),
    }


def _grobid_is_alive(health_url: str) -> bool:
    """Return True if GROBID's health endpoint responds with HTTP 200."""
    try:
        req = urllib.request.urlopen(health_url, timeout=5)
        return req.status == 200
    except (urllib.error.URLError, OSError):
        return False


# ---------------------------------------------------------------------------
# 11. extract_skeleton
# ---------------------------------------------------------------------------

def extract_skeleton(path: str) -> dict:
    """Extract a Python file's API skeleton: imports, signatures, docstrings.

    Uses the ``ast`` module to parse *path* and emit only module-level
    docstrings, imports, constants, class definitions (with docstrings),
    and function/method signatures (with docstrings).  All function bodies
    are replaced with ``...``.

    The result is a valid Python file that communicates the module's public
    API without consuming the full token budget.

    Args:
        path: Path to a ``.py`` file.

    Returns:
        Standard result dict.  ``output`` contains the skeleton source text.
    """
    read_result = read_file(path)
    if not read_result["success"]:
        return read_result

    source = read_result["output"]
    try:
        tree = _ast_module.parse(source)
    except SyntaxError as exc:
        return {
            "success": False,
            "output": "",
            "error": f"Cannot parse '{path}' for skeleton extraction: {exc}",
        }

    lines: list[str] = []

    for node in tree.body:
        if isinstance(node, _ast_module.Expr) and isinstance(
            node.value, _ast_module.Constant
        ):
            # Module-level docstring or standalone string expression
            lines.append(f'"""{node.value.value}"""')
            lines.append("")

        elif isinstance(node, (_ast_module.Import, _ast_module.ImportFrom)):
            lines.append(_ast_module.get_source_segment(source, node) or "")

        elif isinstance(node, (_ast_module.Assign, _ast_module.AnnAssign)):
            lines.append(_ast_module.get_source_segment(source, node) or "")

        elif isinstance(node, _ast_module.FunctionDef):
            lines.append(_format_function_skeleton(source, node, indent=0))

        elif isinstance(node, _ast_module.ClassDef):
            lines.append(_format_class_skeleton(source, node))

    return {"success": True, "output": "\n".join(lines), "error": None}


def _format_function_skeleton(source: str, node: _ast_module.FunctionDef, indent: int = 0) -> str:
    """Return the signature + docstring + ellipsis for a FunctionDef node."""
    prefix = "    " * indent
    # Build signature line from source up to the colon
    sig_segment = _ast_module.get_source_segment(source, node)
    if sig_segment:
        # Take only up to the first colon that ends the signature
        sig_line = sig_segment.split("\n")[0]
        # Ensure we capture multi-line signatures
        if ":" not in sig_line:
            sig_lines_all = sig_segment.split("\n")
            sig_parts = []
            for sl in sig_lines_all:
                sig_parts.append(sl)
                if sl.rstrip().endswith(":"):
                    break
            sig_line = "\n".join(sig_parts)
        else:
            sig_line = sig_line
    else:
        sig_line = f"{prefix}def {node.name}(...):"

    result_lines = [sig_line if indent == 0 else textwrap.indent(sig_line, prefix)]

    # Extract docstring if present
    docstring = _ast_module.get_docstring(node)
    if docstring:
        body_prefix = prefix + "    "
        result_lines.append(f'{body_prefix}"""{docstring}"""')

    result_lines.append(f"{prefix}    ...")
    result_lines.append("")
    return "\n".join(result_lines)


def _format_class_skeleton(source: str, node: _ast_module.ClassDef) -> str:
    """Return the class definition with method skeletons."""
    seg = _ast_module.get_source_segment(source, node)
    first_line = seg.split("\n")[0] if seg else f"class {node.name}:"
    lines = [first_line]

    docstring = _ast_module.get_docstring(node)
    if docstring:
        lines.append(f'    """{docstring}"""')

    for item in node.body:
        if isinstance(item, _ast_module.FunctionDef):
            lines.append(_format_function_skeleton(source, item, indent=1))

    if len(lines) == 1 and not docstring:
        lines.append("    ...")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 12. estimate_tokens
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Estimate the token count of *text* using a word-split heuristic.

    Uses the approximation that 1 token ≈ 0.75 words (i.e., ~4 characters
    per token).  This is intentionally conservative (over-counts) so the
    orchestrator's context-window budget errs on the safe side.

    Args:
        text: Input text.

    Returns:
        Estimated token count as an integer.
    """
    # Character-based estimate: ~4 chars per token on average for English
    return max(1, len(text) // 4)