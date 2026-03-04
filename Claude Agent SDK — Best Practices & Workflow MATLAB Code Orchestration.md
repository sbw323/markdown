# Claude Agent SDK — Best Practices & Workflow for MATLAB Code Orchestration

## Purpose

This document serves as a starting-point reference for building a **Python orchestrator** that uses the **Claude Agent SDK** (`claude-agent-sdk` on PyPI, v0.1.44+) to instantiate an agentic developer loop for writing, testing, and running MATLAB/Simulink scripts. The target domain is BSM/ASM3 wastewater-treatment modeling with perturbation-recovery campaigns, but the patterns are general.

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│  Python Orchestrator  (asyncio / anyio)             │
│  ┌─────────────┐  ┌────────────┐  ┌──────────────┐ │
│  │ Sprint Mgr   │  │ Checkpoint │  │ Verification │ │
│  │  (phases,    │  │  Store     │  │  Engine      │ │
│  │   prompts)   │  │  (JSON +   │  │  (static +   │ │
│  └──────┬───────┘  │  git/file) │  │   runtime)   │ │
│         │          └─────┬──────┘  └──────┬───────┘ │
│         ▼                ▼                ▼         │
│  ┌──────────────────────────────────────────────┐   │
│  │        Claude Agent SDK session              │   │
│  │  (ClaudeSDKClient + hooks + custom tools)    │   │
│  └──────────────┬───────────────────────────────┘   │
│                 │  file I/O confined to sandbox      │
│                 ▼                                    │
│  ┌──────────────────────────────────────────────┐   │
│  │  Working Directory  (sandbox)                │   │
│  │  └─ /sprints/<N>/src/   ← agent writes here  │   │
│  │  └─ /sprints/<N>/tests/ ← test harness        │   │
│  │  └─ /sprints/<N>/data/  ← simulation output   │   │
│  └──────────────────────────────────────────────┘   │
│                 │                                    │
│                 ▼                                    │
│  ┌──────────────────────────────────────────────┐   │
│  │  MATLAB Engine  (matlab.engine for Python)   │   │
│  │  or shell-invoked:  matlab -batch "..."       │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

---

## 2. SDK Installation & Authentication

```bash
pip install claude-agent-sdk            # bundles Claude Code CLI
export ANTHROPIC_API_KEY=sk-ant-...     # or use .env
```

Key options at instantiation:

| Option | Recommended Value | Why |
|---|---|---|
| `model` | `"claude-sonnet-4-5-20250929"` | Cost-efficient for code gen; upgrade to Opus for complex reasoning sprints |
| `fallback_model` | `"claude-sonnet-4-5-20250929"` | Automatic fallback if primary unavailable |
| `max_turns` | 15–30 per sprint phase | Prevents runaway loops; tune per phase complexity |
| `max_budget_usd` | 2.0–5.0 per sprint | Hard cost ceiling per sprint invocation |
| `permission_mode` | `"acceptEdits"` | Auto-accept file writes inside the sandbox |
| `enable_file_checkpointing` | `True` | Enables `rewind_files()` for rollback |
| `allowed_tools` | `["Read", "Write", "Edit", "Bash", "Glob"]` | Minimum viable tool set for MATLAB script work |
| `cwd` | `Path(f"./sprints/{sprint_id}")` | Confine agent to sprint directory |
| `effort` | `"high"` | Controls extended thinking depth |

---

## 3. Sprint-Based Development Workflow

Each sprint is an isolated unit of work. The orchestrator advances through sprints sequentially; each sprint has internal phases.

### 3.1 Sprint Definition Schema

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class SprintPhase(Enum):
    PLAN       = "plan"        # Agent reads requirements, proposes approach
    GENERATE   = "generate"    # Agent writes MATLAB .m files
    STATIC     = "static"      # Orchestrator runs mlint / static checks
    UNIT_TEST  = "unit_test"   # Agent writes & orchestrator runs test harness
    INTEGRATE  = "integrate"   # Orchestrator runs simulation via MATLAB engine
    VERIFY     = "verify"      # Agent reviews outputs against acceptance criteria
    PACKAGE    = "package"     # Agent documents & orchestrator archives

