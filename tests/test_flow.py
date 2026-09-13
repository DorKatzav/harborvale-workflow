"""M5 task 3: the Flow with stub crews — happy path, the refusal path, skip_crew1, publish=False.

Crew 2 is injected as a fake runner here: the real scientist crew and its stub live in `crews/scientist/`
(Yoran's half, issue #18). The fake copies five files produced by a real `train_all` on synthetic rows, so
`validate_outputs` checks a real model, not a mock.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from flow.main import BRIEF_ARTIFACTS, CREW2_FILES, EXIT_CODES, run_flow
from hv.contract import build_contract
from hv.features import build_features, write_features
from hv.model_card import REQUIRED_SECTIONS
from hv.train import train_all
from tests.synthetic import training_frame, write_frame


@pytest.fixture
def raw_xlsx(raw_frame, tmp_path):
    path = tmp_path / "raw.xlsx"
    raw_frame.to_excel(path, sheet_name="E Comm", index=False)
    return path


@pytest.fixture(scope="module")
def trained_crew2(tmp_path_factory) -> Path:
    """Five crew-2 files from one real training run on 150 synthetic rows (shared by the module)."""
    tmp = tmp_path_factory.mktemp("crew2_source")
    df = training_frame(150)
    contract = build_contract(df, "tests/synthetic.py", write_frame(df, tmp / "clean_data.csv"))
    features = build_features(df, contract)
    write_features(features, tmp / "crew2" / "features.csv")
    metrics = train_all(features, contract, tmp / "crew2",
                        protected=df[["CustomerID", "Gender", "MaritalStatus"]])  # fmt: skip
    (tmp / "crew2" / "evaluation_report.md").write_text("# Evaluation\n\nfake narrative\n")
    (tmp / "crew2" / "model_card.md").write_text(
        "# Model card\n\n" + "".join(f"## {s}\n\nfake\n\n" for s in REQUIRED_SECTIONS)
    )
    assert metrics["served"]
    return tmp / "crew2"


def _fake_scientist(source: Path, calls: list | None = None, patch=None):
    """A runner with the `run_scientist_stub` signature that copies the pre-trained files."""

    def runner(contract_json: Path, clean_csv: Path, out_dir: Path):
        if calls is not None:
            calls.append((Path(contract_json), Path(clean_csv), Path(out_dir)))
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for name in CREW2_FILES:
            shutil.copyfile(source / name, out_dir / name)
        if patch:
            patch(out_dir)
        return SimpleNamespace(
            features_csv=out_dir / "features.csv",
            model_path=out_dir / "model.joblib",
            evaluation_md=out_dir / "evaluation_report.md",
            model_card_md=out_dir / "model_card.md",
            metrics_json=out_dir / "metrics.json",
            llm_calls=0,
            cost_usd=0.0,
        )

    return runner


def _never_called(*args, **kwargs):
    raise AssertionError("this crew must not run")


def _events(run_dir: Path) -> list[dict]:
    return [json.loads(ln) for ln in (run_dir / "events.jsonl").read_text().splitlines()]


# ---------------------------------------------------------------- happy path
def test_happy_path_publishes_every_artifact_with_a_manifest(raw_xlsx, tmp_path, trained_crew2):
    artifacts = tmp_path / "artifacts"
    state = run_flow(
        raw_path=raw_xlsx, stub_crews=True, publish=True,
        runs_root=tmp_path / "runs", artifacts_dir=artifacts,
        scientist_runner=_fake_scientist(trained_crew2),
    )  # fmt: skip

    assert state.status == "published"
    assert state.validation["passed"] is True and state.outputs_check["passed"] is True
    run_dir = Path(state.run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    for name in BRIEF_ARTIFACTS:
        entry = manifest["artifacts"][name]
        published = artifacts / entry["path"]
        assert published.exists(), name
        assert published.read_bytes() == (run_dir / entry["path"]).read_bytes(), name
    assert (artifacts / "manifest.json").read_bytes() == (run_dir / "manifest.json").read_bytes()
    assert (artifacts / "flow.log").exists()
    assert manifest["durations_s"]["run_scientist"] >= 0
    assert manifest["llm"] == {"model": "stub", "calls": 0, "cost_usd": 0.0}


def test_events_record_every_step_in_order(raw_xlsx, tmp_path, trained_crew2):
    state = run_flow(
        raw_path=raw_xlsx, stub_crews=True, publish=False,
        runs_root=tmp_path / "runs", scientist_runner=_fake_scientist(trained_crew2),
    )  # fmt: skip
    steps = [(e["step"], e["status"]) for e in _events(Path(state.run_dir))]
    assert [s for s, st in steps if st == "ok"] == [
        "ingest", "run_analyst", "validate_handoff", "run_scientist", "validate_outputs", "flow",
    ]  # fmt: skip
    assert ("publish", "skip") in steps
    assert state.raw_sha256 and state.started_at and state.finished_at


def test_publish_false_leaves_artifacts_untouched_and_ends_verified(raw_xlsx, tmp_path, trained_crew2):
    artifacts = tmp_path / "artifacts"
    state = run_flow(
        raw_path=raw_xlsx, stub_crews=True, publish=False,
        runs_root=tmp_path / "runs", artifacts_dir=artifacts,
        scientist_runner=_fake_scientist(trained_crew2),
    )  # fmt: skip
    assert state.status == "verified"
    assert not artifacts.exists()
    assert (Path(state.run_dir) / "manifest.json").exists()


def test_scientist_receives_the_run_copy_of_the_contract_only(raw_xlsx, tmp_path, trained_crew2):
    calls: list = []
    state = run_flow(
        raw_path=raw_xlsx, stub_crews=True, publish=False,
        runs_root=tmp_path / "runs", scientist_runner=_fake_scientist(trained_crew2, calls),
    )  # fmt: skip
    run_dir = Path(state.run_dir)
    assert calls == [(run_dir / "crew1" / "dataset_contract.json", run_dir / "crew1" / "clean_data.csv",
                      run_dir / "crew2")]  # fmt: skip


# ---------------------------------------------------------------- the refusal path
def test_tampered_handoff_is_refused_before_crew2_runs(raw_xlsx, tmp_path):
    state = run_flow(
        raw_path=raw_xlsx, stub_crews=True, tamper="unit_change", publish=True,
        runs_root=tmp_path / "runs", artifacts_dir=tmp_path / "artifacts",
        scientist_runner=_never_called,
    )  # fmt: skip

    assert state.status == "handoff_failed"
    assert state.validation["passed"] is False
    run_dir = Path(state.run_dir)
    failed = (run_dir / "FAILED.md").read_text(encoding="utf-8")
    assert "CashbackAmount" in failed and "looks like a unit change" in failed
    assert list((run_dir / "crew2").iterdir()) == []
    assert not (tmp_path / "artifacts").exists()
    assert not (run_dir / "manifest.json").exists()
    steps = [(e["step"], e["status"]) for e in _events(run_dir)]
    assert ("validate_handoff", "fail") in steps and ("flow", "fail") in steps


@pytest.mark.parametrize("preset", ["rename_column", "drop_contract_field", "row_loss"])
def test_every_preset_stops_the_flow(raw_xlsx, tmp_path, preset):
    state = run_flow(
        raw_path=raw_xlsx, stub_crews=True, tamper=preset, publish=False,
        runs_root=tmp_path / "runs", scientist_runner=_never_called,
    )  # fmt: skip
    assert state.status == "handoff_failed"
    assert (Path(state.run_dir) / "FAILED.md").exists()


def test_tamper_touches_the_run_copy_never_the_source(raw_xlsx, tmp_path, trained_crew2):
    # a published run first, then a tampered run that starts from those artifacts
    artifacts = tmp_path / "artifacts"
    run_flow(
        raw_path=raw_xlsx, stub_crews=True, publish=True, runs_root=tmp_path / "runs",
        artifacts_dir=artifacts, scientist_runner=_fake_scientist(trained_crew2),
    )  # fmt: skip
    before = {p.name: p.read_bytes() for p in (artifacts / "crew1").iterdir()}

    state = run_flow(
        stub_crews=True, skip_crew1=True, tamper="unit_change", publish=True,
        runs_root=tmp_path / "runs", artifacts_dir=artifacts,
        analyst_runner=_never_called, scientist_runner=_never_called,
    )  # fmt: skip

    assert state.status == "handoff_failed"
    assert {p.name: p.read_bytes() for p in (artifacts / "crew1").iterdir()} == before
    tampered = (Path(state.run_dir) / "crew1" / "clean_data.csv").read_bytes()
    assert tampered != before["clean_data.csv"]


def test_skip_crew1_copies_the_published_crew1_files(raw_xlsx, tmp_path, trained_crew2):
    artifacts = tmp_path / "artifacts"
    first = run_flow(
        raw_path=raw_xlsx, stub_crews=True, publish=True, runs_root=tmp_path / "runs",
        artifacts_dir=artifacts, scientist_runner=_fake_scientist(trained_crew2),
    )  # fmt: skip
    second = run_flow(
        stub_crews=True, skip_crew1=True, publish=False, runs_root=tmp_path / "runs",
        artifacts_dir=artifacts, analyst_runner=_never_called,
        scientist_runner=_fake_scientist(trained_crew2),
    )  # fmt: skip
    assert second.status == "verified"
    for name in ("clean_data.csv", "dataset_contract.json", "stats.json"):
        a = (Path(first.run_dir) / "crew1" / name).read_bytes()
        b = (Path(second.run_dir) / "crew1" / name).read_bytes()
        assert a == b, name
    assert ("run_analyst", "skip") in [(e["step"], e["status"]) for e in _events(Path(second.run_dir))]


def test_skip_crew1_without_published_artifacts_is_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="crew1"):
        run_flow(
            stub_crews=True, skip_crew1=True, publish=False, runs_root=tmp_path / "runs",
            artifacts_dir=tmp_path / "empty", scientist_runner=_never_called,
        )  # fmt: skip


def test_bad_crew2_outputs_are_not_published(raw_xlsx, tmp_path, trained_crew2):
    def sabotage(out_dir: Path):
        m = json.loads((out_dir / "metrics.json").read_text())
        m["variants"][m["served"]]["roc_auc"]["mean"] = 0.1  # worse than the majority baseline
        (out_dir / "metrics.json").write_text(json.dumps(m))

    artifacts = tmp_path / "artifacts"
    state = run_flow(
        raw_path=raw_xlsx, stub_crews=True, publish=True, runs_root=tmp_path / "runs",
        artifacts_dir=artifacts, scientist_runner=_fake_scientist(trained_crew2, patch=sabotage),
    )  # fmt: skip
    assert state.status == "outputs_failed"
    assert state.outputs_check["passed"] is False
    assert "baseline" in (Path(state.run_dir) / "FAILED.md").read_text()
    assert not artifacts.exists()


def test_missing_crew2_file_fails_the_outputs_check(raw_xlsx, tmp_path, trained_crew2):
    def drop_model(out_dir: Path):
        (out_dir / "model.joblib").unlink()

    state = run_flow(
        raw_path=raw_xlsx, stub_crews=True, publish=False, runs_root=tmp_path / "runs",
        scientist_runner=_fake_scientist(trained_crew2, patch=drop_model),
    )  # fmt: skip
    assert state.status == "outputs_failed"
    assert "model.joblib" in (Path(state.run_dir) / "FAILED.md").read_text()


def test_a_crashing_crew_is_logged_and_re_raised(raw_xlsx, tmp_path):
    def crash(raw_path, out_dir):
        raise RuntimeError("provider down")

    with pytest.raises(RuntimeError, match="provider down"):
        run_flow(
            raw_path=raw_xlsx, publish=False, runs_root=tmp_path / "runs",
            analyst_runner=crash, scientist_runner=_never_called,
        )  # fmt: skip
    run_dir = next((tmp_path / "runs").iterdir())
    steps = [(e["step"], e["status"]) for e in _events(run_dir)]
    assert ("run_analyst", "fail") in steps and ("flow", "fail") in steps
    assert "provider down" in (run_dir / "FAILED.md").read_text()


def test_paths_are_shown_relative_to_the_repo_when_inside_it():
    from flow.main import display_path
    from hv.config import ROOT

    assert display_path(ROOT / "runs" / "x" / "FAILED.md") == "runs/x/FAILED.md"
    assert display_path(Path("/elsewhere/runs/x")) == "/elsewhere/runs/x"


def test_exit_codes_follow_the_plan():
    assert EXIT_CODES == {"published": 0, "verified": 0, "handoff_failed": 2, "outputs_failed": 3}
