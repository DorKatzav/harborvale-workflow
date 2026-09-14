"""Stub crews call the same hv functions as the real crews, with canned prose and no network."""

import json
import os

import pandas as pd
import pytest

from crews import stubs
from crews.scientist.crew import HandoffRefused
from hv import insights, model_card
from hv.config import READ_CSV_KW
from hv.contract import build_contract, load_contract, save_contract, tamper
from tests.synthetic import training_frame, write_frame


def test_analyst_stub_produces_the_crew1_files_without_a_key(raw_frame, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    raw = tmp_path / "raw.xlsx"
    raw_frame.to_excel(raw, sheet_name="E Comm", index=False)
    out_dir = tmp_path / "crew1"

    res = stubs.run_analyst_stub(raw, out_dir)

    for p in (res.clean_csv, res.eda_html, res.stats_json, res.insights_md, res.contract_json):
        assert p.exists(), p
    from hv.contract import load_contract, validate

    contract = load_contract(res.contract_json)
    assert validate(res.clean_csv, contract).passed
    assert contract.assumptions and all(c.rationale for c in contract.columns)
    assert res.llm_calls == 0 and res.cost_usd == 0.0
    text = res.insights_md.read_text()
    for name in insights.REQUIRED_SECTIONS:
        assert f"## {name}" in text
    assert "OPENAI_API_KEY" not in os.environ


def test_analyst_stub_is_deterministic(raw_frame, tmp_path):
    raw = tmp_path / "raw.xlsx"
    raw_frame.to_excel(raw, sheet_name="E Comm", index=False)
    a = stubs.run_analyst_stub(raw, tmp_path / "a")
    b = stubs.run_analyst_stub(raw, tmp_path / "b")
    assert a.clean_csv.read_bytes() == b.clean_csv.read_bytes()
    assert a.stats_json.read_bytes() == b.stats_json.read_bytes()
    assert a.insights_md.read_text() == b.insights_md.read_text()
    from crews.analyst.tools import measured_fields
    from hv.contract import load_contract

    assert measured_fields(load_contract(a.contract_json)) == measured_fields(load_contract(b.contract_json))


# --- the scientist stub (M5 task 2) -------------------------------------------------


@pytest.fixture(scope="module")
def handoff(tmp_path_factory):
    """What Crew 1 hands over: one clean file and the contract that describes exactly it."""
    tmp = tmp_path_factory.mktemp("handoff")
    df = training_frame(300)
    clean = write_frame(df, tmp / "clean_data.csv")
    contract = build_contract(df, "tests/synthetic.py", clean)
    contract_path = tmp / "dataset_contract.json"
    save_contract(contract, contract_path)
    return contract_path, clean


@pytest.fixture(scope="module")
def scientist_run(handoff, tmp_path_factory):
    """One real stub run, shared by the tests that only read its output."""
    contract_path, clean = handoff
    return stubs.run_scientist_stub(contract_path, clean, tmp_path_factory.mktemp("crew2a"))


def test_scientist_stub_produces_the_crew2_files_without_a_key(scientist_run, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    res = scientist_run

    for p in (res.features_csv, res.metrics_json, res.model_path, res.evaluation_md, res.model_card_md):
        assert p.exists(), p
    assert res.llm_calls == 0 and res.cost_usd == 0.0
    assert "OPENAI_API_KEY" not in os.environ


def test_scientist_stub_writes_a_model_card_with_the_five_required_sections(scientist_run):
    text = scientist_run.model_card_md.read_text(encoding="utf-8")
    for name in model_card.REQUIRED_SECTIONS:
        assert f"## {name}" in text


def test_scientist_stub_serves_a_variant_that_beats_the_baseline(scientist_run):
    metrics = json.loads(scientist_run.metrics_json.read_text(encoding="utf-8"))
    served = metrics["variants"][metrics["served"]]
    assert len(metrics["variants"]) >= 3
    assert served["roc_auc"]["mean"] > metrics["baseline"]["roc_auc"]
    assert served["precision_at_top10"] > metrics["baseline"]["precision_at_top10"]


def test_scientist_stub_refuses_a_clean_file_that_disagrees_with_its_contract(handoff, tmp_path):
    contract_path, clean = handoff
    broken_df, _ = tamper(pd.read_csv(clean, **READ_CSV_KW), load_contract(contract_path), "unit_change")
    broken = write_frame(broken_df, tmp_path / "broken.csv")
    out_dir = tmp_path / "crew2_refused"

    with pytest.raises(HandoffRefused):
        stubs.run_scientist_stub(contract_path, broken, out_dir)

    assert not (out_dir / "model.joblib").exists()


def test_scientist_stub_is_deterministic(handoff, scientist_run, tmp_path):
    contract_path, clean = handoff
    b = stubs.run_scientist_stub(contract_path, clean, tmp_path / "crew2b")
    assert scientist_run.features_csv.read_bytes() == b.features_csv.read_bytes()
    assert scientist_run.metrics_json.read_bytes() == b.metrics_json.read_bytes()