@dataclass
class Sprint:
    id: str                                       # e.g. "S03"
    title: str                                    # e.g. "Aeration curtailment step-response"
    objective: str                                # detailed goal
    acceptance_criteria: list[str]                # verifiable conditions
    matlab_entry_point: str = "run_simulation.m"  # main script to execute
    max_turns_per_phase: dict[SprintPhase, int] = field(default_factory=lambda: {
        SprintPhase.PLAN: 5,
        SprintPhase.GENERATE: 25,
        SprintPhase.STATIC: 3,
        SprintPhase.UNIT_TEST: 15,
        SprintPhase.INTEGRATE: 10,
        SprintPhase.VERIFY: 8,
        SprintPhase.PACKAGE: 5,
    })
    retry_limit: int = 3                          # max retries per phase
```

### 3.2 Phase Responsibilities

| Phase | Actor | Activities |
|---|---|---|
| **PLAN** | Agent | Read sprint objective + prior outputs → produce `plan.md` with approach, file list, variable names, expected outputs |
| **GENERATE** | Agent | Write `.m` files into `src/`. System prompt enforces coding standards (naming, comments, header blocks). |
| **STATIC** | Orchestrator | Run `mlint` via Bash tool or custom tool. Feed warnings back to agent for remediation. |
| **UNIT_TEST** | Agent + Orchestrator | Agent writes test functions; orchestrator invokes `matlab -batch "runtests('tests')"`. Parse xUnit XML results. |
| **INTEGRATE** | Orchestrator | Execute full simulation via MATLAB engine. Capture stdout, stderr, `.mat` output files. |
| **VERIFY** | Agent | Agent reads simulation output summary + acceptance criteria → produces `verification_report.md` with PASS/FAIL per criterion. |
| **PACKAGE** | Agent + Orchestrator | Agent writes README. Orchestrator commits sprint directory to archive. |

---

## 4. Checkpoint & Rollback Strategy

### 4.1 File Checkpointing (SDK-native)

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, UserMessage

options = ClaudeAgentOptions(
    enable_file_checkpointing=True,
    extra_args={"replay-user-messages": None},  # required for UUID capture
    cwd=str(sprint_dir),
    allowed_tools=["Read", "Write", "Edit", "Bash", "Glob"],
    permission_mode="acceptEdits",
)

checkpoints: dict[str, str] = {}  # phase_name → user_message_uuid

async with ClaudeSDKClient(options=options) as client:
    await client.query(phase_prompt)
    async for msg in client.receive_response():
        if isinstance(msg, UserMessage) and msg.uuid:
            checkpoints[current_phase.value] = msg.uuid
        # ... process assistant messages
```

Rolling back after a failed phase:

```python
async def rollback_to_phase(client: ClaudeSDKClient, phase: SprintPhase):
    target_uuid = checkpoints.get(phase.value)
    if target_uuid:
        await client.rewind_files(target_uuid)
        log.info(f"Rolled back files to checkpoint: {phase.value}")
```

### 4.2 External Checkpoints (Belt-and-Suspenders)

For simulation data integrity beyond the SDK's file checkpointing:

```python
import shutil, json
from pathlib import Path
from datetime import datetime

def save_external_checkpoint(sprint: Sprint, phase: SprintPhase):
    """Archive sprint directory + metadata independently of SDK."""
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    ckpt_dir = Path(f"./checkpoints/{sprint.id}/{phase.value}_{ts}")
    shutil.copytree(f"./sprints/{sprint.id}", ckpt_dir)
    meta = {
        "sprint_id": sprint.id,
        "phase": phase.value,
        "timestamp": ts,
        "acceptance_criteria": sprint.acceptance_criteria,
    }
    (ckpt_dir / "checkpoint_meta.json").write_text(json.dumps(meta, indent=2))
    return ckpt_dir
```

---

## 5. Hooks for Safety & Observability

### 5.1 Pre-Tool-Use: Sandbox Enforcement

Block any writes outside the sprint directory and prevent destructive shell commands.

