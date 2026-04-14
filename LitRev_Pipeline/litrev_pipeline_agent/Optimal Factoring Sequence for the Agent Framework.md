# Optimal Factoring Sequence for the Agent Framework

## Document Purpose

This document defines the exact build order for the four framework modules (`config.py`, `tools.py`, `prompts.py`, `sprints.py`, `orchestrator.py`) and the validation gates between each phase. Each phase includes recursive validation checks that verify the current output against all previous outputs and a terminal audit against the Best Practices document.

---

## Factoring Rationale

The modules have a strict dependency graph:

```
config.py ← tools.py ← prompts.py ← sprints.py ← orchestrator.py
```

- `config.py` depends on nothing.
- `tools.py` depends on `config.py` (for workspace path, timeouts).
- `prompts.py` depends on nothing at runtime, but its templates must reference the output format that `tools.parse_file_tags()` expects, so it is authored after `tools.py`.
- `sprints.py` depends on nothing at runtime, but its `validation_tool` fields must name functions that exist in `tools.py`, and its `acceptance_criteria` must be compatible with the prompt structure in `prompts.py`. So it is authored after both.
- `orchestrator.py` imports and sequences all four, so it is authored last.

Building in this order means each module is written with full knowledge of what it depends on, and each validation gate can check integration against all prior modules.

---

## Phase 1: `config.py`

### Objective

Define all configuration constants, path definitions, environment variable overrides, and a `validate_config()` function.

### Required Contents

1. `WORKSPACE_ROOT` — absolute path to the workspace directory, defaulting to `./workspace/lit_review_pipeline`.
2. `PDF_DIR`, `PARSED_DIR`, `SUMMARIES_DIR`, `VECTORSTORE_DIR` — derived from `WORKSPACE_ROOT`.
3. `ANTHROPIC_API_KEY` — from environment variable.
4. `GROBID_URL` — from environment variable, default `http://localhost:8070`.
5. `AGENT_MODEL` — model string for the agent's own LLM calls (e.g., `claude-sonnet-4-20250514`).
6. `PIPELINE_MODEL` — model string for the generated pipeline's LLM calls.
7. `EMBEDDING_MODEL` — model string for sentence-transformers.
8. `EQUATION_BACKEND` — one of `"nougat"`, `"claude_vision"`, `"both"`, `"none"`.
9. `ENABLE_RERANKING` — boolean flag.
10. `MAX_CHUNK_TOKENS` — integer, default 1500.
11. `MIN_CHUNK_TOKENS` — integer, default 500.
12. `RETRY_BUDGET` — integer, default 3.
13. `SHELL_TIMEOUT` — integer seconds, default 120.
14. `SCRIPT_TIMEOUT` — integer seconds, default 300.
15. `CONTEXT_WINDOW_LIMIT` — integer token estimate for model context window.
16. `RESPONSE_HEADROOM_RATIO` — float, default 0.3 (30% reserved for response).
17. `LOG_FILE` — path to the agent's JSONL log.
18. `validate_config()` — raises `ValueError` with specific message if `ANTHROPIC_API_KEY` is empty.

### Validation Gate 1: `config.py` Self-Consistency

| Check ID | Description | Method |
|----------|-------------|--------|
| V1.1 | File parses without syntax errors | `py_compile.compile()` |
| V1.2 | All 17 listed constants are defined at module level | AST inspection: walk top-level `Assign` nodes, verify names |
| V1.3 | `validate_config()` function exists | AST inspection: find `FunctionDef` named `validate_config` |
| V1.4 | `validate_config()` raises `ValueError` when `ANTHROPIC_API_KEY` is empty | Temporarily set env var to empty, import module, call function, assert `ValueError` |
| V1.5 | All path constants are derived from `WORKSPACE_ROOT` (no hardcoded absolute paths) | Regex scan: no string literal starting with `/` except in `os.environ.get` defaults |
| V1.6 | `os.environ.get` used for `ANTHROPIC_API_KEY` and `GROBID_URL` | AST or string search |
| V1.7 | Type hints present on `validate_config` | AST inspection |
| V1.8 | Module-level docstring present | AST inspection: first node is `Expr` with `Constant` string |

