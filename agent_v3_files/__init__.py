"""
config — Sprint definitions, prompts, and tool configuration for the BSM
refactoring orchestrator.
"""

from config.sprints import DEFAULT_MODEL, Sprint, SprintPhase, SPRINTS
from config.prompts import (
    BASE_CONTEXT,
    BSM_DOMAIN_PREAMBLE,
    CODING_STANDARDS,
    PHASE_PROMPTS,
)
from config.tools import build_matlab_mcp_server, run_matlab_cmd

__all__ = [
    "DEFAULT_MODEL",
    "Sprint",
    "SprintPhase",
    "SPRINTS",
    "BASE_CONTEXT",
    "BSM_DOMAIN_PREAMBLE",
    "CODING_STANDARDS",
    "PHASE_PROMPTS",
    "build_matlab_mcp_server",
    "run_matlab_cmd",
]