```python
from claude_agent_sdk import HookMatcher

SPRINT_DIR = "/absolute/path/to/sprints/S03"

async def enforce_sandbox(input_data, tool_use_id, context):
    tool = input_data["tool_name"]
    tool_input = input_data.get("tool_input", {})

    # Block writes outside sprint dir
    if tool in ("Write", "Edit"):
        file_path = tool_input.get("file_path", "")
        if not file_path.startswith(SPRINT_DIR):
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason":
                        f"Write blocked: {file_path} is outside sandbox {SPRINT_DIR}",
                }
            }

    # Block dangerous bash patterns
    if tool == "Bash":
        cmd = tool_input.get("command", "")
        blocked = ["rm -rf /", "sudo", "pip install", "curl", "wget", "chmod"]
        for pattern in blocked:
            if pattern in cmd:
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason":
                            f"Bash blocked: contains '{pattern}'",
                    }
                }
    return {}

sandbox_hooks = {
    "PreToolUse": [
        HookMatcher(matcher="Write|Edit", hooks=[enforce_sandbox]),
        HookMatcher(matcher="Bash", hooks=[enforce_sandbox]),
    ],
}
```

### 5.2 Post-Tool-Use: Logging & Metrics

```python
import time

tool_metrics = []

async def log_tool_use(input_data, tool_use_id, context):
    tool_metrics.append({
        "tool": input_data["tool_name"],
        "tool_use_id": tool_use_id,
        "timestamp": time.time(),
    })
    return {}

observability_hooks = {
    "PostToolUse": [
        HookMatcher(matcher=None, hooks=[log_tool_use]),  # all tools
    ],
}
```

### 5.3 Stop Hook: Phase Transition Logic

```python
async def on_agent_stop(input_data, tool_use_id, context):
    """Capture final output and signal phase completion."""
    stop_reason = input_data.get("stop_reason", "end_turn")
    log.info(f"Agent stopped: {stop_reason}")
    return {}
```

---

## 6. Custom Tools for MATLAB Integration

Define MATLAB-specific tools as in-process MCP servers so the agent can invoke them directly.

```python
from claude_agent_sdk import create_sdk_mcp_server
from claude_agent_sdk.tools import tool

@tool("run_mlint", "Run MATLAB mlint static analysis on a .m file")
async def run_mlint(file_path: str) -> str:
    """Runs mlint and returns warnings/errors as text."""
    import subprocess
    result = subprocess.run(
        ["matlab", "-batch", f"disp(checkcode('{file_path}','-string'))"],
        capture_output=True, text=True, timeout=60,
    )
    return result.stdout or "No mlint warnings."

@tool("run_matlab_script", "Execute a MATLAB script and return stdout/stderr")
async def run_matlab_script(script_path: str, timeout_seconds: int = 300) -> str:
    """Runs a .m script in headless MATLAB and captures output."""
    import subprocess
    result = subprocess.run(
        ["matlab", "-batch", f"run('{script_path}')"],
        capture_output=True, text=True, timeout=timeout_seconds,
    )
    output = f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
    output += f"\n\nReturn code: {result.returncode}"
    return output

@tool("read_mat_summary", "Read a .mat file and return variable names, sizes, types")
async def read_mat_summary(mat_path: str) -> str:
    """Summarize contents of a .mat file without loading full arrays."""
    import subprocess
    cmd = f"s=whos('-file','{mat_path}'); for i=1:numel(s), fprintf('%s: %s [%s]\\n',s(i).name,mat2str(s(i).size),s(i).class); end"
    result = subprocess.run(
        ["matlab", "-batch", cmd],
        capture_output=True, text=True, timeout=60,
    )
    return result.stdout or "Could not read .mat file."

matlab_server = create_sdk_mcp_server(
    name="matlab-tools",
    tools=[run_mlint, run_matlab_script, read_mat_summary],
)
```

---

## 7. System Prompts Per Phase

Craft phase-specific system prompts. The SDK's `system_prompt` option accepts a string.

