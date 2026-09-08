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
