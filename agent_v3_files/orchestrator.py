#!/usr/bin/env python3
"""
BSM Dynamic Aeration Experiment — Refactoring Orchestrator
===========================================================
Uses the Claude Agent SDK to drive an agentic developer through the
sprint-based implementation plan for the BSM/ASM3 simulation codebase.
Current phase (v3): adding reduction-day patterns, midnight-wrapping
support, and active-day-only aeration energy averaging.
Requirements:
    pip install claude-agent-sdk anyio
    export ANTHROPIC_API_KEY=sk-ant-...
    MATLAB R2023b+ on PATH  (for verification phases)
Usage:
    python orchestrator.py                    # run all sprints
    python orchestrator.py --sprint S02       # run a single sprint
    python orchestrator.py --resume S03       # resume from sprint S03
    python orchestrator.py --dry-run          # validate config, no agent calls
"""
from __future__ import annotations
import argparse
import asyncio
import json
import logging
import shutil
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
# ---------------------------------------------------------------------------
# Claude Agent SDK imports
# ---------------------------------------------------------------------------
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
# ---------------------------------------------------------------------------
# Project config imports
# ---------------------------------------------------------------------------
from config import (
    BASE_CONTEXT,
    DEFAULT_MODEL,
    PHASE_PROMPTS,
    Sprint,
    SprintPhase,
    SPRINTS,
    build_matlab_mcp_server,
    run_matlab_cmd,
)
# ═══════════════════════════════════════════════════════════════════════════
# §1  PATH CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════
# All paths are relative to the project root (where orchestrator.py lives)
PROJECT_ROOT = Path(__file__).resolve().parent
REFERENCE_DIR  = PROJECT_ROOT / "reference"     # read-only source material
SPRINTS_DIR    = PROJECT_ROOT / "sprints"        # agent working directories
CHECKPOINT_DIR = PROJECT_ROOT / "checkpoints"    # external checkpoint archives
OUTPUT_DIR     = PROJECT_ROOT / "verified_outputs"  # promoted sprint results
LOGS_DIR       = PROJECT_ROOT / "logs"           # orchestrator logs + metrics
# Agent model configuration
FALLBACK_MODEL = "claude-haiku-4-5-20251001"
HIGH_REASONING_MODEL = "claude-sonnet-4-5-20250929"
# Budget guardrails
MAX_BUDGET_PER_SPRINT = 15.0   # USD
MAX_BUDGET_PER_PHASE  = 12.0   # USD
# ═══════════════════════════════════════════════════════════════════════════
# §2  LOGGING
# ═══════════════════════════════════════════════════════════════════════════
LOG_FMT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
log = logging.getLogger("bsm_orchestrator")
def setup_logging(verbose: bool = False):
    """Configure console + file logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format=LOG_FMT)
    # File handler → logs/orchestrator.log
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(LOGS_DIR / "orchestrator.log", mode="a")
    fh.setLevel(level)
    fh.setFormatter(logging.Formatter(LOG_FMT))
    logging.getLogger().addHandler(fh)
# ═══════════════════════════════════════════════════════════════════════════
# §3  HOOKS — SANDBOXING & OBSERVABILITY
# ═══════════════════════════════════════════════════════════════════════════
class SprintMetrics:
    """Accumulates tool-use metrics and timing for a sprint."""
    def __init__(self, sprint_id: str):
        self.sprint_id = sprint_id
        self.tool_calls: list[dict] = []
        self.phase_timings: dict[str, float] = {}
        self.start_time = time.time()
    def record_tool_call(self, tool_name: str, tool_use_id: str | None):
        self.tool_calls.append({
            "tool": tool_name,
            "tool_use_id": tool_use_id,
            "elapsed_s": time.time() - self.start_time,
        })
    def to_dict(self) -> dict:
        return {
            "sprint_id": self.sprint_id,
            "total_elapsed_s": time.time() - self.start_time,
            "total_tool_calls": len(self.tool_calls),
            "phase_timings": self.phase_timings,
            "tool_calls": self.tool_calls,
        }
    def append_to_metrics_log(self):
        """Append sprint metrics as a JSON line to logs/tool_metrics.jsonl."""
        metrics_file = LOGS_DIR / "tool_metrics.jsonl"
        with open(metrics_file, "a") as f:
            f.write(json.dumps(self.to_dict()) + "\n")
def build_hooks(sprint_dir: Path, metrics: SprintMetrics) -> dict:
    """Build hook configuration for sandbox enforcement and observability."""
    allowed_root = str(sprint_dir.resolve())
    async def enforce_sandbox(input_data, tool_use_id, context):
        tool = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})
        # Block writes outside sprint directory
        if tool in ("Write", "Edit", "MultiEdit"):
            file_path = tool_input.get("file_path", "")
            resolved = str(Path(file_path).resolve()) if file_path else ""
            if resolved and not resolved.startswith(allowed_root):
                log.warning(f"SANDBOX DENY: Write to {file_path} outside {allowed_root}")
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason":
                            f"Write blocked: {file_path} is outside sprint sandbox {allowed_root}",
                    }
                }
        # Block dangerous bash patterns
        if tool == "Bash":
            cmd = tool_input.get("command", "")
            blocked_patterns = [
                "rm -rf /", "rm -rf ~", "sudo ", "chmod 777",
                "pip install", "npm install",
                "curl ", "wget ", "ssh ",
                "> /dev/sd",
            ]
            for pattern in blocked_patterns:
                if pattern in cmd:
                    log.warning(f"SANDBOX DENY: Bash command contains '{pattern}'")
                    return {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason":
                                f"Bash blocked: contains forbidden pattern '{pattern}'",
                        }
                    }
        return {}
    async def log_tool_use(input_data, tool_use_id, context):
        tool_name = input_data.get("tool_name", "unknown")
        metrics.record_tool_call(tool_name, tool_use_id)
        return {}
    return {
        "PreToolUse": [
            HookMatcher(matcher="Write|Edit|MultiEdit", hooks=[enforce_sandbox]),
            HookMatcher(matcher="Bash", hooks=[enforce_sandbox]),
        ],
        "PostToolUse": [
            HookMatcher(matcher=None, hooks=[log_tool_use]),
        ],
    }
# ═══════════════════════════════════════════════════════════════════════════
# §4  CHECKPOINTING
# ═══════════════════════════════════════════════════════════════════════════
def save_external_checkpoint(sprint: Sprint, phase: SprintPhase, sprint_dir: Path) -> Path:
    """Archive the sprint working directory as an external checkpoint."""
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    ckpt_dir = CHECKPOINT_DIR / sprint.id / f"{phase.value}_{ts}"
    ckpt_dir.parent.mkdir(parents=True, exist_ok=True)
    if sprint_dir.exists():
        shutil.copytree(sprint_dir, ckpt_dir, dirs_exist_ok=True)
    meta = {
        "sprint_id": sprint.id,
        "sprint_title": sprint.title,
        "phase": phase.value,
        "timestamp": ts,
        "acceptance_criteria": sprint.acceptance_criteria,
    }
    (ckpt_dir / "checkpoint_meta.json").write_text(json.dumps(meta, indent=2))
    log.info(f"  Checkpoint saved: {ckpt_dir}")
    return ckpt_dir
def promote_to_output(sprint: Sprint, sprint_dir: Path):
    """Copy verified sprint outputs to the final output directory."""
    dest = OUTPUT_DIR / sprint.id
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(sprint_dir, dest)
    log.info(f"  Promoted outputs: {dest}")
# ═══════════════════════════════════════════════════════════════════════════
# §5  PROMPT COMPOSITION
# ═══════════════════════════════════════════════════════════════════════════
def compose_prompt(
    sprint: Sprint,
    phase: SprintPhase,
    attempt: int,
    error_context: str = "",
    prior_output: str = "",
) -> str:
    """Assemble the full user prompt for a given sprint + phase + attempt."""
    parts = [
        f"# Sprint {sprint.id}: {sprint.title}",
        f"## Objective\n{sprint.objective}",
        "## Acceptance Criteria",
        *[f"- {c}" for c in sprint.acceptance_criteria],
        f"\n## Current Phase: {phase.value} (attempt {attempt}/{sprint.retry_limit})",
    ]
    if sprint.files_to_create:
        parts.append(
            "\n## Files to Create\n"
            + "\n".join(f"- `{f}`" for f in sprint.files_to_create)
        )
    if sprint.files_to_modify:
        parts.append(
            "\n## Files to Modify\n"
            + "\n".join(f"- `{f}`" for f in sprint.files_to_modify)
        )
        if phase == SprintPhase.GENERATE:
            parts.append(
                "\n## ⚠ ACTION REQUIRED\n"
                "You MUST modify the file(s) listed above in this session. "
                "Start by reading each file with the Read tool to understand "
                "its current structure, then apply the changes described in "
                "the Objective using the Edit or MultiEdit tool.\n"
                "Do NOT just describe what you would change — make the edits now."
            )
    if sprint.reference_files:
        parts.append(
            "\n## Reference Files (read-only, in reference/)\n"
            + "\n".join(f"- `reference/{f}`" for f in sprint.reference_files)
        )
    if attempt > 1 and error_context:
        parts.append(
            f"\n## ⚠ Previous Attempt Failed\n"
            f"Error details:\n```\n{error_context}\n```"
        )
        parts.append("Fix the issues identified above.  Do not repeat the same mistakes.")
    if prior_output and phase in (SprintPhase.VERIFY, SprintPhase.INTEGRATE):
        parts.append(f"\n## Prior Phase Output\n```\n{prior_output[:4000]}\n```")
    return "\n".join(parts)
# ═══════════════════════════════════════════════════════════════════════════
# §6  VERIFICATION ROUTINES
# ═══════════════════════════════════════════════════════════════════════════
async def run_static_analysis(sprint_dir: Path) -> tuple[bool, str]:
    """Run mlint on all .m files in the sprint directory."""
    m_files = list(sprint_dir.rglob("*.m"))
    if not m_files:
        return False, "No .m files found for static analysis"
    all_output = []
    all_clean = True
    for mf in m_files:
        rel = mf.relative_to(sprint_dir)
        result = run_matlab_cmd(
            f"msgs = checkcode('{mf}', '-string'); "
            f"if isempty(msgs), disp('CLEAN'); else, disp(msgs); end",
            cwd=sprint_dir,
        )
        stdout = result["stdout"].strip()
        if stdout and "CLEAN" not in stdout:
            all_clean = False
            all_output.append(f"--- {rel} ---\n{stdout}")
        else:
            all_output.append(f"--- {rel} --- CLEAN")
    return all_clean, "\n".join(all_output)
async def run_matlab_tests_for_sprint(sprint: Sprint, sprint_dir: Path) -> tuple[bool, str]:
    """Execute the sprint's MATLAB test command."""
    if not sprint.matlab_test_cmd:
        log.info("  No MATLAB test command defined — skipping")
        return True, "No tests defined"
    result = run_matlab_cmd(
        f"cd('{sprint_dir}'); {sprint.matlab_test_cmd}",
        timeout=300,
        cwd=sprint_dir,
    )
    passed = result["returncode"] == "0"
    output = (
        f"STDOUT:\n{result['stdout']}\n"
        f"STDERR:\n{result['stderr']}\n"
        f"Return code: {result['returncode']}"
    )
    return passed, output
