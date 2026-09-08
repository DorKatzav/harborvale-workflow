"""M2 task 4: the break-it CLI runs the same file-based path the Flow will run."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from hv.contract import build_contract, save_contract
from tests.synthetic import clean_frame, write_frame

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "break_it.py"


@pytest.fixture
def artifacts(tmp_path):
    """A stand-in for artifacts/crew1/ so the CLI can be tested without M1."""
    df = clean_frame()
    csv = write_frame(df, tmp_path / "clean_data.csv")
    contract_path = tmp_path / "dataset_contract.json"
    save_contract(build_contract(df, "tests/synthetic.py", csv), contract_path)
    return csv, contract_path


def run_cli(preset: str, csv: Path, contract: Path, out: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--preset", preset, "--clean", str(csv),
         "--contract", str(contract), "--out", str(out)],
        capture_output=True, text=True, cwd=ROOT,
    )


def test_a_data_break_exits_two_and_prints_the_report(artifacts, tmp_path):
    csv, contract = artifacts
    res = run_cli("unit_change", csv, contract, tmp_path / "out")
    assert res.returncode == 2, res.stdout + res.stderr
    assert "Contract validation - FAILED" in res.stdout
    assert "ratio ~= 100 - looks like a unit change" in res.stdout
    assert "caught by: integrity, range" in res.stdout


def test_a_contract_only_break_keeps_the_original_bytes(artifacts, tmp_path):
    csv, contract = artifacts
    out = tmp_path / "out"
    res = run_cli("drop_contract_field", csv, contract, out)
    assert res.returncode == 2, res.stdout + res.stderr
    assert (out / "clean_data.csv").read_bytes() == csv.read_bytes()  # only the contract changed
    assert "caught by: columns" in res.stdout


def test_the_originals_are_never_touched(artifacts, tmp_path):
    csv, contract = artifacts
    before = csv.read_bytes(), contract.read_bytes()
    run_cli("row_loss", csv, contract, tmp_path / "out")
    assert (csv.read_bytes(), contract.read_bytes()) == before


def test_missing_artifacts_are_reported_not_crashed(tmp_path):
    res = run_cli("unit_change", tmp_path / "nope.csv", tmp_path / "nope.json", tmp_path / "out")
    assert res.returncode == 1
    assert "missing clean CSV" in res.stdout and "run Crew 1 first" in res.stdout