```python
SYSTEM_PROMPTS = {
    SprintPhase.PLAN: """You are a MATLAB/Simulink engineer planning a simulation sprint.
Read the sprint objective and any prior outputs. Produce a plan.md with:
- Approach summary (which ASM3/BSM blocks to modify)
- File manifest (list every .m file you will create/edit)
- Variable naming conventions (use snake_case, prefix with sim_)
- Expected output .mat file schema
- Risk items and mitigation
Do NOT write any MATLAB code yet.""",

    SprintPhase.GENERATE: """You are a MATLAB developer. Write production-quality .m files.
Rules:
1. Every function file starts with: function header block (name, purpose, inputs, outputs, author, date)
2. Use meaningful variable names; no single-letter vars except loop indices
3. Preallocate arrays; avoid grow-in-loop patterns
4. Add inline comments for non-obvious logic
5. All simulation parameters go in a params struct, not hardcoded
6. Write files ONLY to src/ under the current directory
7. If modifying Simulink models, use set_param/get_param; never open GUI""",

    SprintPhase.STATIC: """You are a code reviewer. mlint analysis results are provided.
For each warning:
- If it's a real issue, fix it in the source file
- If it's a false positive, add %#ok<RULE> suppression with a comment explaining why
Iterate until all warnings are resolved or justified.""",

    SprintPhase.UNIT_TEST: """You are a MATLAB test engineer. Write test functions in tests/.
Use the MATLAB unit testing framework (matlab.unittest).
Each test class should:
- Test one source function
- Include setup/teardown for temp files
- Have at least: a nominal case, an edge case, and an error case
- Use verifyEqual, verifyTrue, verifyError appropriately
- Print clear diagnostic messages on failure""",

    SprintPhase.VERIFY: """You are a V&V engineer reviewing simulation results.
Read the simulation output summary and acceptance criteria.
Produce verification_report.md with:
- Table of acceptance criteria: criterion | expected | actual | PASS/FAIL
- Any anomalies or warnings observed in the data
- Recommendation: ACCEPT / REVISE / REJECT this sprint
Be rigorous. A FAIL on any criterion means the sprint must be revised.""",
}
```

---

## 8. Orchestrator Main Loop

```python
import asyncio
import logging
from pathlib import Path
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage, TextBlock

log = logging.getLogger("orchestrator")

async def run_sprint(sprint: Sprint):
    sprint_dir = Path(f"./sprints/{sprint.id}")
    sprint_dir.mkdir(parents=True, exist_ok=True)
    (sprint_dir / "src").mkdir(exist_ok=True)
    (sprint_dir / "tests").mkdir(exist_ok=True)
    (sprint_dir / "data").mkdir(exist_ok=True)

    checkpoints = {}
    phase_order = [
        SprintPhase.PLAN,
        SprintPhase.GENERATE,
        SprintPhase.STATIC,
        SprintPhase.UNIT_TEST,
        SprintPhase.INTEGRATE,
        SprintPhase.VERIFY,
        SprintPhase.PACKAGE,
    ]

    for phase in phase_order:
        success = False
        for attempt in range(1, sprint.retry_limit + 1):
            log.info(f"Sprint {sprint.id} | Phase {phase.value} | Attempt {attempt}")

            # --- Save pre-phase checkpoint ---
            save_external_checkpoint(sprint, phase)

            # --- Build agent options for this phase ---
            options = ClaudeAgentOptions(
                model="claude-sonnet-4-5-20250929",
                system_prompt=SYSTEM_PROMPTS.get(phase, ""),
                max_turns=sprint.max_turns_per_phase.get(phase, 10),
                max_budget_usd=2.0,
                cwd=str(sprint_dir),
                allowed_tools=["Read", "Write", "Edit", "Bash", "Glob"],
                permission_mode="acceptEdits",
                enable_file_checkpointing=True,
                extra_args={"replay-user-messages": None},
                mcp_servers={"matlab-tools": matlab_server},
                hooks={**sandbox_hooks, **observability_hooks},
                effort="high",
            )

            # --- Compose the phase prompt ---
            prompt = compose_phase_prompt(sprint, phase, attempt)

            # --- Run agent session ---
            agent_output = []
            async with ClaudeSDKClient(options=options) as client:
                await client.query(prompt)
                async for msg in client.receive_response():
                    if isinstance(msg, UserMessage) and msg.uuid:
                        checkpoints[phase.value] = msg.uuid
                    if isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, TextBlock):
                                agent_output.append(block.text)

            full_output = "\n".join(agent_output)

            # --- Phase-specific verification ---
            if phase == SprintPhase.STATIC:
                success = await run_static_verification(sprint_dir)
            elif phase == SprintPhase.UNIT_TEST:
                success = await run_unit_tests(sprint_dir)
            elif phase == SprintPhase.INTEGRATE:
                success = await run_simulation(sprint, sprint_dir)
            elif phase == SprintPhase.VERIFY:
                success = "ACCEPT" in full_output
            else:
                success = True  # PLAN, GENERATE, PACKAGE succeed if agent completes

            if success:
                log.info(f"  ✓ Phase {phase.value} passed")
                break
            else:
                log.warning(f"  ✗ Phase {phase.value} failed (attempt {attempt})")
                if attempt < sprint.retry_limit:
                    log.info("  Rolling back and retrying...")

        if not success:
            log.error(f"Sprint {sprint.id} FAILED at phase {phase.value}")
            return False

    log.info(f"Sprint {sprint.id} COMPLETED successfully")
    return True


def compose_phase_prompt(sprint: Sprint, phase: SprintPhase, attempt: int) -> str:
    """Build the user prompt for a given phase."""
    context_parts = [
        f"# Sprint {sprint.id}: {sprint.title}",
        f"## Objective\n{sprint.objective}",
        f"## Acceptance Criteria",
        *[f"- {c}" for c in sprint.acceptance_criteria],
        f"\n## Current Phase: {phase.value} (attempt {attempt})",
    ]

    if phase == SprintPhase.GENERATE and attempt > 1:
        context_parts.append(
            "\nPrevious attempt failed static analysis or tests. "
            "Review the error log in data/last_error.log and fix the issues."
        )

    if phase == SprintPhase.VERIFY:
        context_parts.append(
            "\nSimulation outputs are in data/. Read the .mat summary "
            "and any CSV exports, then evaluate against acceptance criteria."
        )

    return "\n".join(context_parts)
```