**Best Practices Audit (Phase 1):**
- BP 5.1: All configuration in one file — PASS if no other framework file contains hardcoded paths or keys.
- BP 5.2: Environment variable override — checked by V1.6.
- BP 5.3: Validation at import time — checked by V1.4.
- BP 7.1: Type hints — checked by V1.7.
- BP 7.2: Docstrings — checked by V1.8.
- BP 7.3: No global mutable state — AST scan for module-level assignments to `list`, `dict`, or `set` literals that are later mutated.

---

## Phase 2: `tools.py`

### Objective

Implement all tool functions with uniform return contracts, using paths and timeouts from `config.py`.

### Required Functions

1. `write_file(path: str, content: str) -> dict`
2. `read_file(path: str) -> dict`
3. `list_directory(path: str) -> dict`
4. `run_shell(command: str, timeout: int = None) -> dict`
5. `validate_python_syntax(path: str) -> dict`
6. `validate_file_structure(expected_paths: list[str]) -> dict`
7. `run_python_script(path: str, timeout: int = None) -> dict`
8. `parse_file_tags(llm_response: str) -> list[tuple[str, str]]`
9. `install_dependencies(requirements_path: str) -> dict`
10. `start_grobid() -> dict`
11. `extract_skeleton(path: str) -> dict`
12. `estimate_tokens(text: str) -> int`

### Validation Gate 2: `tools.py` Self-Consistency + Recursive Check Against Phase 1

| Check ID | Description | Method |
|----------|-------------|--------|
| V2.1 | File parses without syntax errors | `py_compile.compile()` |
| V2.2 | All 12 listed functions are defined | AST inspection |
| V2.3 | Every function (except `parse_file_tags` and `estimate_tokens`) returns a dict with keys `success`, `output`, `error` | AST inspection: check return type annotation is `dict`; static analysis of return statements |
| V2.4 | `parse_file_tags` return annotation is `list[tuple[str, str]]` | AST inspection |
| V2.5 | Every function has type hints on all parameters and return type | AST inspection |
| V2.6 | Every function has a docstring | AST inspection |
| V2.7 | `write_file` rejects paths containing `..` that escape workspace | Unit test: call with `../../etc/passwd`, assert `success=False` |
| V2.8 | `run_shell` uses `subprocess.run` with `timeout` parameter | AST or source search |
| V2.9 | `parse_file_tags` handles: bare tags, tags inside code fences, multiple files, extra whitespace | Unit test with known inputs |
| V2.10 | `extract_skeleton` uses `ast` module | Import/source inspection |
| V2.11 | `estimate_tokens` returns an integer | Unit test |

**Recursive Check Against Phase 1:**

| Check ID | Description | Method |
|----------|-------------|--------|
| R2.1 | `tools.py` imports `config` | AST inspection of import statements |
| R2.2 | Default timeout values in `run_shell` and `run_python_script` reference `config.SHELL_TIMEOUT` and `config.SCRIPT_TIMEOUT` respectively | Source search |
| R2.3 | `write_file` path resolution uses `config.WORKSPACE_ROOT` | Source search |
| R2.4 | `start_grobid` uses `config.GROBID_URL` for health check | Source search |
| R2.5 | No hardcoded paths, keys, or timeout values that duplicate `config.py` constants | Full source scan for string literals matching any `config.py` default value |

**Best Practices Audit (Phase 2):**
- BP 4.1: Uniform return contract — checked by V2.3.
- BP 4.2: Idempotency — structural review: `write_file` must not fail if file exists; `start_grobid` must check for running container.
- BP 4.3: Timeout enforcement — checked by V2.8 and R2.2.
- BP 4.4: No side effects beyond stated purpose — manual/LLM review of each validation function to ensure no writes.
- BP 4.5: Path safety — checked by V2.7.
- BP 4.6: Robust tag parsing — checked by V2.9.
- BP 4.7: Skeleton extraction — checked by V2.10.
- BP 4.8: Shell command logging — source search for `logging` calls in `run_shell`.
- BP 7.1–7.5: Cross-cutting — checked by V2.5, V2.6, import inspection, error message review.

---

## Phase 3: `prompts.py`

### Objective

Define all prompt templates as string constants with `{}` placeholders. No runtime logic, no imports (except possibly `textwrap.dedent` for readability).

### Required Templates

