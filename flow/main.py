"""The HarborVale Flow (PLAN.md §3.11).

    ingest → run_analyst → validate_handoff → router → run_scientist → validate_outputs → router → publish
                                                ↘ handoff_failed ──────────────────────────↘ outputs_failed
                                                                    → fail_gracefully (FAILED.md)

The seam between the crews is a file: Crew 2 receives the run's copy of `dataset_contract.json` and
`clean_data.csv` and nothing else. The Flow validates one against the other before Crew 2 starts and
refuses to continue when they disagree, writing `FAILED.md` a person can read. Only after Crew 2's
outputs pass their own checks does anything reach `artifacts/`.

The crews are plain callables with the §3.10 signatures, so tests inject stand-ins and the same Flow runs
the stubs (`crews/stubs.py`) or the real crews (`crews/*/crew.py`).
"""

from __future__ import annotations

import os
import shutil
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from crewai.flow.flow import Flow, listen, or_, router, start

from flow.state import FlowState
from hv.config import (
    ARTIFACTS_DIR,
    CSV_KW,
    MODEL_NAME,
    PRIMARY_KEY,
    PROTECTED,
    RAW_PATH,
    READ_CSV_KW,
    RUNS_DIR,
    TARGET,
    display_path,
)
from hv.contract import PRESETS, ValidationReport, file_sha256, load_contract, save_contract, tamper, validate
from hv.features import ENGINEERED_SOURCES
from hv.model_card import REQUIRED_SECTIONS
from hv.runlog import RunLogger, new_run_dir, write_manifest

CREW1_FILES = [
    "clean_data.csv", "cleaning_report.json", "stats.json", "eda_report.html", "insights.md",
    "dataset_contract.json",
]  # fmt: skip
CREW2_FILES = ["features.csv", "metrics.json", "model.joblib", "evaluation_report.md", "model_card.md"]
# the eight deliverables the brief names (the JSON side files are published too, and hashed too)
BRIEF_ARTIFACTS = [
    "clean_data.csv", "eda_report.html", "insights.md", "dataset_contract.json",
    "features.csv", "model.joblib", "evaluation_report.md", "model_card.md",
]  # fmt: skip
EXIT_CODES = {"published": 0, "verified": 0, "handoff_failed": 2, "outputs_failed": 3}
NEVER_A_FEATURE = {PRIMARY_KEY, TARGET, *PROTECTED}

