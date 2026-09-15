"""Crew 2 - Data Scientist crew (PLAN.md §3.10).

Three agents in sequence: the Feature Engineer validates the handoff and builds the model inputs, the
ML Engineer trains and compares the variants, the Model Governance Officer writes the evaluation
report and the model card. They reach the data only through the guarded tools in `tools.py`, and only
ever through the contract - `set_crew1_dir` fixes the one directory they are allowed to read before
the crew is started. Run: ``python -m crews.scientist.crew --contract ... --clean ... --out DIR``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from crews.scientist.tools import (
    EXPECTED_FILES,
    engineer_features,
    read_crew1_artifact,
    set_crew1_dir,
    train_and_evaluate,
    validate_against_contract,
    write_evaluation_report,
    write_model_card,
)
from hv.config import ARTIFACTS_DIR, display_path, estimate_cost_usd, get_llm

VERBOSE = os.getenv("HV_VERBOSE", "0") == "1"
MAX_ITER = 8


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
        return {k: (display_path(v) if isinstance(v, Path) else v) for k, v in d.items()}


@CrewBase
class ScientistCrew:
    """Three agents: Feature Engineer, ML Engineer, Model Governance Officer (five sequential tasks)."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def feature_engineer(self) -> Agent:
        return Agent(
            config=self.agents_config["feature_engineer"],
            tools=[read_crew1_artifact, validate_against_contract, engineer_features],
            llm=get_llm(),
            max_iter=MAX_ITER,
            allow_delegation=False,
            verbose=VERBOSE,
        )

    @agent
    def ml_engineer(self) -> Agent:
        return Agent(
            config=self.agents_config["ml_engineer"],
            tools=[train_and_evaluate],
            llm=get_llm(),
            max_iter=MAX_ITER,
            allow_delegation=False,
            verbose=VERBOSE,
        )

    @agent
    def model_governance_officer(self) -> Agent:
        return Agent(
            config=self.agents_config["model_governance_officer"],
            tools=[write_evaluation_report, write_model_card],
            llm=get_llm(),
            max_iter=MAX_ITER,
            allow_delegation=False,
            verbose=VERBOSE,
        )

    @task
    def validate(self) -> Task:
        return Task(
            config=self.tasks_config["validate"],
            tools=[read_crew1_artifact, validate_against_contract],
        )

    @task
    def engineer_features(self) -> Task:
        return Task(config=self.tasks_config["engineer_features"], tools=[engineer_features])

    @task
    def train_compare(self) -> Task:
        return Task(config=self.tasks_config["train_compare"], tools=[train_and_evaluate])

    @task
    def evaluation_report(self) -> Task:
        return Task(config=self.tasks_config["evaluation_report"], tools=[write_evaluation_report])

    @task
    def model_card(self) -> Task:
        return Task(config=self.tasks_config["model_card"], tools=[write_model_card])

    @crew
    def crew(self) -> Crew:
        return Crew(agents=self.agents, tasks=self.tasks, process=Process.sequential, verbose=VERBOSE)


def run_scientist_crew(
    contract_json: Path, clean_csv: Path, out_dir: Path | None = None
) -> ScientistResult:
    """Kick off Crew 2 and return the artifact paths plus usage. Raises if an expected file is missing.

    The sandbox is pointed at the contract's own directory, so whatever the agents decide to read,
    they cannot reach outside the handoff they were given.
    """
    out_dir = Path(out_dir or Path("runs") / time.strftime("%Y%m%d-%H%M%S") / "crew2")
    out_dir.mkdir(parents=True, exist_ok=True)
    set_crew1_dir(Path(contract_json).resolve().parent)
    t0 = time.perf_counter()
    c = ScientistCrew().crew()
    c.kickoff(
        inputs={
            "contract_json": str(contract_json),
            "clean_csv": str(clean_csv),
            "out_dir": str(out_dir),
        }
    )
    duration = round(time.perf_counter() - t0, 1)

    missing = [f for f in EXPECTED_FILES if not (out_dir / f).exists()]
    if missing:
        raise RuntimeError(f"scientist crew finished without producing: {missing}")

    u = c.usage_metrics
    result = ScientistResult(
        features_csv=out_dir / "features.csv",
        metrics_json=out_dir / "metrics.json",
        model_path=out_dir / "model.joblib",
        evaluation_md=out_dir / "evaluation_report.md",
        model_card_md=out_dir / "model_card.md",
        llm_calls=int(u.successful_requests),
        prompt_tokens=int(u.prompt_tokens),
        cached_prompt_tokens=int(u.cached_prompt_tokens),
        completion_tokens=int(u.completion_tokens),
        cost_usd=estimate_cost_usd(u.prompt_tokens, u.cached_prompt_tokens, u.completion_tokens),
        duration_s=duration,
    )
    (out_dir / "run_meta.json").write_text(
        json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", type=Path, default=ARTIFACTS_DIR / "crew1" / "dataset_contract.json")
    ap.add_argument("--clean", type=Path, default=ARTIFACTS_DIR / "crew1" / "clean_data.csv")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    from dotenv import load_dotenv

    load_dotenv()
    res = run_scientist_crew(args.contract, args.clean, args.out)
    print(json.dumps(res.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