# ═══════════════════════════════════════════════════════════════════════════
# §7  PHASE EXECUTOR
# ═══════════════════════════════════════════════════════════════════════════
async def execute_phase(
    sprint: Sprint,
    phase: SprintPhase,
    sprint_dir: Path,
    attempt: int,
    metrics: SprintMetrics,
    error_context: str = "",
    prior_output: str = "",
) -> tuple[bool, str]:
    """
    Execute a single phase of a sprint.
    Returns (success: bool, output_or_error: str).
    """
    log.info(f"  Phase {phase.value} — attempt {attempt}")
    phase_start = time.time()
    # ── Save checkpoint before the phase ──
    save_external_checkpoint(sprint, phase, sprint_dir)
    # ── Build agent options ──
    system_prompt = BASE_CONTEXT + "\n\n" + PHASE_PROMPTS.get(phase, "")
    matlab_server = build_matlab_mcp_server()
    options = ClaudeAgentOptions(
        model=sprint.model,
        fallback_model=FALLBACK_MODEL,
        system_prompt=system_prompt,
        max_turns=sprint.max_turns_per_phase.get(phase, 15),
        max_budget_usd=MAX_BUDGET_PER_PHASE,
        cwd=str(sprint_dir),
        allowed_tools=["Read", "Write", "Edit", "MultiEdit", "Bash", "Glob"],
        permission_mode="acceptEdits",
        enable_file_checkpointing=True,
        extra_args={"replay-user-messages": None},
        mcp_servers={"matlab-tools": matlab_server},
        hooks=build_hooks(sprint_dir, metrics),
        effort="high",
    )
    # ── Compose the prompt ──
    prompt = compose_prompt(sprint, phase, attempt, error_context, prior_output)
    if phase == SprintPhase.GENERATE:
        log.info(f"  [DEBUG] GENERATE prompt ({len(prompt)} chars):\n{prompt[:2000]}")
    # ── Run the agent session ──
    agent_text_output: list[str] = []
    checkpoint_uuids: list[str] = []
    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)
            async for msg in client.receive_response():
                if isinstance(msg, UserMessage) and msg.uuid:
                    checkpoint_uuids.append(msg.uuid)
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            agent_text_output.append(block.text)
                        elif isinstance(block, ToolUseBlock):
                            log.debug(f"    Tool call: {block.name}")
                        elif isinstance(block, ToolResultBlock):
                            log.debug("    Tool result received")
    except Exception as e:
        log.error(f"  Agent session error: {e}")
        metrics.phase_timings[phase.value] = time.time() - phase_start
        return False, f"Agent session error: {e}"
    full_output = "\n".join(agent_text_output)
    log.info(
        f"  [DEBUG] Agent output ({len(agent_text_output)} blocks, "
        f"{len(full_output)} chars): {full_output[:500]}"
    )
    metrics.phase_timings[phase.value] = time.time() - phase_start
    # ── Phase-specific post-processing and verification ──
    if phase == SprintPhase.STATIC:
        success, analysis = await run_static_analysis(sprint_dir)
        return success, analysis
    elif phase == SprintPhase.UNIT_TEST:
        success, test_output = await run_matlab_tests_for_sprint(sprint, sprint_dir)
        return success, test_output
    elif phase == SprintPhase.INTEGRATE:
        success, test_output = await run_matlab_tests_for_sprint(sprint, sprint_dir)
        return success, test_output
    elif phase == SprintPhase.VERIFY:
        if "ACCEPT" in full_output:
            return True, full_output
        elif "REJECT" in full_output or "REVISE" in full_output:
            return False, full_output
        else:
            log.warning("  Verification phase did not produce a clear verdict")
            return True, full_output
    else:
        # PLAN, GENERATE, PACKAGE — succeed if agent completes without error
        # For GENERATE on modify-in-place sprints: verify the file was actually changed
        if phase == SprintPhase.GENERATE and sprint.files_to_modify:
            for mod_file in sprint.files_to_modify:
                target = sprint_dir / mod_file
                reference = sprint_dir / "reference" / "codebase" / mod_file
                if reference.exists() and target.exists():
                    if target.read_bytes() == reference.read_bytes():
                        return False, (
                            f"GENERATE did not modify {mod_file} — "
                            f"file is identical to the reference copy. "
                            f"Read the file, then use Edit or MultiEdit to "
                            f"apply the changes described in the Objective."
                        )
        return True, full_output
