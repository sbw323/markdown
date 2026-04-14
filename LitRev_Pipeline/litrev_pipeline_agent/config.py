"""Configuration for the LLM-Assisted Literature Review agent framework.

All paths, API keys, model identifiers, feature flags, and tuning parameters
are defined here. No other framework module may contain hardcoded values for
any of these settings. Environment variables override defaults for sensitive
or environment-specific values.
"""

import os
from pathlib import Path


# ---------------------------------------------------------------------------
# Workspace paths — all derived from WORKSPACE_ROOT
# ---------------------------------------------------------------------------

WORKSPACE_ROOT: str = os.environ.get(
    "WORKSPACE_ROOT",
    str(Path(__file__).resolve().parent / "workspace" / "lit_review_pipeline"),
)

PDF_DIR: str = os.path.join(WORKSPACE_ROOT, "data", "pdfs")
PARSED_DIR: str = os.path.join(WORKSPACE_ROOT, "data", "parsed")
SUMMARIES_DIR: str = os.path.join(WORKSPACE_ROOT, "data", "summaries")
VECTORSTORE_DIR: str = os.path.join(WORKSPACE_ROOT, "vectorstore")

# ---------------------------------------------------------------------------
# API keys and service endpoints
# ---------------------------------------------------------------------------

ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
GROBID_URL: str = os.environ.get("GROBID_URL", "http://localhost:8070")

# ---------------------------------------------------------------------------
# Model selection
# ---------------------------------------------------------------------------

AGENT_MODEL: str = os.environ.get("AGENT_MODEL", "claude-sonnet-4-20250514")
PIPELINE_MODEL: str = os.environ.get("PIPELINE_MODEL", "claude-sonnet-4-20250514")
EMBEDDING_MODEL: str = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-large-en-v1.5")

# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------

EQUATION_BACKEND: str = os.environ.get("EQUATION_BACKEND", "claude_vision")
ENABLE_RERANKING: bool = os.environ.get("ENABLE_RERANKING", "true").lower() == "true"

# ---------------------------------------------------------------------------
# Chunking parameters
# ---------------------------------------------------------------------------

MAX_CHUNK_TOKENS: int = int(os.environ.get("MAX_CHUNK_TOKENS", "1500"))
MIN_CHUNK_TOKENS: int = int(os.environ.get("MIN_CHUNK_TOKENS", "500"))

# ---------------------------------------------------------------------------
# Agent runtime parameters
# ---------------------------------------------------------------------------

RETRY_BUDGET: int = int(os.environ.get("RETRY_BUDGET", "3"))
SHELL_TIMEOUT: int = int(os.environ.get("SHELL_TIMEOUT", "120"))
SCRIPT_TIMEOUT: int = int(os.environ.get("SCRIPT_TIMEOUT", "300"))
CONTEXT_WINDOW_LIMIT: int = int(os.environ.get("CONTEXT_WINDOW_LIMIT", "200000"))
RESPONSE_HEADROOM_RATIO: float = float(os.environ.get("RESPONSE_HEADROOM_RATIO", "0.3"))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_FILE: str = os.path.join(WORKSPACE_ROOT, "agent_log.jsonl")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_config() -> None:
    """Validate critical configuration values at startup.

    Raises:
        ValueError: If ANTHROPIC_API_KEY is empty or if EQUATION_BACKEND
            is not one of the recognised options.
    """
    if not ANTHROPIC_API_KEY:
        raise ValueError(
            "ANTHROPIC_API_KEY is empty — set the ANTHROPIC_API_KEY environment "
            "variable before running the agent."
        )

    valid_equation_backends = ("nougat", "claude_vision", "both", "none")
    if EQUATION_BACKEND not in valid_equation_backends:
        raise ValueError(
            f"EQUATION_BACKEND is '{EQUATION_BACKEND}' but must be one of "
            f"{valid_equation_backends}. Set via environment variable or edit config.py."
        )

    if RESPONSE_HEADROOM_RATIO <= 0.0 or RESPONSE_HEADROOM_RATIO >= 1.0:
        raise ValueError(
            f"RESPONSE_HEADROOM_RATIO is {RESPONSE_HEADROOM_RATIO} but must be "
            "between 0.0 and 1.0 exclusive."
        )

    if MIN_CHUNK_TOKENS >= MAX_CHUNK_TOKENS:
        raise ValueError(
            f"MIN_CHUNK_TOKENS ({MIN_CHUNK_TOKENS}) must be less than "
            f"MAX_CHUNK_TOKENS ({MAX_CHUNK_TOKENS})."
        )