"""Run directories, the event log, and the manifest (PLAN.md §3.9).

Every Flow run gets its own folder under `runs/` with `crew1/` and `crew2/` inside. The logger writes
two files side by side: `events.jsonl` (one JSON object per line, for machines and the M7 live tail)
and `flow.log` (one readable line per event, for people). The manifest records the sha256 of every
published artifact, so a later run can prove it produced the same bytes.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from hv.config import RUNS_DIR
from hv.contract import file_sha256

STATUSES = ("start", "ok", "fail", "skip")


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def new_run_dir(root: Path = RUNS_DIR, run_id: str | None = None) -> Path:
    """`root/<run_id>/` with `crew1/` and `crew2/` inside; the id defaults to a timestamp."""
    root = Path(root)
    run_id = run_id or time.strftime("%Y%m%d-%H%M%S")
    run_dir = root / run_id
    for sub in ("crew1", "crew2"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)
    return run_dir


class RunLogger:
    """Appends to `events.jsonl` and `flow.log` in the run directory; remembers step durations."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.run_dir / "events.jsonl"
        self.log_path = self.run_dir / "flow.log"
        self.durations: dict[str, float] = {}

    def event(self, step: str, status: str, **fields) -> None:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}, got {status!r}")
        record = {"ts": _now(), "step": step, "status": status, **fields}
        with self.events_path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, sort_keys=False, default=str) + "\n")
        detail = " ".join(f"{k}={v}" for k, v in fields.items())
        with self.log_path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(f"{record['ts']} {step:<18} {status:<5} {detail}".rstrip() + "\n")

    @contextmanager
    def step(self, name: str) -> Iterator[None]:
        """Log start, then ok (with duration) or fail (with the error) — and re-raise the error."""
        self.event(name, "start")
        t0 = time.perf_counter()
        try:
            yield
        except BaseException as e:
            self.durations[name] = round(time.perf_counter() - t0, 3)
            self.event(name, "fail", duration_s=self.durations[name], error=f"{type(e).__name__}: {e}")
            raise
        self.durations[name] = round(time.perf_counter() - t0, 3)
        self.event(name, "ok", duration_s=self.durations[name])


def _versions() -> dict[str, str]:
    import crewai
    import pandas
    import sklearn

    return {
        "python": ".".join(map(str, sys.version_info[:3])),
        "pandas": pandas.__version__,
        "sklearn": sklearn.__version__,
        "crewai": crewai.__version__,
    }


def write_manifest(run_dir: Path, artifacts: dict[str, Path], extra: dict) -> Path:
    """`manifest.json`: run id, creation time, one hash per artifact, library versions, plus `extra`."""
    run_dir = Path(run_dir)
    listed: dict[str, dict] = {}
    for name, path in artifacts.items():
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"artifact {name!r} is missing: {path}")
        try:
            rel = path.resolve().relative_to(run_dir.resolve()).as_posix()
        except ValueError:
            rel = str(path)
        listed[name] = {"path": rel, "sha256": file_sha256(path), "bytes": path.stat().st_size}
    manifest = {
        "run_id": run_dir.name,
        "created_at": _now(),
        "artifacts": listed,
        "versions": _versions(),
        **extra,
    }
    out = run_dir / "manifest.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return out