# ═══════════════════════════════════════════════════════════════════════════
# §8  SPRINT EXECUTOR
# ═══════════════════════════════════════════════════════════════════════════
async def run_sprint(sprint: Sprint) -> bool:
    """Execute all phases of a sprint with retry logic."""
    log.info(f"{'='*60}")
    log.info(f"SPRINT {sprint.id}: {sprint.title}")
    log.info(f"{'='*60}")
    # ── Prepare sprint working directory ──
    sprint_dir = SPRINTS_DIR / sprint.id
    sprint_dir.mkdir(parents=True, exist_ok=True)
    (sprint_dir / "src").mkdir(exist_ok=True)
    (sprint_dir / "tests").mkdir(exist_ok=True)
    (sprint_dir / "data").mkdir(exist_ok=True)
    (sprint_dir / "reference").mkdir(exist_ok=True)
    # ── Copy reference files into sprint_dir/reference/ ──
    for ref_rel_path in sprint.reference_files:
        src = REFERENCE_DIR / ref_rel_path
        dst = sprint_dir / "reference" / ref_rel_path
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            log.info(f"  Copied reference: {ref_rel_path}")
        else:
            log.warning(f"  Reference file not found: {src}")
    # ── Copy outputs from dependency sprints (FIRST — takes priority) ──
    #    Modified files from prior sprints should be used instead of the
    #    original reference codebase versions.
    for dep_id in sprint.depends_on:
        dep_output = OUTPUT_DIR / dep_id
        if dep_output.exists():
            # Root-level files (modified .m files from prior sprints)
            for f in dep_output.iterdir():
                if f.is_file() and f.suffix == '.m':
                    dst = sprint_dir / f.name
                    if not dst.exists():
                        shutil.copy2(f, dst)
                        log.info(f"  Inherited from {dep_id}: {f.name}")
            # Subdirectory files (src/, tests/)
            for subdir in ["src", "tests"]:
                dep_sub = dep_output / subdir
                if dep_sub.exists():
                    for f in dep_sub.iterdir():
                        if f.is_file():
                            dst = sprint_dir / subdir / f.name
                            if not dst.exists():
                                shutil.copy2(f, dst)
                                log.info(f"  Inherited from {dep_id}: {subdir}/{f.name}")
    # ── Copy files-to-modify into sprint dir root (FALLBACK) ──
    #    These are files the agent will read and edit in-place.
    #    Only copies from reference/codebase/ if not already inherited
    #    from a dependency sprint above.
    for mod_file in sprint.files_to_modify:
        dst = sprint_dir / mod_file
        if dst.exists():
            continue  # already inherited from a dependency or prior run
        # Fall back to the reference codebase
        src = REFERENCE_DIR / "codebase" / mod_file
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            log.info(f"  Copied for modification: {mod_file}")
    metrics = SprintMetrics(sprint.id)
    # ── Phase execution loop ──
    phase_order = [
        SprintPhase.PLAN,
        SprintPhase.GENERATE,
        SprintPhase.STATIC,
        SprintPhase.UNIT_TEST,
        SprintPhase.INTEGRATE,
        SprintPhase.VERIFY,
        SprintPhase.PACKAGE,
    ]
    last_output = ""
    for phase in phase_order:
        if phase in sprint.skip_phases:
            log.info(f"  Skipping phase: {phase.value}")
            continue
        success = False
        error_context = ""
        for attempt in range(1, sprint.retry_limit + 1):
            success, output = await execute_phase(
                sprint=sprint,
                phase=phase,
                sprint_dir=sprint_dir,
                attempt=attempt,
                metrics=metrics,
                error_context=error_context,
                prior_output=last_output,
            )
            if success:
                log.info(f"  ✓ Phase {phase.value} PASSED")
                last_output = output
                break
            else:
                log.warning(
                    f"  ✗ Phase {phase.value} FAILED "
                    f"(attempt {attempt}/{sprint.retry_limit})"
                )
                error_context = output
                if attempt < sprint.retry_limit:
                    log.info(f"  Retrying phase {phase.value}...")
        if not success:
            log.error(
                f"  SPRINT {sprint.id} FAILED at phase {phase.value} "
                f"after {sprint.retry_limit} attempts"
            )
            # Save failure metrics
            metrics_path = sprint_dir / "data" / "sprint_metrics.json"
            metrics_path.write_text(json.dumps(metrics.to_dict(), indent=2))
            metrics.append_to_metrics_log()
            return False
    # ── Sprint completed successfully ──
    metrics_path = sprint_dir / "data" / "sprint_metrics.json"
    metrics_path.write_text(json.dumps(metrics.to_dict(), indent=2))
    metrics.append_to_metrics_log()
    promote_to_output(sprint, sprint_dir)
    log.info(f"  ✓ SPRINT {sprint.id} COMPLETED")
    log.info(f"  Total tool calls: {len(metrics.tool_calls)}")
    log.info(f"  Total elapsed: {time.time() - metrics.start_time:.1f}s")
    return True
