"""Configuration constants for the scientific literature review pipeline."""

import os
from pathlib import Path
from typing import Final

# Workspace root - all paths derived from this
WORKSPACE_ROOT: Final[Path] = Path(__file__).parent

# API Configuration
ANTHROPIC_API_KEY: Final[str] = os.getenv("ANTHROPIC_API_KEY", "")
GROBID_URL: Final[str] = os.getenv("GROBID_URL", "http://localhost:8070")

# Model Configuration
AGENT_MODEL: Final[str] = "claude-3-5-sonnet-20241022"
PIPELINE_MODEL: Final[str] = "claude-sonnet-4-20250514"
EMBEDDING_MODEL: Final[str] = "all-MiniLM-L6-v2"
EQUATION_BACKEND: Final[str] = "nougat"  # Options: "nougat", "grobid", "pymupdf"

# Directory Paths
DATA_DIR: Final[Path] = WORKSPACE_ROOT / "data"
PDFS_DIR: Final[Path] = DATA_DIR / "pdfs"
PARSED_DIR: Final[Path] = DATA_DIR / "parsed"
SUMMARIES_DIR: Final[Path] = DATA_DIR / "summaries"
VECTORSTORE_DIR: Final[Path] = WORKSPACE_ROOT / "vectorstore"

# File Paths
SEARCH_RESULTS_PATH: Final[Path] = DATA_DIR / "search_results.json"
FINAL_REVIEW_PATH: Final[Path] = DATA_DIR / "final_review.md"

# Processing Configuration
MAX_CHUNK_SIZE: Final[int] = 4000
CHUNK_OVERLAP: Final[int] = 200
MAX_PAPERS_PER_QUERY: Final[int] = 50
SIMILARITY_THRESHOLD: Final[float] = 0.7