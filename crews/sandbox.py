"""The one sandbox both crews' tools use: a path is allowed only inside the directory it was given for.

Reads were guarded from M5 (Crew 2 may open the contract and the clean file, nothing else). The M8 audit
found writes were not: a tool handed `out_dir="artifacts/crew2"` would have written the published artifacts
during a server run (finding A1). So every tool that writes now resolves `out_dir` against the run
directory the crew runner announces before kickoff, and refuses anything else - including the Crew-1
handoff directory, which Crew 2 must never modify.
"""

from __future__ import annotations

from pathlib import Path


class SandboxError(Exception):
    """A tool was asked for a path outside the directory it is allowed to use."""


def guard(path: str | Path, allowed_dir: Path | str, what: str = "read") -> Path:
    """Resolve `path` and refuse it unless it is `allowed_dir` or inside it. Returns the resolved path."""
    resolved = Path(path).resolve()
    root = Path(allowed_dir).resolve()
    if resolved != root and root not in resolved.parents:
        raise SandboxError(f"{resolved} is outside {root}; a tool may only {what} inside its own directory")
    return resolved


def guard_write(out_dir: str | Path, run_dir: Path | None, forbidden: Path | None = None) -> Path:
    """`out_dir` must be inside the run directory and outside `forbidden` (the handoff Crew 2 only reads)."""
    if run_dir is None:
        raise SandboxError("the sandbox has no run directory yet; call set_run_dir() first")
    out = guard(out_dir, run_dir, what="write")
    if forbidden is not None:
        banned = Path(forbidden).resolve()
        if out == banned or banned in out.parents:
            raise SandboxError(f"{out} is the Crew-1 handoff directory; Crew 2 reads it, never writes there")
    return out
