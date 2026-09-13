"""M5 task 5: `scripts/run_flow.py` — flags in, exit codes out (0 ok · 2 handoff · 3 outputs · 1 error)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from flow.state import FlowState

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "run_flow.py"


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("run_flow_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake(status: str, run_dir: Path):
    def run(**kwargs):
        run_dir.mkdir(parents=True, exist_ok=True)
        if status not in ("published", "verified"):
            (run_dir / "FAILED.md").write_text(f"# failed: {status}\n")
        return FlowState(run_id=run_dir.name, run_dir=str(run_dir), status=status, **{
            k: v for k, v in kwargs.items() if k in ("tamper", "stub_crews", "skip_crew1", "publish")
        })  # fmt: skip

    return run


@pytest.mark.parametrize(
    "status, code", [("published", 0), ("verified", 0), ("handoff_failed", 2), ("outputs_failed", 3)]
)
def test_exit_code_follows_the_final_status(script, tmp_path, status, code, capsys):
    rc = script.main(["--stub-crews", "--publish", "false"], run=_fake(status, tmp_path / "r"))
    assert rc == code
    out = capsys.readouterr().out
    assert status in out
    if code:
        assert "FAILED.md" in out


def test_flags_reach_run_flow(script, tmp_path):
    seen = {}

    def run(**kwargs):
        seen.update(kwargs)
        return _fake("verified", tmp_path / "r")(**kwargs)

    script.main(
        ["--stub-crews", "--skip-crew1", "--tamper", "row_loss", "--publish", "false",
         "--run-id", "abc", "--runs-root", str(tmp_path)],
        run=run,
    )  # fmt: skip
    assert seen["stub_crews"] is True and seen["skip_crew1"] is True
    assert seen["tamper"] == "row_loss" and seen["publish"] is False
    assert seen["run_id"] == "abc" and Path(seen["runs_root"]) == tmp_path


def test_an_unexpected_error_is_exit_1(script, tmp_path, capsys):
    def run(**kwargs):
        raise RuntimeError("provider down")

    assert script.main(["--stub-crews"], run=run) == 1
    assert "provider down" in capsys.readouterr().out


def test_tampered_run_exits_2_end_to_end(raw_frame, tmp_path):
    raw = tmp_path / "raw.xlsx"
    raw_frame.to_excel(raw, sheet_name="E Comm", index=False)
    res = subprocess.run(
        [sys.executable, str(SCRIPT), "--raw", str(raw), "--stub-crews", "--tamper", "unit_change",
         "--publish", "false", "--runs-root", str(tmp_path / "runs")],
        cwd=ROOT, capture_output=True, text=True, timeout=300,
    )  # fmt: skip
    assert res.returncode == 2, res.stdout[-800:] + res.stderr[-800:]
    failed = next((tmp_path / "runs").glob("*/FAILED.md"))
    assert "CashbackAmount" in failed.read_text() and "looks like a unit change" in res.stdout
