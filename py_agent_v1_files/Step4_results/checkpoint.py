"""
config/checkpoint.py
Crash-safe checkpointing for sprint-based agent execution on preemptible
VMs (GCP spot instances, AWS spot, etc.).

USAGE BY ORCHESTRATOR:
    from config.checkpoint import (
        CheckpointManager,
        install_preemption_handler,
        safe_write_file,
    )

    # 1. Install preemption handler early in main()
    mgr = CheckpointManager(checkpoint_path="checkpoint.json", project_root=".")
    install_preemption_handler(mgr)

    # 2. Load existing checkpoint (returns empty state if none)
    state = mgr.load()

    # 3. In the sprint loop, check completion before running
    for sprint in SPRINTS:
        if mgr.is_sprint_completed(sprint.id):
            continue
        if not mgr.are_dependencies_met(sprint):
            continue

        for phase in SprintPhase:
            if phase in sprint.skip_phases:
                mgr.mark_phase_skipped(sprint.id, phase)
                continue
            if mgr.is_phase_completed(sprint.id, phase):
                continue

            mgr.mark_phase_started(sprint.id, phase)

            # ... run agent for this phase ...

            mgr.mark_phase_completed(sprint.id, phase)
            # ^ This writes checkpoint.json to disk atomically.
            #   If VM is killed between mark_started and mark_completed,
            #   the phase will be re-run on resume.

        mgr.mark_sprint_completed(sprint.id)

    # 4. On resume after preemption, the loop above simply skips
    #    completed sprints/phases and resumes from the first incomplete one.

PREEMPTION HANDLING:
    GCP sends SIGTERM 30 seconds before killing a spot VM.  The
    install_preemption_handler() function catches this signal and:
      1. Writes the current checkpoint state to disk.
      2. Logs the preemption event.
      3. Exits cleanly (exit code 3 = preempted).

    The orchestrator's outer runner (systemd, supervisor, or a GCP
    startup script) should detect exit code 3 and restart the process.

FILE INTEGRITY:
    After each phase completion, the CheckpointManager computes SHA-256
    checksums of all files in the project that have been modified.  On
    resume, verify_file_integrity() compares current checksums against
    the saved ones.  If any file was corrupted by a mid-write preemption,
    the manager identifies which sprint last modified it so the
    orchestrator can re-run that sprint.

NSGA-II RESUME:
    The OptimizationCheckpoint class wraps pymoo's callback mechanism to
    save evolutionary state after each generation.  On resume, it
    restores the algorithm object so optimization continues from the
    last completed generation rather than restarting.

ATOMIC WRITES:
    safe_write_file() writes to a temp file and renames (atomic on POSIX).
    Use this for all file creation/modification in tools and agent actions
    to prevent corrupted files on preemption.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pickle
import signal
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("checkpoint")


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

EXIT_PREEMPTED = 3      # VM preemption detected — restart expected
EXIT_INTEGRITY = 4      # File integrity check failed — manual review needed


# ---------------------------------------------------------------------------
# Phase and sprint status enums
# ---------------------------------------------------------------------------

class SprintStatus(str, Enum):
    PENDING     = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED   = "completed"
    FAILED      = "failed"


class PhaseStatus(str, Enum):
    PENDING     = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED   = "completed"
    SKIPPED     = "skipped"
    FAILED      = "failed"


# ---------------------------------------------------------------------------
# Checkpoint data structures
# ---------------------------------------------------------------------------

@dataclass
class PhaseState:
    """State of a single phase within a sprint."""
    status: PhaseStatus = PhaseStatus.PENDING
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    turn_count: int = 0
    retry_count: int = 0


@dataclass
class SprintState:
    """State of a single sprint."""
    status: SprintStatus = SprintStatus.PENDING
    phases: dict[str, PhaseState] = field(default_factory=dict)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    files_modified: list[str] = field(default_factory=list)


@dataclass
class CheckpointState:
    """Full checkpoint state serialized to disk."""
    project: str = "leyp-water-refactor"
    sprints: dict[str, SprintState] = field(default_factory=dict)
    file_checksums: dict[str, str] = field(default_factory=dict)
    last_checkpoint: Optional[str] = None
    preemption_count: int = 0
    total_elapsed_seconds: float = 0.0
    start_time: Optional[str] = None


# ---------------------------------------------------------------------------
# Atomic file writes
# ---------------------------------------------------------------------------

def safe_write_file(path: str | Path, content: str | bytes) -> None:
    """Write a file atomically using tmp-file + rename.

    If the VM is killed during this function, either the old file is
    intact (kill during write to tmp) or the new file is intact (kill
    after rename).  Never a half-written state.

    Args:
        path: Destination file path.
        content: File content (str for text, bytes for binary).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")

    mode = "w" if isinstance(content, str) else "wb"
    with open(tmp_path, mode) as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())

    os.replace(str(tmp_path), str(path))