1. `SYSTEM_DEVELOPER` — agent persona and coding standards.
2. `SPRINT_INSTRUCTIONS` — placeholders: `{sprint_id}`, `{sprint_name}`, `{goal}`, `{files_to_produce}`, `{acceptance_criteria}`.
3. `CONTEXT_INJECTION` — placeholder: `{context_blocks}` (pre-formatted string of file contents).
4. `CODE_GENERATION` — assembles the three above; placeholders must align with what the orchestrator provides.
5. `VALIDATION_FIX` — placeholders: `{sprint_id}`, `{error_output}`, `{file_contents}`, `{acceptance_criteria}`.
6. `REVIEW_PROMPT` — placeholder: `{code}`, `{acceptance_criteria}`.

### Validation Gate 3: `prompts.py` Self-Consistency + Recursive Check Against Phases 1–2

| Check ID | Description | Method |
|----------|-------------|--------|
| V3.1 | File parses without syntax errors | `py_compile.compile()` |
| V3.2 | All 6 listed template constants are defined at module level | AST inspection |
| V3.3 | Every template is a `str` type (not an f-string, not a function) | AST inspection: top-level `Assign` where value is `Constant(str)` or `Call` to `textwrap.dedent` wrapping a `Constant(str)` |
| V3.4 | `CODE_GENERATION` template contains the `<file path="...">...</file>` format specification | String search within the constant value |
| V3.5 | `CODE_GENERATION` template contains a one-shot example of the file tag format | String search |
| V3.6 | `SPRINT_INSTRUCTIONS` contains placeholders `{sprint_id}`, `{sprint_name}`, `{goal}`, `{files_to_produce}`, `{acceptance_criteria}` | Regex extraction of `{...}` tokens from the template |
| V3.7 | `VALIDATION_FIX` contains placeholders `{sprint_id}`, `{error_output}`, `{file_contents}`, `{acceptance_criteria}` | Regex extraction |
| V3.8 | No template uses f-string syntax (no `f"..."` or `f'...'`) | AST inspection: no `JoinedStr` nodes |
| V3.9 | Each template has an associated comment with approximate token cost | Regex: each constant assignment preceded by a comment containing a number and "token" |
| V3.10 | Module-level docstring present | AST inspection |

**Recursive Check Against Phase 2 (`tools.py`):**

| Check ID | Description | Method |
|----------|-------------|--------|
| R3.1 | The file tag format in `CODE_GENERATION` is parseable by `tools.parse_file_tags()` | Extract the example from the template, run it through `parse_file_tags()`, assert it returns a valid result |
| R3.2 | `SYSTEM_DEVELOPER` specifies the same coding standards that `tools.validate_python_syntax` and `tools.extract_skeleton` expect (e.g., type hints, docstrings) | Manual/LLM review: extract standards from prompt, cross-reference with tool assumptions |

**Recursive Check Against Phase 1 (`config.py`):**

| Check ID | Description | Method |
|----------|-------------|--------|
| R3.3 | `prompts.py` does not import `config` (it is a pure data module; the orchestrator provides config values via format arguments) | AST import inspection |
| R3.4 | No hardcoded model names, paths, or keys in any template | Regex scan for known `config.py` default values appearing as string literals |

**Best Practices Audit (Phase 3):**
- BP 3.1: Separation of concerns — checked by R3.3 (no imports of other modules).
- BP 3.2: Output format enforcement — checked by V3.4 and V3.5.
- BP 3.3: Acceptance criteria in prompt — checked by V3.6 (placeholder exists).
- BP 3.4: Context file formatting — verify `CONTEXT_INJECTION` contains `BEGIN FILE` / `END FILE` delimiters or equivalent.
- BP 3.5: Fix prompt structure — checked by V3.7 (all three required elements have placeholders).
- BP 3.6: No dynamic construction outside `prompts.py` — checked by V3.8.
- BP 3.7: Token budget comments — checked by V3.9.

---

## Phase 4: `sprints.py`

### Objective

Define the complete ordered list of sprint dictionaries with all required fields.

### Required Fields Per Sprint

Each sprint dict must have: `id` (str), `name` (str), `goal` (str), `files_to_produce` (list[str]), `acceptance_criteria` (list[str]), `validation_tool` (str), `depends_on` (list[str]). Optional: `context_files` (list[str]).

### Required Sprints

S0 through S10 as defined in the implementation plan (scaffold, metadata, parse base, equation handler, parse integration, figures, chunking, indexing, retrieval, review, integration test).

### Validation Gate 4: `sprints.py` Self-Consistency + Recursive Check Against Phases 1–3

