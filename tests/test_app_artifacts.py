"""The app reads what the last successful run published, and copes when a half is missing."""

import json
import shutil

import pytest

from app import artifacts as A
from hv.config import ARTIFACTS_DIR


@pytest.fixture
def published(tmp_path):
    """A copy of the committed artifacts, so tests can delete parts of it."""
    dst = tmp_path / "artifacts"
    shutil.copytree(ARTIFACTS_DIR, dst)
    return dst


def test_crew1_exposes_contract_stats_and_rendered_insights(published):
    c1 = A.load_crew1(published)
    assert c1.available
    assert c1.contract.dataset.row_count == 5073
    assert len(c1.contract.columns) == 20
    assert c1.stats["churn_rate"] == pytest.approx(0.1658, abs=1e-4)
    assert c1.cleaning["rows_in"] == 5630
    assert "<h2" in c1.insights_html and "Key numbers" in c1.insights_html
    assert c1.clean_csv.name == "clean_data.csv"


def test_crew1_missing_reports_unavailable_instead_of_raising(tmp_path):
    c1 = A.load_crew1(tmp_path / "nothing")
    assert not c1.available and c1.contract is None


def test_crew2_missing_reports_unavailable(published):
    shutil.rmtree(published / "crew2", ignore_errors=True)
    c2 = A.load_crew2(published)
    assert not c2.available
    assert c2.metrics is None and c2.model_card_html == ""


def test_crew2_when_published_exposes_metrics_and_documents(published):
    crew2 = published / "crew2"
    crew2.mkdir(exist_ok=True)
    (crew2 / "metrics.json").write_text(
        json.dumps(
            {
                "served": "hist_gb",
                "n_rows": 5073,
                "positive_rate": 0.1658,
                "baseline": {"roc_auc": 0.5, "precision_at_top10": 0.1658},
                "variants": {
                    "logreg": {"roc_auc": {"mean": 0.8913, "std": 0.0169}, "precision_at_top10": 0.7712},
                    "hist_gb": {"roc_auc": {"mean": 0.9857, "std": 0.0051}, "precision_at_top10": 0.9724},
                },
                "importances": {"Tenure": 0.0889, "Complain": 0.0209, "CouponUsed": 0.0},
                "fairness": {"Gender": {"Female": {"n": 2026, "recall": 0.89}}},
            }
        )
    )
    (crew2 / "model_card.md").write_text("# Model card\n\n## Purpose\n\nRank customers by churn risk.\n")
    (crew2 / "evaluation_report.md").write_text("# Evaluation\n\nhist_gb wins.\n")
    c2 = A.load_crew2(published)
    assert c2.available and c2.metrics["served"] == "hist_gb"
    assert "<h1" in c2.model_card_html and "Rank customers" in c2.model_card_html
    assert "hist_gb wins" in c2.evaluation_html
    ranked = A.ranked_importances(c2.metrics, limit=2)
    assert [name for name, _ in ranked] == ["Tenure", "Complain"]  # ranked, not alphabetical


def test_run_summary_reads_run_meta(published):
    run = A.load_run(published)
    assert run["cost_usd"] == 0.037
    assert run["llm_calls"] == 10
    assert run["duration_s"] == 176.8


def test_contract_rows_are_display_ready(published):
    c1 = A.load_crew1(published)
    rows = A.contract_rows(c1.contract)
    assert len(rows) == 20
    cashback = next(r for r in rows if r["name"] == "CashbackAmount")
    assert cashback["role"] == "feature" and cashback["unit"] == "USD"
    assert cashback["constraint"].startswith("0")  # a range, rendered for a human
    assert cashback["nulls"] == "none"
    tenure = next(r for r in rows if r["name"] == "Tenure")
    assert tenure["nulls"] == "231"
    device = next(r for r in rows if r["name"] == "PreferredLoginDevice")
    assert "Computer" in device["constraint"]
