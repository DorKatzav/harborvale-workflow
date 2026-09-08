"""The analyst tools are thin wrappers over hv/: they take paths, return JSON strings, and write files."""

import json

import pytest

from crews.analyst import tools


@pytest.fixture
def raw_xlsx(raw_frame, tmp_path):
    path = tmp_path / "raw.xlsx"
    raw_frame.to_excel(path, sheet_name="E Comm", index=False)
    return path


def test_profile_raw_data_returns_json_facts(raw_xlsx):
    out = json.loads(tools.profile_raw_data.func(str(raw_xlsx)))
    assert out["rows"] == 8 and out["duplicate_records"] == 2
    assert "PreferredLoginDevice" in out["columns"]


def test_clean_dataset_writes_clean_csv_and_report(raw_xlsx, tmp_path):
    out_dir = tmp_path / "crew1"
    out = json.loads(tools.clean_dataset.func(str(raw_xlsx), str(out_dir)))
    assert (out_dir / "clean_data.csv").exists() and (out_dir / "cleaning_report.json").exists()
    assert out["report"]["rows_out"] == 6
    assert out["clean_csv"].endswith("clean_data.csv") and len(out["sha256"]) == 64


def test_run_eda_writes_stats_and_html(raw_xlsx, tmp_path):
    out_dir = tmp_path / "crew1"
    tools.clean_dataset.func(str(raw_xlsx), str(out_dir))
    out = json.loads(tools.run_eda.func(str(out_dir / "clean_data.csv"), str(out_dir)))
    assert (out_dir / "stats.json").exists() and (out_dir / "eda_report.html").exists()
    assert out["stats"]["churn_rate"] == pytest.approx(0.5)
    assert out["stats"]["top_drivers"]  # the agent gets the numbers it must write about


def test_write_insights_renders_from_files_and_refuses_missing_section(raw_xlsx, tmp_path):
    out_dir = tmp_path / "crew1"
    tools.clean_dataset.func(str(raw_xlsx), str(out_dir))
    tools.run_eda.func(str(out_dir / "clean_data.csv"), str(out_dir))
    sections = {
        "Overview": "o", "Cleaning": "c", "Who churns": "w", "Drivers": "d", "Recommendations": "r",
    }  # fmt: skip
    path = tools.write_insights.func(str(out_dir), json.dumps(sections))
    text = (out_dir / "insights.md").read_text()
    assert path.endswith("insights.md") and "| Churn rate | 50.0% |" in text
    bad = json.dumps({k: v for k, v in sections.items() if k != "Cleaning"})
    result = tools.write_insights.func(str(out_dir), bad)
    assert result.startswith("ERROR") and "Cleaning" in result


def test_tools_are_crewai_tools_with_descriptions():
    for t in tools.ANALYST_TOOLS:
        assert t.name and t.description


# ---------------------------------------------------------------- M3b: the Data Steward's tools
def _prepared(raw_xlsx, tmp_path):
    out_dir = tmp_path / "crew1"
    tools.clean_dataset.func(str(raw_xlsx), str(out_dir))
    return out_dir


def test_build_contract_measured_writes_a_contract_that_validates_the_clean_file(raw_xlsx, tmp_path):
    from hv.contract import load_contract, validate

    out_dir = _prepared(raw_xlsx, tmp_path)
    raw = tools.build_contract_measured.func(str(out_dir / "clean_data.csv"), str(out_dir), str(raw_xlsx))
    out = json.loads(raw)
    path = out_dir / "dataset_contract.json"
    assert path.exists() and out["contract_path"] == str(path)
    assert out["row_count"] == 6 and len(out["columns"]) == 20
    names = {c["name"] for c in out["columns"]}
    assert "CashbackAmount" in names and out["columns"][0]["name"] == "CustomerID"
    c = load_contract(path)
    assert c.produced_by == "analyst_crew"
    assert validate(out_dir / "clean_data.csv", c).passed


def test_write_contract_human_fields_touches_only_human_fields(raw_xlsx, tmp_path):
    from hv.contract import load_contract

    out_dir = _prepared(raw_xlsx, tmp_path)
    tools.build_contract_measured.func(str(out_dir / "clean_data.csv"), str(out_dir), str(raw_xlsx))
    path = out_dir / "dataset_contract.json"
    before = tools.measured_fields(load_contract(path))
    result = tools.write_contract_human_fields.func(
        str(path),
        json.dumps({"CashbackAmount": "Average cashback last month, in USD"}),
        json.dumps({"CashbackAmount": "USD, not cents: the range 0-324.99 is what Crew 2 may assume"}),
        json.dumps(["Amounts are in USD", "Missing Tenure means the customer is new"]),
    )
    assert result == str(path)
    after = load_contract(path)
    assert tools.measured_fields(after) == before
    col = after.column("CashbackAmount")
    assert col.description.startswith("Average cashback") and "cents" in col.rationale
    assert after.assumptions == ["Amounts are in USD", "Missing Tenure means the customer is new"]


def test_write_contract_human_fields_rejects_unknown_columns_and_bad_json(raw_xlsx, tmp_path):
    out_dir = _prepared(raw_xlsx, tmp_path)
    tools.build_contract_measured.func(str(out_dir / "clean_data.csv"), str(out_dir), str(raw_xlsx))
    path = str(out_dir / "dataset_contract.json")
    r = tools.write_contract_human_fields.func(path, json.dumps({"NoSuchColumn": "x"}), "{}", "[]")
    assert r.startswith("ERROR") and "NoSuchColumn" in r
    r = tools.write_contract_human_fields.func(path, "not json", "{}", "[]")
    assert r.startswith("ERROR")


def test_measured_fields_ignore_prose_and_timestamps(raw_xlsx, tmp_path):
    from hv.contract import apply_human_fields, load_contract

    out_dir = _prepared(raw_xlsx, tmp_path)
    tools.build_contract_measured.func(str(out_dir / "clean_data.csv"), str(out_dir), str(raw_xlsx))
    c = load_contract(out_dir / "dataset_contract.json")
    edited = apply_human_fields(c, descriptions={"Tenure": "months with us"}, assumptions=["x"])
    edited.created_at = "2000-01-01T00:00:00+00:00"
    edited.produced_by = "someone else"
    assert tools.measured_fields(edited) == tools.measured_fields(c)
