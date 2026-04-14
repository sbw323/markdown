"""Sprint definitions for the LLM-Assisted Literature Review agent framework.

Each sprint is a dictionary containing the goal, file targets, acceptance
criteria, validation tool, and dependency information the orchestrator needs
to execute it.  Sprints are processed sequentially in list order — the order
is a valid topological sort of the dependency graph.
"""

sprints: list[dict] = [
    # ------------------------------------------------------------------
    # S0: Project Scaffolding
    # ------------------------------------------------------------------
    {
        "id": "S0_scaffold",
        "name": "Project Scaffolding",
        "goal": "Create the full directory structure and requirements.txt",
        "files_to_produce": [
            "workspace/lit_review_pipeline/requirements.txt",
            "workspace/lit_review_pipeline/config.py",
            "workspace/lit_review_pipeline/data/.gitkeep",
            "workspace/lit_review_pipeline/data/pdfs/.gitkeep",
            "workspace/lit_review_pipeline/data/parsed/.gitkeep",
            "workspace/lit_review_pipeline/data/summaries/.gitkeep",
            "workspace/lit_review_pipeline/vectorstore/.gitkeep",
            "workspace/lit_review_pipeline/utils/__init__.py",
        ],
        "acceptance_criteria": [
            "All listed directories and files exist after the sprint completes",
            "requirements.txt contains all dependencies: pymupdf4llm, pymupdf, chromadb, langchain, langchain-anthropic, langchain-community, rank-bm25, sentence-transformers, nougat-ocr, grobid-client-python, pydantic",
            "config.py defines placeholder constants for ANTHROPIC_API_KEY, GROBID_URL, AGENT_MODEL, PIPELINE_MODEL, EMBEDDING_MODEL, EQUATION_BACKEND, and all path constants derived from a WORKSPACE_ROOT variable",
        ],
        "validation_tool": "validate_file_structure",
        "depends_on": [],
    },
    # ------------------------------------------------------------------
    # S1: PDF Intake & Metadata Extraction
    # ------------------------------------------------------------------
    {
        "id": "S1_metadata",
        "name": "PDF Intake & Metadata Extraction",
        "goal": (
            "Build 01_ingest.py and utils/metadata.py — GROBID integration "
            "with Claude vision fallback for metadata extraction"
        ),
        "files_to_produce": [
            "workspace/lit_review_pipeline/01_ingest.py",
            "workspace/lit_review_pipeline/utils/metadata.py",
        ],
        "acceptance_criteria": [
            "01_ingest.py scans data/pdfs/ for all PDF files and processes each through GROBID",
            "utils/metadata.py contains a TEI-XML parser that extracts title, authors, year, journal, doi, and abstract into a dictionary",
            "Fallback path renders the first page as a PNG and sends it to the Claude API for structured metadata extraction when GROBID fails",
            "Outputs data/manifest.json containing one JSON object per paper with keys: filename, title, authors, year, journal, doi, abstract",
            "Script is runnable standalone via python 01_ingest.py with an if __name__ == '__main__' block",
        ],
        "validation_tool": "validate_python_syntax",
        "context_files": [
            "workspace/lit_review_pipeline/config.py",
        ],
        "depends_on": ["S0_scaffold"],
    },
    # ------------------------------------------------------------------
    # S2: Base Text Extraction
    # ------------------------------------------------------------------
    {
        "id": "S2_parse_base",
        "name": "Base Text Extraction with PyMuPDF4LLM",
        "goal": "Build the first pass of 02_parse.py — PyMuPDF4LLM Markdown extraction",
        "files_to_produce": [
            "workspace/lit_review_pipeline/02_parse.py",
        ],
        "acceptance_criteria": [
            "Loads data/manifest.json and iterates over every PDF entry in the manifest",
            "Calls pymupdf4llm.to_markdown() on each PDF file path from the manifest",
            "Saves the raw Markdown output for each paper to data/parsed/{filename_stem}.md using the stem of the original PDF filename",
            "Wraps each PDF extraction in a try/except block, logs errors via the logging module, and continues to the next paper on failure",
        ],
        "validation_tool": "validate_python_syntax",
        "context_files": [
            "workspace/lit_review_pipeline/config.py",
        ],
        "depends_on": ["S1_metadata"],
    },
    # ------------------------------------------------------------------
    # S3: Equation Detection & LaTeX Extraction
    # ------------------------------------------------------------------
    {
        "id": "S3_equation_handler",
        "name": "Equation Detection & LaTeX Extraction",
        "goal": (
            "Build utils/equation_handler.py — equation density detection, "
            "Nougat integration, Claude vision fallback, and merge logic"
        ),
        "files_to_produce": [
            "workspace/lit_review_pipeline/utils/equation_handler.py",
        ],
        "acceptance_criteria": [
            "Defines an equation_density_score() function that scores each page based on garbled-text ratio, partial LaTeX fragment count, and text-to-whitespace gap ratio",
            "Defines a nougat_extract() function that runs Nougat on flagged pages and returns Markdown with LaTeX math blocks",
            "Defines a claude_vision_extract() function that renders a page as 300 DPI PNG via PyMuPDF and sends it to the Claude API with a prompt requesting LaTeX equation extraction",
            "Defines merge_extractions() that takes PyMuPDF4LLM base Markdown and equation-source Markdown and produces a single merged Markdown output per paper",
            "All LaTeX content is wrapped in consistent $...$ (inline) or $$...$$ (display) delimiters with an [EQUATION] tag prefix",
            "Reads config.EQUATION_BACKEND to select the active backend: 'nougat', 'claude_vision', 'both', or 'none'",
        ],
        "validation_tool": "validate_python_syntax",
        "context_files": [
            "workspace/lit_review_pipeline/02_parse.py",
            "workspace/lit_review_pipeline/config.py",
        ],
        "depends_on": ["S2_parse_base"],
    },
    # ------------------------------------------------------------------
    # S4: Integrate Equation Handler into Parse Pipeline
    # ------------------------------------------------------------------
    {
        "id": "S4_parse_integration",
        "name": "Integrate Equation Handler into Parse Pipeline",
        "goal": (
            "Update 02_parse.py to call equation_handler and produce final "
            "merged Markdown per paper"
        ),
        "files_to_produce": [
            "workspace/lit_review_pipeline/02_parse.py",
        ],
        "acceptance_criteria": [
            "02_parse.py runs Pass 1 (pymupdf4llm.to_markdown) then Pass 2 (utils.equation_handler) sequentially for each PDF",
            "Outputs data/parsed/{filename_stem}_merged.md as the authoritative parsed output for each paper",
            "Logs which pages were flagged as equation-heavy and which equation backend was used for each paper",
            "Skips Pass 2 entirely and copies the Pass 1 output as the merged file when config.EQUATION_BACKEND is set to 'none'",
        ],
        "validation_tool": "validate_python_syntax",
        "context_files": [
            "workspace/lit_review_pipeline/02_parse.py",
            "workspace/lit_review_pipeline/utils/equation_handler.py",
            "workspace/lit_review_pipeline/config.py",
        ],
        "depends_on": ["S2_parse_base", "S3_equation_handler"],
    },
    # ------------------------------------------------------------------
    # S5: Figure Extraction & Caption Association
    # ------------------------------------------------------------------
    {
        "id": "S5_figures",
        "name": "Figure Extraction & Caption Association",
        "goal": (
            "Build utils/figure_handler.py — extract images, match to "
            "captions, save alongside parsed output"
        ),
        "files_to_produce": [
            "workspace/lit_review_pipeline/utils/figure_handler.py",
        ],
        "acceptance_criteria": [
            "Defines an extract_figures() function that extracts embedded images from a PDF via PyMuPDF page.get_images() and fitz.Pixmap",
            "Saves each extracted image as a PNG file to the data/parsed/{filename_stem}_figures/ directory, creating it if needed",
            "Defines a match_captions() heuristic that finds the nearest text block containing 'Fig.' or 'Figure' to each extracted image by page proximity",
            "Returns a list of dictionaries each containing image_path, caption_text, and page_number keys",
        ],
        "validation_tool": "validate_python_syntax",
        "context_files": [
            "workspace/lit_review_pipeline/config.py",
        ],
        "depends_on": ["S2_parse_base"],
    },
    # ------------------------------------------------------------------
    # S6: Section-Aware Chunking
    # ------------------------------------------------------------------
    {
        "id": "S6_chunking",
        "name": "Section-Aware Chunking",
        "goal": "Build 03_chunk.py with equation-safe, section-aware chunking logic",
        "files_to_produce": [
            "workspace/lit_review_pipeline/03_chunk.py",
        ],
        "acceptance_criteria": [
            "Defines a regex pattern that detects standard scientific paper section headers (Abstract, Introduction, Methods, Results, Discussion, Conclusions, References) and numbered headings like '2.1 Methodology'",
            "Splits merged Markdown at section boundaries and sub-splits sections exceeding config.MAX_CHUNK_TOKENS at paragraph breaks (double newlines)",
            "Never splits inside $$...$$ or $...$ delimited LaTeX equation blocks",
            "Prepends the preceding prose paragraph to any chunk where LaTeX content exceeds 60 percent of the token length",
            "Attaches a metadata dict to each chunk containing: paper_id, title, authors, year, journal, doi, section, chunk_index, has_equations, has_figures, page_numbers",
            "Outputs a per-paper {filename_stem}_chunks.json and an aggregated all_chunks.json in data/parsed/",
            "Token counting uses len(text.split()) as a heuristic with a target range of config.MIN_CHUNK_TOKENS to config.MAX_CHUNK_TOKENS",
        ],
        "validation_tool": "validate_python_syntax",
        "context_files": [
            "workspace/lit_review_pipeline/config.py",
            "workspace/lit_review_pipeline/02_parse.py",
        ],
        "depends_on": ["S4_parse_integration", "S5_figures"],
    },
    # ------------------------------------------------------------------
    # S7: Embedding & Vector Store Indexing
    # ------------------------------------------------------------------
    {
        "id": "S7_indexing",
        "name": "Embedding & Vector Store Indexing",
        "goal": "Build 04_index.py — ChromaDB + BM25 dual index",
        "files_to_produce": [
            "workspace/lit_review_pipeline/04_index.py",
        ],
        "acceptance_criteria": [
            "Loads all_chunks.json from data/parsed/ and validates it is non-empty before proceeding",
            "Creates or recreates a ChromaDB persistent collection named 'lit_review' in the vectorstore/ directory",
            "Embeds each chunk using sentence-transformers with the model name read from config.EMBEDDING_MODEL",
            "For chunks where has_equations is True, strips LaTeX delimiters and equation content before embedding but stores the full original text as the document",
            "Builds a BM25Okapi index over all chunk texts and pickles the index object plus a parallel chunk-ID list to vectorstore/bm25_index.pkl",
            "Is idempotent: deletes and rebuilds the ChromaDB collection and BM25 pickle if they already exist",
        ],
        "validation_tool": "validate_python_syntax",
        "context_files": [
            "workspace/lit_review_pipeline/config.py",
        ],
        "depends_on": ["S6_chunking"],
    },
    # ------------------------------------------------------------------
    # S8: Hybrid Retrieval & Query Pipeline
    # ------------------------------------------------------------------
    {
        "id": "S8_retrieval",
        "name": "Hybrid Retrieval & Query Pipeline",
        "goal": "Build 05_query.py — RRF fusion, optional reranking, Claude LLM call",
        "files_to_produce": [
            "workspace/lit_review_pipeline/05_query.py",
        ],
        "acceptance_criteria": [
            "Accepts a query string via command-line argument and returns an answer with source paper citations",
            "Performs dense retrieval returning the top 15 chunks from the ChromaDB collection",
            "Performs sparse retrieval returning the top 15 chunks from the pickled BM25 index",
            "Fuses results using Reciprocal Rank Fusion with k=60 and selects the top 8 fused candidates",
            "Optionally reranks the top 8 candidates using a cross-encoder model when config.ENABLE_RERANKING is True",
            "Constructs an LLM prompt containing retrieved chunks each prefixed with paper metadata (title, authors, year, section)",
            "Calls the Claude API using config.PIPELINE_MODEL and returns the response text",
            "Runnable standalone via python 05_query.py 'your question here' with an if __name__ == '__main__' block and argparse",
        ],
        "validation_tool": "validate_python_syntax",
        "context_files": [
            "workspace/lit_review_pipeline/config.py",
        ],
        "depends_on": ["S7_indexing"],
    },
    # ------------------------------------------------------------------
    # S9: Map-Reduce Literature Review
    # ------------------------------------------------------------------
    {
        "id": "S9_review",
        "name": "Map-Reduce Literature Review Orchestrator",
        "goal": "Build 06_review.py — per-paper summaries then cross-paper synthesis",
        "files_to_produce": [
            "workspace/lit_review_pipeline/06_review.py",
        ],
        "acceptance_criteria": [
            "Map phase: for each paper loads all its chunks in order and stuffs them into a single Claude API call that outputs a PaperSummary Pydantic model",
            "PaperSummary model includes fields: paper_id, title, authors (list), year (int), objective (str), methodology (str), key_equations (list of LaTeX strings), key_findings (list of str), limitations (str), relevance_tags (list of str)",
            "Saves each PaperSummary as a JSON file to data/summaries/{paper_id}_summary.json using Pydantic's model_dump_json method",
            "Reduce phase: loads all summary JSON files and concatenates them into a single Claude prompt requesting thematic grouping, methodological comparison, equation/model comparison, consensus vs contradictions, identified gaps, and suggested future work",
            "Outputs the final synthesised literature review as a Markdown file to data/summaries/literature_review.md with section headings",
            "Runnable standalone via python 06_review.py with an if __name__ == '__main__' block",
        ],
        "validation_tool": "validate_python_syntax",
        "context_files": [
            "workspace/lit_review_pipeline/config.py",
        ],
        "depends_on": ["S8_retrieval"],
    },
    # ------------------------------------------------------------------
    # S10: End-to-End Integration Test
    # ------------------------------------------------------------------
    {
        "id": "S10_integration_test",
        "name": "End-to-End Integration Validation",
        "goal": "Generate a test script that runs the full pipeline on a synthetic or sample PDF",
        "files_to_produce": [
            "workspace/lit_review_pipeline/test_pipeline.py",
        ],
        "acceptance_criteria": [
            "Creates a minimal synthetic PDF containing body text, a LaTeX-style equation rendered as an image, and an embedded figure using reportlab or fpdf2",
            "Runs 01_ingest.py through 06_review.py in sequence as subprocesses and captures each script's exit code",
            "Asserts that manifest.json exists and contains at least one entry after the ingest step",
            "Asserts that at least one _merged.md file exists in data/parsed/ after the parse step",
            "Asserts that all_chunks.json exists and is non-empty after the chunking step",
            "Asserts that the ChromaDB collection contains at least one document after the indexing step",
            "Asserts that a test query to 05_query.py returns a non-empty response string",
            "Asserts that data/summaries/literature_review.md exists and is non-empty after the review step",
            "Reports pass/fail per pipeline phase with elapsed wall-clock time in seconds",
        ],
        "validation_tool": "run_python_script",
        "context_files": [
            "workspace/lit_review_pipeline/config.py",
        ],
        "depends_on": ["S9_review"],
    },
]