| Check ID | Description | Method |
|----------|-------------|--------|
| V4.1 | File parses without syntax errors | `py_compile.compile()` |
| V4.2 | Module defines a `sprints` list at module level | AST inspection |
| V4.3 | `sprints` list contains exactly 11 entries (S0–S10) | Length check after import |
| V4.4 | Every sprint dict has all required keys: `id`, `name`, `goal`, `files_to_produce`, `acceptance_criteria`, `validation_tool`, `depends_on` | Key presence check on each dict |
| V4.5 | All sprint `id` values are unique | Set comparison |
| V4.6 | `depends_on` references only `id` values that exist in the list | Cross-reference |
| V4.7 | Dependency graph is acyclic | Topological sort; fail if cycle detected |
| V4.8 | Sprint list order is a valid topological sort of the dependency graph | Verify that for every sprint, all its dependencies appear earlier in the list |
| V4.9 | Every `context_files` entry names a file that appears in some prior sprint's `files_to_produce` | Cross-reference |
| V4.10 | No sprint has an empty `acceptance_criteria` list | Length check |
| V4.11 | Every `files_to_produce` path starts with `workspace/` | String check |
| V4.12 | If two sprints list the same file in `files_to_produce`, the later sprint includes the earlier sprint's ID in `depends_on` | Cross-reference |

**Recursive Check Against Phase 2 (`tools.py`):**

| Check ID | Description | Method |
|----------|-------------|--------|
| R4.1 | Every sprint's `validation_tool` value matches the name of a function defined in `tools.py` | Import `tools`, use `hasattr()` or AST function list from Phase 2 validation |
| R4.2 | `validate_file_structure` is the validation tool for S0, and S0's `files_to_produce` matches what `validate_file_structure` will be called with | Structural cross-check |

**Recursive Check Against Phase 3 (`prompts.py`):**

| Check ID | Description | Method |
|----------|-------------|--------|
| R4.3 | Sprint dict keys (`id`, `name`, `goal`, `files_to_produce`, `acceptance_criteria`) align with the placeholder names in `SPRINT_INSTRUCTIONS` | Extract placeholders from template, verify sprint dict keys are a superset |
| R4.4 | Every acceptance criterion is a concrete, testable statement (heuristic: no criterion is shorter than 10 words, none contains only qualitative adjectives without a noun referencing a code element) | Length check + LLM-assisted review for vagueness |

**Recursive Check Against Phase 1 (`config.py`):**

| Check ID | Description | Method |
|----------|-------------|--------|
| R4.5 | Sprint S0's `files_to_produce` includes `config.py` at the expected path matching `config.WORKSPACE_ROOT` structure | Path comparison |

**Best Practices Audit (Phase 4):**
- BP 2.1: Sprint atomicity — LLM-assisted review: can each sprint's goal be stated in one sentence?
- BP 2.2: Explicit file targets — checked by V4.11.
- BP 2.3: Testable criteria — checked by R4.4.
- BP 2.4: Context file minimality — flag any sprint where `context_files` includes more than 4 files (warning, not failure).
- BP 2.5: Dependency integrity — checked by V4.9 (context files exist in prior outputs).
- BP 2.6: No circular dependencies — checked by V4.7.
- BP 2.7: Overwrite semantics — checked by V4.12.

---

## Phase 5: `orchestrator.py`

### Objective

Implement the main loop that sequences sprints, assembles prompts, calls the LLM, dispatches tools, and handles retries.

### Required Components

1. `main()` function as the entry point.
2. Sprint loop iterating over `sprints.sprints`.
3. Context gathering: reads `context_files` + prior sprint outputs.
4. Prompt assembly: uses `prompts.CODE_GENERATION.format(...)`.
5. LLM call: Anthropic API with `config.AGENT_MODEL`, temperature 0.
6. Response parsing: `tools.parse_file_tags()`.
7. File writing: `tools.write_file()` for each parsed file.
8. Validation: calls the tool named by sprint's `validation_tool`.
9. Retry loop: on validation failure, uses `prompts.VALIDATION_FIX`, max `config.RETRY_BUDGET` attempts.
10. Context window management: `tools.estimate_tokens()` on assembled prompt, fallback to `tools.extract_skeleton()` if over budget.
11. JSONL logging per sprint.
12. `--resume` flag support via `argparse`.
13. Post-sprint hooks: `tools.install_dependencies()` after S0, summary report after S10.

### Validation Gate 5: `orchestrator.py` Self-Consistency + Recursive Check Against All Prior Phases