---

## 9. Verification Routines

### 9.1 Static Analysis (mlint)

```python
async def run_static_verification(sprint_dir: Path) -> bool:
    import subprocess
    m_files = list((sprint_dir / "src").glob("*.m"))
    if not m_files:
        log.warning("No .m files found for static analysis")
        return False

    all_clean = True
    for mf in m_files:
        result = subprocess.run(
            ["matlab", "-batch", f"checkcode('{mf}','-string')"],
            capture_output=True, text=True, timeout=60,
        )
        if result.stdout.strip():
            log.warning(f"mlint issues in {mf.name}:\n{result.stdout}")
            (sprint_dir / "data" / "last_error.log").write_text(result.stdout)
            all_clean = False
    return all_clean
```

### 9.2 Unit Tests

```python
async def run_unit_tests(sprint_dir: Path) -> bool:
    import subprocess
    test_cmd = (
        f"cd('{sprint_dir}'); "
        f"addpath('src'); "
        f"results = runtests('tests'); "
        f"disp(table(results)); "
        f"exit(any([results.Failed]));"
    )
    result = subprocess.run(
        ["matlab", "-batch", test_cmd],
        capture_output=True, text=True, timeout=300,
    )
    passed = result.returncode == 0
    if not passed:
        (sprint_dir / "data" / "last_error.log").write_text(
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return passed
```

### 9.3 Full Simulation

```python
async def run_simulation(sprint: Sprint, sprint_dir: Path) -> bool:
    import subprocess
    sim_cmd = (
        f"cd('{sprint_dir / 'src'}'); "
        f"try, "
        f"  {Path(sprint.matlab_entry_point).stem}; "  # run main script
        f"  fprintf('SIM_SUCCESS\\n'); "
        f"catch e, "
        f"  fprintf('SIM_FAILURE: %s\\n', e.message); "
        f"  exit(1); "
        f"end"
    )
    result = subprocess.run(
        ["matlab", "-batch", sim_cmd],
        capture_output=True, text=True, timeout=1800,  # 30 min for long sims
    )
    success = "SIM_SUCCESS" in result.stdout
    # Save output regardless
    (sprint_dir / "data" / "sim_stdout.log").write_text(result.stdout)
    (sprint_dir / "data" / "sim_stderr.log").write_text(result.stderr)
    if not success:
        (sprint_dir / "data" / "last_error.log").write_text(result.stdout + result.stderr)
    return success
```

---

## 10. Best Practices Checklist

### Agent Configuration
- [ ] Set `max_turns` per phase — prevents infinite loops
- [ ] Set `max_budget_usd` per sprint — hard cost ceiling
- [ ] Use `permission_mode="acceptEdits"` in sandboxed environments only
- [ ] Enable `file_checkpointing` for every session
- [ ] Set `cwd` to the sprint-specific directory to confine writes
- [ ] Use `effort="high"` for complex reasoning; `"medium"` for boilerplate phases

