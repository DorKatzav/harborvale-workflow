"""The Flow's state (PLAN.md §3.11): everything a run knows about itself, serialisable as JSON."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from hv.config import RAW_PATH

# "verified" is not in PLAN §3.11: it is where a run ends when every check passed but publishing was
# switched off (--publish false). Calling that run "published" would be a lie (D-M5-1).
Status = Literal[
    "pending", "handoff_ok", "handoff_failed", "outputs_failed", "verified", "published"
]


class FlowState(BaseModel):
    run_id: str = ""
    run_dir: str = ""
    raw_path: str = str(RAW_PATH)
    raw_sha256: str = ""
    tamper: str | None = None
    stub_crews: bool = False
    skip_crew1: bool = False
    publish: bool = True
    crew1: dict[str, str] = Field(default_factory=dict)
    crew2: dict[str, str] = Field(default_factory=dict)
    validation: dict = Field(default_factory=dict)
    outputs_check: dict = Field(default_factory=dict)
    status: Status = "pending"
    llm_calls: int = 0
    cost_usd: float = 0.0
    started_at: str = ""
    finished_at: str = ""
