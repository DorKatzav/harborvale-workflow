"""Stub crews call the same hv functions as the real crews, with canned prose and no network."""

import os

from crews import stubs
from hv import insights


def test_analyst_stub_produces_the_crew1_files_without_a_key(raw_frame, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    raw = tmp_path / "raw.xlsx"
    raw_frame.to_excel(raw, sheet_name="E Comm", index=False)
    out_dir = tmp_path / "crew1"

    res = stubs.run_analyst_stub(raw, out_dir)

    for p in (res.clean_csv, res.eda_html, res.stats_json, res.insights_md):
        assert p.exists(), p
    assert res.contract_json is None  # the Data Steward task arrives with M2 (M3b)
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