| Check ID | Description | Method |
|----------|-------------|--------|
| V5.1 | File parses without syntax errors | `py_compile.compile()` |
| V5.2 | `main()` function defined | AST inspection |
| V5.3 | `argparse` used with `--resume` flag | AST/source search |
| V5.4 | Imports `config`, `tools`, `prompts`, `sprints` | AST import inspection |
| V5.5 | Contains a loop over `sprints.sprints` | AST: `For` node iterating over attribute access `sprints.sprints` |
| V5.6 | Calls `prompts.CODE_GENERATION.format(...)` or equivalent | Source search |
| V5.7 | Calls Anthropic API with `config.AGENT_MODEL` | Source search for `config.AGENT_MODEL` in an API call context |
| V5.8 | Calls `tools.parse_file_tags()` on LLM response | Source search |
| V5.9 | Calls `tools.write_file()` in a loop over parsed files | Source search |
| V5.10 | Retry loop with counter bounded by `config.RETRY_BUDGET` | AST: while/for loop with comparison against `config.RETRY_BUDGET` |
| V5.11 | Context window check using `tools.estimate_tokens()` | Source search |
| V5.12 | Falls back to `tools.extract_skeleton()` when over token budget | Source search |
| V5.13 | Opens and writes to `config.LOG_FILE` in JSONL format | Source search for `json.dumps` and `LOG_FILE` |
| V5.14 | Uses `logging` module, no `print()` calls | AST: no `Call` nodes where `func` is `Name(id='print')` |
| V5.15 | All functions have type hints and docstrings | AST inspection |

**Recursive Check Against Phase 4 (`sprints.py`):**

| Check ID | Description | Method |
|----------|-------------|--------|
| R5.1 | Orchestrator accesses sprint dict keys that exist: `id`, `name`, `goal`, `files_to_produce`, `acceptance_criteria`, `validation_tool`, `depends_on`, `context_files` | AST: find all subscript accesses on sprint loop variable, verify each key is in the required set |
| R5.2 | Orchestrator handles optional `context_files` key (uses `.get("context_files", [])` or equivalent) | Source search |
| R5.3 | Post-sprint hook for S0 references the sprint by ID `"S0_scaffold"` | Source search |

**Recursive Check Against Phase 3 (`prompts.py`):**

| Check ID | Description | Method |
|----------|-------------|--------|
| R5.4 | `prompts.CODE_GENERATION.format()` call provides all required keyword arguments: cross-reference with placeholders extracted in V3.6 | Extract `.format()` kwargs from source, compare with placeholder set |
| R5.5 | `prompts.VALIDATION_FIX.format()` call provides all required keyword arguments | Same method |
| R5.6 | Context injection format matches `prompts.CONTEXT_INJECTION` template structure | Verify orchestrator builds a `context_blocks` string with `BEGIN FILE`/`END FILE` delimiters matching the template |

**Recursive Check Against Phase 2 (`tools.py`):**

| Check ID | Description | Method |
|----------|-------------|--------|
| R5.7 | Orchestrator uses `getattr(tools, sprint["validation_tool"])` or equivalent dynamic dispatch to call the right validation function | Source search for `getattr` on `tools` |
| R5.8 | Orchestrator checks the `success` key of every tool return value | Source search: every `tools.xxx()` call is followed by an `if` on `["success"]` or `result["success"]` |
| R5.9 | Orchestrator reads `error` from tool return for injection into fix prompts | Source search |

**Recursive Check Against Phase 1 (`config.py`):**

| Check ID | Description | Method |
|----------|-------------|--------|
| R5.10 | Orchestrator calls `config.validate_config()` before entering the sprint loop | AST: `config.validate_config()` call appears before the sprint loop |
| R5.11 | All config references use `config.X` attribute access, no re-declarations | AST: no top-level assignments that shadow config constants |

**Best Practices Audit (Phase 5):**
- BP 1.1: Single responsibility — checked by V5.4 (imports all modules) + verify no inline prompt strings (source scan for multi-line string literals).
- BP 1.2: Deterministic sequencing — checked by V5.5 (iterates list in order).
- BP 1.3: Retry budget — checked by V5.10.
- BP 1.4: Context window discipline — checked by V5.11 and V5.12.
- BP 1.5: Structured logging — checked by V5.13 and V5.14.
- BP 1.6: No implicit state — AST scan for module-level mutable assignments outside `main()`.

---

