"""Crew 2 - the Data Scientist crew (PLAN.md §3.10).

Three agents in sequence: the Feature Engineer builds the model inputs, the ML Engineer trains and
compares the variants, the Model Governance Officer writes the evaluation report and the model card.
They reach the data only through the guarded tools in `tools.py`, and only ever through the contract.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


class HandoffRefused(RuntimeError):
    """Crew 2 was handed a clean file that disagrees with its contract, so it trained nothing.

    The Flow already refuses this handoff before Crew 2 is called; Crew 2 asks the same question
    again because the brief's whole point is that the seam is enforced by the file, not by trust.
    """


@dataclass
class ScientistResult:
    """What Crew 2 hands back - the same shape whether the run was stubbed or real."""

    features_csv: Path
    metrics_json: Path
    model_path: Path
    evaluation_md: Path
    model_card_md: Path
    llm_calls: int
    prompt_tokens: int
    cached_prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    duration_s: float

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: (str(v) if isinstance(v, Path) else v) for k, v in d.items()}