Runner = Callable[..., Any]


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class HarborValeFlow(Flow[FlowState]):
    def __init__(
        self,
        *,
        log: RunLogger,
        analyst_runner: Runner,
        scientist_runner: Runner,
        artifacts_dir: Path = ARTIFACTS_DIR,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.log = log
        self.analyst_runner = analyst_runner
        self.scientist_runner = scientist_runner
        self.artifacts_dir = Path(artifacts_dir)
        self.handoff_report: ValidationReport | None = None

    # ------------------------------------------------------------ helpers
    @property
    def run_dir(self) -> Path:
        return Path(self.state.run_dir)

    def _add_usage(self, result: Any) -> None:
        self.state.llm_calls += int(getattr(result, "llm_calls", 0) or 0)
        self.state.cost_usd = round(self.state.cost_usd + float(getattr(result, "cost_usd", 0.0) or 0.0), 4)

    def _timed(self, name: str, passed: bool, t0: float, **fields) -> None:
        """Log a validation step whose outcome is a verdict, not an exception."""
        import time

        self.log.durations[name] = round(time.perf_counter() - t0, 3)
        self.log.event(name, "ok" if passed else "fail", duration_s=self.log.durations[name], **fields)

    # ------------------------------------------------------------ steps
    @start()
    def ingest(self) -> None:
        self.state.started_at = _now()
        with self.log.step("ingest"):
            raw = Path(self.state.raw_path)
            if raw.exists():
                self.state.raw_sha256 = file_sha256(raw)
            elif not self.state.skip_crew1:
                raise FileNotFoundError(f"raw dataset not found: {raw}")

    @listen(ingest)
    def run_analyst(self) -> None:
        crew1 = self.run_dir / "crew1"
        if self.state.skip_crew1:
            source = self.artifacts_dir / "crew1"
            missing = [f for f in CREW1_FILES if not (source / f).exists()]
            if missing:
                raise FileNotFoundError(f"--skip-crew1 needs a published {source}; missing {missing}")
            for name in [*CREW1_FILES, "run_meta.json"]:
                if (source / name).exists():
                    shutil.copyfile(source / name, crew1 / name)
            self.log.event("run_analyst", "skip", reason=f"copied from {display_path(source)}")
        else:
            with self.log.step("run_analyst"):
                result = self.analyst_runner(Path(self.state.raw_path), crew1)
                self._add_usage(result)
                missing = [f for f in CREW1_FILES if not (crew1 / f).exists()]
                if missing:
                    raise RuntimeError(f"the analyst crew finished without producing {missing}")
        self.state.crew1 = {name: str(crew1 / name) for name in CREW1_FILES}

    @listen(run_analyst)
    def validate_handoff(self) -> None:
        import time

        import pandas as pd

        clean_csv = Path(self.state.crew1["clean_data.csv"])
        contract_json = Path(self.state.crew1["dataset_contract.json"])
        if self.state.tamper:
            # break the RUN's copy on purpose; the published artifacts are never touched
            original = pd.read_csv(clean_csv, **READ_CSV_KW)
            tampered, tampered_contract = tamper(original, load_contract(contract_json), self.state.tamper)
            if not tampered.equals(original):
                tampered.to_csv(clean_csv, **CSV_KW)
            save_contract(tampered_contract, contract_json)
            self.log.event("tamper", "ok", preset=self.state.tamper)

        t0 = time.perf_counter()
        # the columns Crew 2's feature engineering reads must be declared, and declared as features
        report = validate(clean_csv, contract_json, required_features=ENGINEERED_SOURCES)
        report.source = display_path(clean_csv)
        self.handoff_report = report
        self.state.validation = report.to_dict()
        self.state.status = "handoff_ok" if report.passed else "handoff_failed"
        self._timed(
            "validate_handoff", report.passed, t0,
            checks=len(report.checks), failed=sorted(report.failed_names),
        )  # fmt: skip

    @router(validate_handoff)
    def route_handoff(self) -> str:
        return "handoff_ok" if self.state.status == "handoff_ok" else "handoff_failed"

    @listen("handoff_ok")
    def run_scientist(self) -> None:
        crew2 = self.run_dir / "crew2"
        with self.log.step("run_scientist"):
            result = self.scientist_runner(
                Path(self.state.crew1["dataset_contract.json"]),
                Path(self.state.crew1["clean_data.csv"]),
                crew2,
            )
            self._add_usage(result)
        self.state.crew2 = {name: str(crew2 / name) for name in CREW2_FILES if (crew2 / name).exists()}

    @listen(run_scientist)
    def validate_outputs(self) -> None:
        import time

        t0 = time.perf_counter()
        checks = _check_crew2_outputs(self.run_dir / "crew2", Path(self.state.crew1["clean_data.csv"]))
        passed = all(c["passed"] for c in checks)
        self.state.outputs_check = {"passed": passed, "checks": checks}
        if not passed:
            self.state.status = "outputs_failed"
        self._timed(
            "validate_outputs", passed, t0,
            checks=len(checks), failed=[c["name"] for c in checks if not c["passed"]],
        )  # fmt: skip

    @router(validate_outputs)
    def route_outputs(self) -> str:
        return "outputs_failed" if self.state.status == "outputs_failed" else "outputs_ok"

    @listen("outputs_ok")
    def publish(self) -> None:
        run_dir = self.run_dir
        artifacts = {
            **{name: run_dir / "crew1" / name for name in CREW1_FILES},
            **{name: run_dir / "crew2" / name for name in CREW2_FILES},
        }
        for crew in ("crew1", "crew2"):
            meta = run_dir / crew / "run_meta.json"
            if meta.exists():
                artifacts[f"{crew}/run_meta.json"] = meta
        manifest = write_manifest(
            run_dir,
            artifacts,
            {
                "durations_s": dict(self.log.durations),
                "llm": {
                    "model": "stub" if self.state.stub_crews else MODEL_NAME,
                    "calls": self.state.llm_calls,
                    "cost_usd": self.state.cost_usd,
                },
                "raw_sha256": self.state.raw_sha256,
                "tamper": self.state.tamper,
                "skip_crew1": self.state.skip_crew1,
                "started_at": self.state.started_at,
            },
        )
        if not self.state.publish:
            self.state.status = "verified"
            self.log.event("publish", "skip", reason="--publish false; run left in the run directory")
            return
        with self.log.step("publish"):
            for path in artifacts.values():
                target = self.artifacts_dir / path.relative_to(run_dir)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
            shutil.copyfile(manifest, self.artifacts_dir / "manifest.json")
        self.state.status = "published"

    @listen(or_("handoff_failed", "outputs_failed"))
    def fail_gracefully(self) -> None:
        if self.state.status == "handoff_failed":
            stopped = "validate_handoff"
            body = self.handoff_report.to_markdown() if self.handoff_report else ""
            next_step = (
                "Crew 2 did not run and `crew2/` is empty. Fix the data or the contract upstream, then rerun."
            )
        else:
            stopped = "validate_outputs"
            failed = [c for c in self.state.outputs_check.get("checks", []) if not c["passed"]]
            body = "\n".join(["| check | what is wrong |", "|---|---|"] + [
                f"| {c['name']} | {c['message']} |" for c in failed
            ])  # fmt: skip
            next_step = "Nothing was published; `artifacts/` still holds the last good run."
        _write_failed(self.run_dir, self.state.run_id, self.state.status, stopped, body, next_step)
        self.log.event("fail_gracefully", "ok", failed_md=display_path(self.run_dir / "FAILED.md"))


# ---------------------------------------------------------------- outputs check
def _check_crew2_outputs(crew2: Path, clean_csv: Path) -> list[dict]:
    """What the Flow demands of Crew 2 before publishing: the same questions gate M4 asks."""
    import json

    checks: list[dict] = []

    def add(name: str, fn: Callable[[], str]) -> None:
        try:
            checks.append({"name": name, "passed": True, "message": fn()})
        except Exception as e:  # noqa: BLE001 - every check reports, none crashes the run
            checks.append({"name": name, "passed": False, "message": f"{type(e).__name__}: {e}"})

    def files() -> str:
        missing = [f for f in CREW2_FILES if not (crew2 / f).exists()]
        if missing:
            raise FileNotFoundError(f"missing in crew2/: {missing}")
        return f"{len(CREW2_FILES)} files present"

    def metrics() -> dict:
        return json.loads((crew2 / "metrics.json").read_text(encoding="utf-8"))

    def shape() -> str:
        m = metrics()
        assert "baseline" in m, "metrics.json has no baseline"
        n_variants = len(m.get("variants", {}))
        assert n_variants >= 3, f"only {n_variants} variants, the brief asks for three"
        assert m.get("served") in m["variants"], f"served model {m.get('served')!r} is not a variant"
        return f"{len(m['variants'])} variants, served {m['served']}"

    def leakage() -> str:
        m = metrics()
        f = m["features"]
        listed = set(f["numeric"]) | set(f["categorical"]) | set(f["engineered"])
        leaked = sorted((listed | set(m.get("importances", {}))) & NEVER_A_FEATURE)
        assert not leaked, f"these must never be model inputs: {leaked}"
        return f"{len(listed)} features, none of {sorted(NEVER_A_FEATURE)}"

    def beats_baseline() -> str:
        m = metrics()
        served, base = m["variants"][m["served"]], m["baseline"]
        assert served["roc_auc"]["mean"] > base["roc_auc"], (
            f"served roc_auc {served['roc_auc']['mean']} does not beat the baseline {base['roc_auc']}"
        )
        assert served["precision_at_top10"] > base["precision_at_top10"], (
            f"precision@top10 {served['precision_at_top10']} does not beat the baseline "
            f"{base['precision_at_top10']}"
        )
        return f"roc_auc {served['roc_auc']['mean']} vs baseline {base['roc_auc']}"

    def predicts() -> str:
        import pandas as pd

        from hv.train import predict_one

        row = pd.read_csv(clean_csv, **READ_CSV_KW).iloc[0].to_dict()
        proba = predict_one(crew2 / "model.joblib", row)
        assert 0.0 <= proba <= 1.0, f"{proba} is not a probability"
        return f"first clean row scores {proba}"

    def card() -> str:
        text = (crew2 / "model_card.md").read_text(encoding="utf-8")
        missing = [s for s in REQUIRED_SECTIONS if f"## {s}" not in text]
        assert not missing, f"model_card.md lacks sections: {missing}"
        return "five sections present"

    add("files", files)
    add("metrics_shape", shape)
    add("no_leakage", leakage)
    add("beats_baseline", beats_baseline)
    add("model_predicts", predicts)
    add("model_card_sections", card)
    return checks


def _write_failed(run_dir: Path, run_id: str, status: str, stopped: str, body: str, next_step: str) -> Path:
    text = "\n".join(
        [
            f"# Run {run_id} — {status}",
            "",
            f"**Stopped at:** `{stopped}`  ",
            f"**Run directory:** `{display_path(run_dir)}`",
            "",
            body.rstrip(),
            "",
            next_step,
            "",
        ]
    )
    path = run_dir / "FAILED.md"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


# ---------------------------------------------------------------- runners
def _default_analyst(stub: bool) -> Runner:
    if stub:
        from crews.stubs import run_analyst_stub

        return run_analyst_stub
    from crews.analyst.crew import run_analyst_crew

    return run_analyst_crew


def _default_scientist(stub: bool) -> Runner:
    """Resolved at call time: a run that stops at the handoff never needs Crew 2."""

    def resolve(*args):
        if stub:
            from crews import stubs

            fn = getattr(stubs, "run_scientist_stub", None)
            if fn is None:
                raise NotImplementedError(
                    "crews.stubs.run_scientist_stub has not landed yet (crews/scientist is Yoran's half, "
                    "issue #18)"
                )
            return fn(*args)
        try:
            from crews.scientist.crew import run_scientist_crew
        except ImportError as e:
            raise NotImplementedError("crews/scientist/crew.py has not landed yet (issue #18)") from e
        return run_scientist_crew(*args)

    return resolve


def _quiet_console() -> None:
    """CrewAI's Rich panels are noise in a log; HV_VERBOSE=1 brings them back."""
    from crewai.events.event_listener import EventListener
    from rich.console import Console

    verbose = os.getenv("HV_VERBOSE", "0") == "1"
    formatter = EventListener().formatter
    formatter.verbose = verbose
    # flow panels ignore `verbose`, so the console itself goes quiet
    formatter.console = Console(width=None, quiet=not verbose)


def run_flow(
    raw_path: Path = RAW_PATH,
    tamper: str | None = None,
    stub_crews: bool = False,
    skip_crew1: bool = False,
    publish: bool = True,
    *,
    run_id: str | None = None,
    runs_root: Path = RUNS_DIR,
    artifacts_dir: Path = ARTIFACTS_DIR,
    analyst_runner: Runner | None = None,
    scientist_runner: Runner | None = None,
    echo: bool = False,
) -> FlowState:
    """Run the whole pipeline once and return its state; an unexpected error is logged, then raised."""
    if tamper is not None and tamper not in PRESETS:
        raise ValueError(f"unknown tamper preset {tamper!r}; known presets: {PRESETS}")
    run_dir = new_run_dir(runs_root, run_id)
    log = RunLogger(run_dir, echo=echo)
    _quiet_console()
    flow = HarborValeFlow(
        log=log,
        analyst_runner=analyst_runner or _default_analyst(stub_crews),
        scientist_runner=scientist_runner or _default_scientist(stub_crews),
        artifacts_dir=artifacts_dir,
    )
    log.event(
        "flow", "start", run_id=run_dir.name, stub_crews=stub_crews, skip_crew1=skip_crew1,
        tamper=tamper, publish=publish,
    )  # fmt: skip
    try:
        flow.kickoff(
            inputs={
                "run_id": run_dir.name,
                "run_dir": str(run_dir),
                "raw_path": str(raw_path),
                "tamper": tamper,
                "stub_crews": stub_crews,
                "skip_crew1": skip_crew1,
                "publish": publish,
            }
        )
    except Exception as e:
        log.event("flow", "fail", error=f"{type(e).__name__}: {e}")
        _write_failed(
            run_dir, run_dir.name, "error", "unexpected error", "```\n" + traceback.format_exc() + "```",
            "The run crashed outside the validators; see events.jsonl for the step that failed.",
        )  # fmt: skip
        raise
    state = flow.state
    state.finished_at = _now()
    if state.status in ("published", "verified"):
        log.event("flow", "ok", result=state.status, llm_calls=state.llm_calls, cost_usd=state.cost_usd)
        if state.status == "published":
            shutil.copyfile(log.log_path, Path(artifacts_dir) / "flow.log")
    else:
        log.event("flow", "fail", result=state.status)
    return state