### Sandboxing & Safety
- [ ] PreToolUse hooks block writes outside sprint directory
- [ ] PreToolUse hooks block dangerous Bash patterns
- [ ] Agent has no network access (no curl/wget/pip)
- [ ] MATLAB is invoked via subprocess, not agent-initiated install
- [ ] External checkpoint copies exist before every phase

### System Prompts
- [ ] Phase-specific prompts constrain agent behavior
- [ ] Coding standards are explicit (naming, comments, structure)
- [ ] Agent is told NOT to do things outside current phase scope
- [ ] Retry prompts reference the specific failure from the prior attempt

### Verification
- [ ] Static analysis (mlint) runs after every GENERATE phase
- [ ] Unit tests use MATLAB's built-in framework (`matlab.unittest`)
- [ ] Test results are parsed programmatically (return code + xUnit XML)
- [ ] Full simulation has a timeout (30 min default, configurable)
- [ ] Simulation success/failure is determined by explicit markers in stdout
- [ ] Verification phase produces a structured PASS/FAIL report

### Data Integrity
- [ ] All `.mat` outputs live in `data/` under the sprint directory
- [ ] Error logs persist across retries (`last_error.log`)
- [ ] External checkpoints include metadata JSON
- [ ] Sprint directories are never deleted — only archived
- [ ] Git or similar VCS tracks sprint progression (optional but recommended)

### Observability
- [ ] PostToolUse hooks log every tool invocation with timestamps
- [ ] Sprint-level metrics: total cost, turns used, time elapsed per phase
- [ ] Agent stop reasons are captured and logged
- [ ] Failed phases produce diagnosable error context for retry prompts

### Multi-Session / Multi-Sprint
- [ ] Each sprint gets a fresh `ClaudeSDKClient` session
- [ ] Prior sprint outputs can be referenced via `add_dirs` option
- [ ] Compaction is handled automatically by the SDK for long sessions
- [ ] Subagents can parallelize independent verification tasks

---

## 11. SDK Feature Reference (Quick Look)

| Feature | API | Use Case |
|---|---|---|
| One-shot query | `query(prompt, options)` | Simple single-phase execution |
| Interactive session | `ClaudeSDKClient` | Multi-turn phases, retries, rollback |
| Custom tools | `create_sdk_mcp_server()` + `@tool` | MATLAB integration (mlint, run, mat read) |
| Hooks — PreToolUse | `HookMatcher(matcher="Bash")` | Sandbox enforcement |
| Hooks — PostToolUse | `HookMatcher(matcher=None)` | Logging, metrics |
| Hooks — Stop | `"Stop"` event | Phase completion capture |
| File checkpointing | `enable_file_checkpointing=True` | Roll back failed phase file changes |
| File rewind | `client.rewind_files(uuid)` | Restore to pre-phase state |
| Subagents | SDK-native | Parallel verification, context isolation |
| Compaction | Automatic | Long-running sessions |
| Structured outputs | `output_format={...}` | Force JSON schema for verification reports |
| Cost tracking | `max_budget_usd` | Per-sprint budgeting |
| Sandbox mode | `sandbox={"enabled": True}` | Docker-isolated execution |
| Extended context | `betas=["context-1m-2025-08-07"]` | Large codebases in context |

---

## 12. Suggested Next Steps

1. **Scaffold the project** — Create the directory structure (`sprints/`, `checkpoints/`, `config/`) and a `pyproject.toml` with `claude-agent-sdk` as a dependency.
2. **Implement Sprint definitions** — Encode your BSM/ASM3 perturbation-recovery campaigns as Sprint dataclass instances.
3. **Build custom MATLAB tools** — Start with `run_mlint` and `run_matlab_script`; test them independently before wiring into the agent.
4. **Test a single sprint end-to-end** — Run one sprint through all phases manually (using `query()` for simplicity) to validate prompts and verification logic.
5. **Add hooks and checkpointing** — Layer in sandbox enforcement and file checkpointing once the happy path works.
6. **Graduate to `ClaudeSDKClient`** — Switch from one-shot `query()` to the interactive client for multi-turn retry logic within phases.
7. **Parallelize with subagents** — Use subagents for independent tasks like running mlint on multiple files simultaneously.

---

*Generated as a starting-point reference. Adapt the sprint definitions, system prompts, and verification thresholds to your specific BSM/ASM3 campaign protocols.*