## Phase 6: Final Integration Validation

After all five modules pass their individual gates, run the following integration checks.

### Cross-Module Integration Checks

| Check ID | Description | Method |
|----------|-------------|--------|
| F1 | All five modules import successfully in a single Python process without circular import errors | `python -c "import config, tools, prompts, sprints, orchestrator"` |
| F2 | `orchestrator.main()` can be called with `--resume` on an empty workspace without crashing before the first LLM call (i.e., all setup steps work) | Mock the Anthropic API call to return a canned response, run `main()`, verify it reaches the LLM call step |
| F3 | Every validation tool named in `sprints.py` is callable and returns the correct dict structure | For each unique `validation_tool`, call `getattr(tools, name)` with dummy arguments, verify return has `success`, `output`, `error` keys |
| F4 | Prompt assembly produces valid strings: for each sprint, assemble the `CODE_GENERATION` prompt with dummy context and verify `.format()` does not raise `KeyError` | Loop over sprints, call `prompts.CODE_GENERATION.format(...)` with sprint fields |
| F5 | Token estimation of the largest possible prompt (all context files at maximum expected size) stays within `config.CONTEXT_WINDOW_LIMIT * (1 - config.RESPONSE_HEADROOM_RATIO)` | Estimate with `tools.estimate_tokens()` using mock files of expected size |

### Full Best Practices Compliance Audit

This is the terminal gate. Every check from the Best Practices document is re-verified across all modules as a batch. The checks are organized by practice number.

| BP Section | Check | Modules Affected | Method |
|------------|-------|------------------|--------|
| 1.1 | No domain logic in orchestrator | orchestrator.py | Source scan: no string templates, no `os.makedirs`, no `os.path.join` with literal paths |
| 1.5 | JSONL logging, no print | orchestrator.py | AST: no `print()` calls; `logging` imported and used |
| 2.3 | All acceptance criteria testable | sprints.py | LLM-assisted: feed each criterion to a classifier prompt that returns "testable" or "vague" |
| 2.6 | No circular deps | sprints.py | Already checked in V4.7, re-verify |
| 3.6 | No f-strings in prompts | prompts.py | Already checked in V3.8, re-verify |
| 4.1 | Uniform return contract | tools.py | Already checked in V2.3, re-verify |
| 5.1 | Single source of truth for config | All modules | Grep all modules for string literals matching IP addresses, port numbers, model name patterns, file extensions — flag any that should be in config |
| 7.1 | Type hints everywhere | All modules | AST scan all modules: every `FunctionDef` and `AsyncFunctionDef` must have `returns` annotation and all `arg` nodes in `args` must have `annotation` |
| 7.2 | Docstrings on public functions | All modules | AST scan: every function not prefixed with `_` must have a docstring |
| 7.3 | No global mutable state | All modules | AST scan: no module-level `Assign` to `List()`, `Dict()`, or `Set()` that appear in any `AugAssign`, `Subscript` store, or method call later in the module |
| 7.4 | Import hygiene | All modules | AST scan: all `Import` and `ImportFrom` nodes are before the first `FunctionDef` or `ClassDef` (except guarded conditional imports with a comment) |
| 7.5 | Actionable error messages | All modules | Extract all string arguments to `raise` statements and `logging.error` calls; LLM-assisted review for actionability |

### Validation Outcome

If all checks pass: the framework is ready for execution. Run `python orchestrator.py` to begin building the literature review pipeline.

If any check fails: the failure report identifies the specific check ID, the module, the violating line or construct, and the best practice it violates. Fix the module and re-run that module's validation gate plus all downstream recursive checks (since a change to `tools.py` could invalidate checks in `prompts.py`, `sprints.py`, and `orchestrator.py`).

---

## Summary: Execution Order

```
Phase 1: Write config.py        → Run Gate 1 (8 checks)
Phase 2: Write tools.py         → Run Gate 2 (11 + 5 recursive + BP audit)
Phase 3: Write prompts.py       → Run Gate 3 (10 + 4 recursive + BP audit)
Phase 4: Write sprints.py       → Run Gate 4 (12 + 5 recursive + BP audit)
Phase 5: Write orchestrator.py  → Run Gate 5 (15 + 11 recursive + BP audit)
Phase 6: Integration            → Run 5 integration checks + full BP audit
```

Total validation checks: **86 discrete checks** across 6 gates, each traceable to a specific best practice or integration requirement.