# ═══════════════════════════════════════════════════════════════════════════
# §9  CAMPAIGN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════
async def run_campaign(
    sprints: list[Sprint],
    start_from: str | None = None,
    single_sprint: str | None = None,
    dry_run: bool = False,
):
    """Execute a sequence of sprints with dependency resolution."""
    # ── Ensure working directories exist ──
    SPRINTS_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    # ── Filter sprints if requested ──
    if single_sprint:
        sprints = [s for s in sprints if s.id == single_sprint]
        if not sprints:
            log.error(f"Sprint '{single_sprint}' not found")
            return
    if start_from:
        ids = [s.id for s in sprints]
        if start_from not in ids:
            log.error(f"Sprint '{start_from}' not found for resume")
            return
        idx = ids.index(start_from)
        sprints = sprints[idx:]
        log.info(f"Resuming from sprint {start_from}")
    # ── Validate dependencies ──
    completed_ids: set[str] = set()
    for s in SPRINTS:
        if (OUTPUT_DIR / s.id).exists():
            completed_ids.add(s.id)
    log.info(f"Previously completed sprints: {completed_ids or 'none'}")
    # ── Dry run ──
    if dry_run:
        log.info("DRY RUN — validating sprint configuration:")
        for s in sprints:
            missing_deps = [d for d in s.depends_on if d not in completed_ids]
            status = "READY" if not missing_deps else f"BLOCKED (needs: {missing_deps})"
            log.info(f"  {s.id}: {s.title} — {status}")
            log.info(f"    Phases: {[p.value for p in SprintPhase if p not in s.skip_phases]}")
            log.info(f"    Create: {s.files_to_create}")
            log.info(f"    Modify: {s.files_to_modify}")
            log.info(f"    Refs:   {s.reference_files}")
        # Validate reference directory exists
        if not REFERENCE_DIR.exists():
            log.warning(f"Reference directory not found: {REFERENCE_DIR}")
        else:
            for subdir in ["codebase", "docs"]:
                d = REFERENCE_DIR / subdir
                if d.exists():
                    files = list(d.iterdir())
                    log.info(f"  reference/{subdir}/: {len(files)} files")
                else:
                    log.warning(f"  reference/{subdir}/: MISSING")
        return
    # ── Execute sprints ──
    campaign_start = time.time()
    results: dict[str, bool] = {}
    for sprint in sprints:
        # Check dependencies
        missing = [d for d in sprint.depends_on if d not in completed_ids]
        if missing:
            log.error(f"Sprint {sprint.id} blocked — missing dependencies: {missing}")
            results[sprint.id] = False
            break
        success = await run_sprint(sprint)
        results[sprint.id] = success
        if success:
            completed_ids.add(sprint.id)
        else:
            log.error(f"Campaign halted at sprint {sprint.id}")
            break
    # ── Summary ──
    elapsed = time.time() - campaign_start
    log.info(f"\n{'='*60}")
    log.info("CAMPAIGN SUMMARY")
    log.info(f"{'='*60}")
    for sid, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        log.info(f"  {sid}: {status}")
    log.info(f"Total elapsed: {elapsed:.1f}s")
    # Save campaign summary
    summary = {
        "timestamp": datetime.now().isoformat(),
        "results": {k: ("PASS" if v else "FAIL") for k, v in results.items()},
        "elapsed_seconds": elapsed,
    }
    summary_path = LOGS_DIR / "campaign_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    log.info(f"Campaign summary: {summary_path}")