def safe_write_json(path: str | Path, data: dict) -> None:
    """Atomically write a JSON file with pretty formatting."""
    content = json.dumps(data, indent=2, default=str, sort_keys=False)
    safe_write_file(path, content)


# ---------------------------------------------------------------------------
# File integrity helpers
# ---------------------------------------------------------------------------

def compute_checksum(file_path: str | Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_project_checksums(
    project_root: str | Path,
    extensions: tuple[str, ...] = (".py", ".yaml", ".yml", ".csv"),
    exclude_dirs: tuple[str, ...] = (
        "__pycache__", ".git", "node_modules", ".mypy_cache", "tests",
    ),
) -> dict[str, str]:
    """Compute checksums for all tracked files in the project.

    Args:
        project_root: Root directory to scan.
        extensions: File extensions to include.
        exclude_dirs: Directory names to skip.

    Returns:
        dict mapping relative file paths to SHA-256 hex digests.
    """
    checksums = {}
    root = Path(project_root)
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if any(excl in path.parts for excl in exclude_dirs):
            continue
        if path.suffix not in extensions:
            continue
        rel = str(path.relative_to(root))
        try:
            checksums[rel] = compute_checksum(path)
        except OSError:
            logger.warning("Could not checksum %s", rel)
    return checksums


# ---------------------------------------------------------------------------
# CheckpointManager
# ---------------------------------------------------------------------------


def _safe_enum(value: str | None, enum_cls: type, default):
    """Convert a string to an enum value, falling back to default.

    Used during checkpoint deserialization to handle unexpected status
    values from corrupted, manually edited, or future-version
    checkpoint files without crashing.
    """
    if value is None:
        return default
    try:
        return enum_cls(value)
    except ValueError:
        logger.warning(
            "Unknown %s value %r in checkpoint — defaulting to %s",
            enum_cls.__name__, value, default.value,
        )
        return default


class CheckpointManager:
    """Manages sprint checkpoint state with atomic persistence.

    The checkpoint file is written after every phase completion and on
    preemption signals.  On resume, the orchestrator reads it to
    determine where to continue.

    Args:
        checkpoint_path: Path to the checkpoint JSON file.
        project_root: Root directory of the project (for checksums).
        project_name: Identifier for the project.
    """

    def __init__(
        self,
        checkpoint_path: str | Path = "checkpoint.json",
        project_root: str | Path = ".",
        project_name: str = "leyp-water-refactor",
    ) -> None:
        self.checkpoint_path = Path(checkpoint_path)
        self.project_root = Path(project_root)
        self.project_name = project_name
        self.state = CheckpointState(project=project_name)
        self._session_start = time.monotonic()

    # ── Persistence ────────────────────────────────────────────────────

    def load(self) -> CheckpointState:
        """Load checkpoint from disk.  Returns fresh state if none exists.

        Returns:
            The loaded or newly created CheckpointState.
        """
        if not self.checkpoint_path.exists():
            logger.info("No checkpoint found — starting fresh.")
            self.state = CheckpointState(project=self.project_name)
            self.state.start_time = _now_iso()
            return self.state

        try:
            with open(self.checkpoint_path) as f:
                raw = json.load(f)

            state = CheckpointState(
                project=raw.get("project", self.project_name),
                preemption_count=raw.get("preemption_count", 0),
                total_elapsed_seconds=raw.get("total_elapsed_seconds", 0.0),
                start_time=raw.get("start_time"),
                last_checkpoint=raw.get("last_checkpoint"),
                file_checksums=raw.get("file_checksums", {}),
            )

            for sid, sdata in raw.get("sprints", {}).items():
                sprint_state = SprintState(
                    status=_safe_enum(sdata.get("status"), SprintStatus, SprintStatus.PENDING),
                    started_at=sdata.get("started_at"),
                    completed_at=sdata.get("completed_at"),
                    files_modified=sdata.get("files_modified", []),
                )
                for pid, pdata in sdata.get("phases", {}).items():
                    sprint_state.phases[pid] = PhaseState(
                        status=_safe_enum(pdata.get("status"), PhaseStatus, PhaseStatus.PENDING),
                        started_at=pdata.get("started_at"),
                        completed_at=pdata.get("completed_at"),
                        turn_count=pdata.get("turn_count", 0),
                        retry_count=pdata.get("retry_count", 0),
                    )
                state.sprints[sid] = sprint_state

            self.state = state
            logger.info(
                "Checkpoint loaded: %d sprints tracked, %d preemptions so far.",
                len(state.sprints),
                state.preemption_count,
            )
            return self.state

        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning("Corrupt checkpoint file — starting fresh: %s", e)
            self.state = CheckpointState(project=self.project_name)
            self.state.start_time = _now_iso()
            return self.state

    def save(self) -> None:
        """Persist current state to disk atomically."""
        now = time.monotonic()
        elapsed = now - self._session_start
        self.state.total_elapsed_seconds += elapsed
        self._session_start = now
        self.state.last_checkpoint = _now_iso()

        safe_write_json(self.checkpoint_path, _state_to_dict(self.state))
        logger.debug("Checkpoint saved to %s", self.checkpoint_path)

    def save_preemption(self) -> None:
        """Save state specifically on preemption — increments counter."""
        self.state.preemption_count += 1
        self.save()
        logger.warning(
            "Preemption checkpoint saved (count: %d).",
            self.state.preemption_count,
        )

    # ── Sprint status queries ──────────────────────────────────────────

    def _ensure_sprint(self, sprint_id: str) -> SprintState:
        """Get or create the SprintState for a sprint ID."""
        if sprint_id not in self.state.sprints:
            self.state.sprints[sprint_id] = SprintState()
        return self.state.sprints[sprint_id]

    def _ensure_phase(self, sprint_id: str, phase_name: str) -> PhaseState:
        """Get or create the PhaseState for a sprint/phase."""
        ss = self._ensure_sprint(sprint_id)
        if phase_name not in ss.phases:
            ss.phases[phase_name] = PhaseState()
        return ss.phases[phase_name]

    def is_sprint_completed(self, sprint_id: str) -> bool:
        """True if the sprint has status 'completed'."""
        ss = self.state.sprints.get(sprint_id)
        return ss is not None and ss.status == SprintStatus.COMPLETED

    def is_phase_completed(self, sprint_id: str, phase: Enum) -> bool:
        """True if the phase has status 'completed' or 'skipped'."""
        ss = self.state.sprints.get(sprint_id)
        if ss is None:
            return False
        ps = ss.phases.get(phase.value)
        if ps is None:
            return False
        return ps.status in (PhaseStatus.COMPLETED, PhaseStatus.SKIPPED)

    def are_dependencies_met(self, sprint) -> bool:
        """True if all sprints in sprint.depends_on are completed."""
        for dep_id in sprint.depends_on:
            if not self.is_sprint_completed(dep_id):
                return False
        return True

    # ── Sprint status mutations ────────────────────────────────────────

    def mark_sprint_started(self, sprint_id: str) -> None:
        """Mark a sprint as in-progress."""
        ss = self._ensure_sprint(sprint_id)
        if ss.status != SprintStatus.COMPLETED:
            ss.status = SprintStatus.IN_PROGRESS
            ss.started_at = ss.started_at or _now_iso()

    def mark_sprint_completed(self, sprint_id: str) -> None:
        """Mark a sprint as completed, snapshot file checksums, save."""
        ss = self._ensure_sprint(sprint_id)
        ss.status = SprintStatus.COMPLETED
        ss.completed_at = _now_iso()
        self.state.file_checksums = compute_project_checksums(self.project_root)
        self.save()
        logger.info("Sprint %s completed.", sprint_id)

    def mark_sprint_failed(self, sprint_id: str) -> None:
        """Mark a sprint as failed and save."""
        ss = self._ensure_sprint(sprint_id)
        ss.status = SprintStatus.FAILED
        self.save()
        logger.error("Sprint %s marked as failed.", sprint_id)

    # ── Phase status mutations ─────────────────────────────────────────

    def mark_phase_started(self, sprint_id: str, phase: Enum) -> None:
        """Mark a phase as in-progress."""
        self.mark_sprint_started(sprint_id)
        ps = self._ensure_phase(sprint_id, phase.value)
        ps.status = PhaseStatus.IN_PROGRESS
        ps.started_at = ps.started_at or _now_iso()

    def mark_phase_completed(
        self,
        sprint_id: str,
        phase: Enum,
        files_modified: list[str] | None = None,
    ) -> None:
        """Mark a phase as completed and save checkpoint.

        This is the primary checkpoint trigger.  Every completed phase
        gets persisted to disk, so at most one phase of work is lost
        on preemption.

        Args:
            sprint_id: The sprint this phase belongs to.
            phase: The SprintPhase enum value.
            files_modified: Optional list of files changed in this phase.
        """
        ps = self._ensure_phase(sprint_id, phase.value)
        ps.status = PhaseStatus.COMPLETED
        ps.completed_at = _now_iso()

        if files_modified:
            ss = self._ensure_sprint(sprint_id)
            for f in files_modified:
                if f not in ss.files_modified:
                    ss.files_modified.append(f)

        self.save()
        logger.info("Phase %s.%s completed.", sprint_id, phase.value)

    def mark_phase_skipped(self, sprint_id: str, phase: Enum) -> None:
        """Mark a phase as skipped (per sprint.skip_phases)."""
        ps = self._ensure_phase(sprint_id, phase.value)
        ps.status = PhaseStatus.SKIPPED

    def mark_phase_failed(self, sprint_id: str, phase: Enum) -> None:
        """Mark a phase as failed."""
        ps = self._ensure_phase(sprint_id, phase.value)
        ps.status = PhaseStatus.FAILED

    def increment_turn(self, sprint_id: str, phase: Enum) -> int:
        """Increment and return the turn count for a phase."""
        ps = self._ensure_phase(sprint_id, phase.value)
        ps.turn_count += 1
        return ps.turn_count

    def increment_retry(self, sprint_id: str, phase: Enum) -> int:
        """Increment and return the retry count for a phase."""
        ps = self._ensure_phase(sprint_id, phase.value)
        ps.retry_count += 1
        return ps.retry_count

    def reset_phase_for_retry(self, sprint_id: str, phase: Enum) -> None:
        """Reset a phase to in-progress for a retry attempt.

        Preserves the retry_count but resets turn_count and status.
        """
        ps = self._ensure_phase(sprint_id, phase.value)
        ps.status = PhaseStatus.IN_PROGRESS
        ps.turn_count = 0
        ps.started_at = _now_iso()

    # ── File integrity verification ────────────────────────────────────

    def verify_file_integrity(self) -> list[dict[str, str]]:
        """Compare current file checksums against the checkpoint.

        Call this on resume before running any sprints.  Returns a list
        of integrity violations.  Each violation is a dict with keys:
            file: relative path
            expected: checksum from checkpoint
            actual: current checksum (or 'MISSING' / 'NEW')
            last_modified_by: sprint ID that last modified the file

        Returns:
            List of violation dicts.  Empty list = all files intact.
        """
        if not self.state.file_checksums:
            logger.info("No checksums in checkpoint — skipping integrity check.")
            return []

        current = compute_project_checksums(self.project_root)
        violations = []

        for fpath, expected in self.state.file_checksums.items():
            actual = current.get(fpath)
            if actual is None:
                violations.append({
                    "file": fpath,
                    "expected": expected[:16] + "...",
                    "actual": "MISSING",
                    "last_modified_by": self._find_modifier(fpath),
                })
            elif actual != expected:
                violations.append({
                    "file": fpath,
                    "expected": expected[:16] + "...",
                    "actual": actual[:16] + "...",
                    "last_modified_by": self._find_modifier(fpath),
                })

        if violations:
            logger.warning(
                "File integrity check found %d violations.", len(violations)
            )
        else:
            logger.info("File integrity check passed — all files intact.")

        return violations

    def _find_modifier(self, file_path: str) -> str:
        """Find the last sprint that lists this file in files_modified."""
        last = "unknown"
        for sid, ss in self.state.sprints.items():
            if file_path in ss.files_modified:
                last = sid
        return last

    # ── Progress reporting ─────────────────────────────────────────────

    def get_progress_summary(self) -> str:
        """Return a human-readable progress summary."""
        lines = [
            f"Project: {self.state.project}",
            f"Preemptions: {self.state.preemption_count}",
            f"Total elapsed: {self.state.total_elapsed_seconds:.0f}s",
            f"Last checkpoint: {self.state.last_checkpoint or 'never'}",
            "",
        ]
        for sid, ss in sorted(self.state.sprints.items()):
            phase_summary = []
            for pname, ps in ss.phases.items():
                icon = {
                    PhaseStatus.COMPLETED: "done",
                    PhaseStatus.SKIPPED: "skip",
                    PhaseStatus.IN_PROGRESS: ">>",
                    PhaseStatus.FAILED: "FAIL",
                    PhaseStatus.PENDING: "..",
                }.get(ps.status, "??")
                phase_summary.append(f"{pname}:{icon}")
            phases_str = "  ".join(phase_summary)
            lines.append(f"  {sid} [{ss.status:12s}] {phases_str}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# GCP preemption signal handler
# ---------------------------------------------------------------------------

_checkpoint_manager_ref: Optional[CheckpointManager] = None


def install_preemption_handler(manager: CheckpointManager) -> None:
    """Install a SIGTERM handler that saves the checkpoint on preemption.

    GCP spot VMs receive SIGTERM 30 seconds before termination.  This
    handler writes the current state to disk and exits with code 3
    (EXIT_PREEMPTED), which the outer runner can detect to trigger a
    restart.

    Also handles SIGINT (Ctrl-C) for local development graceful shutdown.

    Args:
        manager: The CheckpointManager whose state will be saved.
    """
    global _checkpoint_manager_ref
    _checkpoint_manager_ref = manager

    def _handle_signal(signum: int, frame: Any) -> None:
        sig_name = signal.Signals(signum).name
        logger.warning("Received %s — saving checkpoint and exiting.", sig_name)

        if _checkpoint_manager_ref is not None:
            _checkpoint_manager_ref.save_preemption()

        if signum == signal.SIGTERM:
            sys.exit(EXIT_PREEMPTED)
        else:
            sys.exit(0)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    logger.info("Preemption handler installed (SIGTERM → checkpoint + exit %d).", EXIT_PREEMPTED)


def check_gcp_preemption() -> bool:
    """Poll GCP metadata server to check if preemption is imminent.

    This is a supplementary check — the SIGTERM handler is the primary
    mechanism.  Use this for polling between long-running operations
    (e.g., between NSGA-II generations).

    Returns:
        True if the VM is being preempted, False otherwise.
        Returns False on any error (not on GCP, network issue, etc.).
    """
    try:
        import requests
        resp = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/preempted",
            headers={"Metadata-Flavor": "Google"},
            timeout=1,
        )
        return resp.text.strip().lower() == "true"
    except Exception:
        return False


# ---------------------------------------------------------------------------
# NSGA-II optimization checkpointing
# ---------------------------------------------------------------------------

class OptimizationCheckpoint:
    """Wraps pymoo's callback to save/restore NSGA-II state per generation.

    Usage in leyp_optimizer.py:

        from config.checkpoint import OptimizationCheckpoint

        opt_ckpt = OptimizationCheckpoint("nsga2_checkpoint.pkl")

        # Resume if checkpoint exists
        algorithm = opt_ckpt.restore_or_create(
            lambda: NSGA2(pop_size=50, ...)
        )

        res = minimize(
            problem, algorithm, termination,
            callback=opt_ckpt.get_callback(),
            seed=seed, verbose=True,
        )

        # Clean up checkpoint after successful completion
        opt_ckpt.cleanup()

    Args:
        checkpoint_path: Path to the pickle file for algorithm state.
        save_every_n_gen: Save checkpoint every N generations (default 1).
    """

    def __init__(
        self,
        checkpoint_path: str | Path = "nsga2_checkpoint.pkl",
        save_every_n_gen: int = 1,
    ) -> None:
        self.checkpoint_path = Path(checkpoint_path)
        self.save_every_n_gen = save_every_n_gen
        self._last_gen = 0

    def restore_or_create(self, factory: Callable[[], Any]) -> Any:
        """Restore algorithm from checkpoint or create a new one.

        Args:
            factory: Callable that returns a fresh NSGA2 algorithm instance.
                     Only called if no checkpoint exists.

        Returns:
            The restored or newly created algorithm object.
        """
        if self.checkpoint_path.exists():
            try:
                with open(self.checkpoint_path, "rb") as f:
                    algorithm = pickle.load(f)
                self._last_gen = getattr(algorithm, "n_gen", 0) or 0
                logger.info(
                    "Restored NSGA-II from generation %d.", self._last_gen
                )
                return algorithm
            except (pickle.UnpicklingError, EOFError, AttributeError) as e:
                logger.warning(
                    "Corrupt NSGA-II checkpoint — creating fresh: %s", e
                )

        logger.info("No NSGA-II checkpoint — starting fresh.")
        return factory()

    def get_callback(self):
        """Return a pymoo Callback that saves state after each generation.

        The callback also checks for GCP preemption between generations
        and triggers a clean exit if preemption is detected.
        """
        from pymoo.core.callback import Callback

        outer = self

        class _CheckpointCallback(Callback):
            def notify(self, algorithm):
                gen = algorithm.n_gen or 0
                if gen % outer.save_every_n_gen == 0:
                    try:
                        tmp = outer.checkpoint_path.with_suffix(".pkl.tmp")
                        with open(tmp, "wb") as f:
                            pickle.dump(algorithm, f)
                            f.flush()
                            os.fsync(f.fileno())
                        os.replace(str(tmp), str(outer.checkpoint_path))
                        logger.debug("NSGA-II checkpoint saved at gen %d.", gen)
                    except Exception as e:
                        logger.warning("Failed to save NSGA-II checkpoint: %s", e)

                if check_gcp_preemption():
                    logger.warning("GCP preemption detected at gen %d.", gen)
                    if _checkpoint_manager_ref is not None:
                        _checkpoint_manager_ref.save_preemption()
                    sys.exit(EXIT_PREEMPTED)

        return _CheckpointCallback()

    def cleanup(self) -> None:
        """Remove the checkpoint file after successful completion."""
        if self.checkpoint_path.exists():
            self.checkpoint_path.unlink()
            logger.info("NSGA-II checkpoint cleaned up.")

    @property
    def resumed_from_gen(self) -> int:
        """The generation number restored from checkpoint (0 if fresh)."""
        return self._last_gen


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    """Current time as ISO 8601 string in UTC."""
    return datetime.now(timezone.utc).isoformat()


def _state_to_dict(state: CheckpointState) -> dict:
    """Convert CheckpointState to a JSON-serializable dict."""
    result = {
        "project": state.project,
        "preemption_count": state.preemption_count,
        "total_elapsed_seconds": round(state.total_elapsed_seconds, 1),
        "start_time": state.start_time,
        "last_checkpoint": state.last_checkpoint,
        "file_checksums": state.file_checksums,
        "sprints": {},
    }
    for sid, ss in state.sprints.items():
        sprint_dict = {
            "status": ss.status,
            "started_at": ss.started_at,
            "completed_at": ss.completed_at,
            "files_modified": ss.files_modified,
            "phases": {},
        }
        for pid, ps in ss.phases.items():
            sprint_dict["phases"][pid] = {
                "status": ps.status,
                "started_at": ps.started_at,
                "completed_at": ps.completed_at,
                "turn_count": ps.turn_count,
                "retry_count": ps.retry_count,
            }
        result["sprints"][sid] = sprint_dict
    return result
