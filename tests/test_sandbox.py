"""The seam, enforced in code: Crew 2 may read the contract and the clean file, and nothing else.

Gate M5 runs this file by path. Every test here is a way somebody could reach around the contract -
the raw workbook, a parent-directory escape, an absolute path somewhere else on the machine - and the
tools have to refuse all of them by raising SandboxError before any file is opened.
"""

from __future__ import annotations

import json

import pytest

from crews.scientist import tools
from crews.scientist.tools import SandboxError
from hv.config import ROOT
from hv.contract import build_contract, save_contract
from tests.synthetic import clean_frame, write_frame


@pytest.fixture
def crew1(tmp_path):
    """A Crew-1 handoff directory, and the sandbox pointed at it."""
    crew1_dir = tmp_path / "run" / "crew1"
    df = clean_frame()
    clean = write_frame(df, crew1_dir / "clean_data.csv")
    save_contract(
        build_contract(df, "tests/synthetic.py", clean), crew1_dir / "dataset_contract.json"
    )
    tools.set_crew1_dir(crew1_dir)
    return crew1_dir


# ---------------------------------------------------------------- writes (M8 audit, finding A1)
@pytest.fixture
def run_dir(crew1):
    """The run directory the tools may write into (its crew2/), and the sandbox told about it."""
    root = crew1.parent
    tools.set_run_dir(root)
    return root


@pytest.mark.parametrize(
    "out_dir",
    [
        pytest.param("/somewhere/else", id="absolute"),
        pytest.param("crew2/../../outside", id="dotdot"),
        pytest.param(str(ROOT / "artifacts" / "crew2"), id="the_published_artifacts"),
    ],
)
def test_a_tool_refuses_to_write_outside_the_run_directory(crew1, run_dir, out_dir):
    target = out_dir if out_dir.startswith("/") else str(run_dir / out_dir)
    clean, contract = str(crew1 / "clean_data.csv"), str(crew1 / "dataset_contract.json")
    with pytest.raises(SandboxError):
        tools.engineer_features.func(clean, contract, target)
    with pytest.raises(SandboxError):
        tools.write_evaluation_report.func(target, "{}")
    with pytest.raises(SandboxError):
        tools.write_model_card.func(target, "{}")
    with pytest.raises(SandboxError):
        tools.train_and_evaluate.func(str(run_dir / "crew2" / "features.csv"), contract, target)


def test_a_tool_refuses_to_write_into_the_crew1_handoff(crew1, run_dir):
    clean, contract = str(crew1 / "clean_data.csv"), str(crew1 / "dataset_contract.json")
    with pytest.raises(SandboxError):
        tools.engineer_features.func(clean, contract, str(crew1))


def test_a_tool_writes_inside_the_run_directory(crew1, run_dir):
    out = json.loads(
        tools.engineer_features.func(
            str(crew1 / "clean_data.csv"), str(crew1 / "dataset_contract.json"), str(run_dir / "crew2")
        )
    )
    assert (run_dir / "crew2" / "features.csv").exists() and out["rows"] == 20


def test_writes_are_refused_before_the_run_directory_is_set(crew1, monkeypatch):
    monkeypatch.setattr(tools, "_RUN_DIR", None)
    with pytest.raises(SandboxError):
        tools.engineer_features.func(
            str(crew1 / "clean_data.csv"), str(crew1 / "dataset_contract.json"), str(crew1.parent / "crew2")
        )


def test_the_analyst_tools_refuse_to_write_outside_their_run_directory(tmp_path, raw_frame):
    from crews.analyst import tools as analyst_tools

    raw = tmp_path / "raw.xlsx"
    raw_frame.to_excel(raw, sheet_name="E Comm", index=False)
    analyst_tools.set_run_dir(tmp_path / "run")
    with pytest.raises(SandboxError):
        analyst_tools.clean_dataset.func(str(raw), str(tmp_path / "elsewhere"))
    with pytest.raises(SandboxError):
        analyst_tools.clean_dataset.func(str(raw), "artifacts/crew1")
    out = json.loads(analyst_tools.clean_dataset.func(str(raw), str(tmp_path / "run" / "crew1")))
    assert out["report"]["rows_out"] == 6


def test_the_raw_workbook_is_out_of_reach(crew1):
    with pytest.raises(SandboxError):
        tools.read_crew1_artifact.func("data/raw/ecommerce_churn.xlsx")


def test_a_parent_directory_escape_is_refused(crew1):
    with pytest.raises(SandboxError):
        tools.read_crew1_artifact.func(str(crew1 / ".." / "crew2" / "metrics.json"))


def test_an_absolute_path_somewhere_else_is_refused(crew1, tmp_path):
    elsewhere = tmp_path / "elsewhere.txt"
    elsewhere.write_text("not yours", encoding="utf-8")
    with pytest.raises(SandboxError):
        tools.read_crew1_artifact.func(str(elsewhere))


def test_a_missing_file_outside_the_sandbox_is_refused_before_it_is_opened(crew1, tmp_path):
    """The guard runs on the path, not on the file - an escape is refused whether it exists or not."""
    with pytest.raises(SandboxError):
        tools.read_crew1_artifact.func(str(tmp_path / "does_not_exist.csv"))


def test_a_file_inside_crew1_is_read(crew1):
    text = tools.read_crew1_artifact.func(str(crew1 / "dataset_contract.json"))
    assert '"columns"' in text


def test_the_sandbox_refuses_to_work_before_it_is_pointed_at_a_directory(monkeypatch):
    monkeypatch.setattr(tools, "_CREW1_DIR", None)
    with pytest.raises(SandboxError):
        tools.read_crew1_artifact.func("dataset_contract.json")


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda crew1, escape, out: tools.read_crew1_artifact.func(escape), id="read"),
        pytest.param(
            lambda crew1, escape, out: tools.validate_against_contract.func(
                escape, str(crew1 / "dataset_contract.json")
            ),
            id="validate_clean_csv",
        ),
        pytest.param(
            lambda crew1, escape, out: tools.validate_against_contract.func(
                str(crew1 / "clean_data.csv"), escape
            ),
            id="validate_contract",
        ),
        pytest.param(
            lambda crew1, escape, out: tools.engineer_features.func(
                escape, str(crew1 / "dataset_contract.json"), str(out)
            ),
            id="engineer_features",
        ),
        pytest.param(
            lambda crew1, escape, out: tools.train_and_evaluate.func(
                escape, str(crew1 / "dataset_contract.json"), str(out)
            ),
            id="train_and_evaluate",
        ),
    ],
)
def test_every_tool_that_reads_goes_through_the_guard(crew1, tmp_path, call):
    escape = str(tmp_path / "smuggled.csv")
    write_frame(clean_frame(), tmp_path / "smuggled.csv")  # a real, readable file - still refused
    with pytest.raises(SandboxError):
        call(crew1, escape, tmp_path / "crew2")
