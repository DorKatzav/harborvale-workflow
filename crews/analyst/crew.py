"""Crew 1 — Data Analyst crew (PLAN.md §3.10).

Agents and tasks are declared in config/*.yaml. Every number in the outputs comes from an hv tool; the agents
orchestrate and write prose. Run: ``python -m crews.analyst.crew --out runs/<id>/crew1``.
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

from crews.analyst.tools import clean_dataset, profile_raw_data, run_eda, write_insights
from hv.config import RAW_PATH, estimate_cost_usd, get_llm

VERBOSE = os.getenv("HV_VERBOSE", "0") == "1"
MAX_ITER = 8


@CrewBase
class AnalystCrew:
    """Two agents active now (Data Quality Engineer, Business Analyst); the Data Steward joins in M3b."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def data_quality_engineer(self) -> Agent:
        return Agent(
            config=self.agents_config["data_quality_engineer"],
            tools=[profile_raw_data, clean_dataset],
            llm=get_llm(),
            max_iter=MAX_ITER,
            allow_delegation=False,
            verbose=VERBOSE,
        )

    @agent
    def business_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["business_analyst"],
            tools=[run_eda, write_insights],
            llm=get_llm(),
            max_iter=MAX_ITER,
            allow_delegation=False,
            verbose=VERBOSE,
        )

    @task
    def profile_and_clean(self) -> Task:
        return Task(config=self.tasks_config["profile_and_clean"], tools=[profile_raw_data, clean_dataset])

    @task
    def explore(self) -> Task:
        return Task(config=self.tasks_config["explore"], tools=[run_eda])

    @task
    def write_insights(self) -> Task:
        return Task(config=self.tasks_config["write_insights"], tools=[write_insights])

    @crew
    def crew(self) -> Crew:
        return Crew(agents=self.agents, tasks=self.tasks, process=Process.sequential, verbose=VERBOSE)


@dataclass
class AnalystResult:
    clean_csv: Path
    eda_html: Path
    stats_json: Path
    insights_md: Path
    contract_json: Path | None
    llm_calls: int
    prompt_tokens: int
    cached_prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    duration_s: float

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: (str(v) if isinstance(v, Path) else v) for k, v in d.items()}


EXPECTED_FILES = ["clean_data.csv", "cleaning_report.json", "stats.json", "eda_report.html", "insights.md"]


def run_analyst_crew(raw_path: Path = RAW_PATH, out_dir: Path | None = None) -> AnalystResult:
    """Kick off the crew and return the artifact paths plus usage. Raises if an expected file is missing."""
    out_dir = Path(out_dir or Path("runs") / time.strftime("%Y%m%d-%H%M%S") / "crew1")
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    c = AnalystCrew().crew()
    c.kickoff(inputs={"raw_path": str(raw_path), "out_dir": str(out_dir)})
    duration = round(time.perf_counter() - t0, 1)

    missing = [f for f in EXPECTED_FILES if not (out_dir / f).exists()]
    if missing:
        raise RuntimeError(f"analyst crew finished without producing: {missing}")

    u = c.usage_metrics
    result = AnalystResult(
        clean_csv=out_dir / "clean_data.csv",
        eda_html=out_dir / "eda_report.html",
        stats_json=out_dir / "stats.json",
        insights_md=out_dir / "insights.md",
        contract_json=None,
        llm_calls=int(u.successful_requests),
        prompt_tokens=int(u.prompt_tokens),
        cached_prompt_tokens=int(u.cached_prompt_tokens),
        completion_tokens=int(u.completion_tokens),
        cost_usd=estimate_cost_usd(u.prompt_tokens, u.cached_prompt_tokens, u.completion_tokens),
        duration_s=duration,
    )
    (out_dir / "run_meta.json").write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, default=RAW_PATH)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    from dotenv import load_dotenv

    load_dotenv()
    res = run_analyst_crew(args.raw, args.out)
    print(json.dumps(res.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
