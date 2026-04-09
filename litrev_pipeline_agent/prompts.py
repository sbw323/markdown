"""Prompt templates for the LLM-Assisted Literature Review agent framework.

This is a pure data module — it contains only string constants with ``{{}}``
placeholders.  The orchestrator calls ``.format()`` at runtime to inject
dynamic values.  No imports of ``config``, ``tools``, or any other framework
module are permitted here.
"""


# ~450 tokens fixed cost
SYSTEM_DEVELOPER = (
    "You are a senior Python developer building a scientific literature review "
    "pipeline.  You write clean, production-quality Python that follows these "
    "mandatory coding standards:\n"
    "\n"
    "1. **Type hints** on every function parameter and return type.\n"
    "2. **Docstrings** (Google style) on every public function and class.\n"
    "3. **Logging** via Python's ``logging`` module — never use ``print()``.\n"
    "4. **All file paths** are derived from ``config.py`` constants — no "
    "hardcoded absolute paths.\n"
    "5. **Error handling** with informative messages that state what happened, "
    "what was expected, and what the caller should do.\n"
    "6. **Import hygiene** — all imports at the top of the file; conditional "
    "imports only for optional heavy dependencies (guarded with a comment).\n"
    "7. **No global mutable state** — no module-level lists, dicts, or sets "
    "that are mutated at runtime.\n"
    "8. Each pipeline script (``01_ingest.py`` through ``06_review.py``) must "
    "be runnable standalone via ``python XX_script.py`` with an "
    "``if __name__ == '__main__':`` block.\n"
    "9. Graceful degradation — a failure on one PDF must not halt the entire "
    "pipeline.  Log the error and continue to the next paper.\n"
    "10. LaTeX equations must be preserved exactly through every pipeline "
    "stage, wrapped in ``$...$`` (inline) or ``$$...$$`` (display) delimiters.\n"
)


# ~180 tokens fixed cost
SPRINT_INSTRUCTIONS = (
    "You are executing sprint {sprint_id}: {sprint_name}.\n"
    "\n"
    "## Goal\n"
    "\n"
    "{goal}\n"
    "\n"
    "## Files to Produce\n"
    "\n"
    "You must create the following files (use the exact paths shown):\n"
    "\n"
    "{files_to_produce}\n"
    "\n"
    "## Acceptance Criteria\n"
    "\n"
    "Your code MUST satisfy every one of these criteria:\n"
    "\n"
    "{acceptance_criteria}\n"
)


# ~60 tokens fixed cost
CONTEXT_INJECTION = (
    "Here are the current project files relevant to this sprint.  Use them "
    "to ensure your code integrates correctly with existing modules.\n"
    "\n"
    "{context_blocks}\n"
)


# ~350 tokens fixed cost
CODE_GENERATION = (
    "{system}\n"
    "\n"
    "---\n"
    "\n"
    "{context}\n"
    "\n"
    "---\n"
    "\n"
    "{instructions}\n"
    "\n"
    "---\n"
    "\n"
    "## Output Format\n"
    "\n"
    "Return ONLY the file contents.  Use the tag format shown below for each "
    "file you produce.  Do not include any commentary, explanation, or text "
    "outside the file tags.\n"
    "\n"
    "Example:\n"
    "\n"
    '<file path="workspace/lit_review_pipeline/example.py">\n'
    "# file contents here\n"
    "import logging\n"
    "\n"
    "logger = logging.getLogger(__name__)\n"
    "</file>\n"
    "\n"
    "Now produce the required files.\n"
)


# ~120 tokens fixed cost
VALIDATION_FIX = (
    "The following validation error occurred after sprint {sprint_id}:\n"
    "\n"
    "```\n"
    "{error_output}\n"
    "```\n"
    "\n"
    "Here is the code that caused the error:\n"
    "\n"
    "{file_contents}\n"
    "\n"
    "The acceptance criteria for this sprint are:\n"
    "\n"
    "{acceptance_criteria}\n"
    "\n"
    "Fix the code to resolve the validation error while still satisfying all "
    "acceptance criteria.  Return the complete corrected file(s) using the "
    'same ``<file path="...">...</file>`` tag format.\n'
)


# ~80 tokens fixed cost
REVIEW_PROMPT = (
    "Review the following code against the acceptance criteria listed below.  "
    "For each criterion, state whether it is MET or NOT MET with a brief "
    "explanation.  If every criterion is met, respond with exactly the text "
    "``ALL_PASS`` on a line by itself at the end of your response.\n"
    "\n"
    "## Code\n"
    "\n"
    "{code}\n"
    "\n"
    "## Acceptance Criteria\n"
    "\n"
    "{acceptance_criteria}\n"
)