# ═══════════════════════════════════════════════════════════════════════════
# §10  CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="BSM Dynamic Aeration Refactoring Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python orchestrator.py                      Run all 6 sprints
  python orchestrator.py --sprint S01         Run only sprint S01
  python orchestrator.py --resume S03         Resume from sprint S03
  python orchestrator.py --dry-run            Validate config
  python orchestrator.py --list               List all sprints
""",
    )
    parser.add_argument("--sprint", type=str, help="Run a single sprint by ID")
    parser.add_argument("--resume", type=str, help="Resume from a specific sprint")
    parser.add_argument("--dry-run", action="store_true", help="Validate config without running")
    parser.add_argument("--list", action="store_true", help="List all sprints and exit")
    parser.add_argument("--model", type=str, help="Override model for all sprints")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    args = parser.parse_args()
    # Set up logging (console + file)
    setup_logging(verbose=args.verbose)
    if args.model:
        for s in SPRINTS:
            s.model = args.model
    # List mode
    if args.list:
        print(f"\n{'ID':<6} {'Title':<50} {'Deps':<12} {'Skip'}")
        print("-" * 90)
        for s in SPRINTS:
            deps = ", ".join(s.depends_on) if s.depends_on else "—"
            skips = ", ".join(p.value for p in s.skip_phases) if s.skip_phases else "—"
            print(f"{s.id:<6} {s.title:<50} {deps:<12} {skips}")
        return
    # Validate reference directory
    if not REFERENCE_DIR.exists():
        log.warning(
            f"Reference directory not found: {REFERENCE_DIR}\n"
            f"The orchestrator will still run but reference file copying will fail.\n"
            f"Run the setup script to populate reference/."
        )
    log.info(f"Project root: {PROJECT_ROOT}")
    log.info(f"Reference:    {REFERENCE_DIR}")
    log.info(f"Sprints dir:  {SPRINTS_DIR}")
    log.info(f"Sprints:      {len(SPRINTS)}")
    # Run
    asyncio.run(
        run_campaign(
            sprints=SPRINTS,
            single_sprint=args.sprint,
            start_from=args.resume,
            dry_run=args.dry_run,
        )
    )
if __name__ == "__main__":
    main()